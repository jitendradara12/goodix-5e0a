#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <lfs.h>
#include <glib.h>
#include <bz_dyn.h>

extern const LFSPARMS g_lfsparms_V2;

int main() {
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

    const int W = 160;
    const int H = 128;
    unsigned char img1[160 * 128];
    unsigned char img2[160 * 128];

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
            img1[r * W + c] = (unsigned char)norm;
            // img2 with slight shift / noise
            int norm2 = norm + ((c % 3 == 0) ? 2 : -2);
            if (norm2 < 0) norm2 = 0; if (norm2 > 255) norm2 = 255;
            img2[r * W + c] = (unsigned char)norm2;
        }
    }

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    MINUTIAE *m1 = NULL, *m2 = NULL;
    int *qmap, *dmap, *lcmap, *lfmap, *hcmap;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;

    get_minutiae(&m1, &qmap, &dmap, &lcmap, &lfmap, &hcmap, &mw, &mh, &bdata, &bw, &bh, &bd,
                 img1, W, H, 8, ppmm, &parms);
    get_minutiae(&m2, &qmap, &dmap, &lcmap, &lfmap, &hcmap, &mw, &mh, &bdata, &bw, &bh, &bd,
                 img2, W, H, 8, ppmm, &parms);

    printf("Minutiae 1: %d, Minutiae 2: %d\n", m1 ? m1->num : 0, m2 ? m2->num : 0);

    // Bozorth match score
    int *xyt1 = malloc(m1->num * 4 * sizeof(int));
    int *xyt2 = malloc(m2->num * 4 * sizeof(int));
    for (int i = 0; i < m1->num; ++i) {
        MINUTIA *min = m1->list[i];
        xyt1[i*4 + 0] = min->x;
        xyt1[i*4 + 1] = min->y;
        xyt1[i*4 + 2] = min->theta;
        xyt1[i*4 + 3] = min->reliability * 100;
    }
    for (int i = 0; i < m2->num; ++i) {
        MINUTIA *min = m2->list[i];
        xyt2[i*4 + 0] = min->x;
        xyt2[i*4 + 1] = min->y;
        xyt2[i*4 + 2] = min->theta;
        xyt2[i*4 + 3] = min->reliability * 100;
    }

    int score = bozorth_main(xyt1, xyt2);
    printf("Bozorth match score between identical/noisy prints: %d\n", score);
    return 0;
}
