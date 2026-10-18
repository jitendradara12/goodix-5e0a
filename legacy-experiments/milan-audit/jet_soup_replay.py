"""Audit Jet-Soup's issue #12 archive without opening a sensor.

Historical reproduction only: first 12 frames are THREE physical touches,
not a valid 12-touch enrollment. Finger identity is unknown. Each experiment
runs in a fresh process through the native production PE loader. The supplied
patch's actual C normalizer is compiled separately as normalization-reference.c.
"""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from native import NativeEngine
from replay import box_mean, read_pgm
from run import DLL, DLL_SHA256, identify, u64

ARCHIVE_SHA256 = "693d54803145987315da04bb6f6e35deb07b21243a930c5c2296d24abf25c7a8"
TARGETS = (60, 80, 100, 140, 180, 220)


def inputs(root):
    paths = sorted((root / "dumps").glob("*_raw.pgm"))
    if len(paths) != 24:
        raise ValueError("Expected exactly 24 raw frames")
    raw = [read_pgm(p) for p in paths]
    saved = [read_pgm(p.with_name(p.name.replace("_raw", "_norm")), 255)
             .astype(np.uint8) for p in paths]
    return paths, raw, saved


def reference(library):
    lib = ctypes.CDLL(str(library.resolve()))
    fn = lib.goodix5e0a_normalize_raw_frame
    fn.argtypes = [ctypes.c_void_p] * 4
    fn.restype = ctypes.c_int

    def normalize(raw):
        output = np.empty((80, 64), dtype=np.uint8)
        if fn(raw.ctypes.data, output.ctypes.data, None, None) != 1:
            raise RuntimeError("Supplied C normalizer rejected frame")
        return output

    return normalize


def old_range_normalize(raw):
    residual = raw.astype(np.float32) - box_mean(raw, 4)
    gain = np.float32(127) / max(abs(residual.min()), abs(residual.max()))
    values = np.float32(128) + residual * gain
    return np.clip(np.floor(values + np.float32(.5)), 0, 255).astype(np.uint8)


def inventory(args):
    paths, raw, saved = inputs(args.dataset)
    os.environ["GOODIX_TARGET_STD"] = "80"
    os.environ.pop("GOODIX_INVERT", None)
    normalize = reference(args.reference_library)
    patch_outputs = [normalize(r) for r in raw]
    independent_mismatches = []
    for r, c in zip(raw, patch_outputs):
        residual = r.astype(np.float32) - box_mean(r, 4)
        sd = np.sqrt(np.mean(residual.astype(np.float64) ** 2) -
                     np.mean(residual.astype(np.float64)) ** 2)
        values = np.float32(128) + residual * np.float32(80 / sd)
        expected = np.clip(np.floor(values + np.float32(.5)), 0, 255).astype(np.uint8)
        independent_mismatches.append(int(np.count_nonzero(expected != c)))
    if any(independent_mismatches):
        raise ValueError("Compiled normalizer disagrees with independent patch transcription")
    mean = np.mean(raw, axis=0, dtype=np.float64).ravel()
    fpn_path = args.dataset / "fpn_estimate_raw.pgm"
    fpn = read_pgm(fpn_path).ravel()
    all_inputs = sorted(args.dataset.rglob("*.pgm"))
    all_inputs += sorted((args.dataset / "patches").glob("*.patch"))
    all_inputs += [args.dataset / "README.md"]
    return {
        "source": "https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6250208075",
        "archive_sha256": ARCHIVE_SHA256,
        "engine_sha256": DLL_SHA256,
        "reference_source_sha256": hashlib.sha256((Path(__file__).parent / "jet-results" /
                                                    "normalization-reference.c").read_bytes()).hexdigest(),
        "c_reference_vs_independent_python_different_pixels": independent_mismatches,
        "input_sha256": {str(p.relative_to(args.dataset)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in all_inputs},
        "raw_frames": 24, "physical_touches_reported": 6,
        "enrollment_frame_submissions": 12, "enrollment_physical_touches": 3,
        "probe_frames": 12, "probe_physical_touches": 3,
        "finger_identity": "unspecified; no genuine/wrong-finger rate can be computed",
        "normalized_frames": [
            {"frame": p.name,
             "saved_vs_patch_std80_different_pixels": int(np.count_nonzero(s != c)),
             "saved_vs_old_range_different_pixels": int(np.count_nonzero(s != old_range_normalize(r))),
             "saved_sd": float(s.std()), "patch_std80_output_sd": float(c.std())}
            for p, r, s, c in zip(paths, raw, saved, patch_outputs)],
        "supplied_fpn": {
            "leading_sample": int(fpn[0]),
            "remaining_5119_equal_floor_mean_first_5119": bool(np.array_equal(fpn[1:], mean[:-1].astype(np.uint16))),
            "unshifted_different_pixels": int(np.count_nonzero(fpn != mean.astype(np.uint16))),
            "calibration": "none; neither this image nor a corrected finger-frame average is a measured background"},
        "limitations": [
            "Twelve enrollment frames come from only three touches.",
            "No finger identity labels, enrollment journal, pre-wire-change raw frames or USB capture supplied.",
            "FPN mode uses all normalized frames, including probes: historical reproduction with test leakage only.",
            "The patch retains production's negative-score clamp; this runner additionally preserves signed engine outputs.",
            "No hardware run or driver installation; capture-setting improvement remains contributor-reported."],
    }


def worker(args):
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Unreviewed engine DLL")
    _, raw, saved = inputs(args.dataset)
    os.environ["GOODIX_TARGET_STD"] = str(args.target)
    os.environ.pop("GOODIX_INVERT", None)
    normalized = saved if args.saved else [reference(args.reference_library)(r) for r in raw]
    if args.fpn:
        # Exact supplied harness arithmetic, NOT a candidate calibration method.
        fpn = np.sum(normalized, axis=0, dtype=np.float32) / np.float32(24) - np.float32(128)
        normalized = [np.clip(np.floor(n.astype(np.float32) - fpn + np.float32(.5)), 0, 255)
                      .astype(np.uint8) for n in normalized]
    engine = NativeEngine(DLL, args.native_library.resolve())
    context = engine.call("enrolStartEx", [engine.put(struct.pack("<i", 16))])
    if not context:
        raise RuntimeError("enrolStartEx failed")
    engine.mem_write(context + 8, struct.pack("<H", 12))
    result = {"enrollment": [], "probes": []}
    try:
        for index, pixels in enumerate(normalized[:12], 1):
            pixels = pixels.tobytes()
            _, quality, _ = engine.quality(pixels)
            code = engine.call("enrolAddImage", [context, engine.image(pixels), 0, 0, 0,
                                                engine.put(bytes(8))]) & 0xffffffff
            count, progress = struct.unpack("<Hi", engine.mem_read(context + 10, 6))
            result["enrollment"].append({"frame": index, "return_code": code, "accepted": count,
                                          "progress": progress, "quality": quality})
        result["enrollment_complete"] = count == 12 and progress == 100
        # The contributor's harness packs even after failed enrollment. Preserve
        # that behavior only for reproduction and record its invalidity explicitly.
        master_output = engine.put(bytes(8))
        result["commit_return_code"] = engine.call("enrolGetTemplate", [context, master_output]) & 0xffffffff
        if result["commit_return_code"] != 0:
            raise RuntimeError("Historical commit failed")
        master = u64(engine, master_output)
        size = engine.call("templateGetPackedSize", [master]) & 0xffffffff
        if not 0 < size <= 4 * 1024 * 1024:
            raise RuntimeError("Invalid packed template size")
        output = engine.put(bytes(size))
        if engine.call("templatePack", [master, output]) != 0:
            raise RuntimeError("templatePack failed")
        packed = bytes(engine.mem_read(output, size))
        result["template_bytes"] = size
    finally:
        engine.call("enrolFinish", [context])
    for index, pixels in enumerate(normalized[12:], 13):
        pixels = pixels.tobytes()
        unpacked = engine.put(bytes(8))
        if engine.call("templateUnPack", [engine.put(packed), size, 0, unpacked]) != 0:
            raise RuntimeError("templateUnPack failed")
        template = u64(engine, unpacked)
        try:
            decision = identify(engine, template, pixels)
        finally:
            engine.call("templateDelete", [template])
        _, quality, _ = engine.quality(pixels)
        result["probes"].append({"frame": index, "quality": quality, **decision,
                                  "matched": decision["matched_index"] == 0 and decision["signed_score"] > 0})
    result["probe_counts"] = {"unknown": {"frames": 12, "matched": sum(p["matched"] for p in result["probes"])}}
    result["processing"] = {"saved_norm": args.saved, "target": args.target, "all_frame_fpn": args.fpn}
    args.out.write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--native-library", type=Path, required=True)
    parser.add_argument("--reference-library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--target", type=int, default=80)
    parser.add_argument("--fpn", action="store_true")
    parser.add_argument("--saved", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    report = inventory(args)
    report["experiments"] = []
    scenarios = [(t, f, False) for t in TARGETS for f in (False, True)] + [(80, False, True)]
    for target, fpn, saved in scenarios:
        name = "saved-normalized" if saved else f"std{target}" + ("-all-frame-fpn" if fpn else "")
        output = args.out / f"{name}.json"
        command = [sys.executable, __file__, str(args.dataset), "--native-library", str(args.native_library),
                   "--reference-library", str(args.reference_library), "--out", str(output),
                   "--worker", "--target", str(target)]
        if fpn:
            command.append("--fpn")
        if saved:
            command.append("--saved")
        subprocess.run(command, check=True)
        result = json.loads(output.read_text())
        row = {"experiment": name, "enrollment_complete": result["enrollment_complete"],
               "probe_counts": result.get("probe_counts"), "result": output.name}
        report["experiments"].append(row)
        print(json.dumps(row), flush=True)
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
