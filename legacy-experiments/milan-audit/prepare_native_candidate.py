"""Prepare an opt-in hardware candidate patch in an isolated directory.

Does not edit the checkout, install anything, or access USB. Supply ptrip7's
published bandpass-normalize.patch from the issue #12 archive. The patch keeps
the driver's canonical raster/default normalization and gates the experimental
band-pass plus engine transpose behind GOODIX_5E0A_NATIVE_RASTER=1.
"""

import argparse
import difflib
from pathlib import Path
import subprocess


def normalization(source):
    start = source.index("static gboolean\ngoodix5e0a_normalize_raw_frame (")
    # Skip the forward declaration, if this driver revision has one.
    while source.index(";", start) < source.index("{", start):
        start = source.index("static gboolean\ngoodix5e0a_normalize_raw_frame (", start + 1)
    end = source.index("\n/* Ticket 39:", start)
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bandpass_patch", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="New directory outside the checkout")
    parser.add_argument("--patch-out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if out == root or root in out.parents:
        raise ValueError("Candidate build directory must be outside the checkout")
    out.mkdir(parents=True, exist_ok=False)
    files = ["libfprint-driver/" + f for f in ("goodix5e0a.c", "goodix5e0a.h", "goodix_milan.c", "goodix_milan.h")]
    original = {}
    for name in files:
        original[name] = (root / name).read_text()
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original[name])
    subprocess.run(["git", "apply", "--no-index", "--check", str(args.bandpass_patch.resolve())], cwd=out, check=True)
    subprocess.run(["git", "apply", "--no-index", str(args.bandpass_patch.resolve())], cwd=out, check=True)
    path = out / files[0]
    source = path.read_text()
    bandpass = normalization(source)
    candidate = bandpass.replace("goodix5e0a_normalize_raw_frame", "goodix5e0a_normalize_bandpass_candidate", 1)
    stock = normalization(original[files[0]])
    condition = '''  if (g_strcmp0 (g_getenv ("GOODIX_5E0A_NATIVE_RASTER"), "1") == 0)
    return goodix5e0a_normalize_bandpass_candidate (pix, out_norm, out_min, out_max);

'''
    stock = stock.replace("  const int W =", condition + "  const int W =", 1)
    source = source.replace(bandpass, candidate + "\n" + stock, 1)
    # Expose only selected numerical diagnostics without enabling packet/image
    # debug logging for the whole driver domain. Defaults retain fp_dbg.
    macro = '''#define goodix5e0a_candidate_log(...) \\
  G_STMT_START { \\
    if (g_strcmp0 (g_getenv ("GOODIX_5E0A_NATIVE_RASTER"), "1") == 0) \\
      g_message (__VA_ARGS__); \\
    else \\
      fp_dbg (__VA_ARGS__); \\
  } G_STMT_END

'''
    source = source.replace("/* Mean over a (2r+1)x(2r+1) window", macro + "/* Mean over a (2r+1)x(2r+1) window", 1)
    for message in ("5e0a Milan verify:", "5e0a Milan identify:", "5e0a Milan enrollAddImage:",
                    "5e0a Milan enrollment committed successfully!"):
        old = 'fp_dbg ("' + message
        assert source.count(old) == 1
        source = source.replace(old, 'goodix5e0a_candidate_log ("' + message, 1)
    path.write_text(source)
    path = out / files[2]
    source = path.read_text()
    old = "static void make_goodix_image("
    assert source.count(old) == 1
    source = source.replace(old, "static guint8 *make_goodix_image(", 1)
    before = "    img->overlap = 100;\n}"
    after = '''    img->overlap = 100;
    /* Offline issue-12 candidate. Public driver inputs remain canonical 64x80.
     * A new enrollment is required when enabling this processing path. */
    if (width == 64 && height == 80 &&
        g_strcmp0(g_getenv("GOODIX_5E0A_NATIVE_RASTER"), "1") == 0) {
        guint8 *native = g_malloc(64 * 80);
        for (int y = 0; y < 80; y++)
            for (int x = 0; x < 64; x++)
                native[x * 80 + y] = pix[y * 64 + x];
        img->data = native;
        img->width = 80;
        img->height = 64;
        return native;
    }
    return NULL;
}'''
    assert source.count(before) == 1
    source = source.replace(before, after, 1)
    assert source.count("    make_goodix_image(") == 4
    source = source.replace("    make_goodix_image(", "    g_autofree guint8 *image_storage = make_goodix_image(")
    # Gallery unpack failures jump forward to fail_closed. Initialize ownership
    # before those jumps so automatic cleanup never sees an uninitialized value.
    start = source.index("int goodix_milan_identify_image (")
    gallery = source[start:]
    gallery = gallery.replace("    void **unpacked =", "    g_autofree guint8 *image_storage = NULL;\n    void **unpacked =", 1)
    gallery = gallery.replace("    g_autofree guint8 *image_storage = make_goodix_image(",
                              "    image_storage = make_goodix_image(", 1)
    source = source[:start] + gallery
    path.write_text(source)
    probe = out / "legacy-experiments/milan-audit/native_probe.c"
    probe.parent.mkdir(parents=True)
    probe.write_bytes((root / "legacy-experiments/milan-audit/native_probe.c").read_bytes())
    # Extract the candidate's real C functions for sensor-free byte comparison.
    source = (out / files[0]).read_text()
    start = source.index("/* Mean over a (2r+1)x(2r+1) window")
    end = source.index("\n/* Ticket 39:", start)
    functions = source[start:end].replace("static gboolean\ngoodix5e0a_normalize_raw_frame", "gboolean\ngoodix5e0a_normalize_raw_frame", 1)
    prefix = '''#include <glib.h>
#include <math.h>
#include <string.h>
typedef guint16 GoodixTls5xxPix;
#define GOODIX_5E0A_WIDTH 64
#define GOODIX_5E0A_HEIGHT 80
#define GOODIX_5E0A_FRAME_SIZE 5120
#define GOODIX_5E0A_NORMALIZE_MIDPOINT 128.0f
#define GOODIX_5E0A_CONTRAST_GAIN 1.5f
#define GOODIX_5E0A_BANDPASS_SMOOTH_RADIUS 1
#define GOODIX_5E0A_BANDPASS_BACKGROUND_RADIUS 5
#define GOODIX_5E0A_BANDPASS_TARGET_STD 80.0f
'''
    (out / "normalization.c").write_text(prefix + functions)
    diffs = []
    for name in files:
        updated = (out / name).read_text()
        if updated != original[name]:
            diffs.append("diff --git a/" + name + " b/" + name + "\n")
            diffs.extend(difflib.unified_diff(original[name].splitlines(True), updated.splitlines(True),
                                            fromfile="a/" + name, tofile="b/" + name))
    args.patch_out.write_text("".join(diffs))
    print(out)
    print(args.patch_out)


if __name__ == "__main__":
    main()
