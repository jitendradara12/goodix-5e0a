/*
 * Empirical Stress Test: Direct Wire-to-Pixel Decoding Equivalence & Memory Safety
 * 
 * Verifies 100% bitwise equivalence between:
 *   - Old 2-step unpacking (80 memcpys to 7680-byte intermediate buffer + unpack)
 *   - New direct block unpacking (direct wire-to-pixel decoding from goodix5e0a.c)
 * 
 * Stress-tests bounds, padding isolation, synthetic edge cases, real captures,
 * truncated packets, and ASAN/UBSAN safety.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <time.h>

#define GOODIX_5E0A_WIDTH 64
#define GOODIX_5E0A_HEIGHT 80
#define GOODIX_5E0A_FRAME_SIZE (GOODIX_5E0A_WIDTH * GOODIX_5E0A_HEIGHT) /* 5120 */
#define GOODIX_5E0A_FRAME_BLOCKS 80
#define GOODIX_5E0A_BLOCK_BYTES 132
#define GOODIX_5E0A_BLOCK_ACTIVE_BYTES 96
#define GOODIX_5E0A_ACT_BYTES (GOODIX_5E0A_FRAME_BLOCKS * GOODIX_5E0A_BLOCK_ACTIVE_BYTES) /* 7680 */
#define GOODIX_5E0A_FRAME_WIRE_BYTES (GOODIX_5E0A_FRAME_BLOCKS * GOODIX_5E0A_BLOCK_BYTES + 4) /* 10564 */

typedef uint16_t GoodixTls5xxPix;

/* Old 2-step decoding implementation (as was in goodix5e0a.c before commit) */
static uint32_t
decode_frame_old (GoodixTls5xxPix *out_row_major, const uint8_t *data, uint16_t len)
{
  uint8_t packed[GOODIX_5E0A_ACT_BYTES];
  memset (packed, 0, sizeof(packed));
  uint32_t packed_len = 0;

  if (!out_row_major || !data)
    return 0;

  for (uint32_t block = 0; block < GOODIX_5E0A_FRAME_BLOCKS; block++)
    {
      uint32_t src = block * GOODIX_5E0A_BLOCK_BYTES;
      if (src + GOODIX_5E0A_BLOCK_ACTIVE_BYTES > len)
        break;

      memcpy (packed + packed_len, data + src, GOODIX_5E0A_BLOCK_ACTIVE_BYTES);
      packed_len += GOODIX_5E0A_BLOCK_ACTIVE_BYTES;
    }

  uint32_t pixel_idx = 0;
  for (uint32_t i = 0; i + 6 <= packed_len && pixel_idx + 4 <= GOODIX_5E0A_FRAME_SIZE; i += 6)
    {
      const uint8_t *c = packed + i;
      out_row_major[pixel_idx++] = ((c[0] & 0x0f) << 8) | c[1];
      out_row_major[pixel_idx++] = (c[3] << 4) | (c[0] >> 4);
      out_row_major[pixel_idx++] = ((c[5] & 0x0f) << 8) | c[2];
      out_row_major[pixel_idx++] = (c[4] << 4) | (c[5] >> 4);
    }

  return pixel_idx;
}

/* New direct block decoding implementation (from goodix5e0a.c:818-847) */
static uint32_t
decode_frame_new (GoodixTls5xxPix *out_row_major, const uint8_t *data, uint16_t len)
{
  uint32_t pixel_idx = 0;

  if (!out_row_major || !data)
    return 0;

  for (uint32_t block = 0; block < GOODIX_5E0A_FRAME_BLOCKS; block++)
    {
      uint32_t src = block * GOODIX_5E0A_BLOCK_BYTES;
      if (src + GOODIX_5E0A_BLOCK_ACTIVE_BYTES > len)
        break;

      const uint8_t *blk = data + src;
      for (uint32_t i = 0; i < GOODIX_5E0A_BLOCK_ACTIVE_BYTES && pixel_idx + 4 <= GOODIX_5E0A_FRAME_SIZE; i += 6)
        {
          const uint8_t *c = blk + i;
          out_row_major[pixel_idx++] = ((c[0] & 0x0f) << 8) | c[1];
          out_row_major[pixel_idx++] = (c[3] << 4) | (c[0] >> 4);
          out_row_major[pixel_idx++] = ((c[5] & 0x0f) << 8) | c[2];
          out_row_major[pixel_idx++] = (c[4] << 4) | (c[5] >> 4);
        }
    }

  return pixel_idx;
}

/* Helper to pack 4 pixels into 6 wire bytes */
static void
pack_4_pixels (uint8_t *chunk, uint16_t p0, uint16_t p1, uint16_t p2, uint16_t p3)
{
  chunk[0] = (uint8_t)(((p0 >> 8) & 0x0F) | ((p1 & 0x0F) << 4));
  chunk[1] = (uint8_t)(p0 & 0xFF);
  chunk[2] = (uint8_t)(p2 & 0xFF);
  chunk[3] = (uint8_t)((p1 >> 4) & 0xFF);
  chunk[4] = (uint8_t)((p3 >> 4) & 0xFF);
  chunk[5] = (uint8_t)(((p2 >> 8) & 0x0F) | ((p3 & 0x0F) << 4));
}

static void
assert_identical (const GoodixTls5xxPix *out_old, const GoodixTls5xxPix *out_new,
                  uint32_t ret_old, uint32_t ret_new, const char *scenario)
{
  if (ret_old != ret_new)
    {
      fprintf (stderr, "FAIL [%s]: Return count mismatch: old=%u, new=%u\n",
               scenario, ret_old, ret_new);
      exit (1);
    }

  for (uint32_t i = 0; i < ret_old; i++)
    {
      if (out_old[i] != out_new[i])
        {
          fprintf (stderr, "FAIL [%s]: Pixel mismatch at index %u: old=0x%04x (%u), new=0x%04x (%u)\n",
                   scenario, i, out_old[i], out_old[i], out_new[i], out_new[i]);
          exit (1);
        }
      /* Assert strictly within 12-bit range */
      if (out_new[i] > 4095)
        {
          fprintf (stderr, "FAIL [%s]: Pixel exceeds 12-bit range at index %u: value=%u\n",
                   scenario, i, out_new[i]);
          exit (1);
        }
    }
}

int main (void)
{
  GoodixTls5xxPix out_old[GOODIX_5E0A_FRAME_SIZE + 64] = {0};
  GoodixTls5xxPix out_new[GOODIX_5E0A_FRAME_SIZE + 64] = {0};
  uint8_t wire[GOODIX_5E0A_FRAME_WIRE_BYTES + 1024] = {0};

  printf ("=================================================================\n");
  printf ("EMPIRICAL STRESS TEST: WIRE-TO-PIXEL DECODER EQUIVALENCE\n");
  printf ("=================================================================\n\n");

  /* --- Test 1: NULL pointer safety --- */
  printf ("[1] Testing NULL pointer guards...\n");
  assert (decode_frame_old (NULL, wire, GOODIX_5E0A_FRAME_WIRE_BYTES) == 0);
  assert (decode_frame_new (NULL, wire, GOODIX_5E0A_FRAME_WIRE_BYTES) == 0);
  assert (decode_frame_old (out_old, NULL, GOODIX_5E0A_FRAME_WIRE_BYTES) == 0);
  assert (decode_frame_new (out_new, NULL, GOODIX_5E0A_FRAME_WIRE_BYTES) == 0);
  printf ("    PASS: NULL pointers handled cleanly.\n");

  /* --- Test 2: All 0x00 wire buffer --- */
  printf ("[2] Testing all-0x00 synthetic wire buffer (10,564 bytes)...\n");
  memset (wire, 0, sizeof (wire));
  memset (out_old, 0x55, sizeof (out_old));
  memset (out_new, 0xAA, sizeof (out_new));
  uint32_t ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  uint32_t ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  assert_identical (out_old, out_new, ret_old, ret_new, "All 0x00");
  assert (ret_new == GOODIX_5E0A_FRAME_SIZE);
  for (uint32_t i = 0; i < ret_new; i++) assert (out_new[i] == 0);
  printf ("    PASS: All 5,120 pixels are 0; bitwise identical.\n");

  /* --- Test 3: All 0xFF wire buffer --- */
  printf ("[3] Testing all-0xFF synthetic wire buffer (10,564 bytes)...\n");
  memset (wire, 0xFF, sizeof (wire));
  memset (out_old, 0, sizeof (out_old));
  memset (out_new, 0, sizeof (out_new));
  ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  assert_identical (out_old, out_new, ret_old, ret_new, "All 0xFF");
  assert (ret_new == GOODIX_5E0A_FRAME_SIZE);
  for (uint32_t i = 0; i < ret_new; i++) assert (out_new[i] == 4095);
  printf ("    PASS: All 5,120 pixels are 4095 (0xFFF); bitwise identical.\n");

  /* --- Test 4: Alternating bit patterns (0xAA, 0x55, 0x5A, 0xA5) --- */
  printf ("[4] Testing alternating bit patterns...\n");
  uint8_t patterns[] = { 0xAA, 0x55, 0x5A, 0xA5, 0x33, 0xCC, 0x0F, 0xF0 };
  for (size_t p = 0; p < sizeof (patterns) / sizeof (patterns[0]); p++)
    {
      memset (wire, patterns[p], sizeof (wire));
      ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
      ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
      char label[32];
      snprintf (label, sizeof (label), "Pattern 0x%02X", patterns[p]);
      assert_identical (out_old, out_new, ret_old, ret_new, label);
      assert (ret_new == GOODIX_5E0A_FRAME_SIZE);
    }
  printf ("    PASS: 8 distinct bit patterns matched bitwise across 5,120 pixels.\n");

  /* --- Test 5: Incrementing sequential byte ramp --- */
  printf ("[5] Testing sequential ramp (wire[i] = i %% 256)...\n");
  for (size_t i = 0; i < sizeof (wire); i++) wire[i] = (uint8_t)(i & 0xFF);
  ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  assert_identical (out_old, out_new, ret_old, ret_new, "Sequential Ramp");
  assert (ret_new == GOODIX_5E0A_FRAME_SIZE);
  printf ("    PASS: Sequential ramp bitwise identical across all 5,120 pixels.\n");

  /* --- Test 6: Real capture legacy-experiments/fingerprint.pgm --- */
  printf ("[6] Testing real sensor capture (legacy-experiments/fingerprint.pgm)...\n");
  FILE *f = fopen ("legacy-experiments/fingerprint.pgm", "r");
  if (!f)
    f = fopen ("experiments/fingerprint.pgm", "r");
  assert (f != NULL && "legacy-experiments/fingerprint.pgm must exist");
  char magic[8];
  int pw, ph, maxv;
  assert (fscanf (f, "%7s %d %d %d", magic, &pw, &ph, &maxv) == 4);
  assert (strcmp (magic, "P2") == 0);
  assert (pw == 64 && ph == 80);
  uint16_t real_pixels[GOODIX_5E0A_FRAME_SIZE];
  for (int i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      int val;
      assert (fscanf (f, "%d", &val) == 1);
      real_pixels[i] = (uint16_t)val;
    }
  fclose (f);

  /* Pack real_pixels into wire buffer format: 80 blocks of 132 bytes (96 active + 36 pad) + 4 footer */
  memset (wire, 0, sizeof (wire));
  for (uint32_t b = 0; b < GOODIX_5E0A_FRAME_BLOCKS; b++)
    {
      uint8_t *blk = wire + b * GOODIX_5E0A_BLOCK_BYTES;
      for (uint32_t grp = 0; grp < 16; grp++)
        {
          uint32_t px = b * 64 + grp * 4;
          pack_4_pixels (blk + grp * 6,
                         real_pixels[px + 0], real_pixels[px + 1],
                         real_pixels[px + 2], real_pixels[px + 3]);
        }
      /* Pad with zeroes */
      memset (blk + GOODIX_5E0A_BLOCK_ACTIVE_BYTES, 0, 36);
    }
  wire[80 * 132 + 0] = 0x12;
  wire[80 * 132 + 1] = 0x34;
  wire[80 * 132 + 2] = 0x56;
  wire[80 * 132 + 3] = 0x78;

  ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  assert_identical (out_old, out_new, ret_old, ret_new, "Real fingerprint.pgm");
  assert (ret_new == GOODIX_5E0A_FRAME_SIZE);

  /* Verify round-trip accuracy against ground-truth real_pixels */
  for (uint32_t i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      if (out_new[i] != real_pixels[i])
        {
          fprintf (stderr, "FAIL: Round-trip mismatch at %u: got %u, expected %u\n",
                   i, out_new[i], real_pixels[i]);
          exit (1);
        }
    }
  printf ("    PASS: 100%% round-trip bitwise match against 5,120 real hardware pixels.\n");

  /* --- Test 7: Padding isolation adversarial stress --- */
  printf ("[7] Testing padding isolation (injecting garbage/noise into 36-byte padding & footer)...\n");
  /* Fill all padding bytes with random non-zero values */
  for (uint32_t b = 0; b < GOODIX_5E0A_FRAME_BLOCKS; b++)
    {
      uint8_t *pad = wire + b * GOODIX_5E0A_BLOCK_BYTES + GOODIX_5E0A_BLOCK_ACTIVE_BYTES;
      for (int k = 0; k < 36; k++)
        pad[k] = (uint8_t)(rand () | 1); /* Non-zero */
    }
  wire[80 * 132 + 0] = 0xDE;
  wire[80 * 132 + 1] = 0xAD;
  wire[80 * 132 + 2] = 0xBE;
  wire[80 * 132 + 3] = 0xEF;

  ret_old = decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  ret_new = decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  assert_identical (out_old, out_new, ret_old, ret_new, "Padding Noise Injection");
  for (uint32_t i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    assert (out_new[i] == real_pixels[i]);
  printf ("    PASS: Padding noise strictly isolated; decoded pixels unchanged.\n");

  /* --- Test 8: Length truncation boundary stress --- */
  printf ("[8] Testing length truncation boundary conditions (0 to 11,000 bytes)...\n");
  for (uint32_t len = 0; len <= GOODIX_5E0A_FRAME_WIRE_BYTES + 50; len++)
    {
      ret_old = decode_frame_old (out_old, wire, (uint16_t)len);
      ret_new = decode_frame_new (out_new, wire, (uint16_t)len);
      char label[32];
      snprintf (label, sizeof (label), "Truncation len=%u", len);
      assert_identical (out_old, out_new, ret_old, ret_new, label);

      /* Expected block count = len / 132, capped at 80 */
      /* But wait: if len has src + 96 <= len, block is decoded */
      uint32_t expected_blocks = 0;
      for (uint32_t b = 0; b < 80; b++)
        {
          if (b * 132 + 96 <= len)
            expected_blocks++;
          else
            break;
        }
      assert (ret_new == expected_blocks * 64);
    }
  printf ("    PASS: All truncation lengths (0..10614) produced exact matching pixel subsets.\n");

  /* --- Test 9: Fuzzing with 10,000 randomized wire streams --- */
  printf ("[9] Fuzzing 10,000 randomized wire buffers...\n");
  srand (1337);
  for (int iter = 0; iter < 10000; iter++)
    {
      uint16_t fuzzed_len = (uint16_t)(rand () % (GOODIX_5E0A_FRAME_WIRE_BYTES + 100));
      for (uint32_t i = 0; i < fuzzed_len; i++)
        wire[i] = (uint8_t)(rand () & 0xFF);

      ret_old = decode_frame_old (out_old, wire, fuzzed_len);
      ret_new = decode_frame_new (out_new, wire, fuzzed_len);
      assert_identical (out_old, out_new, ret_old, ret_new, "Fuzz Iteration");
    }
  printf ("    PASS: 10,000 random fuzzed iterations completed with zero discrepancies.\n");

  /* --- Test 10: Performance Benchmark (50,000 iterations) --- */
  printf ("[10] Performance shootout (50,000 full frame decodes)...\n");
  clock_t t0 = clock ();
  for (int iter = 0; iter < 50000; iter++)
    decode_frame_old (out_old, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  clock_t t1 = clock ();
  double old_time_sec = (double)(t1 - t0) / CLOCKS_PER_SEC;

  clock_t t2 = clock ();
  for (int iter = 0; iter < 50000; iter++)
    decode_frame_new (out_new, wire, GOODIX_5E0A_FRAME_WIRE_BYTES);
  clock_t t3 = clock ();
  double new_time_sec = (double)(t3 - t2) / CLOCKS_PER_SEC;

  printf ("    Old 2-step (memcpy): %.3f ms total (%.3f µs/frame)\n",
          old_time_sec * 1000.0, (old_time_sec / 50000.0) * 1e6);
  printf ("    New direct unpack  : %.3f ms total (%.3f µs/frame)\n",
          new_time_sec * 1000.0, (new_time_sec / 50000.0) * 1e6);
  printf ("    Speedup: %.2fx faster, zero heap allocations.\n", old_time_sec / new_time_sec);

  printf ("\n=================================================================\n");
  printf ("ALL WIRE DECODING EQUIVALENCE TESTS PASSED (100%% VERIFIED)!\n");
  printf ("=================================================================\n");

  return 0;
}
