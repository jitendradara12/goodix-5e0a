#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <lfs.h>
#include <glib.h>

void test_img(const char *name, unsigned char *data, int W, int H) {
    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;

    for (double dpi = 250.0; dpi <= 750.0; dpi += 250.0) {
        MINUTIAE *minutiae = NULL;
        int *qmap, *dmap, *lcmap, *lfmap, *hcmap;
        int mw, mh, bw, bh, bd;
        unsigned char *bdata = NULL;
        double ppmm = dpi / 25.4;
        int ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                               &mw, &mh, &bdata, &bw, &bh, &bd,
                               data, W, H, 8, ppmm, &parms);
        int n = minutiae ? minutiae->num : -1;
        printf("  %s (%dx%d) @ %.0f DPI: ret=%d, minutiae=%d, map=%dx%d\n",
               name, W, H, dpi, ret, n, mw, mh);
    }
}

int main(int argc, char **argv) {
    FILE *f = fopen("windows_unpacked.pgm", "rb");
    if (!f) return 1;
    char header[64];
    for (int i=0; i<3; ++i) fgets(header, sizeof(header), f);
    unsigned char orig[80 * 64];
    fread(orig, 1, 80 * 64, f);
    fclose(f);

    unsigned short samples[19][64];
    for (int k=0; k<19; ++k) {
        int col = 4 * k + 3;
        for (int r=0; r<64; ++r) {
            samples[k][r] = orig[r * 80 + col];
        }
    }

    // Current goodix5e0a.c 160x128 logic:
    const int W = 160;
    const int H = 128;
    unsigned char img[160 * 128];
    unsigned char img_inv[160 * 128];

    for (int r = 0; r < H; ++r) {
        float orig_r = (float) r / 2.0f;
        int r0 = (int) orig_r;
        int r1 = (r0 + 1 < 64) ? r0 + 1 : r0;
        float r_frac = orig_r - (float) r0;

        for (int c = 0; c < W; ++c) {
            float orig_c = (float) c / 2.0f;
            float pos = (orig_c - 3.0f) / 4.0f;
            float val;

            if (pos <= 0.0f) {
                val = (float) samples[0][r0] * (1.0f - r_frac) + (float) samples[0][r1] * r_frac;
            } else if (pos >= 18.0f) {
                val = (float) samples[18][r0] * (1.0f - r_frac) + (float) samples[18][r1] * r_frac;
            } else {
                int k = (int) pos;
                float c_frac = pos - (float) k;
                float top = (float) samples[k][r0] * (1.0f - c_frac) + (float) samples[k + 1][r0] * c_frac;
                float bot = (float) samples[k][r1] * (1.0f - c_frac) + (float) samples[k + 1][r1] * c_frac;
                val = top * (1.0f - r_frac) + bot * r_frac;
            }
            int norm = (int)val;
            if (norm < 0) norm = 0; if (norm > 255) norm = 255;
            img[r * W + c] = (unsigned char)norm;
            img_inv[r * W + c] = 255 - (unsigned char)norm;
        }
    }

    printf("=== Testing Current goodix5e0a.c (160x128) ===\n");
    test_img("goodix5e0a_160x128", img, 160, 128);
    test_img("goodix5e0a_160x128_inv", img_inv, 160, 128);
    return 0;
}
