"""Run the opt-in candidate's actual C wrappers on saved, labeled captures.

The installed driver and sensor are never used. Run in a fresh process for
each flag/scenario. Packed templates stay in process memory and are not saved.
"""

import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from ptrip7_replay import selection, synthetic_controls
from replay import normalize, read_pgm
from run import DLL, DLL_SHA256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset", type=Path)
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--normalization-library", type=Path, required=True)
    p.add_argument("--scenario", choices=("labeled", "fold1", "fold2"), default="labeled")
    p.add_argument("--enabled", choices=("0", "1"), required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Unreviewed engine DLL")
    os.environ["GOODIX_5E0A_NATIVE_RASTER"] = args.enabled
    norm = c.CDLL(str(args.normalization_library.resolve())).goodix5e0a_normalize_raw_frame
    norm.argtypes = [c.c_void_p] * 4
    norm.restype = c.c_int

    def pixels(raw):
        output = np.empty((80, 64), dtype=np.uint8)
        norm(raw.ctypes.data, output.ctypes.data, None, None)
        return output.tobytes()

    method = "bandpass" if args.enabled == "1" else "current"
    paths = sorted(args.dataset.rglob("*_raw.pgm"))
    differences = [str(path) for path in paths if pixels(read_pgm(path)) != normalize(read_pgm(path), method)]
    if differences:
        raise AssertionError(f"Candidate C/Python normalization disagreement: {differences}")
    lib = c.CDLL(str(args.library.resolve()))
    lib.goodix_milan_init.argtypes = [c.c_char_p]
    assert lib.goodix_milan_init(str(DLL).encode()) == 1
    lib.goodix_milan_enroll_start.argtypes = [c.c_void_p]
    lib.goodix_milan_enroll_start.restype = c.c_void_p
    lib.goodix_milan_frame_quality.argtypes = [c.c_char_p, c.c_int, c.c_int, c.c_void_p, c.c_void_p]
    lib.goodix_milan_enroll_add_image.argtypes = [c.c_void_p, c.c_char_p, c.c_int, c.c_int, c.c_void_p, c.c_void_p]
    lib.goodix_milan_enroll_commit.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p]
    lib.goodix_milan_enroll_finish.argtypes = [c.c_void_p]
    lib.goodix_milan_verify_image.argtypes = [c.c_char_p, c.c_int, c.c_int, c.c_void_p, c.c_size_t, c.c_void_p]
    lib.goodix_milan_identify_image.argtypes = [c.c_char_p, c.c_int, c.c_int, c.c_void_p, c.c_void_p,
                                               c.c_int, c.c_void_p, c.c_void_p]

    def frame(raw):
        output = pixels(raw)
        quality, overlap = c.c_uint(), c.c_uint()
        lib.goodix_milan_frame_quality(output, 64, 80, c.byref(quality), c.byref(overlap))
        active = raw[raw > 30]
        dynamic_range = int(active.max() - active.min()) if len(active) else 0
        return output, (quality.value, overlap.value, dynamic_range, len(active))

    data, policy, provenance = selection(args.dataset, args.scenario)
    if args.scenario == "labeled":
        provenance["synthetic_controls"] = synthetic_controls(data)
    result = {"candidate_enabled": args.enabled == "1", "scenario": args.scenario,
              "hardware_run": False, "normalized_frames_byte_identical": len(paths),
              "dll_sha256": DLL_SHA256,
              "public_input_geometry": "64x80", "engine_geometry": "80x64" if args.enabled == "1" else "64x80",
              "provenance": provenance, "enrollment": [], "probes": []}
    context = lib.goodix_milan_enroll_start(None)
    if not context:
        raise RuntimeError("Enrollment initialization failed")
    count, progress = c.c_int(), c.c_int()
    blob, size = c.c_void_p(), c.c_size_t()
    try:
        for touch, group in enumerate(data["enrollment"], 1):
            candidates = [frame(raw) for raw in group]
            best = max(range(len(candidates)), key=lambda i: candidates[i][1])
            code = lib.goodix_milan_enroll_add_image(context, candidates[best][0], 64, 80,
                                                     c.byref(count), c.byref(progress))
            result["enrollment"].append({"touch": touch, "selected_frame": best + 1,
                                          "return_code": code, "accepted": count.value,
                                          "progress": progress.value, "rank": candidates[best][1]})
            if code != 0:
                break
        result["enrollment_complete"] = count.value == 12 and progress.value == 100
        if result["enrollment_complete"]:
            assert lib.goodix_milan_enroll_commit(context, c.byref(blob), c.byref(size)) == 0
            result["template_bytes"] = size.value
    finally:
        lib.goodix_milan_enroll_finish(context)

    def verify(item, number, phase):
        score = c.c_int(-999)
        match = lib.goodix_milan_verify_image(item[0], 64, 80, blob, size, c.byref(score))
        return {"frame": number, "phase": phase, "matched": bool(match), "score": score.value}

    if result["enrollment_complete"]:
        for probe in data["probes"]:
            best, best_frame, attempts = None, None, []
            for index, raw in enumerate(probe["frames"], 1):
                item = frame(raw)
                if best is None or item[1] > best[1]:
                    best, best_frame = item, index
                if policy == "driver" and index == 1 and item[1][3] >= 1500 and item[1][2] >= 500:
                    attempts.append(verify(best, best_frame, "first-frame-fast-path"))
                    if attempts[-1]["score"] > 0:
                        break
            attempts.append(verify(best, best_frame, "final-best-frame"))
            result["probes"].append({"id": probe["id"], "label": probe["label"],
                                      "matched": attempts[-1]["matched"], "attempts": attempts})
    result["counts"] = {label: {"probes": sum(p["label"] == label for p in result["probes"]),
                                "matched": sum(p["label"] == label and p["matched"] for p in result["probes"])}
                        for label in sorted({p["label"] for p in result["probes"]})}
    if result["enrollment_complete"] and args.scenario == "labeled":
        result["gallery_checks"] = []
        for label in ("genuine", "wrong"):
            probe = next(p for p in data["probes"] if p["label"] == label)
            index, score = c.c_int(-999), c.c_int(-999)
            blobs, sizes = (c.c_void_p * 1)(blob.value), (c.c_size_t * 1)(size.value)
            match = lib.goodix_milan_identify_image(pixels(probe["frames"][0]), 64, 80,
                                                   blobs, sizes, 1, c.byref(index), c.byref(score))
            assert bool(match) == (label == "genuine")
            result["gallery_checks"].append({"label": label, "matched": bool(match),
                                              "index": index.value, "score": score.value})
        # Exercise the fail_closed jump before the scratch buffer is allocated.
        index, score = c.c_int(-999), c.c_int(-999)
        invalid, sizes = (c.c_void_p * 1)(None), (c.c_size_t * 1)(0)
        assert lib.goodix_milan_identify_image(pixels(data["probes"][0]["frames"][0]), 64, 80,
                                               invalid, sizes, 1, c.byref(index), c.byref(score)) == 0
        assert (index.value, score.value) == (-1, 0)
        result["gallery_invalid_template_rejected"] = True
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"scenario": args.scenario, "enabled": args.enabled,
                      "normalization_byte_checks": len(paths), "enrollment_complete": result["enrollment_complete"],
                      "counts": result["counts"]}))


if __name__ == "__main__":
    main()
