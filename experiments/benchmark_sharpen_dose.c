/* Ticket 67: sharpen dose-response benchmark (offline, driver-faithful).
 *
 * Pipeline mirrors libfprint-driver/goodix5e0a.c process_raw_frame exactly:
 *   1. 3x3 clamped-window local-mean subtraction -> residual field
 *      (driver lines ~1478-1496; same MAX(0,..)/MIN(H-1,..) edge handling).
 *   2. Empty-air gates BEFORE normalization: active<64 || range<8 and
 *      residual_range<1.0f return NULL with 0 minutiae (driver invariant).
 *   3. Dose application on the residual field:
 *        sharpened = r + A * (r - blur3(r))   (blur3 = same 3x3 mean)
 *      linear model: CLAMP(128 + sharpened * 1.0f)   (ticket-65 baseline
 *        is exactly A=0.00 linear)
 *      tanh model:   128 + 127*tanhf(sharpened/127)  (ticket-66 soft knee;
 *        A=0.00 tanh isolates the soft-knee effect from the sharpen effect)
 *   4. 2x bilinear upscale with the driver's exact sampling grid
 *      (src = (d+0.5)*0.5-0.5, driver lines ~1518-1542).
 *   5. mindtct get_minutiae with g_lfsparms_V2, remove_perimeter_pts=0,
 *      ppmm=500/25.4 (same parameters as goodix5e0a_count_minutiae), image
 *      inverted before extraction (driver sets FPI_IMAGE_COLORS_INVERTED).
 *   6. Metrics per dose x model: total minutiae M, high-reliability
 *      M>=0.2, Bozorth3 self-match B_self, perturbed-probe B_pert (1px
 *      shift + checker +-1 noise, the ticket-66 harness protocol), clip
 *      fraction (% of 64x80 pixels pinned at 0/255), mean gradient
 *      steepness (mean |dx|+|dy| on the normalized pre-upscale image).
 *
 * Doses A in {0.00, 0.10, 0.20, 0.25, 0.50, 1.00} per the ticket.
 * Go/no-go gate (ticket s3): proceed to hardware ONLY if some dose raises
 * M>=0.2 by >=15% AND raises B_pert over the A=0.00 linear baseline without
 * spurious minutiae; otherwise the contrast line closes on linear.
 *
 * Build: gcc -O2 -I/tmp/libfprint-goodix/libfprint/nbis/include \
 *   experiments/benchmark_sharpen_dose.c \
 *   /tmp/libfprint-goodix/build/libfprint/libnbis.a -lm \
 *   -o /tmp/opencode/benchmark_sharpen_dose
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>
#include <bozorth.h>

#define W 64
#define H 80
#define NPIX (W * H)
#define DST_W 128
#define DST_H 160
#define PPMM (500.0 / 25.4)
#define MID 128.0f
#define GAIN 1.0f
#define KNEE 127.0f

extern LFSPARMS g_lfsparms_V2;

static float doses[] = {0.00f, 0.10f, 0.20f, 0.25f, 0.50f, 1.00f};

static int read_pgm12(const char *path, unsigned short *pix) {
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return -1; }
    char magic[8];
    int w, h, maxv;
    if (fscanf(f, "%7s", magic) != 1 || strcmp(magic, "P2") != 0) {
        fprintf(stderr, "%s: not P2\n", path); fclose(f); return -1;
    }
    /* Skip comments. */
    int c;
    do {
        c = fgetc(f);
        if (c == '#') { while ((c = fgetc(f)) != '\n' && c != EOF); }
        else { ungetc(c, f); break; }
    } while (1);
    if (fscanf(f, "%d %d %d", &w, &h, &maxv) != 3 || w != W || h != H) {
        fprintf(stderr, "%s: want 64x80, got %dx%d\n", path, w, h);
        fclose(f); return -1;
    }
    for (int i = 0; i < NPIX; i++) {
        int v;
        if (fscanf(f, "%d", &v) != 1) {
            fprintf(stderr, "%s: short (%d px)\n", path, i);
            fclose(f); return -1;
        }
        pix[i] = (unsigned short)v;
    }
    fclose(f);
    return 0;
}

/* Driver-faithful 3x3 clamped local mean residual. */
static void compute_residual(const unsigned short *pix, float *res,
                             float *rmin, float *rmax) {
    float mn = 1e30f, mx = -1e30f;
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            unsigned int s = 0, n = 0;
            int y0 = y > 0 ? y - 1 : 0, y1 = y + 1 < H ? y + 1 : H - 1;
            int x0 = x > 0 ? x - 1 : 0, x1 = x + 1 < W ? x + 1 : W - 1;
            for (int yy = y0; yy <= y1; yy++)
                for (int xx = x0; xx <= x1; xx++) {
                    s += pix[yy * W + xx];
                    n++;
                }
            float v = (float)pix[y * W + x] - (float)s / (float)n;
            res[y * W + x] = v;
            if (v < mn) mn = v;
            if (v > mx) mx = v;
        }
    }
    *rmin = mn; *rmax = mx;
}

/* 3x3 clamped blur of the residual field (ticket-66 unsharp mask term). */
static void blur3(const float *in, float *out) {
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            double s = 0.0;
            int n = 0;
            int y0 = y > 0 ? y - 1 : 0, y1 = y + 1 < H ? y + 1 : H - 1;
            int x0 = x > 0 ? x - 1 : 0, x1 = x + 1 < W ? x + 1 : W - 1;
            for (int yy = y0; yy <= y1; yy++)
                for (int xx = x0; xx <= x1; xx++) {
                    s += in[yy * W + xx];
                    n++;
                }
            out[y * W + x] = (float)(s / n);
        }
    }
}

static void upscale_2x_bilinear(const unsigned char *src, unsigned char *dst) {
    for (int y = 0; y < DST_H; y++) {
        float src_y = (y + 0.5f) * 0.5f - 0.5f;
        if (src_y < 0.0f) src_y = 0.0f;
        int y0 = (int)src_y;
        int y1 = (y0 + 1 < H) ? y0 + 1 : y0;
        float y_frac = src_y - (float)y0;
        for (int x = 0; x < DST_W; x++) {
            float src_x = (x + 0.5f) * 0.5f - 0.5f;
            if (src_x < 0.0f) src_x = 0.0f;
            int x0 = (int)src_x;
            int x1 = (x0 + 1 < W) ? x0 + 1 : x0;
            float x_frac = src_x - (float)x0;
            float top = (float)src[y0 * W + x0] * (1.0f - x_frac)
                      + (float)src[y0 * W + x1] * x_frac;
            float bot = (float)src[y1 * W + x0] * (1.0f - x_frac)
                      + (float)src[y1 * W + x1] * x_frac;
            float val = top * (1.0f - y_frac) + bot * y_frac;
            int norm = (int)roundf(val);
            if (norm < 0) norm = 0;
            if (norm > 255) norm = 255;
            dst[y * DST_W + x] = (unsigned char)norm;
        }
    }
}

static void minutiae_to_xyt(MINUTIAE *minutiae, int bw, int bh,
                            struct xyt_struct *xyt) {
    int nmin = minutiae ? minutiae->num : 0;
    if (nmin > MAX_BOZORTH_MINUTIAE) nmin = MAX_BOZORTH_MINUTIAE;
    struct minutiae_struct c[MAX_BOZORTH_MINUTIAE];
    for (int i = 0; i < nmin; i++) {
        MINUTIA *m = minutiae->list[i];
        lfs2nist_minutia_XYT(&c[i].col[0], &c[i].col[1], &c[i].col[2],
                             m, bw, bh);
        c[i].col[3] = (int)round(m->reliability * 100.0);
        if (c[i].col[2] > 180) c[i].col[2] -= 360;
    }
    if (nmin > 0) qsort(c, nmin, sizeof(struct minutiae_struct), sort_x_y);
    for (int i = 0; i < nmin; i++) {
        xyt->xcol[i] = c[i].col[0];
        xyt->ycol[i] = c[i].col[1];
        xyt->thetacol[i] = c[i].col[2];
    }
    xyt->nrows = nmin;
}

typedef struct {
    int total;
    int hirel;
    struct xyt_struct xyt;
    MINUTIAE *m;
} ExtractOut;

static void extract(const unsigned char *scaled, ExtractOut *o) {
    unsigned char *img = malloc(DST_W * DST_H);
    for (int i = 0; i < DST_W * DST_H; i++)
        img[i] = (unsigned char)(255 - scaled[i]); /* INVERTED flag */
    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    MINUTIAE *minutiae = NULL;
    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;
    get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                 &mw, &mh, &bdata, &bw, &bh, &bd,
                 img, DST_W, DST_H, 8, PPMM, &parms);
    o->total = minutiae ? minutiae->num : 0;
    o->hirel = 0;
    if (minutiae)
        for (int i = 0; i < minutiae->num; i++)
            if (minutiae->list[i]->reliability >= 0.20)
                o->hirel++;
    memset(&o->xyt, 0, sizeof(o->xyt));
    minutiae_to_xyt(minutiae, DST_W, DST_H, &o->xyt);
    o->m = minutiae;
    free(img);
    if (qmap) free(qmap);
    if (dmap) free(dmap);
    if (lcmap) free(lcmap);
    if (lfmap) free(lfmap);
    if (hcmap) free(hcmap);
    if (bdata) free(bdata);
}

static void free_extract(ExtractOut *o) {
    if (o->m) free_minutiae(o->m);
    o->m = NULL;
}

static int bozorth_match(struct xyt_struct *p, struct xyt_struct *g) {
    if (p->nrows < 2 || g->nrows < 2) return 0;
    int probe_len = bozorth_probe_init(p);
    return bozorth_to_gallery(probe_len, p, g);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <64x80 P2 pgm>...\n", argv[0]);
        return 1;
    }
    for (int f = 1; f < argc; f++) {
        unsigned short pix[NPIX];
        if (read_pgm12(argv[f], pix) != 0) return 1;

        unsigned active = 0;
        unsigned short min_v = 65535, max_v = 0;
        for (int i = 0; i < NPIX; i++)
            if (pix[i] > 30) {
                active++;
                if (pix[i] < min_v) min_v = pix[i];
                if (pix[i] > max_v) max_v = pix[i];
            }
        if (min_v == 65535) min_v = 0;
        unsigned range = (max_v > min_v) ? (unsigned)(max_v - min_v) : 1;

        printf("=== %s: active=%u min=%u max=%u range=%u\n",
               argv[f], active, min_v, max_v, range);
        if (active < 64 || range < 8) {
            printf("  AIR GATE: NULL, 0 minutiae (driver-faithful)\n");
            continue;
        }

        static float res[NPIX], blur[NPIX];
        float rmin, rmax;
        compute_residual(pix, res, &rmin, &rmax);
        printf("  residual: min=%.1f max=%.1f range=%.1f\n",
               rmin, rmax, rmax - rmin);
        if (rmax - rmin < 1.0f) {
            printf("  RESIDUAL GATE: NULL, 0 minutiae (driver-faithful)\n");
            continue;
        }
        blur3(res, blur);

        printf("  %-14s %4s %6s %6s %7s %7s %7s %9s\n",
               "config", "M", "M>=.2", "Bself", "Bpert", "clip%", "grad", "note");
        for (int mi = 0; mi < 2; mi++) {
            const char *mname = mi == 0 ? "linear" : "tanh";
            for (unsigned di = 0;
                 di < sizeof(doses) / sizeof(doses[0]); di++) {
                float A = doses[di];
                static unsigned char norm[NPIX], scaled[DST_W * DST_H];
                unsigned clipped = 0;
                double grad = 0.0;
                for (int i = 0; i < NPIX; i++) {
                    float sharp = res[i] + A * (res[i] - blur[i]);
                    int v;
                    if (mi == 0)
                        v = (int)roundf(MID + sharp * GAIN);
                    else
                        v = (int)roundf(MID + KNEE * tanhf(sharp / KNEE));
                    if (v < 0) v = 0;
                    if (v > 255) v = 255;
                    norm[i] = (unsigned char)v;
                    if (v == 0 || v == 255) clipped++;
                }
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++) {
                        int i = y * W + x;
                        if (x + 1 < W) grad += abs((int)norm[i + 1] - (int)norm[i]);
                        if (y + 1 < H) grad += abs((int)norm[i + W] - (int)norm[i]);
                    }
                grad /= (double)(2 * NPIX - W - H);
                upscale_2x_bilinear(norm, scaled);

                ExtractOut o;
                extract(scaled, &o);
                int bself = bozorth_match(&o.xyt, &o.xyt);

                /* Perturbed probe: 1px shift + checker +-1 (ticket-66). */
                static unsigned char pert[DST_W * DST_H];
                for (int y = 0; y < DST_H; y++) {
                    int sy = y > 1 ? y - 1 : 0;
                    for (int x = 0; x < DST_W; x++) {
                        int sx = x > 1 ? x - 1 : 0;
                        int v = (int)scaled[sy * DST_W + sx]
                              + ((x % 2 == 0) ? 1 : -1);
                        pert[y * DST_W + x] =
                            (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
                    }
                }
                ExtractOut p;
                extract(pert, &p);
                int bpert = bozorth_match(&p.xyt, &o.xyt);

                const char *note = "";
                if (mi == 0 && A == 0.0f) note = "<- t65 baseline";
                if (mi == 1 && A == 1.0f) note = "<- t66 shipped";
                char label[16];
                snprintf(label, sizeof(label), "%s A=%.2f", mname, A);
                printf("  %-14s %4d %6d %6d %7d %6.2f%% %7.2f %s\n",
                       label,
                       o.total, o.hirel, bself, bpert,
                       100.0 * clipped / NPIX, grad, note);
                free_extract(&o);
                free_extract(&p);
            }
        }
    }
    return 0;
}
