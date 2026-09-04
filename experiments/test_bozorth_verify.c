#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>
#include <bozorth.h>

#define W 80
#define H 64


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

int match_prints(MINUTIAE *m1, MINUTIAE *m2, int w, int h) {
    if (!m1 || !m2) return 0;
    if (m1->num < 10 || m2->num < 10) return 0;

    struct xyt_struct xyt1 = {0};
    struct xyt_struct xyt2 = {0};
    minutiae_to_xyt(m1, w, h, &xyt1);
    minutiae_to_xyt(m2, w, h, &xyt2);

    int probe_len = bozorth_probe_init(&xyt1);
    return bozorth_to_gallery(probe_len, &xyt1, &xyt2);
}

int main() {
    FILE *f = fopen("/tmp/live_touch.pgm", "r");
    if (!f) { printf("Cannot open /tmp/live_touch.pgm\n"); return 1; }
    char line[128];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] != '#' && strstr(line, "4095")) break;
    }
    int vals[5120];
    int n = 0;
    while (n < 5120 && fscanf(f, "%d", &vals[n]) == 1) n++;
    fclose(f);

    int min_v = vals[0], max_v = vals[0];
    for (int i = 1; i < 5120; i++) {
        if (vals[i] < min_v) min_v = vals[i];
        if (vals[i] > max_v) max_v = vals[i];
    }
    int range = (max_v > min_v) ? (max_v - min_v) : 1;
    unsigned char norm[5120];
    for (int i = 0; i < 5120; i++) {
        int v = (int)(((vals[i] - min_v) * 255.0f) / range);
        norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
    }

    int dst_w = W * 2; // 160
    int dst_h = H * 2; // 128
    unsigned char *img1 = malloc(dst_w * dst_h);
    upscale_2x_bilinear(norm, W, H, img1);
    for (int i = 0; i < dst_w * dst_h; i++) img1[i] = 255 - img1[i]; // Inverted

    // Synthetic touch 2 (probe with slight noise & shift)
    unsigned char *img2 = malloc(dst_w * dst_h);
    for (int y = 0; y < dst_h; y++) {
        int sy = (y > 0) ? y - 1 : 0;
        for (int x = 0; x < dst_w; x++) {
            int sx = (x > 0) ? x - 1 : 0;
            int delta = (x % 3 == 0) ? 2 : -2;
            int v = (int)img1[sy * dst_w + sx] + delta;
            img2[y * dst_w + x] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
    }

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    MINUTIAE *m1 = NULL, *m2 = NULL;
    int *qmap, *dmap, *lcmap, *lfmap, *hcmap, mw, mh, bw, bh, bd;
    unsigned char *bdata;

    get_minutiae(&m1, &qmap, &dmap, &lcmap, &lfmap, &hcmap, &mw, &mh, &bdata, &bw, &bh, &bd,
                 img1, dst_w, dst_h, 8, ppmm, &parms);
    get_minutiae(&m2, &qmap, &dmap, &lcmap, &lfmap, &hcmap, &mw, &mh, &bdata, &bw, &bh, &bd,
                 img2, dst_w, dst_h, 8, ppmm, &parms);

    printf("Gallery minutiae: %d\n", m1 ? m1->num : 0);
    printf("Probe minutiae:   %d\n", m2 ? m2->num : 0);

    int score_self = match_prints(m1, m1, dst_w, dst_h);
    int score_match = match_prints(m1, m2, dst_w, dst_h);

    printf("Bozorth3 Self-Match Score:  %d (Threshold >= 12)\n", score_self);
    printf("Bozorth3 Probe-Match Score: %d (Threshold >= 12)\n", score_match);

    if (score_match >= 12) {
        printf(">>> VERIFICATION SUCCESSFUL! <<<\n");
    } else {
        printf(">>> VERIFICATION FAILED! <<<\n");
    }

    return 0;
}
