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
#define WIRE_BYTES (FRAME_BLOCKS * BLOCK_BYTES + 4)

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

static int get_minutiae_and_xyt(const unsigned char *scaled, int dst_w, int dst_h,
                                double ppmm, int inverted,
                                MINUTIAE **out_m, struct xyt_struct *xyt) {
    unsigned char *img = malloc(dst_w * dst_h);
    if (inverted) {
        for (int i = 0; i < dst_w * dst_h; i++)
            img[i] = 255 - scaled[i];
    } else {
        memcpy(img, scaled, dst_w * dst_h);
    }

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;

    MINUTIAE *minutiae = NULL;
    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;
    int ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                           &mw, &mh, &bdata, &bw, &bh, &bd,
                           img, dst_w, dst_h, 8, ppmm, &parms);
    int num = (minutiae ? minutiae->num : 0);
    if (xyt) {
        memset(xyt, 0, sizeof(*xyt));
        minutiae_to_xyt(minutiae, dst_w, dst_h, xyt);
    }

    if (out_m) {
        *out_m = minutiae;
    } else if (minutiae) {
        free_minutiae(minutiae);
    }

    free(img);
    if (qmap) free(qmap);
    if (dmap) free(dmap);
    if (lcmap) free(lcmap);
    if (lfmap) free(lfmap);
    if (hcmap) free(hcmap);
    if (bdata) free(bdata);
    return num;
}

static int bozorth_match(struct xyt_struct *p, struct xyt_struct *g) {
    if (p->nrows < 10 || g->nrows < 10) return 0;
    int probe_len = bozorth_probe_init(p);
    return bozorth_to_gallery(probe_len, p, g);
}

static int compare_float(const void *a, const void *b) {
    float fa = *(const float *)a;
    float fb = *(const float *)b;
    return (fa > fb) - (fa < fb);
}

int main(int argc, char **argv) {
    const char *raw_path = (argc > 1) ? argv[1] : "/dev/shm/live_frame.raw";
    FILE *f = fopen(raw_path, "rb");
    if (!f) {
        fprintf(stderr, "Cannot open %s\n", raw_path);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *raw_data = malloc(len);
    if (fread(raw_data, 1, len, f) != (size_t)len) {
        fprintf(stderr, "Short read\n");
        return 1;
    }
    fclose(f);

    unsigned short pix[TOTAL_PIXELS];
    decode_frame(pix, raw_data, len);
    free(raw_data);

    // Compute 3x3 local mean residual
    float residual[TOTAL_PIXELS];
    float residual_sorted[TOTAL_PIXELS];
    float res_min = 1e9f, res_max = -1e9f;
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            unsigned int local_sum = 0;
            unsigned int local_count = 0;
            for (int yy = (y > 0 ? y - 1 : 0); yy <= (y + 1 < H ? y + 1 : H - 1); yy++) {
                for (int xx = (x > 0 ? x - 1 : 0); xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
                    local_sum += pix[yy * W + xx];
                    local_count++;
                }
            }
            float val = pix[y * W + x] - (float)local_sum / local_count;
            residual[y * W + x] = val;
            residual_sorted[y * W + x] = val;
            if (val < res_min) res_min = val;
            if (val > res_max) res_max = val;
        }
    }
    qsort(residual_sorted, TOTAL_PIXELS, sizeof(float), compare_float);

    double ppmm_500 = 500.0 / 25.4;
    int dst_w = W * 2;
    int dst_h = H * 2;

    printf("======================================================================\n");
    printf("EVALUATION OF CONTRAST ENHANCEMENT METHODS ON /dev/shm/live_frame.raw\n");
    printf("======================================================================\n\n");

    // Helper: test a normalization array
    // Computes:
    // 1. Minutiae count and XYT
    // 2. Perturbed probe: shifted 1px dx, 1px dy + slight noise
    // 3. Bozorth score between original and perturbed
    #define TEST_CONFIG(label, norm_expr) do { \
        unsigned char norm[TOTAL_PIXELS]; \
        norm_expr; \
        unsigned char scaled[dst_w * dst_h]; \
        upscale_2x_bilinear(norm, W, H, scaled); \
        struct xyt_struct orig_xyt; \
        int count = get_minutiae_and_xyt(scaled, dst_w, dst_h, ppmm_500, 1, NULL, &orig_xyt); \
        /* Perturbed version */ \
        unsigned char perturbed[dst_w * dst_h]; \
        for (int py = 0; py < dst_h; py++) { \
            int sy = py > 1 ? py - 1 : 0; \
            for (int px = 0; px < dst_w; px++) { \
                int sx = px > 1 ? px - 1 : 0; \
                int v = (int)scaled[sy * dst_w + sx] + ((px % 2 == 0) ? 1 : -1); \
                perturbed[py * dst_w + px] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v)); \
            } \
        } \
        struct xyt_struct pert_xyt; \
        int pcount = get_minutiae_and_xyt(perturbed, dst_w, dst_h, ppmm_500, 1, NULL, &pert_xyt); \
        int bz_score = bozorth_match(&pert_xyt, &orig_xyt); \
        printf("%-50s: minutiae=%2d (pert=%2d) bz_score=%2d/12\n", label, count, pcount, bz_score); \
    } while(0)

    // Baseline
    float res_range = res_max - res_min;
    TEST_CONFIG("1. Baseline min-max (Run 14)", {
        for (int i = 0; i < TOTAL_PIXELS; i++) {
            int v = (int)(((residual[i] - res_min) * 255.0f) / res_range);
            norm[i] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
    });

    printf("\n--- Test A: Direct Contrast Gain Expansion: 128 + residual * G ---\n");
    float test_gains[] = {1.0f, 1.25f, 1.5f, 1.75f, 2.0f, 2.5f, 3.0f, 3.5f, 4.0f, 5.0f};
    for (size_t i = 0; i < sizeof(test_gains)/sizeof(test_gains[0]); i++) {
        float G = test_gains[i];
        char desc[64];
        snprintf(desc, sizeof(desc), "Gain G=%.2f (128 + res * %.2f)", G, G);
        TEST_CONFIG(desc, {
            for (int j = 0; j < TOTAL_PIXELS; j++) {
                int v = (int)roundf(128.0f + residual[j] * G);
                norm[j] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
        });
    }

    printf("\n--- Test B: Gain on Baseline min-max: 128 + (base - 128) * G ---\n");
    for (size_t i = 0; i < sizeof(test_gains)/sizeof(test_gains[0]); i++) {
        float G = test_gains[i];
        char desc[64];
        snprintf(desc, sizeof(desc), "Base Gain G=%.2f", G);
        TEST_CONFIG(desc, {
            for (int j = 0; j < TOTAL_PIXELS; j++) {
                float base_val = ((residual[j] - res_min) * 255.0f) / res_range;
                int v = (int)roundf(128.0f + (base_val - 128.0f) * G);
                norm[j] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
        });
    }

    printf("\n--- Test C: Percentile Clipping [p_low, p_high] -> [0, 255] ---\n");
    float pcts[] = {0.005f, 0.01f, 0.02f, 0.03f, 0.04f, 0.05f, 0.08f, 0.10f};
    for (size_t i = 0; i < sizeof(pcts)/sizeof(pcts[0]); i++) {
        float p = pcts[i];
        float lo_val = residual_sorted[(int)(p * TOTAL_PIXELS)];
        float hi_val = residual_sorted[(int)((1.0f - p) * TOTAL_PIXELS)];
        float span = hi_val - lo_val;
        char desc[64];
        snprintf(desc, sizeof(desc), "Percentile [%.1f%%, %.1f%%] (span=%.1f)", p*100, (1.0f-p)*100, span);
        TEST_CONFIG(desc, {
            for (int j = 0; j < TOTAL_PIXELS; j++) {
                int v = (int)roundf(((residual[j] - lo_val) * 255.0f) / span);
                norm[j] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
        });
    }

    printf("\n--- Test D: Symmetric Bound Clipping [-K, +K] -> [0, 255] ---\n");
    float bounds[] = {40.0f, 50.0f, 60.0f, 70.0f, 80.0f, 100.0f, 120.0f, 150.0f, 200.0f};
    for (size_t i = 0; i < sizeof(bounds)/sizeof(bounds[0]); i++) {
        float K = bounds[i];
        char desc[64];
        snprintf(desc, sizeof(desc), "Symmetric [-%.0f, +%.0f] (gain=%.2f)", K, K, 255.0f/(2.0f*K));
        TEST_CONFIG(desc, {
            for (int j = 0; j < TOTAL_PIXELS; j++) {
                int v = (int)roundf(((residual[j] + K) * 255.0f) / (2.0f * K));
                norm[j] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
            }
        });
    }

    printf("\n--- Test E: Resolution PPMM Variation (with Baseline min-max) ---\n");
    double test_ppmms[] = {0.0, 10.0, 500.0/25.4, 600.0/25.4, 750.0/25.4, 1000.0/25.4};
    for (size_t i = 0; i < sizeof(test_ppmms)/sizeof(test_ppmms[0]); i++) {
        double p = test_ppmms[i];
        unsigned char norm[TOTAL_PIXELS];
        for (int j = 0; j < TOTAL_PIXELS; j++) {
            int v = (int)(((residual[j] - res_min) * 255.0f) / res_range);
            norm[j] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
        unsigned char scaled[dst_w * dst_h];
        upscale_2x_bilinear(norm, W, H, scaled);
        struct xyt_struct xyt;
        int count = get_minutiae_and_xyt(scaled, dst_w, dst_h, p, 1, NULL, &xyt);
        printf("ppmm=%.3f (approx %.0f DPI): minutiae=%d\n", p, p * 25.4, count);
    }

    return 0;
}
