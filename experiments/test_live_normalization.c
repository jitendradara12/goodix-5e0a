#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>
#include <bozorth.h>

#define W 80
#define H 64

extern LFSPARMS g_lfsparms_V2;

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

int count_minutiae(const unsigned char *norm_img, int dst_w, int dst_h) {
    unsigned char *img = malloc(dst_w * dst_h);
    for (int i = 0; i < dst_w * dst_h; i++) img[i] = 255 - norm_img[i]; // Invert

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    MINUTIAE *m = NULL;
    int *qmap, *dmap, *lcmap, *lfmap, *hcmap, mw, mh, bw, bh, bd;
    unsigned char *bdata;

    get_minutiae(&m, &qmap, &dmap, &lcmap, &lfmap, &hcmap, &mw, &mh, &bdata, &bw, &bh, &bd,
                 img, dst_w, dst_h, 8, ppmm, &parms);
    int num = m ? m->num : 0;
    if (m) free_minutiae(m);
    free(img);
    return num;
}

int main() {
    FILE *f = fopen("/tmp/live_touch.pgm", "r");
    if (!f) return 1;
    char line[128];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] != '#' && strstr(line, "4095")) break;
    }
    int vals[5120];
    int n = 0;
    while (n < 5120 && fscanf(f, "%d", &vals[n]) == 1) n++;
    fclose(f);

    // Method 1: Current driver logic (min_v = min(v > 30))
    int min_nz = 65535, max_v = 0;
    for (int i = 0; i < 5120; i++) {
        if (vals[i] > 30) {
            if (vals[i] < min_nz) min_nz = vals[i];
            if (vals[i] > max_v) max_v = vals[i];
        }
    }
    int range_nz = (max_v > min_nz) ? (max_v - min_nz) : 1;
    unsigned char norm1[5120];
    for (int i = 0; i < 5120; i++) {
        int v = (int)(((vals[i] - min_nz) * 255.0f) / range_nz);
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        norm1[i] = (unsigned char)v;
    }
    unsigned char up1[160 * 128];
    upscale_2x_bilinear(norm1, W, H, up1);
    int m1 = count_minutiae(up1, 160, 128);

    // Method 2: Zero-baseline normalization (min_v = 0, range = max_v)
    unsigned char norm2[5120];
    for (int i = 0; i < 5120; i++) {
        int v = (int)((vals[i] * 255.0f) / max_v);
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        norm2[i] = (unsigned char)v;
    }
    unsigned char up2[160 * 128];
    upscale_2x_bilinear(norm2, W, H, up2);
    int m2 = count_minutiae(up2, 160, 128);

    printf("fingerprint.pgm Method 1 (min_nz=%d, max=%d, range=%d): %d minutiae\n", min_nz, max_v, range_nz, m1);
    printf("fingerprint.pgm Method 2 (min=0, max=%d, range=%d): %d minutiae\n", max_v, max_v, m2);

    return 0;
}
