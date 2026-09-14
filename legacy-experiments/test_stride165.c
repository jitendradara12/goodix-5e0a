#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define W 80
#define H 64
#define ROW_RAW_BYTES 165
#define ROW_ACT_BYTES 120

static void pack_row_major_stride165(const unsigned short *pix, unsigned char *data) {
    memset(data, 0, H * ROW_RAW_BYTES + 4);
    for (int r = 0; r < H; r++) {
        unsigned char *row_data = data + r * ROW_RAW_BYTES;
        const unsigned short *row_pix = pix + r * W;
        for (int i = 0; i < W; i += 4) {
            unsigned short p0 = row_pix[i + 0];
            unsigned short p1 = row_pix[i + 1];
            unsigned short p2 = row_pix[i + 2];
            unsigned short p3 = row_pix[i + 3];

            unsigned char *c = row_data + (i / 4) * 6;
            c[0] = ((p1 & 0x0f) << 4) | ((p0 >> 8) & 0x0f);
            c[1] = p0 & 0xff;
            c[2] = p2 & 0xff;
            c[3] = (p1 >> 4) & 0xff;
            c[4] = (p3 >> 4) & 0xff;
            c[5] = ((p3 & 0x0f) << 4) | ((p2 >> 8) & 0x0f);
        }
    }
}

static void decode_frame_stride165(unsigned short *out, const unsigned char *data, int len) {
    for (int r = 0; r < H; r++) {
        const unsigned char *row_data = data + r * ROW_RAW_BYTES;
        unsigned short *row_out = out + r * W;
        for (int i = 0; i < ROW_ACT_BYTES; i += 6) {
            const unsigned char *c = row_data + i;
            *row_out++ = ((c[0] & 0x0f) << 8) | c[1];
            *row_out++ = (c[3] << 4) | (c[0] >> 4);
            *row_out++ = ((c[5] & 0x0f) << 8) | c[2];
            *row_out++ = (c[4] << 4) | (c[5] >> 4);
        }
    }
}

int main() {
    FILE *f = fopen("/tmp/live_touch.pgm", "r");
    if (!f) return 1;
    char line[128];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] != '#' && strstr(line, "4095")) break;
    }
    unsigned short orig_pix[5120];
    int n = 0;
    while (n < 5120 && fscanf(f, "%hu", &orig_pix[n]) == 1) n++;
    fclose(f);

    unsigned char payload[H * ROW_RAW_BYTES + 4];
    pack_row_major_stride165(orig_pix, payload);

    unsigned short decoded[5120];
    decode_frame_stride165(decoded, payload, sizeof(payload));

    int diffs = 0;
    for (int i = 0; i < 5120; i++) {
        if (orig_pix[i] != decoded[i]) diffs++;
    }
    printf("Stride-165 Round-trip diffs: %d / 5120\n", diffs);

    // Also simulate what linear decode of 7680 bytes gave on this payload:
    int nonzero_linear = 0, zero_linear = 0;
    for (int i = 0; i + 6 <= 7680; i += 6) {
        int r = (i / 165);
        int offset = (i % 165);
        // 4 pixels
        for (int p = 0; p < 4; p++) {
            if (offset < 120) nonzero_linear++;
            else zero_linear++;
        }
    }
    printf("Simulated linear decode of 7680B on Stride-165: active=%d, zeros=%d, total=%d\n",
           nonzero_linear, zero_linear, nonzero_linear + zero_linear);

    return 0;
}
