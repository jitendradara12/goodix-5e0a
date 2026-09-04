#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define W 80
#define H 64
#define FRAME_SIZE (W * H)

void unpack_true_wbdi(const unsigned char *raw_10564, unsigned short *out_80x64) {
    // 1. Gather 96 active bytes per column from 80 columns of 132 bytes
    unsigned char packed_7680[7680];
    for (int col = 0; col < 80; col++) {
        memcpy(packed_7680 + col * 96, raw_10564 + col * 132, 96);
    }

    // 2. Unpack column-major (0x18004ea50 in wbdi.dll)
    int pixel_idx = 0;
    for (int i = 0; i < 7680; i += 6) {
        const unsigned char *c = packed_7680 + i;
        unsigned short pix[4];
        pix[0] = ((c[0] & 0x0f) << 8) | c[1];
        pix[1] = (c[3] << 4) | (c[0] >> 4);
        pix[2] = ((c[5] & 0x0f) << 8) | c[2];
        pix[3] = (c[4] << 4) | (c[5] >> 4);

        for (int p = 0; p < 4; p++) {
            int row = pixel_idx % H; // % 64
            int col = pixel_idx / H; // / 64
            out_80x64[row * W + col] = pix[p];
            pixel_idx++;
        }
    }
}

int main() {
    printf("True wbdi unpack algorithm compiled.\n");
    return 0;
}
