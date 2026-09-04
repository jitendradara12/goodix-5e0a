#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W 80
#define H 64
#define FRAME_SIZE (W * H)
#define ACT_BYTES (FRAME_SIZE * 3 / 2) // 7680

void wbdi_decode_frame(unsigned short *out_row_major, const unsigned char *data, int len) {
    int max_bytes = (len < ACT_BYTES) ? len : ACT_BYTES;
    int pixel_idx = 0;

    for (int i = 0; i + 6 <= max_bytes && pixel_idx < FRAME_SIZE; i += 6) {
        const unsigned char *c = data + i;
        unsigned short pix[4];
        pix[0] = ((c[0] & 0x0f) << 8) | c[1];
        pix[1] = (c[3] << 4) | (c[0] >> 4);
        pix[2] = ((c[5] & 0x0f) << 8) | c[2];
        pix[3] = (c[4] << 4) | (c[5] >> 4);

        for (int p = 0; p < 4 && pixel_idx < FRAME_SIZE; p++) {
            int row = pixel_idx % H; // % 64
            int col = pixel_idx / H; // / 64
            out_row_major[row * W + col] = pix[p];
            pixel_idx++;
        }
    }
}

int main() {
    printf("Wbdi decode frame compiled successfully.\n");
    return 0;
}
