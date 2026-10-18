/* Offline extraction of goodix5e0a_normalize_raw_frame from Jet-Soup's
 * patch 0002 applied to 5bfb69d. Function body is unchanged; the static linkage
 * is removed to expose it to ctypes. Scalar typedef and normalization constants
 * are copied from that declared base. No device activation code is included.
 * Source ZIP SHA-256:
 * 693d54803145987315da04bb6f6e35deb07b21243a930c5c2296d24abf25c7a8
 * See docs/jet-soup-replay-2026-10-18.md for scope and reproduction.
 */
#include <glib.h>
#include <math.h>
#include <string.h>
typedef guint16 GoodixTls5xxPix;
#define GOODIX_5E0A_WIDTH 64
#define GOODIX_5E0A_HEIGHT 80
#define GOODIX_5E0A_FRAME_SIZE 5120
#define GOODIX_5E0A_NORMALIZE_MIDPOINT 128.0f
#define GOODIX_5E0A_CONTRAST_GAIN 1.5f
gboolean
goodix5e0a_normalize_raw_frame (const GoodixTls5xxPix *pix, guint8 *out_norm,
                                float *out_min, float *out_max)
{
  if (!pix || !out_norm)
    return FALSE;

  const int W = GOODIX_5E0A_WIDTH, H = GOODIX_5E0A_HEIGHT;
  guint active = 0;

  for (int i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    if (pix[i] > 30)
      active++;

  if (active < 64)
    {
      memset (out_norm, 0, GOODIX_5E0A_FRAME_SIZE);
      return FALSE;
    }

  g_autofree float *residual = g_new (float, GOODIX_5E0A_FRAME_SIZE);
  float residual_min = G_MAXFLOAT, residual_max = -G_MAXFLOAT;

  /* Ridge pitch on this panel is ~10 px dump measurements, so a 3x3 window
   * (the old code) differentiates at pixel scale: it erased the ridges and
   * amplified the per-pixel readout noise instead. Radius 4 = 9x9 keeps the
   * ridge band. */
  const int radius = 4;

  for (int y = 0; y < H; y++)
    {
      for (int x = 0; x < W; x++)
        {
          guint32 local_sum = 0;
          guint local_count = 0;
          for (int yy = MAX (0, y - radius); yy <= MIN (H - 1, y + radius); yy++)
            for (int xx = MAX (0, x - radius); xx <= MIN (W - 1, x + radius); xx++)
              {
                local_sum += pix[yy * W + xx];
                local_count++;
              }

          float value = pix[y * W + x] - (float) local_sum / local_count;
          residual[y * W + x] = value;
          residual_min = MIN (residual_min, value);
          residual_max = MAX (residual_max, value);
        }
    }

  float residual_range = residual_max - residual_min;
  if (out_min)
    *out_min = residual_min;
  if (out_max)
    *out_max = residual_max;

  if (residual_range < 1.0f)
    {
      memset (out_norm, 0, GOODIX_5E0A_FRAME_SIZE);
      return FALSE;
    }

  /* Target contrast instead of range filling. Issue #12 measurements: the engine
   * expects a ridge std around 80; filling the full range gave std ~28 here,
   * which reads as "not enough ridge structure" (pts=0). GOODIX_TARGET_STD
   * overrides the target for A/B tests. */
  double sum = 0.0, sum_sq = 0.0;
  for (guint i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      sum += residual[i];
      sum_sq += (double) residual[i] * residual[i];
    }
  double mean = sum / GOODIX_5E0A_FRAME_SIZE;
  double variance = sum_sq / GOODIX_5E0A_FRAME_SIZE - mean * mean;
  double sd = sqrt (MAX (variance, 0.0));

  const char *target_env = g_getenv ("GOODIX_TARGET_STD");
  double target = (target_env && *target_env) ? g_ascii_strtod (target_env, NULL) : 80.0;
  float gain = (sd > 1e-6) ? (float) (target / sd) : GOODIX_5E0A_CONTRAST_GAIN;

  for (guint i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      int value = (int) roundf (GOODIX_5E0A_NORMALIZE_MIDPOINT + residual[i] * gain);
      out_norm[i] = (guint8) CLAMP (value, 0, 255);
    }

  /* Engine-side polarity is not documented: GOODIX_INVERT=1 flips ridges and
   * valleys without touching the sensor, for a quick A/B on quality scores. */
  if (g_getenv ("GOODIX_INVERT"))
    for (guint i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
      out_norm[i] = 255 - out_norm[i];

  return TRUE;
}
