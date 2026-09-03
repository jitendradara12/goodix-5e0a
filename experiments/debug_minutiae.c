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
    if (argc < 2) return 1;
    int mode = atoi(argv[1]);

    FILE *f = fopen("windows_unpacked.pgm", "rb");
    if (!f) return 1;
    char header[64];
    for (int i=0; i<3; ++i) fgets(header, sizeof(header), f);
    unsigned char orig[80 * 64];
    fread(orig, 1, 80 * 64, f);
    fclose(f);

    int cols[19];
    for (int k = 0; k < 19; ++k) cols[k] = 4 * k + 3;
    unsigned char dense[19 * 64];
    for (int y = 0; y < 64; ++y)
        for (int k = 0; k < 19; ++k)
            dense[y * 19 + k] = orig[y * 80 + cols[k]];

    if (mode == 3) {
        unsigned char enl[152 * 128];
        unsigned char enl_inv[152 * 128];
        for (int y = 0; y < 128; ++y) {
            float y_pos = (float)y / 2.0f;
            int r0 = (int)y_pos;
            int r1 = (r0 + 1 < 64) ? r0 + 1 : r0;
            float r_frac = y_pos - (float)r0;
            for (int x = 0; x < 152; ++x) {
                float x_pos = (float)x / 8.0f;
                int k = (int)x_pos;
                int k1 = (k + 1 < 19) ? k + 1 : k;
                float c_frac = x_pos - (float)k;
                float top = (float)dense[r0 * 19 + k] * (1.0f - c_frac) + (float)dense[r0 * 19 + k1] * c_frac;
                float bot = (float)dense[r1 * 19 + k] * (1.0f - c_frac) + (float)dense[r1 * 19 + k1] * c_frac;
                float val = top * (1.0f - r_frac) + bot * r_frac;
                int v = (int)val;
                if (v < 0) v = 0; if (v > 255) v = 255;
                enl[y * 152 + x] = (unsigned char)v;
                enl_inv[y * 152 + x] = 255 - (unsigned char)v;
            }
        }
        printf("=== Testing 2x Enlarged (152x128) ===\n");
        test_img("Enlarge_2x", enl, 152, 128);
        test_img("Enlarge_2x_Inv", enl_inv, 152, 128);
    }
    return 0;
}
