#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>

#define W 64
#define H 80

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

int test_image(const char *label, const unsigned char *norm_64x80, int inverted) {
    int dst_w = W * 2; // 128
    int dst_h = H * 2; // 160
    unsigned char *scaled = malloc(dst_w * dst_h);
    upscale_2x_bilinear(norm_64x80, W, H, scaled);

    if (inverted) {
        for (int i = 0; i < dst_w * dst_h; i++)
            scaled[i] = 255 - scaled[i];
    }

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    MINUTIAE *minutiae = NULL;
    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;
    int ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                           &mw, &mh, &bdata, &bw, &bh, &bd,
                           scaled, dst_w, dst_h, 8, ppmm, &parms);
    int num = (minutiae ? minutiae->num : 0);
    printf("  [%s] inverted=%d -> ret=%d minutiae_count=%d\n", label, inverted, ret, num);

    free(scaled);
    if (minutiae) free_minutiae(minutiae);
    if (qmap) free(qmap);
    if (dmap) free(dmap);
    if (lcmap) free(lcmap);
    if (lfmap) free(lfmap);
    if (hcmap) free(hcmap);
    if (bdata) free(bdata);
    return num;
}

int main() {
    // Load live_touch.pgm (which has 80 lines of 64 numbers)
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
    printf("Read %d values from /tmp/live_touch.pgm\n", n);

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

    // Geometry 1: Natural order 64x80 (row y in 0..79, col x in 0..63)
    // norm[y * 64 + x]
    printf("\n=== Geometry 1: 64x80 (W=64, H=80 -> Scaled 128x160) ===\n");
    test_image("64x80 Natural", norm, 0);
    test_image("64x80 Inverted", norm, 1);

    // Geometry 2: Transposed 80x64 (W=80, H=64 -> Scaled 160x128)
    // trans[y * 80 + x] = norm[x * 64 + y]
    unsigned char trans[5120];
    for (int y = 0; y < 64; y++) {
        for (int x = 0; x < 80; x++) {
            trans[y * 80 + x] = norm[x * 64 + y];
        }
    }
    printf("\n=== Geometry 2: 80x64 (W=80, H=64 -> Scaled 160x128) ===\n");
    test_image("80x64 Transposed", trans, 0);
    test_image("80x64 Transposed Inverted", trans, 1);

    return 0;
}
