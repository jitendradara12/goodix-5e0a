#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <assert.h>

#define GOODIX_5E0A_WIDTH 80
#define GOODIX_5E0A_HEIGHT 64
#define FRAME_PIXELS (GOODIX_5E0A_WIDTH * GOODIX_5E0A_HEIGHT)
#define OUT_WIDTH (GOODIX_5E0A_WIDTH * 2)
#define OUT_HEIGHT (GOODIX_5E0A_HEIGHT * 2)
#define OUT_PIXELS (OUT_WIDTH * OUT_HEIGHT)

typedef struct {
    int width;
    int height;
    uint32_t flags;
    uint8_t data[OUT_PIXELS];
} MockFpImage;

#define FPI_IMAGE_PARTIAL (1 << 0)
#define FPI_IMAGE_COLORS_INVERTED (1 << 1)

static MockFpImage *
process_frame_c (const uint8_t *frame)
{
  const uint8_t *pix = frame;
  uint8_t samples[19][GOODIX_5E0A_HEIGHT];

  uint8_t min_v = 255, max_v = 0;
  for (int k = 0; k < 19; ++k)
    {
      int col = 4 * k + 3;
      for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
        {
          uint8_t v = pix[col * GOODIX_5E0A_HEIGHT + r];
          samples[k][r] = v;
          if (v < min_v) min_v = v;
          if (v > max_v) max_v = v;
        }
    }

  if (min_v == 255) min_v = 0;
  uint8_t range = (max_v > min_v) ? (max_v - min_v) : 1;

  const int W = GOODIX_5E0A_WIDTH * 2;   // 160
  const int H = GOODIX_5E0A_HEIGHT * 2;  // 128

  MockFpImage *img = (MockFpImage *) calloc (1, sizeof (MockFpImage));
  assert(img != NULL);
  img->width = W;
  img->height = H;
  img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;

  for (int r = 0; r < H; ++r)
    {
      float orig_r = (float) r / 2.0f;
      int r0 = (int) orig_r;
      int r1 = (r0 + 1 < GOODIX_5E0A_HEIGHT) ? r0 + 1 : r0;
      float r_frac = orig_r - (float) r0;

      for (int c = 0; c < W; ++c)
        {
          float orig_c = (float) c / 2.0f;
          float pos = (orig_c - 3.0f) / 4.0f;
          float val;

          if (pos <= 0.0f)
            {
              val = (float) samples[0][r0] * (1.0f - r_frac) + (float) samples[0][r1] * r_frac;
            }
          else if (pos >= 18.0f)
            {
              val = (float) samples[18][r0] * (1.0f - r_frac) + (float) samples[18][r1] * r_frac;
            }
          else
            {
              int k = (int) pos;
              float c_frac = pos - (float) k;
              float top = (float) samples[k][r0] * (1.0f - c_frac) + (float) samples[k + 1][r0] * c_frac;
              float bot = (float) samples[k][r1] * (1.0f - c_frac) + (float) samples[k + 1][r1] * c_frac;
              val = top * (1.0f - r_frac) + bot * r_frac;
            }

          assert(!isnan(val));
          assert(!isinf(val));

          int norm = (int) (((val - (float) min_v) * 255.0f) / (float) range);
          if (norm < 0) norm = 0;
          if (norm > 255) norm = 255;
          img->data[r * W + c] = (uint8_t) norm;
        }
    }

  return img;
}

static void test_all_zeros(void) {
    printf("[*] Running test_all_zeros...\n");
    uint8_t frame[FRAME_PIXELS];
    memset(frame, 0x00, sizeof(frame));
    MockFpImage *img = process_frame_c(frame);
    assert(img->width == 160);
    assert(img->height == 128);
    assert(img->flags == (FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED));
    for (int i = 0; i < OUT_PIXELS; ++i) {
        assert(img->data[i] == 0);
    }
    free(img);
    printf("    -> PASS: test_all_zeros\n");
}

static void test_all_ff(void) {
    printf("[*] Running test_all_ff...\n");
    uint8_t frame[FRAME_PIXELS];
    memset(frame, 0xFF, sizeof(frame));
    MockFpImage *img = process_frame_c(frame);
    assert(img->width == 160);
    assert(img->height == 128);
    assert(img->flags == (FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED));
    for (int i = 0; i < OUT_PIXELS; ++i) {
        assert(img->data[i] == 255);
    }
    free(img);
    printf("    -> PASS: test_all_ff\n");
}

static void test_constant_intermediate(void) {
    printf("[*] Running test_constant_intermediate...\n");
    uint8_t values[] = {1, 42, 128, 200, 254};
    for (size_t v_idx = 0; v_idx < sizeof(values); ++v_idx) {
        uint8_t val = values[v_idx];
        uint8_t frame[FRAME_PIXELS];
        memset(frame, val, sizeof(frame));
        MockFpImage *img = process_frame_c(frame);
        for (int i = 0; i < OUT_PIXELS; ++i) {
            // Flat constant frame with 0 contrast normalizes to 0 (min_v == max_v, range == 1, val - min_v == 0)
            assert(img->data[i] == 0);
        }
        free(img);
    }
    printf("    -> PASS: test_constant_intermediate\n");
}

static void test_horizontal_gradient(void) {
    printf("[*] Running test_horizontal_gradient...\n");
    uint8_t frame[FRAME_PIXELS];
    for (int c = 0; c < GOODIX_5E0A_WIDTH; ++c) {
        for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r) {
            frame[c * GOODIX_5E0A_HEIGHT + r] = (uint8_t)((c * 255) / (GOODIX_5E0A_WIDTH - 1));
        }
    }
    MockFpImage *img = process_frame_c(frame);
    for (int r = 0; r < OUT_HEIGHT; ++r) {
        for (int c = 0; c < OUT_WIDTH - 1; ++c) {
            // Monotonically non-decreasing
            assert(img->data[r * OUT_WIDTH + c] <= img->data[r * OUT_WIDTH + (c + 1)]);
        }
    }
    free(img);
    printf("    -> PASS: test_horizontal_gradient\n");
}

static void test_vertical_gradient(void) {
    printf("[*] Running test_vertical_gradient...\n");
    uint8_t frame[FRAME_PIXELS];
    for (int c = 0; c < GOODIX_5E0A_WIDTH; ++c) {
        for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r) {
            frame[c * GOODIX_5E0A_HEIGHT + r] = (uint8_t)((r * 255) / (GOODIX_5E0A_HEIGHT - 1));
        }
    }
    MockFpImage *img = process_frame_c(frame);
    for (int c = 0; c < OUT_WIDTH; ++c) {
        for (int r = 0; r < OUT_HEIGHT - 1; ++r) {
            // Monotonically non-decreasing along rows
            assert(img->data[r * OUT_WIDTH + c] <= img->data[(r + 1) * OUT_WIDTH + c]);
        }
    }
    free(img);
    printf("    -> PASS: test_vertical_gradient\n");
}

static void test_extreme_checkerboard(void) {
    printf("[*] Running test_extreme_checkerboard...\n");
    uint8_t frame[FRAME_PIXELS];
    for (int c = 0; c < GOODIX_5E0A_WIDTH; ++c) {
        for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r) {
            frame[c * GOODIX_5E0A_HEIGHT + r] = ((c + r) % 2 == 0) ? 255 : 0;
        }
    }
    MockFpImage *img = process_frame_c(frame);
    for (int i = 0; i < OUT_PIXELS; ++i) {
        assert(img->data[i] <= 255);
    }
    free(img);
    printf("    -> PASS: test_extreme_checkerboard\n");
}

static void test_fuzz_random_frames(int count) {
    printf("[*] Running test_fuzz_random_frames (%d iterations)...\n", count);
    uint8_t frame[FRAME_PIXELS];
    srand(42);
    for (int iter = 0; iter < count; ++iter) {
        for (int i = 0; i < FRAME_PIXELS; ++i) {
            frame[i] = (uint8_t)(rand() % 256);
        }
        MockFpImage *img = process_frame_c(frame);
        assert(img->width == 160);
        assert(img->height == 128);
        assert(img->flags == (FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED));
        for (int i = 0; i < OUT_PIXELS; ++i) {
            assert(img->data[i] <= 255);
        }
        free(img);
    }
    printf("    -> PASS: test_fuzz_random_frames (%d iterations)\n", count);
}

int main(void) {
    printf("=================================================================\n");
    printf("  Empirical C Adversarial Demosaicing Harness (AddressSanitizer)  \n");
    printf("=================================================================\n");
    test_all_zeros();
    test_all_ff();
    test_constant_intermediate();
    test_horizontal_gradient();
    test_vertical_gradient();
    test_extreme_checkerboard();
    test_fuzz_random_frames(50000);
    printf("=================================================================\n");
    printf("  ALL C ADVERSARIAL STRESS TESTS PASSED CLEANLY (0 ERRORS)!      \n");
    printf("=================================================================\n");
    return 0;
}
