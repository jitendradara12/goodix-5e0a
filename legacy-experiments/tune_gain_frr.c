// legacy-experiments/tune_gain_frr.c — Ticket 101: FRR contrast-lane sweep.
//
// Reproduces the gain table in
// .scratch/goodix-5e0a/issues/101-ready-for-hardware-verify-frr-contrast-lane-per-touch-burst.md
// through the REAL GoodixEngineAdapter.dll (in-process PE loader), using the
// driver's exact normalization: 3x3 local-mean residual, midpoint 128, gain G.
//
// Battery per gain G in {1.0, 1.5, 2.0, 2.5, 3.0}:
//   - enroll 5 synthetic masters, 12 distinct jittered touches each
//     (the post-fix driver flow: one fresh burst per touch);
//   - 20 genuine "sloppy touch" probes vs master 0 (contrast attenuation
//     0.9..0.3, +/-2/+/-4 px shifts, +/-4/+/-6 deg rotations, 3x3 blur,
//     +/-15 noise, 1.3x/1.6x sharpening);
//   - 18 impostor/garbage probes (4 different fingers x {exact, soft, blur,
//     sharp} + flat128 + noise30);
//   - 4-finger identify gallery: genuine probes must hit their own index,
//     impostors must not match.
// Match rule is the driver's own: engine score > 0.
//
// Setup (from repo root):
//   for s in 67 68 101 102 103; do
//     python3 legacy-experiments/gen_dense_live.py --seed $s \
//       --out legacy-experiments/dense_$s.pgm
//   done
// Build (system glib):
//   gcc -O2 -I libfprint-driver -o /tmp/tune_gain_frr \
//     legacy-experiments/tune_gain_frr.c libfprint-driver/goodix_milan.c -lm
// Run:
//   GOODIX_ENGINE_DLL_PATH=/path/to/GoodixEngineAdapter.dll /tmp/tune_gain_frr [-v]
//
// Expected: gain 1.0 genuine=14/20 (contrast cliff at soft0.6);
// gain >= 1.5 genuine=18/20 (only the two blur probes fail — information
// destroyed, no front-end gain recovers them); impostor_accepts=0 and
// identify_fa=0 at EVERY gain.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

#include "goodix_milan.h"

#define W 64
#define H 80
#define N (W * H)
#define TOUCHES 12
#define NGEN 5

static float g_gain = 1.0f;

static int
read_p2_pgm (const char *path, uint16_t *out)
{
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
  return (w == W && h == H) ? 0 : -4;
}

/* Driver's goodix5e0a_normalize_raw_frame at gain g_gain. */
static void
normalize_driver (const uint16_t *pix, uint8_t *out)
{
  float res[N];
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
    int v = (int) roundf (128.0f + res[i] * g_gain);
    out[i] = (uint8_t) (v < 0 ? 0 : (v > 255 ? 255 : v));
  }
}

static void
shift (const uint8_t *src, uint8_t *dst, int dx, int dy)
{
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      int sx = x - dx, sy = y - dy;
      if (sx < 0) sx = 0; if (sx >= W) sx = W - 1;
      if (sy < 0) sy = 0; if (sy >= H) sy = H - 1;
      dst[y * W + x] = src[sy * W + sx];
    }
}

static void
rotate (const uint8_t *src, uint8_t *dst, double deg)
{
  double a = deg * M_PI / 180.0;
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      double cx = x - W / 2.0, cy = y - H / 2.0;
      int sx = (int) (cx * cos (a) - cy * sin (a) + W / 2.0 + 0.5);
      int sy = (int) (cx * sin (a) + cy * cos (a) + H / 2.0 + 0.5);
      if (sx < 0) sx = 0; if (sx >= W) sx = W - 1;
      if (sy < 0) sy = 0; if (sy >= H) sy = H - 1;
      dst[y * W + x] = src[sy * W + sx];
    }
}

/* Blend toward local mean: keep fraction of residual contrast (soft press). */
static void
softer (const uint8_t *src, uint8_t *dst, float keep)
{
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      uint32_t s = 0, c = 0;
      for (int yy = y > 0 ? y - 1 : 0; yy <= (y + 1 < H ? y + 1 : H - 1); yy++)
        for (int xx = x > 0 ? x - 1 : 0; xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
          s += src[yy * W + xx]; c++;
        }
      float mean = (float) s / c;
      float v = mean + (src[y * W + x] - mean) * keep;
      dst[y * W + x] = (uint8_t) (v < 0 ? 0 : (v > 255 ? 255 : v));
    }
}

/* Multiply residual contrast (heavy press / dry skin sharpening). */
static void
sharper (const uint8_t *src, uint8_t *dst, float mul)
{
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      uint32_t s = 0, c = 0;
      for (int yy = y > 0 ? y - 1 : 0; yy <= (y + 1 < H ? y + 1 : H - 1); yy++)
        for (int xx = x > 0 ? x - 1 : 0; xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
          s += src[yy * W + xx]; c++;
        }
      float mean = (float) s / c;
      float v = mean + (src[y * W + x] - mean) * mul;
      dst[y * W + x] = (uint8_t) (v < 0 ? 0 : (v > 255 ? 255 : v));
    }
}

static void
blur3 (const uint8_t *src, uint8_t *dst)
{
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      uint32_t s = 0, c = 0;
      for (int yy = y > 0 ? y - 1 : 0; yy <= (y + 1 < H ? y + 1 : H - 1); yy++)
        for (int xx = x > 0 ? x - 1 : 0; xx <= (x + 1 < W ? x + 1 : W - 1); xx++) {
          s += src[yy * W + xx]; c++;
        }
      dst[y * W + x] = (uint8_t) (s / c);
    }
}

static void
addnoise (const uint8_t *src, uint8_t *dst, int amp)
{
  for (int i = 0; i < N; i++) {
    int v = src[i] + (rand () % (2 * amp + 1)) - amp;
    dst[i] = (uint8_t) (v < 0 ? 0 : (v > 255 ? 255 : v));
  }
}

static uint16_t raws[NGEN][N];
static uint8_t base[NGEN][N], t0[N], t1[N], t2[N];

static int
score_of (const uint8_t *probe, const uint8_t *blob, size_t len)
{
  int s = -9;
  goodix_milan_verify_image (probe, W, H, blob, len, &s);
  return s < 0 ? 0 : s;
}

/* Build the genuine battery for finger 0. Returns #accepted. */
static int
genuine_battery (const uint8_t *blob, size_t len, int verbose)
{
  static const char *names[] = {
    "exact", "soft0.9", "soft0.8", "soft0.7", "soft0.6", "soft0.5",
    "soft0.4", "soft0.3", "s+2soft0.7", "s-2soft0.7", "s+4soft0.7",
    "rot4soft0.8", "rot-4soft0.8", "rot6", "rot-6", "blur", "blursoft0.9",
    "noisesoft0.7", "sharp1.3", "sharp1.6",
  };
  static uint8_t probes[20][N];
  int n = (int) (sizeof names / sizeof names[0]);

  memcpy (probes[0], base[0], N);
  softer (base[0], probes[1], 0.9f);
  softer (base[0], probes[2], 0.8f);
  softer (base[0], probes[3], 0.7f);
  softer (base[0], probes[4], 0.6f);
  softer (base[0], probes[5], 0.5f);
  softer (base[0], probes[6], 0.4f);
  softer (base[0], probes[7], 0.3f);
  shift (base[0], t1, 2, 0); softer (t1, probes[8], 0.7f);
  shift (base[0], t1, -2, 0); softer (t1, probes[9], 0.7f);
  shift (base[0], t1, 4, 0); softer (t1, probes[10], 0.7f);
  rotate (base[0], t1, 4.0); softer (t1, probes[11], 0.8f);
  rotate (base[0], t1, -4.0); softer (t1, probes[12], 0.8f);
  rotate (base[0], probes[13], 6.0);
  rotate (base[0], probes[14], -6.0);
  blur3 (base[0], probes[15]);
  blur3 (base[0], t1); softer (t1, probes[16], 0.9f);
  softer (base[0], t1, 0.7f); addnoise (t1, probes[17], 15);
  sharper (base[0], probes[18], 1.3f);
  sharper (base[0], probes[19], 1.6f);

  int acc = 0;
  for (int i = 0; i < n; i++) {
    int s = score_of (probes[i], blob, len);
    acc += s > 0;
    if (verbose) printf ("  GEN %-13s score=%3d %s\n", names[i], s,
                         s > 0 ? "" : "<<< REJECTED");
  }
  return acc;
}

/* Impostor battery: fingers 1..4 vs finger 0's template + garbage frames.
 * Returns #false-accepts; also tracks the max impostor score. */
static int
impostor_battery (const uint8_t *blob, size_t len, int *maxscore, int verbose)
{
  int accepts = 0;
  *maxscore = 0;
  for (int f = 1; f < NGEN; f++) {
    static const char *names[] = { "exact", "soft0.8", "blur", "sharp1.3" };
    for (unsigned k = 0; k < sizeof names / sizeof names[0]; k++) {
      memcpy (t1, base[f], N);
      if (k == 1) { softer (t1, t2, 0.8f); memcpy (t1, t2, N); }
      if (k == 2) { blur3 (t1, t2); memcpy (t1, t2, N); }
      if (k == 3) { sharper (t1, t2, 1.3f); memcpy (t1, t2, N); }
      int s = score_of (t1, blob, len);
      if (s > *maxscore) *maxscore = s;
      if (s > 0) accepts++;
      if (verbose) printf ("  IMP f%d %-9s score=%3d %s\n", f, names[k], s,
                           s > 0 ? "<<< FALSE ACCEPT" : "");
    }
  }
  /* Garbage / non-finger frames must never match. */
  for (int i = 0; i < N; i++) t1[i] = 128;
  { int s = score_of (t1, blob, len);
    if (s > *maxscore) *maxscore = s;
    if (s > 0) accepts++;
    if (verbose) printf ("  IMP flat128      score=%3d %s\n", s, s > 0 ? "<<< FALSE ACCEPT" : ""); }
  for (int i = 0; i < N; i++) t1[i] = (uint8_t) (128 + (rand () % 61) - 30);
  { int s = score_of (t1, blob, len);
    if (s > *maxscore) *maxscore = s;
    if (s > 0) accepts++;
    if (verbose) printf ("  IMP noise30      score=%3d %s\n", s, s > 0 ? "<<< FALSE ACCEPT" : ""); }
  return accepts;
}

int
main (int argc, char **argv)
{
  float gains[] = { 1.0f, 1.5f, 2.0f, 2.5f, 3.0f };
  int ng = (int) (sizeof gains / sizeof gains[0]);
  int verbose = argc > 1 && strcmp (argv[1], "-v") == 0;
  const char *dir = ".";

  if (!goodix_milan_init (NULL)) {
    fprintf (stderr, "[!] engine init failed (GOODIX_ENGINE_DLL_PATH set?)\n");
    return 2;
  }
  printf ("VERSION %s battery: 20 genuine, 18 impostor+garbage, 4-finger gallery\n\n",
          goodix_milan_get_version ());
  (void) dir;

  char paths[NGEN][256];
  static const int seeds[NGEN] = { 67, 68, 101, 102, 103 };
  for (int f = 0; f < NGEN; f++)
    snprintf (paths[f], sizeof paths[f], "dense_%d.pgm", seeds[f]);

  for (int g = 0; g < ng; g++) {
    g_gain = gains[g];
    for (int f = 0; f < NGEN; f++)
      if (read_p2_pgm (paths[f], raws[f]) != 0) {
        fprintf (stderr, "[!] pgm load failed: %s (run gen_dense_live.py --seed %d)\n",
                 paths[f], seeds[f]);
        return 2;
      }
    for (int f = 0; f < NGEN; f++)
      normalize_driver (raws[f], base[f]);

    /* Enroll NGEN masters, 12 distinct touches each (post-fix driver flow). */
    uint8_t *blobs[NGEN] = {0};
    size_t lens[NGEN] = {0};
    int enroll_ok = 1;
    srand (20260927);
    for (int f = 0; f < NGEN && enroll_ok; f++) {
      void *ctx = goodix_milan_enroll_start (NULL);
      if (!ctx) { enroll_ok = 0; break; }
      uint8_t frame[N];
      int rc = 0;
      for (int t = 0; t < TOUCHES && rc == 0; t++) {
        shift (base[f], frame, (t % 5) - 2, ((t * 2) % 5) - 2);
        int ec = 0, pp = 0;
        rc = goodix_milan_enroll_add_image (ctx, frame, W, H, &ec, &pp);
      }
      if (rc != 0) { goodix_milan_enroll_finish (ctx); enroll_ok = 0; break; }
      rc = goodix_milan_enroll_commit (ctx, &blobs[f], &lens[f]);
      goodix_milan_enroll_finish (ctx);
      if (rc != 0) enroll_ok = 0;
    }
    if (!enroll_ok) {
      printf ("gain %.1f: ENROLLMENT FAILED\n", g_gain);
      continue;
    }

    printf ("=== gain %.1f ===\n", g_gain);
    int gen = genuine_battery (blobs[0], lens[0], verbose);
    int maxs = 0;
    int imp = impostor_battery (blobs[0], lens[0], &maxs, verbose);

    /* 4-finger gallery identify: genuine probes hit own index, impostors
     * (finger 4 vs gallery of fingers 0-3) and garbage must not match. */
    const uint8_t *gal4[4] = { blobs[0], blobs[1], blobs[2], blobs[3] };
    size_t glen4[4] = { lens[0], lens[1], lens[2], lens[3] };
    int id_ok = 0, id_tot = 0, id_fa = 0;
    for (int p = 0; p < 6; p++) {
      shift (base[0], t1, (p % 3) - 1, (p / 3) - 1);
      softer (t1, t2, 0.7f);
      int idx = -9, s = -9;
      goodix_milan_identify_image (t2, W, H, gal4, glen4, 4, &idx, &s);
      id_tot++;
      id_ok += (s > 0 && idx == 0);
    }
    {
      int idx = -9, s = -9;
      goodix_milan_identify_image (base[4], W, H, gal4, glen4, 4, &idx, &s);
      id_fa += s > 0;
      softer (base[4], t1, 0.8f);
      idx = -9; s = -9;
      goodix_milan_identify_image (t1, W, H, gal4, glen4, 4, &idx, &s);
      id_fa += s > 0;
    }

    printf ("SUMMARY gain=%.1f genuine=%d/20 impostor_accepts=%d max_imp=%d "
            "identify_genuine=%d/6 identify_fa=%d\n\n",
            g_gain, gen, imp, maxs, id_ok, id_fa);

    for (int f = 0; f < NGEN; f++) free (blobs[f]);
  }
  return 0;
}
