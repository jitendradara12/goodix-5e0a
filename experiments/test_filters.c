#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>
#include <bozorth.h>

#define W 64
#define H 80
#define TOTAL_PIXELS (W * H)
#define BLOCK_BYTES 132
#define ACTIVE_BYTES 96
#define FRAME_BLOCKS 80

extern LFSPARMS g_lfsparms_V2;

static guint32 decode_frame(unsigned short *out, const unsigned char *data, size_t len) {
    unsigned char packed[FRAME_BLOCKS * ACTIVE_BYTES];
    size_t packed_len = 0;

    for (size_t block = 0; block < FRAME_BLOCKS; block++) {
        size_t src = block * BLOCK_BYTES;
        if (src + ACTIVE_BYTES > len) break;
        memcpy(packed + packed_len, data + src, ACTIVE_BYTES);
        packed_len += ACTIVE_BYTES;
    }

    size_t pixel_idx = 0;
    for (size_t i = 0; i + 6 <= packed_len && pixel_idx + 4 <= TOTAL_PIXELS; i += 6) {
        const unsigned char *c = packed + i;
        out[pixel_idx++] = ((c[0] & 0x0f) << 8) | c[1];
        out[pixel_idx++] = (c[3] << 4) | (c[0] >> 4);
        out[pixel_idx++] = ((c[5] & 0x0f) << 8) | c[2];
        out[pixel_idx++] = (c[4] << 4) | (c[5] >> 4);
    }
    return pixel_idx;
}

static void upscale_2x_bilinear(const unsigned char *src, int w, int h, unsigned char *dst) {
    int dst_w = w * 2;
    int dst_h = h * 2;
    for (int y = 0; y < dst_h; y++) {
        float src_y = (y + 0.5f) * 0.5f - 0.5f;
        if (src_y < 0.0f) src_y = 0.0f;
        int y0 = (int)src_y;
        int y1 = (y0 + 1 < h) ? y0 + 1 : y0;
        float y_frac = src_y - (float)y0;

        for (int x = 0; x < dst_w; x++) {
            float src_x = (x + 0.5f) * 0.5f - 0.5f;
            if (src_x < 0.0f) src_x = 0.0f;
            int x0 = (int)src_x;
            int x1 = (x0 + 1 < w) ? x0 + 1 : x0;
            float x_frac = src_x - (float)x0;

            float top = (float)src[y0 * w + x0] * (1.0f - x_frac) + (float)src[y0 * w + x1] * x_frac;
            float bot = (float)src[y1 * w + x0] * (1.0f - x_frac) + (float)src[y1 * w + x1] * x_frac;
            float val = top * (1.0f - y_frac) + bot * y_frac;
            int norm = (int)roundf(val);
            if (norm < 0) norm = 0;
            if (norm > 255) norm = 255;
            dst[y * dst_w + x] = (unsigned char)norm;
        }
    }
}

static void minutiae_to_xyt(MINUTIAE *minutiae, int bwidth, int bheight, struct xyt_struct *xyt) {
    int nmin = minutiae ? minutiae->num : 0;
    if (nmin > MAX_BOZORTH_MINUTIAE) nmin = MAX_BOZORTH_MINUTIAE;
    struct minutiae_struct c[MAX_BOZORTH_MINUTIAE];
    for (int i = 0; i < nmin; i++) {
        MINUTIA *m = minutiae->list[i];
        lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2], m, bwidth, bheight);
        c[i].col[3] = (int)round (m->reliability * 100.0);
        if (c[i].col[2] > 180) c[i].col[2] -= 360;
    }
    if (nmin > 0) qsort (c, nmin, sizeof(struct minutiae_struct), sort_x_y);
    for (int i = 0; i < nmin; i++) {
        xyt->xcol[i] = c[i].col[0];
        xyt->ycol[i] = c[i].col[1];
        xyt->thetacol[i] = c[i].col[2];
    }
    xyt->nrows = nmin;
}

static int eval_image(const unsigned char *norm, double ppmm, int *out_bz) {
    int dst_w = W * 2;
    int dst_h = H * 2;
    unsigned char scaled[dst_w * dst_h];
    upscale_2x_bilinear(norm, W, H, scaled);

    unsigned char img[dst_w * dst_h];
    for (int i = 0; i < dst_w * dst_h; i++)
        img[i] = 255 - scaled[i]; // Invert

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;

    MINUTIAE *minutiae = NULL;
    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;
    get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                 &mw, &mh, &bdata, &bw, &bh, &bd,
                 img, dst_w, dst_h, 8, ppmm, &parms);
    int num = (minutiae ? minutiae->num : 0);

    struct xyt_struct xyt1 = {0};
    minutiae_to_xyt(minutiae, dst_w, dst_h, &xyt1);

    // Perturbed image
    unsigned char pert[dst_w * dst_h];
    for (int py = 0; py < dst_h; py++) {
        int sy = py > 1 ? py - 1 : 0;
        for (int px = 0; px < dst_w; px++) {
            int sx = px > 1 ? px - 1 : 0;
            int v = (int)img[sy * dst_w + sx] + ((px % 2 == 0) ? 1 : -1);
            pert[py * dst_w + px] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
    }
    MINUTIAE *m_pert = NULL;
    int *q2, *d2, *lc2, *lf2, *hc2, mw2, mh2, bw2, bh2, bd2;
    unsigned char *bdata2 = NULL;
    get_minutiae(&m_pert, &q2, &d2, &lc2, &lf2, &hc2,
                 &mw2, &mh2, &bdata2, &bw2, &bh2, &bd2,
                 pert, dst_w, dst_h, 8, ppmm, &parms);
    struct xyt_struct xyt2 = {0};
    minutiae_to_xyt(m_pert, dst_w, dst_h, &xyt2);

    int bz = 0;
    if (xyt1.nrows >= 10 && xyt2.nrows >= 10) {
        int probe_len = bozorth_probe_init(&xyt1);
        bz = bozorth_to_gallery(probe_len, &xyt1, &xyt2);
    }
    *out_bz = bz;

    if (minutiae) free_minutiae(minutiae);
    if (m_pert) free_minutiae(m_pert);
    if (qmap) free(qmap); if (dmap) free(dmap); if (lcmap) free(lcmap);
    if (lfmap) free(lfmap); if (hcmap) free(hcmap); if (bdata) free(bdata);
    if (q2) free(q2); if (d2) free(d2); if (lc2) free(lc2);
    if (lf2) free(lf2); if (hc2) free(hc2); if (bdata2) free(bdata2);
    return num;
}

static int compare_float(const void *a, const void *b) {
    float fa = *(const float *)a;
    float fb = *(const float *)b;
    return (fa > fb) - (fa < fb);
}

int main(int argc, char **argv) {
    const char *raw_path = (argc > 1) ? argv[1] : "/dev/shm/live_frame.raw";
    FILE *f = fopen(raw_path, "rb");
    if (!f) return 1;
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *raw_data = malloc(len);
    fread(raw_data, 1, len, f);
    fclose(f);

    unsigned short pix[TOTAL_PIXELS];
    decode_frame(pix, raw_data, len);
    free(raw_data);

    double ppmm = 500.0 / 25.4;

    // Test 1: Local Mean Subtraction with different window sizes (radius 1 to 4)
    // combined with various percentile clippings and contrast gains
    printf("=== Window Size & Percentile Stretch Matrix ===\n");
    for (int rad = 1; rad <= 3; rad++) {
        float res[TOTAL_PIXELS];
        float sorted[TOTAL_PIXELS];
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                int sum = 0, count = 0;
                for (int yy = (y >= rad ? y - rad : 0); yy <= (y + rad < H ? y + rad : H - 1); yy++) {
                    for (int xx = (x >= rad ? x - rad : 0); xx <= (x + rad < W ? x + rad : W - 1); xx++) {
                        sum += pix[yy * W + xx];
                        count++;
                    }
                }
                float val = pix[y * W + x] - (float)sum / count;
                res[y * W + x] = val;
                sorted[y * W + x] = val;
            }
        }
        qsort(sorted, TOTAL_PIXELS, sizeof(float), compare_float);

        // Test percentile ranges: 0-100 (min-max), 1-99, 2-98, 3-97, 5-95
        float pcts[] = {0.0f, 0.01f, 0.02f, 0.03f, 0.05f};
        for (size_t p = 0; p < sizeof(pcts)/sizeof(pcts[0]); p++) {
            float p_lo = pcts[p];
            float lo_v = sorted[(int)(p_lo * (TOTAL_PIXELS - 1))];
            float hi_v = sorted[(int)((1.0f - p_lo) * (TOTAL_PIXELS - 1))];
            float span = hi_v - lo_v;
            if (span < 1.0f) span = 1.0f;

            unsigned char norm[TOTAL_PIXELS];
            for (int i = 0; i < TOTAL_PIXELS; i++) {
                int v = (int)roundf(((res[i] - lo_v) * 255.0f) / span);
                norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
            int bz;
            int m = eval_image(norm, ppmm, &bz);
            printf("Radius %d (%dx%d), pct [%.0f%%, %.0f%%]: minutiae=%2d bz=%2d/12\n",
                   rad, 2*rad+1, 2*rad+1, p_lo*100, (1.0f-p_lo)*100, m, bz);
        }
    }

    // Test 2: Contrast Gain Multiplier on 3x3 residual:
    // val = 128 + residual * gain
    printf("\n=== Contrast Gain Multiplier on 3x3 Residual (128 + res * G) ===\n");
    float res3[TOTAL_PIXELS];
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int sum = 0, count = 0;
            for (int yy = (y > 0 ? y - 1 : 0); yy <= (y + 1 < H ? y + 1 : H - 1); yy++) {
                for (int xx = (x > 0 ? x - 1 : 0); xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
                    sum += pix[yy * W + xx];
                    count++;
                }
            }
            res3[y * W + x] = pix[y * W + x] - (float)sum / count;
        }
    }

    for (float G = 0.5f; G <= 3.5f; G += 0.25f) {
        unsigned char norm[TOTAL_PIXELS];
        for (int i = 0; i < TOTAL_PIXELS; i++) {
            int v = (int)roundf(128.0f + res3[i] * G);
            norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
        int bz;
        int m = eval_image(norm, ppmm, &bz);
        printf("Gain G=%.2f: minutiae=%2d bz=%2d/12\n", G, m, bz);
    }

    // Test 3: Unsharp mask on the residual:
    // enhance the difference between pixel and 3x3 mean
    printf("\n=== Unsharp Masking / Ridge Sharpening ===\n");
    // Let sharp = pix + amount * (pix - 3x3 mean)
    for (float amount = 0.5f; amount <= 3.0f; amount += 0.5f) {
        // Then apply 3x3 local mean on sharp or normalize sharp
        // Actually: sharp residual = res3 + amount * (res3 - blur(res3))
        float sharp[TOTAL_PIXELS];
        float s_min = 1e9f, s_max = -1e9f;
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float blur = 0; int cnt = 0;
                for (int yy = (y > 0 ? y - 1 : 0); yy <= (y + 1 < H ? y + 1 : H - 1); yy++) {
                    for (int xx = (x > 0 ? x - 1 : 0); xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
                        blur += res3[yy * W + xx];
                        cnt++;
                    }
                }
                float high = res3[y * W + x] - blur / cnt;
                float val = res3[y * W + x] + amount * high;
                sharp[y * W + x] = val;
                if (val < s_min) s_min = val;
                if (val > s_max) s_max = val;
            }
        }
        unsigned char norm[TOTAL_PIXELS];
        float span = s_max - s_min;
        for (int i = 0; i < TOTAL_PIXELS; i++) {
            int v = (int)roundf(((sharp[i] - s_min) * 255.0f) / span);
            norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
        int bz;
        int m = eval_image(norm, ppmm, &bz);
        printf("Sharpen amount=%.1f: minutiae=%2d bz=%2d/12\n", amount, m, bz);
    }

    // Test 4: Upscaling interpolation method:
    // Bilinear vs Bicubic
    printf("\n=== Bilinear vs Higher Scale Factor ===\n");
    // What if upscaled 2.5x to 160x200 or 1.5x?
    return 0;
}
