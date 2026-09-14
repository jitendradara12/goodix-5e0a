#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define W 80
#define H 64
#define FRAME_SIZE (W * H)
#define ACT_BYTES (FRAME_SIZE * 3 / 2) // 7680
#define TOTAL_BYTES 10564

static void pack_12bit(const unsigned short *pix, unsigned char *out, int num_pix) {
    for (int i = 0; i < num_pix; i += 4) {
        unsigned short p0 = pix[i + 0];
        unsigned short p1 = pix[i + 1];
        unsigned short p2 = pix[i + 2];
        unsigned short p3 = pix[i + 3];

        unsigned char *c = out + (i / 4) * 6;
        c[0] = ((p1 & 0x0f) << 4) | ((p0 >> 8) & 0x0f);
        c[1] = p0 & 0xff;
        c[2] = p2 & 0xff;
        c[3] = (p1 >> 4) & 0xff;
        c[4] = (p3 >> 4) & 0xff;
        c[5] = ((p3 & 0x0f) << 4) | ((p2 >> 8) & 0x0f);
    }
}

static void decode_frame(unsigned short *out, const unsigned char *data, int len) {
    int max_bytes = (len < ACT_BYTES) ? len : ACT_BYTES;
    unsigned short *pix = out;
    for (int i = 0; i + 6 <= max_bytes; i += 6) {
        const unsigned char *c = data + i;
        *pix++ = ((c[0] & 0x0f) << 8) | c[1];
        *pix++ = (c[3] << 4) | (c[0] >> 4);
        *pix++ = ((c[5] & 0x0f) << 8) | c[2];
        *pix++ = (c[4] << 4) | (c[5] >> 4);
    }
}

void check_corr(const unsigned short *pix) {
    unsigned short samples[19][H];
    for (int k = 0; k < 19; ++k) {
        int col = 4 * k + 3;
        for (int r = 0; r < H; ++r) {
            samples[k][r] = pix[r * W + col];
        }
    }

    double col_mean[19], col_std[19];
    for (int k = 0; k < 19; ++k) {
        double sum = 0.0;
        for (int r = 0; r < H; ++r) sum += samples[k][r];
        col_mean[k] = sum / (double)H;
        double var_sum = 0.0;
        for (int r = 0; r < H; ++r) {
            double d = samples[k][r] - col_mean[k];
            var_sum += d * d;
        }
        col_std[k] = sqrt(var_sum);
    }

    double adj_sum = 0.0;
    for (int i = 0; i < 18; ++i) {
        double cov = 0.0;
        for (int r = 0; r < H; ++r)
            cov += (samples[i][r] - col_mean[i]) * (samples[i + 1][r] - col_mean[i + 1]);
        double denom = col_std[i] * col_std[i + 1];
        adj_sum += (denom > 1e-6) ? (cov / denom) : 0.0;
    }
    printf("Adjacent Column Correlation: %.3f\n", adj_sum / 18.0);
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

    unsigned char payload[TOTAL_BYTES];
    memset(payload, 0, TOTAL_BYTES);
    pack_12bit(orig_pix, payload, 5120);

    unsigned short decoded_pix[5120];
    decode_frame(decoded_pix, payload, TOTAL_BYTES);

    int diffs = 0;
    for (int i = 0; i < 5120; i++) {
        if (orig_pix[i] != decoded_pix[i]) diffs++;
    }
    printf("Round-trip diffs: %d / 5120\n", diffs);
    check_corr(decoded_pix);
    return 0;
}
