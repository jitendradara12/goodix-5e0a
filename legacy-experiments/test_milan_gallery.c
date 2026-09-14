// experiments/test_milan_gallery.c — Ticket 77 offline multi-finger gallery probe.
//
// Enrolls TWO distinct masters (Finger A: live_dense_pad, Finger B:
// live_dense_pad_seed68 — the shootout's documented different-finger pair)
// and probes a 2-template gallery with ONE identifyImage call per probe
// through the DRIVER's gallery API (goodix_milan_identify_image, count=N).
//
// Pass = genuine A -> idx 0, genuine B -> idx 1, impostor/blank/noise ->
// no-match (zero false accepts). Exit 0 only if the full matrix is green.
//
// NOTE on gain: impressions use the ticket-72 local-contrast path at gain
// 1.5 (the proven 100-vs-0 separation regime). The driver feeds gain 1.0
// buffers (ticket 78/79 lane); gallery isolation is independent of that.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

#include "goodix_milan.h"

#define W 64
#define H 80
#define N (W * H)

static int read_p2_pgm (const char *path, uint16_t *out, int *ow, int *oh) {
    FILE *f = fopen (path, "r");
    if (!f) return -1;
    char line[256];
    if (!fgets (line, sizeof line, f) || line[0] != 'P' || line[1] != '2') {
        fclose (f); return -2;
    }
    int w = 0, h = 0, maxval = 0;
    while (fgets (line, sizeof line, f)) {
        if (line[0] == '#') continue;
        if (sscanf (line, "%d %d", &w, &h) == 2) break;
    }
    while (fgets (line, sizeof line, f)) {
        if (line[0] == '#') continue;
        if (sscanf (line, "%d", &maxval) == 1) break;
    }
    for (int i = 0; i < w * h; i++) {
        int v = 0;
        if (fscanf (f, "%d", &v) != 1) { fclose (f); return -3; }
        out[i] = (uint16_t) v;
    }
    fclose (f);
    *ow = w; *oh = h;
    return 0;
}

static void local_contrast_15 (const uint16_t *pix, uint8_t *out) {
    float res[N], mn = 1e9f, mx = -1e9f;
    (void) mn; (void) mx;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            uint32_t s = 0, c = 0;
            for (int yy = y > 0 ? y - 1 : 0; yy <= (y + 1 < H ? y + 1 : H - 1); yy++)
                for (int xx = x > 0 ? x - 1 : 0; xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
                    s += pix[yy * W + xx]; c++;
                }
            res[y * W + x] = (float) pix[y * W + x] - (float) s / c;
        }
    for (int i = 0; i < N; i++) {
        int v = (int) roundf (128.0f + res[i] * 1.5f);
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        out[i] = (uint8_t) v;
    }
}

static void perturb (const uint8_t *base, uint8_t *out, int dx, int dy, int noise) {
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int sx = x + dx, sy = y + dy;
            if (sx < 0) sx = 0; if (sx >= W) sx = W - 1;
            if (sy < 0) sy = 0; if (sy >= H) sy = H - 1;
            int v = base[sy * W + sx];
            if (noise) v += (rand () % 7) - 3;
            if (v < 0) v = 0;
            if (v > 255) v = 255;
            out[y * W + x] = (uint8_t) v;
        }
}

static int enroll_master (const uint8_t *base, uint8_t **blob, size_t *len, const char *tag) {
    void *ctx = goodix_milan_enroll_start (NULL);
    if (!ctx) { fprintf (stderr, "[!] %s: enroll_start NULL\n", tag); return -1; }
    uint8_t frame[N];
    for (int s = 0; s < 8; s++) {
        perturb (base, frame, (s % 3) - 1, (s / 3) - 1, s & 1);
        int ec = 0, pp = 0;
        int r = goodix_milan_enroll_add_image (ctx, frame, W, H, &ec, &pp);
        fprintf (stderr, "  [%s touch %d/8] add_res=%d stitched=%d progress=%d%%\n",
                 tag, s + 1, r, ec, pp);
        if (r != 0) { goodix_milan_enroll_finish (ctx); return -2; }
    }
    int r = goodix_milan_enroll_commit (ctx, blob, len);
    goodix_milan_enroll_finish (ctx);
    if (r != 0) { fprintf (stderr, "[!] %s: commit err=%d\n", tag, r); return -3; }
    fprintf (stderr, "  [%s] master packed: %zu bytes\n", tag, *len);
    return 0;
}

int main (void) {
    fprintf (stderr, "=== Ticket 77: Milan 2-finger gallery offline probe ===\n");
    if (!goodix_milan_init (NULL)) {
        fprintf (stderr, "[!] engine init failed\n");
        return 2;
    }
    fprintf (stderr, "[milan] %s\n", goodix_milan_get_version ());

    static uint16_t rawA[N], rawB[N], rawI[N], rawC[N];
    int w, h;
    if (read_p2_pgm ("legacy-experiments/live_dense_pad.pgm", rawA, &w, &h)
        || read_p2_pgm ("legacy-experiments/live_dense_pad_seed68.pgm", rawB, &w, &h)
        || read_p2_pgm ("legacy-experiments/fingerprint.pgm", rawI, &w, &h)
        || read_p2_pgm ("legacy-experiments/clear-0.pgm", rawC, &w, &h)) {
        fprintf (stderr, "[!] pgm load failed\n");
        return 2;
    }
    static uint8_t baseA[N], baseB[N], baseI[N];
    local_contrast_15 (rawA, baseA);
    local_contrast_15 (rawB, baseB);
    local_contrast_15 (rawI, baseI);
    static uint8_t blank[N];
    memset (blank, 0, sizeof blank);
    static uint8_t noise[N];
    srand (12345);
    for (int i = 0; i < N; i++) noise[i] = (uint8_t) (rand () % 256);
    (void) rawC;

    uint8_t *blobA = NULL, *blobB = NULL;
    size_t lenA = 0, lenB = 0;
    fprintf (stderr, "-- enroll finger A (live_dense_pad) --\n");
    if (enroll_master (baseA, &blobA, &lenA, "A")) return 2;
    fprintf (stderr, "-- enroll finger B (seed68) --\n");
    if (enroll_master (baseB, &blobB, &lenB, "B")) return 2;

    const uint8_t *gallery[2] = { blobA, blobB };
    const size_t lens[2] = { lenA, lenB };

    struct { const char *name; uint8_t *img; int want_idx; } cases[] = {
        { "Genuine A (exact base)", baseA, 0 },
        { "Genuine B (exact base)", baseB, 1 },
        { "Impostor fingerprint.pgm", baseI, -1 },
        { "Blank (zeros)", blank, -1 },
        { "White noise", noise, -1 },
    };
    // Genuine perturbed variants (never enrolled verbatim)
    static uint8_t varA[N], varB[N];
    perturb (baseA, varA, 1, 0, 1);
    perturb (baseB, varB, 0, 1, 1);

    int fails = 0, n_gen = 0, gen_ok = 0, n_imp = 0, imp_ok = 0;
    fprintf (stderr, "%-32s | result   | idx | score | status\n", "Probe");
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        int idx = -9, score = -9;
        int m = goodix_milan_identify_image (cases[i].img, W, H, gallery, lens, 2, &idx, &score);
        int want_m = cases[i].want_idx >= 0;
        int ok = (m == want_m) && (idx == cases[i].want_idx || !want_m);
        if (want_m) { n_gen++; gen_ok += ok; } else { n_imp++; imp_ok += ok; }
        fails += !ok;
        fprintf (stderr, "%-32s | %-8s | %3d | %5d | %s\n", cases[i].name,
                 m ? "MATCH" : "NO_MATCH", idx, score, ok ? "PASS" : "FAIL");
    }
    struct { const char *name; uint8_t *img; int want_idx; } vars[] = {
        { "Genuine A (shift+noise)", varA, 0 },
        { "Genuine B (shift+noise)", varB, 1 },
    };
    for (unsigned i = 0; i < sizeof vars / sizeof vars[0]; i++) {
        int idx = -9, score = -9;
        int m = goodix_milan_identify_image (vars[i].img, W, H, gallery, lens, 2, &idx, &score);
        int ok = (m == 1) && (idx == vars[i].want_idx);
        n_gen++; gen_ok += ok; fails += !ok;
        fprintf (stderr, "%-32s | %-8s | %3d | %5d | %s\n", vars[i].name,
                 m ? "MATCH" : "NO_MATCH", idx, score, ok ? "PASS" : "FAIL");
    }

    // Regression: single-template verify path unchanged
    {
        int s = -9;
        int mAA = goodix_milan_verify_image (baseA, W, H, blobA, lenA, &s);
        int okAA = (mAA == 1 && s > 0);
        fails += !okAA;
        fprintf (stderr, "%-32s | %-8s | %5d | %s\n", "verify A-vs-A (regression)",
                 mAA ? "MATCH" : "NO_MATCH", s, okAA ? "PASS" : "FAIL");
        s = -9;
        int mAB = goodix_milan_verify_image (baseA, W, H, blobB, lenB, &s);
        int okAB = (mAB == 0);
        fails += !okAB;
        fprintf (stderr, "%-32s | %-8s | %5d | %s\n", "verify A-vs-B (regression)",
                 mAB ? "MATCH" : "NO_MATCH", s, okAB ? "PASS" : "FAIL");
    }

    // Fail-closed: corrupt gallery entry must not false-accept
    {
        uint8_t bad[64];
        memset (bad, 0xAB, sizeof bad);
        const uint8_t *g2[2] = { blobA, bad };
        const size_t l2[2] = { lenA, sizeof bad };
        int idx = -9, score = -9;
        int m = goodix_milan_identify_image (baseA, W, H, g2, l2, 2, &idx, &score);
        int ok = (m == 0 && idx == -1);
        fails += !ok;
        fprintf (stderr, "%-32s | %-8s | %3d | %s\n", "corrupt-blob gallery (fail-closed)",
                 m ? "MATCH" : "NO_MATCH", idx, ok ? "PASS" : "FAIL");
    }

    fprintf (stderr, "[SUMMARY] genuine %d/%d, impostor-reject %d/%d, FAR=%.1f%%\n",
             gen_ok, n_gen, imp_ok, n_imp, n_imp ? 100.0 * (n_imp - imp_ok) / n_imp : 0.0);
    free (blobA);
    free (blobB);
    if (fails == 0) {
        fprintf (stderr, "[VERDICT: CONFIRMED] 2-finger gallery isolates with zero false accepts.\n");
        return 0;
    }
    fprintf (stderr, "[VERDICT: FALSIFIED] %d case(s) failed.\n", fails);
    return 1;
}
