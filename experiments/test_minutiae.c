#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// NBIS declarations
typedef struct minutiae_struct {
    int alloc;
    int num;
    void **list;
} MINUTIAE;

typedef struct lfsparms_struct {
    int pad_value;
    int join_minutia_dist;
    int trans_minutia_dist;
    int max_minutiae;
    int remove_perimeter_pts;
    int min_loop_len;
    int max_overlap_dist;
    int min_overlap_dist;
    int max_overlap_join_dist;
    int num_overlap_angles;
    int overlap_angles[10];
    int max_xyt_overlap_dist;
    int min_xyt_overlap_dist;
    int max_xyt_overlap_join_dist;
    int num_xyt_overlap_angles;
    int xyt_overlap_angles[10];
    int appearance_len;
    int max_curvature_dist;
    int num_curvature_angles;
    int curvature_angles[10];
    int max_theta;
    int min_loop_aspect_dist;
    int min_planar_aspect_dist;
    int max_fct;
    int min_fct;
    int max_isect_dist;
    int max_isect_offset;
    int min_isect_length;
    int max_pore_dist;
    int min_pore_dist;
    int max_pore_length;
} LFSPARMS;

extern const LFSPARMS g_lfsparms_V2;

int get_minutiae(MINUTIAE **ominutiae, int **oquality_map,
                 int **odirection_map, int **olow_contrast_map,
                 int **olow_flow_map, int **ohigh_curve_map,
                 int *omap_w, int *omap_h,
                 unsigned char **obdata, int *obw, int *obh, int *obd,
                 unsigned char *idata, const int iw, const int ih,
                 const int id, const double ppmm, const LFSPARMS *lfsparms);

int main(int argc, char **argv) {
    if (argc < 4) {
        printf("Usage: %s <pgm_file> <width> <height>\n", argv[0]);
        return 1;
    }
    const char *path = argv[1];
    int W = atoi(argv[2]);
    int H = atoi(argv[3]);

    FILE *f = fopen(path, "rb");
    if (!f) { perror("fopen"); return 1; }
    char header[64];
    fgets(header, sizeof(header), f);
    fgets(header, sizeof(header), f);
    fgets(header, sizeof(header), f);
    unsigned char *data = malloc(W * H);
    fread(data, 1, W * H, f);
    fclose(f);

    MINUTIAE *minutiae = NULL;
    int *qmap, *dmap, *lcmap, *lfmap, *hcmap;
    int mw, mh, bw, bh, bd;
    unsigned char *bdata = NULL;

    LFSPARMS parms = g_lfsparms_V2;
    parms.remove_perimeter_pts = 0; // partial = false
    double ppmm = 500.0 / 25.4;

    int ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                           &mw, &mh, &bdata, &bw, &bh, &bd,
                           data, W, H, 8, ppmm, &parms);

    printf("Image %s (%dx%d): ret=%d, minutiae=%d\n",
           path, W, H, ret, (minutiae ? minutiae->num : -1));

    // Also test with inverted colors
    for (int i = 0; i < W * H; ++i) data[i] = 255 - data[i];
    minutiae = NULL;
    ret = get_minutiae(&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                       &mw, &mh, &bdata, &bw, &bh, &bd,
                       data, W, H, 8, ppmm, &parms);
    printf("Inverted %s (%dx%d): ret=%d, minutiae=%d\n",
           path, W, H, ret, (minutiae ? minutiae->num : -1));

    free(data);
    return 0;
}
