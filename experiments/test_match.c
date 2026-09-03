#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <glib.h>
#include <lfs.h>
#include <bozorth.h>



int sort_x_y (const void *a, const void *b) {
    const struct minutiae_struct *m1 = a;
    const struct minutiae_struct *m2 = b;
    if (m1->col[0] < m2->col[0]) return -1;
    if (m1->col[0] > m2->col[0]) return 1;
    if (m1->col[1] < m2->col[1]) return -1;
    if (m1->col[1] > m2->col[1]) return 1;
    return 0;
}

static void minutiae_to_xyt (MINUTIAE *minutiae, int bwidth, int bheight, struct xyt_struct *xyt) {
    struct minutiae_struct c[MAX_FILE_MINUTIAE];
    int nmin = (minutiae->num < MAX_BOZORTH_MINUTIAE) ? minutiae->num : MAX_BOZORTH_MINUTIAE;
    for (int i = 0; i < nmin; i++) {
        MINUTIA *m = minutiae->list[i];
        lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2], m, bwidth, bheight);
        c[i].col[3] = (int)round (m->reliability * 100.0);
        if (c[i].col[2] > 180) c[i].col[2] -= 360;
    }
    qsort (c, nmin, sizeof(struct minutiae_struct), sort_x_y);
    for (int i = 0; i < nmin; i++) {
        xyt->xcol[i] = c[i].col[0];
        xyt->ycol[i] = c[i].col[1];
        xyt->thetacol[i] = c[i].col[2];
    }
    xyt->nrows = nmin;
}

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
            int norm2 = norm + ((c % 4 == 0) ? 3 : -2);
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

    struct xyt_struct xyt1 = {0};
    struct xyt_struct xyt2 = {0};
    minutiae_to_xyt(m1, W, H, &xyt1);
    minutiae_to_xyt(m2, W, H, &xyt2);

    int probe_len = bozorth_probe_init(&xyt1);
    int score = bozorth_to_gallery(probe_len, &xyt1, &xyt2);

    printf("=== Bozorth3 Match Score: %d ===\n", score);
    return 0;
}
