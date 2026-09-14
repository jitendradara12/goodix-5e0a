#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <glib.h>
#include <lfs.h>
#include <bozorth.h>

#define W 64
#define H 80
#define TOTAL_PIXELS (W * H)
#define BLOCK_BYTES 132
#define ACTIVE_BYTES 96
#define FRAME_BLOCKS 80
#define WIRE_BYTES (FRAME_BLOCKS * BLOCK_BYTES + 4)
#define DST_W 128
#define DST_H 160
#define DST_PIXELS (DST_W * DST_H)

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

static int extract_minutiae_and_xyt(const unsigned char *scaled, MINUTIAE **out_m, struct xyt_struct *xyt, double *avg_rel) {
    unsigned char img[DST_PIXELS];
    // Inverted colors for capacitive ridges (high ADC = black = 255)
    for (int i = 0; i < DST_PIXELS; i++)
        img[i] = 255 - scaled[i];

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0;
    double ppmm = 500.0 / 25.4;

    MINUTIAE *minutiae = NULL;
    int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;

    int ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                           &mw, &mh, &bdata, &bw, &bh, &bd,
                           img, DST_W, DST_H, 8, ppmm, &parms);
    int num = (ret == 0 && minutiae) ? minutiae->num : 0;

    double rel_sum = 0.0;
    if (minutiae && minutiae->num > 0) {
        for (int i = 0; i < minutiae->num; i++) {
            rel_sum += minutiae->list[i]->reliability;
        }
        if (avg_rel) *avg_rel = rel_sum / minutiae->num;
    } else {
        if (avg_rel) *avg_rel = 0.0;
    }

    if (xyt) {
        memset(xyt, 0, sizeof(*xyt));
        minutiae_to_xyt(minutiae, DST_W, DST_H, xyt);
    }

    if (out_m) {
        *out_m = minutiae;
    } else if (minutiae) {
        free_minutiae(minutiae);
    }

    if (qmap) free(qmap);
    if (dmap) free(dmap);
    if (lcmap) free(lcmap);
    if (lfmap) free(lfmap);
    if (hcmap) free(hcmap);
    if (bdata) free(bdata);
    return num;
}

static int run_bozorth(struct xyt_struct *probe, struct xyt_struct *gallery) {
    if (probe->nrows < 10 || gallery->nrows < 10) return 0;
    int probe_len = bozorth_probe_init(probe);
    return bozorth_to_gallery(probe_len, probe, gallery);
}

typedef struct {
    float gain;
    int min_val;
    int max_val;
    int clipped_0;
    int clipped_255;
    float clip_pct;
    float mean_val;
    float std_val;
    float grad_energy;
    int minutiae_count;
    double avg_rel;
    int self_bz;
    int pert_bz;
    int bz_against_g10; // match against G=1.0 template
} GainEvaluation;

static void evaluate_gain(const float *residual, float gain, struct xyt_struct *g10_xyt, GainEvaluation *ev, struct xyt_struct *out_xyt) {
    ev->gain = gain;
    unsigned char norm[TOTAL_PIXELS];
    int c0 = 0, c255 = 0;
    double sum = 0.0, sum_sq = 0.0;
    int min_v = 999999, max_v = -999999;

    for (int i = 0; i < TOTAL_PIXELS; i++) {
        int val = (int)roundf(128.0f + residual[i] * gain);
        if (val < min_v) min_v = val;
        if (val > max_v) max_v = val;
        if (val <= 0) c0++;
        if (val >= 255) c255++;
        int clamped = val < 0 ? 0 : (val > 255 ? 255 : val);
        norm[i] = (unsigned char)clamped;
        sum += clamped;
        sum_sq += clamped * clamped;
    }

    ev->min_val = min_v;
    ev->max_val = max_v;
    ev->clipped_0 = c0;
    ev->clipped_255 = c255;
    ev->clip_pct = (float)(c0 + c255) * 100.0f / TOTAL_PIXELS;
    ev->mean_val = (float)(sum / TOTAL_PIXELS);
    ev->std_val = (float)sqrt((sum_sq / TOTAL_PIXELS) - (ev->mean_val * ev->mean_val));

    // Gradient energy (ridge-valley edge sharpness)
    double grad = 0.0;
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            if (x + 1 < W) grad += abs((int)norm[y * W + x + 1] - (int)norm[y * W + x]);
            if (y + 1 < H) grad += abs((int)norm[(y + 1) * W + x] - (int)norm[y * W + x]);
        }
    }
    ev->grad_energy = (float)(grad / TOTAL_PIXELS);

    // Upscale to 128x160
    unsigned char scaled[DST_PIXELS];
    upscale_2x_bilinear(norm, W, H, scaled);

    // Minutiae extraction
    struct xyt_struct xyt;
    ev->minutiae_count = extract_minutiae_and_xyt(scaled, NULL, &xyt, &ev->avg_rel);
    if (out_xyt) *out_xyt = xyt;

    // Self-match
    ev->self_bz = run_bozorth(&xyt, &xyt);

    // Perturbed match (shift 1px dx, 1px dy + slight alternating noise)
    unsigned char pert_scaled[DST_PIXELS];
    for (int py = 0; py < DST_H; py++) {
        int sy = py > 1 ? py - 1 : 0;
        for (int px = 0; px < DST_W; px++) {
            int sx = px > 1 ? px - 1 : 0;
            int v = (int)scaled[sy * DST_W + sx] + ((px % 2 == 0) ? 1 : -1);
            pert_scaled[py * DST_W + px] = (unsigned char)(v < 0 ? 0 : (v > 255 ? 255 : v));
        }
    }
    struct xyt_struct pert_xyt;
    extract_minutiae_and_xyt(pert_scaled, NULL, &pert_xyt, NULL);
    ev->pert_bz = run_bozorth(&pert_xyt, &xyt);

    // Cross-gain match against G=1.0 template
    if (g10_xyt) {
        ev->bz_against_g10 = run_bozorth(&xyt, g10_xyt);
    } else {
        ev->bz_against_g10 = 0;
    }
}

int main(int argc, char **argv) {
    const char *raw_path = (argc > 1) ? argv[1] : "/dev/shm/live_frame.raw";
    printf("========================================================================================\n");
    printf("ADVERSARIAL EMPIRICAL CHALLENGE: CONTRAST GAIN G=1.8f VS DYNAMIC RANGE & BIOMETRICS\n");
    printf("Target Frame: %s\n", raw_path);
    printf("========================================================================================\n\n");

    FILE *f = fopen(raw_path, "rb");
    if (!f) {
        fprintf(stderr, "ERROR: Cannot open %s\n", raw_path);
        return 1;
    }
    unsigned short pix[TOTAL_PIXELS];
    if (strstr(raw_path, ".pgm")) {
        char line[128];
        while (fgets(line, sizeof(line), f)) {
            if (line[0] != '#' && strstr(line, "4095")) break;
        }
        int n = 0;
        int val;
        while (n < TOTAL_PIXELS && fscanf(f, "%d", &val) == 1) {
            pix[n++] = (unsigned short)val;
        }
        fclose(f);
        if (n < TOTAL_PIXELS) {
            fprintf(stderr, "ERROR: Read only %d pixels from %s (expected %d)\n", n, raw_path, TOTAL_PIXELS);
            return 1;
        }
    } else {
        fseek(f, 0, SEEK_END);
        long len = ftell(f);
        fseek(f, 0, SEEK_SET);
        unsigned char *raw_bytes = malloc(len);
        if (fread(raw_bytes, 1, len, f) != (size_t)len) {
            fprintf(stderr, "ERROR: Failed to read %s\n", raw_path);
            fclose(f);
            return 1;
        }
        fclose(f);
        decode_frame(pix, raw_bytes, len);
        free(raw_bytes);
    }

    int min_raw = 65535, max_raw = 0;
    double sum_raw = 0.0;
    for (int i = 0; i < TOTAL_PIXELS; i++) {
        if (pix[i] < min_raw) min_raw = pix[i];
        if (pix[i] > max_raw) max_raw = pix[i];
        sum_raw += pix[i];
    }
    printf("1. RAW FRAME CHARACTERISTICS:\n");
    printf("   Dimensions: %dx%d (%d pixels)\n", W, H, TOTAL_PIXELS);
    printf("   Raw ADC: min=%d max=%d range=%d mean=%.1f\n\n", min_raw, max_raw, max_raw - min_raw, sum_raw / TOTAL_PIXELS);

    // Compute 3x3 local mean residual
    float residual[TOTAL_PIXELS];
    float res_min = 1e9f, res_max = -1e9f;
    double res_sum = 0.0, res_sum_sq = 0.0;

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
            if (val < res_min) res_min = val;
            if (val > res_max) res_max = val;
            res_sum += val;
            res_sum_sq += val * val;
        }
    }
    float res_mean = (float)(res_sum / TOTAL_PIXELS);
    float res_std = (float)sqrt((res_sum_sq / TOTAL_PIXELS) - (res_mean * res_mean));
    printf("2. 3x3 LOCAL MEAN RESIDUAL METRICS:\n");
    printf("   min=%.2f max=%.2f range=%.2f mean=%.2f stddev=%.2f\n\n",
           res_min, res_max, res_max - res_min, res_mean, res_std);

    // First obtain G=1.0 template for cross-gain comparison
    struct xyt_struct g10_xyt;
    GainEvaluation ev10;
    evaluate_gain(residual, 1.0f, NULL, &ev10, &g10_xyt);

    printf("3. CONTRAST GAIN SWEEP ON REAL FRAME (/dev/shm/live_frame.raw):\n");
    printf("%-6s | %-12s | %-6s %-6s (%-5s) | %-6s %-6s | %-6s | %-5s %-6s | %-5s %-5s %-7s\n",
           "Gain", "Pre-clamp", "Clip0", "Clip255", "Total%", "Mean", "StdDev", "GradE", "Minut", "AvgRel", "Self", "Pert", "vs G1.0");
    printf("--------------------------------------------------------------------------------------------------------------\n");

    float gains[] = {0.50f, 0.80f, 1.00f, 1.20f, 1.40f, 1.60f, 1.80f, 2.00f, 2.20f, 2.50f, 3.00f, 4.00f};
    int n_gains = sizeof(gains) / sizeof(gains[0]);

    for (int i = 0; i < n_gains; i++) {
        GainEvaluation ev;
        evaluate_gain(residual, gains[i], &g10_xyt, &ev, NULL);
        char pre_clamp_str[24];
        snprintf(pre_clamp_str, sizeof(pre_clamp_str), "[%d, %d]", ev.min_val, ev.max_val);
        printf("%-6.2f | %-12s | %-6d %-6d (%4.1f%%) | %-6.1f %-6.1f | %-6.1f | %-5d %-6.3f | %-5d %-5d %-7d\n",
               ev.gain, pre_clamp_str, ev.clipped_0, ev.clipped_255, ev.clip_pct,
               ev.mean_val, ev.std_val, ev.grad_energy, ev.minutiae_count, ev.avg_rel,
               ev.self_bz, ev.pert_bz, ev.bz_against_g10);
    }
    printf("--------------------------------------------------------------------------------------------------------------\n\n");

    // 4. ADVERSARIAL PRESSURE SIMULATION (Varying Touch Force):
    // Light touch reduces ridge-valley amplitude (residuals scaled down).
    // Heavy touch increases ridge-valley amplitude (residuals scaled up).
    printf("4. ADVERSARIAL CONTACT PRESSURE STRESS TEST:\n");
    printf("Simulating variation in touch force: Faint (0.4x), Light (0.7x), Normal (1.0x), Firm (1.3x), Heavy (1.6x)\n\n");

    float pressures[] = {0.40f, 0.60f, 0.75f, 1.00f, 1.30f, 1.60f, 2.00f};
    const char *p_labels[] = {"Very Faint (0.4x)", "Faint (0.6x)", "Light (0.75x)", "Normal (1.0x)", "Firm (1.3x)", "Heavy (1.6x)", "Very Heavy (2.0x)"};
    int n_pressures = sizeof(pressures) / sizeof(pressures[0]);

    printf("%-20s | %-18s | %-18s | %-18s\n", "Contact Pressure", "G=1.0f (Old)", "G=1.8f (Production)", "G=2.5f (Alternative)");
    printf("%-20s | %-6s %-5s %-5s | %-6s %-5s %-5s | %-6s %-5s %-5s\n", "", "Clip%", "Minut", "Pert", "Clip%", "Minut", "Pert", "Clip%", "Minut", "Pert");
    printf("-------------------------------------------------------------------------------------------------\n");

    for (int p = 0; p < n_pressures; p++) {
        float p_scale = pressures[p];
        float sim_residual[TOTAL_PIXELS];
        for (int i = 0; i < TOTAL_PIXELS; i++)
            sim_residual[i] = residual[i] * p_scale;

        GainEvaluation ev_10, ev_18, ev_25;
        evaluate_gain(sim_residual, 1.0f, NULL, &ev_10, NULL);
        evaluate_gain(sim_residual, 1.8f, NULL, &ev_18, NULL);
        evaluate_gain(sim_residual, 2.5f, NULL, &ev_25, NULL);

        printf("%-20s | %4.1f%%  %-5d %-5d | %4.1f%%  %-5d %-5d | %4.1f%%  %-5d %-5d\n",
               p_labels[p],
               ev_10.clip_pct, ev_10.minutiae_count, ev_10.pert_bz,
               ev_18.clip_pct, ev_18.minutiae_count, ev_18.pert_bz,
               ev_25.clip_pct, ev_25.minutiae_count, ev_25.pert_bz);
    }
    printf("-------------------------------------------------------------------------------------------------\n\n");

    // 5. CROSS-CONDITION RECOGNITION:
    // Gallery enrolled at normal touch (G=1.8f), verified across different pressure touches
    printf("5. CROSS-PRESSURE VERIFICATION (Enroll Normal at G=1.8f, Verify at Varied Pressures):\n");
    struct xyt_struct gallery_norm_18;
    GainEvaluation dummy;
    evaluate_gain(residual, 1.8f, NULL, &dummy, &gallery_norm_18);

    for (int p = 0; p < n_pressures; p++) {
        float p_scale = pressures[p];
        float sim_residual[TOTAL_PIXELS];
        for (int i = 0; i < TOTAL_PIXELS; i++)
            sim_residual[i] = residual[i] * p_scale;

        struct xyt_struct probe_18;
        GainEvaluation ev_probe;
        evaluate_gain(sim_residual, 1.8f, NULL, &ev_probe, &probe_18);
        int bz_cross = run_bozorth(&probe_18, &gallery_norm_18);
        const char *verdict = (ev_probe.minutiae_count < 10) ? "ABORT (<10)" :
                              (ev_probe.minutiae_count < 15) ? "WARN (<15)" :
                              (bz_cross >= 12) ? "PASS (MATCH)" : "FAIL (NO MATCH)";
        printf("   Verify %-18s: minutiae=%2d, match_score=%2d/12 -> %s\n",
               p_labels[p], ev_probe.minutiae_count, bz_cross, verdict);
    }
    printf("\n");

    // 6. ADVERSARIAL EXTREME DC GRADIENT STRESS TEST:
    // Test whether residual extraction + G=1.8f remains stable under huge DC tilt (e.g. wet or uneven thumb)
    printf("6. ADVERSARIAL LARGE DC TILT GRADIENT STRESS TEST:\n");
    float tilts[] = {0.0f, 500.0f, 1500.0f, 3000.0f};
    for (int t = 0; t < 4; t++) {
        float tilt_max = tilts[t];
        unsigned short tilted_pix[TOTAL_PIXELS];
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float tilt = tilt_max * ((float)x / W + (float)y / H) * 0.5f;
                int v = (int)roundf(pix[y * W + x] + tilt);
                tilted_pix[y * W + x] = (unsigned short)(v < 0 ? 0 : (v > 4095 ? 4095 : v));
            }
        }
        // Re-compute 3x3 local mean residual on tilted image
        float tilted_residual[TOTAL_PIXELS];
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                unsigned int local_sum = 0;
                unsigned int local_count = 0;
                for (int yy = (y > 0 ? y - 1 : 0); yy <= (y + 1 < H ? y + 1 : H - 1); yy++) {
                    for (int xx = (x > 0 ? x - 1 : 0); xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
                        local_sum += tilted_pix[yy * W + xx];
                        local_count++;
                    }
                }
                tilted_residual[y * W + x] = tilted_pix[y * W + x] - (float)local_sum / local_count;
            }
        }
        GainEvaluation ev_tilt;
        evaluate_gain(tilted_residual, 1.8f, NULL, &ev_tilt, NULL);
        printf("   DC Tilt +%-4.0f ADC: clip=%4.1f%% minutiae=%2d avg_rel=%.3f self_bz=%d pert_bz=%d\n",
               tilt_max, ev_tilt.clip_pct, ev_tilt.minutiae_count, ev_tilt.avg_rel, ev_tilt.self_bz, ev_tilt.pert_bz);
    }
    printf("\n");

    return 0;
}
