#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <glib.h>
#include <lfs.h>
#include <bozorth.h>

typedef struct {
    char image_name[32];
    char mode[16];          // "raw" or "interp19"
    int w;
    int h;
    char ordering[16];      // "row-major" or "col-major"
    int scale;              // 1 or 2
    int inverted;           // 0 (normal) or 1 (inverted)
    int remove_perimeter;   // 0 or 1
    int total_minutiae;
    int high_rel_minutiae;  // reliability >= 0.20
    int score_self;
    int score_noisy;
    int score_shifted;
    int tripped_floor;      // 1 if < 10 minutiae
} BenchResult;

static void minutiae_to_xyt (MINUTIAE *minutiae, int bwidth, int bheight, struct xyt_struct *xyt) {
    struct minutiae_struct c[MAX_FILE_MINUTIAE];
    int nmin = (minutiae && minutiae->num < MAX_BOZORTH_MINUTIAE) ? minutiae->num : (minutiae ? MAX_BOZORTH_MINUTIAE : 0);
    for (int i = 0; i < nmin; i++) {
        MINUTIA *m = minutiae->list[i];
        lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2], m, bwidth, bheight);
        c[i].col[3] = (int)round (m->reliability * 100.0);
        if (c[i].col[2] > 180) c[i].col[2] -= 360;
    }
    if (nmin > 0) {
        qsort (c, nmin, sizeof(struct minutiae_struct), sort_x_y);
    }
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

// Extract minutiae and return count & list
static int run_mindtct(const unsigned char *img, int w, int h, int remove_perimeter, MINUTIAE **out_m) {
    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = remove_perimeter;
    double ppmm = 500.0 / 25.4;

    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;
    *out_m = NULL;

    unsigned char *img_copy = malloc(w * h);
    memcpy(img_copy, img, w * h);

    int ret = get_minutiae(out_m, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                           &mw, &mh, &bdata, &bw, &bh, &bd,
                           img_copy, w, h, 8, ppmm, &parms);

    free(img_copy);
    if (qmap) free(qmap);
    if (dmap) free(dmap);
    if (lcmap) free(lcmap);
    if (lfmap) free(lfmap);
    if (hcmap) free(hcmap);
    if (bdata) free(bdata);

    return ret;
}

static int match_prints(MINUTIAE *m1, MINUTIAE *m2, int w, int h) {
    if (!m1 || !m2) return 0;
    if (m1->num < 10 || m2->num < 10) return 0;

    struct xyt_struct xyt1 = {0};
    struct xyt_struct xyt2 = {0};
    minutiae_to_xyt(m1, w, h, &xyt1);
    minutiae_to_xyt(m2, w, h, &xyt2);

    int probe_len = bozorth_probe_init(&xyt1);
    return bozorth_to_gallery(probe_len, &xyt1, &xyt2);
}

static void evaluate_variant(const char *image_name, const char *mode,
                             const unsigned char *base_img, int w, int h,
                             const char *ordering, int scale, int inverted, int remove_perimeter,
                             BenchResult *res) {
    int cur_w = (scale == 2) ? w * 2 : w;
    int cur_h = (scale == 2) ? h * 2 : h;
    int npix = cur_w * cur_h;

    unsigned char *final_img = malloc(npix);
    if (scale == 2) {
        upscale_2x_bilinear(base_img, w, h, final_img);
    } else {
        memcpy(final_img, base_img, npix);
    }

    if (inverted) {
        for (int i = 0; i < npix; i++) {
            final_img[i] = 255 - final_img[i];
        }
    }

    // 1. Minutiae detection on primary image
    MINUTIAE *m_main = NULL;
    int ret = run_mindtct(final_img, cur_w, cur_h, remove_perimeter, &m_main);

    int num = (m_main ? m_main->num : 0);
    int high_rel = 0;
    if (m_main) {
        for (int i = 0; i < m_main->num; i++) {
            if (m_main->list[i]->reliability >= 0.20)
                high_rel++;
        }
    }

    // Self-match score
    int score_self = 0;
    if (num >= 10) {
        score_self = match_prints(m_main, m_main, cur_w, cur_h);
    }

    // 2. Noisy variant: small intensity jitter
    unsigned char *noisy_img = malloc(npix);
    for (int i = 0; i < npix; i++) {
        int delta = ((i % 5) == 0) ? 3 : (((i % 3) == 0) ? -3 : 1);
        int v = (int)final_img[i] + delta;
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        noisy_img[i] = (unsigned char)v;
    }
    MINUTIAE *m_noisy = NULL;
    run_mindtct(noisy_img, cur_w, cur_h, remove_perimeter, &m_noisy);
    int score_noisy = 0;
    if (num >= 10 && m_noisy && m_noisy->num >= 10) {
        score_noisy = match_prints(m_main, m_noisy, cur_w, cur_h);
    }

    // 3. Shifted variant: +1 pixel in X and Y
    unsigned char *shifted_img = malloc(npix);
    for (int y = 0; y < cur_h; y++) {
        int sy = (y > 0) ? y - 1 : 0;
        for (int x = 0; x < cur_w; x++) {
            int sx = (x > 0) ? x - 1 : 0;
            shifted_img[y * cur_w + x] = final_img[sy * cur_w + sx];
        }
    }
    MINUTIAE *m_shifted = NULL;
    run_mindtct(shifted_img, cur_w, cur_h, remove_perimeter, &m_shifted);
    int score_shifted = 0;
    if (num >= 10 && m_shifted && m_shifted->num >= 10) {
        score_shifted = match_prints(m_main, m_shifted, cur_w, cur_h);
    }

    // Fill result
    strncpy(res->image_name, image_name, sizeof(res->image_name) - 1);
    strncpy(res->mode, mode, sizeof(res->mode) - 1);
    res->w = cur_w;
    res->h = cur_h;
    strncpy(res->ordering, ordering, sizeof(res->ordering) - 1);
    res->scale = scale;
    res->inverted = inverted;
    res->remove_perimeter = remove_perimeter;
    res->total_minutiae = num;
    res->high_rel_minutiae = high_rel;
    res->score_self = score_self;
    res->score_noisy = score_noisy;
    res->score_shifted = score_shifted;
    res->tripped_floor = (num < 10) ? 1 : 0;

    if (m_main) free_minutiae(m_main);
    if (m_noisy) free_minutiae(m_noisy);
    if (m_shifted) free_minutiae(m_shifted);
    free(final_img);
    free(noisy_img);
    free(shifted_img);
}

// Load raw 5120 pixels from P5 or P2 file
static int load_raw_5120(const char *path, unsigned char *out_raw) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    char line[128];
    if (!fgets(line, sizeof(line), f)) { fclose(f); return -1; }

    if (line[0] == 'P' && line[1] == '5') {
        int count = 0;
        while (count < 2 && fgets(line, sizeof(line), f)) {
            if (line[0] == '#') continue;
            count++;
        }
        int read_n = fread(out_raw, 1, 5120, f);
        fclose(f);
        return (read_n == 5120) ? 0 : -2;
    } else if (line[0] == 'P' && line[1] == '2') {
        int w = 0, h = 0, maxv = 0;
        while (fgets(line, sizeof(line), f)) {
            if (line[0] == '#') continue;
            if (sscanf(line, "%d %d", &w, &h) == 2) break;
        }
        while (fgets(line, sizeof(line), f)) {
            if (line[0] == '#') continue;
            if (sscanf(line, "%d", &maxv) == 1) break;
        }
        int *vals = malloc(5120 * sizeof(int));
        int n = 0;
        while (n < 5120 && fscanf(f, "%d", &vals[n]) == 1) {
            n++;
        }
        fclose(f);
        if (n < 5120) { free(vals); return -3; }

        int min_v = vals[0], max_val = vals[0];
        for (int i = 1; i < 5120; i++) {
            if (vals[i] < min_v) min_v = vals[i];
            if (vals[i] > max_val) max_val = vals[i];
        }
        int range = (max_val > min_v) ? (max_val - min_v) : 1;
        for (int i = 0; i < 5120; i++) {
            int norm = (int)(((vals[i] - min_v) * 255.0f) / range);
            if (norm < 0) norm = 0;
            if (norm > 255) norm = 255;
            out_raw[i] = (unsigned char)norm;
        }
        free(vals);
        return 0;
    }
    fclose(f);
    return -4;
}

int main(int argc, char **argv) {
    const char *images[] = {
        "/home/sastauser/code/temp/goodix/experiments/windows_unpacked.pgm",
        "/home/sastauser/code/temp/goodix/experiments/fingerprint.pgm",
        "/tmp/live_touch.pgm"
    };
    int num_images = sizeof(images) / sizeof(images[0]);

    printf("=======================================================================================================================\n");
    printf("GOODIX 5E0A MINUTIAE & BOZORTH3 GEOMETRY BENCHMARK\n");
    printf("=======================================================================================================================\n\n");

    static BenchResult all_results[500];
    int res_count = 0;

    for (int img_idx = 0; img_idx < num_images; img_idx++) {
        unsigned char raw[5120];
        if (load_raw_5120(images[img_idx], raw) != 0) {
            printf("[SKIP] Could not load image: %s\n", images[img_idx]);
            continue;
        }

        const char *img_short = strrchr(images[img_idx], '/');
        img_short = img_short ? (img_short + 1) : images[img_idx];
        printf(">>> Processing Image: %s <<<\n", img_short);

        int dims[2][2] = { {80, 64}, {64, 80} };
        const char *orderings[] = { "row-major", "col-major" };
        int scales[] = { 1, 2 };
        int inverts[] = { 0, 1 };
        int perims[] = { 0, 1 };

        // 1. RAW MATRIX EVALUATION
        for (int d = 0; d < 2; d++) {
            int w = dims[d][0];
            int h = dims[d][1];

            for (int ord = 0; ord < 2; ord++) {
                const char *ordering = orderings[ord];
                unsigned char base_img[5120];

                if (w == 80 && h == 64) {
                    if (ord == 0) {
                        for (int r = 0; r < 64; r++)
                            for (int c = 0; c < 80; c++)
                                base_img[r * 80 + c] = raw[r * 80 + c];
                    } else {
                        for (int r = 0; r < 64; r++)
                            for (int c = 0; c < 80; c++)
                                base_img[r * 80 + c] = raw[c * 64 + r];
                    }
                } else { // 64x80
                    if (ord == 0) {
                        for (int r = 0; r < 80; r++)
                            for (int c = 0; c < 64; c++)
                                base_img[r * 64 + c] = raw[r * 64 + c];
                    } else {
                        for (int r = 0; r < 80; r++)
                            for (int c = 0; c < 64; c++)
                                base_img[r * 64 + c] = raw[c * 80 + r];
                    }
                }

                for (int s = 0; s < 2; s++) {
                    int scale = scales[s];
                    for (int inv = 0; inv < 2; inv++) {
                        int inverted = inverts[inv];
                        for (int p = 0; p < 2; p++) {
                            int remove_perim = perims[p];

                            BenchResult r;
                            evaluate_variant(img_short, "raw", base_img, w, h,
                                             ordering, scale, inverted, remove_perim, &r);
                            all_results[res_count++] = r;
                        }
                    }
                }
            }
        }

        // 2. RECONSTRUCTED 19-CHANNEL COLUMN HORIZONTAL INTERPOLATION (like test_match.c)
        {
            unsigned short samples19[19][64];
            for (int k = 0; k < 19; ++k) {
                int col = 4 * k + 3;
                for (int r = 0; r < 64; ++r) {
                    samples19[k][r] = raw[r * 80 + col];
                }
            }
            // Reconstruct 80x64
            unsigned char recon80x64[80 * 64];
            for (int r = 0; r < 64; ++r) {
                for (int c = 0; c < 80; ++c) {
                    float pos = (float)(c - 3) / 4.0f;
                    float val;
                    if (pos <= 0.0f) {
                        val = (float)samples19[0][r];
                    } else if (pos >= 18.0f) {
                        val = (float)samples19[18][r];
                    } else {
                        int k = (int)pos;
                        float frac = pos - (float)k;
                        val = (float)samples19[k][r] * (1.0f - frac) + (float)samples19[k + 1][r] * frac;
                    }
                    int v = (int)roundf(val);
                    if (v < 0) v = 0; if (v > 255) v = 255;
                    recon80x64[r * 80 + c] = (unsigned char)v;
                }
            }
            // Reconstruct 64x80 (transposed)
            unsigned char recon64x80[64 * 80];
            for (int r = 0; r < 80; ++r) {
                for (int c = 0; c < 64; ++c) {
                    recon64x80[r * 64 + c] = recon80x64[c * 80 + r];
                }
            }

            for (int s = 0; s < 2; s++) {
                int scale = scales[s];
                for (int inv = 0; inv < 2; inv++) {
                    int inverted = inverts[inv];
                    for (int p = 0; p < 2; p++) {
                        int remove_perim = perims[p];

                        BenchResult r80;
                        evaluate_variant(img_short, "recon19", recon80x64, 80, 64,
                                         "interp-col", scale, inverted, remove_perim, &r80);
                        all_results[res_count++] = r80;

                        BenchResult r64;
                        evaluate_variant(img_short, "recon19", recon64x80, 64, 80,
                                         "interp-row", scale, inverted, remove_perim, &r64);
                        all_results[res_count++] = r64;
                    }
                }
            }
        }
    }

    // PRINT SUMMARY TABLES
    printf("\n%s\n", "=================================================================================================================================================");
    printf("%-20s | %-8s | %-8s | %-10s | %-5s | %-8s | %-8s | %-6s | %-6s | %-6s | %-6s | %-7s | %-6s\n",
           "Image", "Mode", "Dim(WxH)", "Ordering", "Scale", "Polarity", "Partial", "TotalM", "Rel>=.2", "SelfSc", "NoisySc", "ShiftSc", "Trip<10");
    printf("%s\n", "---------------------+----------+----------+------------+-------+----------+----------+--------+--------+--------+--------+---------+-------");

    for (int i = 0; i < res_count; i++) {
        BenchResult *r = &all_results[i];
        printf("%-20s | %-8s | %3dx%-4d | %-10s | %2dx   | %-8s | %-8s | %6d | %6d | %6d | %6d | %7d | %-6s\n",
               r->image_name,
               r->mode,
               r->w, r->h,
               r->ordering,
               r->scale,
               r->inverted ? "Inverted" : "Normal",
               r->remove_perimeter ? "Part=1" : "Part=0",
               r->total_minutiae,
               r->high_rel_minutiae,
               r->score_self,
               r->score_noisy,
               r->score_shifted,
               r->tripped_floor ? "YES" : "no");
    }
    printf("%s\n", "=================================================================================================================================================");

    return 0;
}
