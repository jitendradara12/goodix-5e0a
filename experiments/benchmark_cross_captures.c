#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lfs.h>
#include <bozorth.h>

#define W 80
#define H 64
#define DST_W (W * 2)
#define DST_H (H * 2)

typedef struct {
    char name[64];
    char path[256];
    int minutiae_count;
    MINUTIAE *minutiae;
    struct xyt_struct xyt;
} Capture;

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

static int load_and_preprocess(const char *path, unsigned char *out_dst) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;

    char magic[3] = {0};
    if (fscanf(f, "%2s", magic) != 1) { fclose(f); return -2; }

    int pw = 0, ph = 0, max_val = 0;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#') continue;
        if (sscanf(line, "%d %d", &pw, &ph) == 2) break;
    }
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#') continue;
        if (sscanf(line, "%d", &max_val) == 1) break;
    }

    int raw_vals[5120];
    if (strcmp(magic, "P2") == 0) {
        int n = 0;
        while (n < 5120 && fscanf(f, "%d", &raw_vals[n]) == 1) n++;
        fclose(f);
        if (n < 5120) return -3;
    } else if (strcmp(magic, "P5") == 0) {
        unsigned char buf[5120];
        size_t rd = fread(buf, 1, 5120, f);
        fclose(f);
        if (rd < 5120) return -3;
        for (int i = 0; i < 5120; i++) raw_vals[i] = buf[i];
    } else {
        fclose(f);
        return -4;
    }

    int min_v = raw_vals[0], max_v = raw_vals[0];
    for (int i = 1; i < 5120; i++) {
        if (raw_vals[i] < min_v) min_v = raw_vals[i];
        if (raw_vals[i] > max_v) max_v = raw_vals[i];
    }
    int range = (max_v > min_v) ? (max_v - min_v) : 1;

    unsigned char norm[5120];
    for (int i = 0; i < 5120; i++) {
        int v = (range > 0 && max_v > 0) ? (int)(((raw_vals[i] - min_v) * 255.0f) / range) : 0;
        norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
    }

    upscale_2x_bilinear(norm, W, H, out_dst);
    for (int i = 0; i < DST_W * DST_H; i++) {
        out_dst[i] = 255 - out_dst[i]; // Invert polarity for capacitive ridge
    }

    return 0;
}

static int match_captures(Capture *c1, Capture *c2) {
    if (!c1 || !c2 || !c1->minutiae || !c2->minutiae) return 0;
    if (c1->minutiae_count < 10 || c2->minutiae_count < 10) return 0;

    int probe_len = bozorth_probe_init(&c1->xyt);
    return bozorth_to_gallery(probe_len, &c1->xyt, &c2->xyt);
}

int main() {
    Capture caps[] = {
        { "Finger A (Cap 1)", "/home/sastauser/code/temp/goodix/experiments/fingerprint.pgm", 0, NULL, {0} },
        { "Finger A (Cap 2)", "/tmp/touch_test_raw.pgm", 0, NULL, {0} },
        { "Finger B (WinWBDI)", "/home/sastauser/code/temp/goodix/experiments/windows_unpacked.pgm", 0, NULL, {0} },
        { "Finger C (Off1)", "/tmp/frame_off1.pgm", 0, NULL, {0} },
        { "Air Baseline", "/home/sastauser/code/temp/goodix/experiments/clear-0.pgm", 0, NULL, {0} }
    };
    int n_caps = sizeof(caps) / sizeof(caps[0]);

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    printf("=========================================================================================\n");
    printf("OFFLINE BIOMETRIC ACCURACY BENCHMARK — REAL CAPTURES & CROSS-MATCH MATRIX\n");
    printf("=========================================================================================\n\n");

    printf("1. Minutiae Extraction Yield (2x Bilinear, 160x128, Polarity Inverted, PPMM=%.3f):\n", ppmm);
    printf("-----------------------------------------------------------------------------------------\n");

    for (int i = 0; i < n_caps; i++) {
        unsigned char img[DST_W * DST_H];
        if (load_and_preprocess(caps[i].path, img) != 0) {
            printf("Failed to load %s\n", caps[i].path);
            continue;
        }

        int *qmap, *dmap, *lcmap, *lfmap, *hcmap, mw, mh, bw, bh, bd;
        unsigned char *bdata;
        get_minutiae(&caps[i].minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                     &mw, &mh, &bdata, &bw, &bh, &bd,
                     img, DST_W, DST_H, 8, ppmm, &parms);

        caps[i].minutiae_count = caps[i].minutiae ? caps[i].minutiae->num : 0;
        minutiae_to_xyt(caps[i].minutiae, DST_W, DST_H, &caps[i].xyt);

        printf("  [%d] %-20s : %3d minutiae (floor >= 12: %s)\n",
               i, caps[i].name, caps[i].minutiae_count,
               caps[i].minutiae_count >= 12 ? "PASS" : "FAIL/AIR");
    }

    printf("\n2. Pairwise Bozorth3 Match Score Matrix (Operating Threshold = 14):\n");
    printf("-----------------------------------------------------------------------------------------\n");
    printf("%-20s", "Gallery \\ Probe");
    for (int j = 0; j < n_caps; j++) {
        printf(" | [%d] %-10s", j, caps[j].name);
    }
    printf("\n");
    printf("--------------------+---------------+---------------+---------------+---------------+---------------\n");

    for (int i = 0; i < n_caps; i++) {
        printf("[%-2d] %-16s", i, caps[i].name);
        for (int j = 0; j < n_caps; j++) {
            int score = match_captures(&caps[i], &caps[j]);
            printf(" | %13d", score);
        }
        printf("\n");
    }

    printf("=========================================================================================\n\n");

    int genuine_score = match_captures(&caps[0], &caps[1]);
    printf("3. Biometric Verification Analysis:\n");
    printf("  - Genuine Pair (Finger A Cap 1 vs Finger A Cap 2):\n");
    printf("      Bozorth3 Score: %d (Threshold = 14) -> %s\n",
           genuine_score, genuine_score >= 14 ? "GENUINE MATCH (VERIFIED)" : "FALSE REJECTION");
    printf("      Safety Margin:  +%d points above threshold\n", genuine_score - 14);

    int max_impostor = 0;
    for (int i = 0; i < n_caps; i++) {
        for (int j = 0; j < n_caps; j++) {
            if (i == j) continue;
            // Skip genuine pair (0,1) and (1,0)
            if ((i == 0 && j == 1) || (i == 1 && j == 0)) continue;
            int s = match_captures(&caps[i], &caps[j]);
            if (s > max_impostor) max_impostor = s;
        }
    }
    printf("\n  - Impostor Pairs (Cross-Finger & Air Trials):\n");
    printf("      Max Impostor Score: %d (Threshold = 14) -> %s\n",
           max_impostor, max_impostor < 14 ? "100% IMPOSTOR REJECTION" : "LEAKAGE DETECTED");
    printf("      Rejection Margin:   -%d points below threshold\n", 14 - max_impostor);
    printf("=========================================================================================\n");

    return 0;
}
