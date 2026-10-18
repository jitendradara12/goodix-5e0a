"""Compare current, band-pass, and vendor processing on labeled saved touches.

No sensor/service operations. Enrollment is fixed to 12 distinct touch groups.
Each group contains 1..4 raw PGMs. Probe groups model verify's first-frame
fast path and final best-frame decision, using the real Milan exports.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from preprocess import HEIGHT, PIXELS, WIDTH, VendorPreprocessor
from run import DLL, DLL_SHA256, identify, u64


def read_pgm(path, expected_maximum=4095):
    data = Path(path).read_bytes()
    position = 0

    def token():
        nonlocal position
        while position < len(data):
            if data[position : position + 1].isspace():
                position += 1
            elif data[position] == 35:
                newline = data.find(b"\n", position)
                position = len(data) if newline < 0 else newline + 1
            else:
                break
        start = position
        while position < len(data) and not data[position : position + 1].isspace():
            position += 1
        if position == start:
            raise ValueError(f"Truncated PGM: {path}")
        return data[start:position]

    magic, width, height, maximum = token(), int(token()), int(token()), int(token())
    if (width, height, maximum) != (WIDTH, HEIGHT, expected_maximum):
        raise ValueError(
            f"Expected 64x80 PGM with max value {expected_maximum}: {path}"
        )
    if magic == b"P2":
        values = np.array([int(token()) for _ in range(PIXELS)], dtype=np.int32)
        # Reject extra samples; whitespace and trailing comments are fine.
        try:
            token()
        except ValueError:
            pass
        else:
            raise ValueError(f"Extra pixels in PGM: {path}")
    elif magic == b"P5":
        if data[position : position + 2] == b"\r\n":
            position += 2
        elif data[position : position + 1].isspace():
            position += 1
        else:
            raise ValueError(f"Missing binary PGM delimiter: {path}")
        payload = data[position:]
        sample_bytes = 2 if maximum > 255 else 1
        if len(payload) != PIXELS * sample_bytes:
            raise ValueError(f"Wrong binary PGM payload size: {path}")
        values = np.frombuffer(
            payload, dtype=">u2" if sample_bytes == 2 else "u1"
        ).astype(np.int32)
    else:
        raise ValueError(f"Unsupported PGM type: {path}")
    if np.any(values < 0) or np.any(values > maximum):
        raise ValueError(f"Out-of-range pixel in {path}")
    return values.astype(np.uint16).reshape(HEIGHT, WIDTH)


def box_mean(raw, radius):
    padded = np.pad(np.asarray(raw, dtype=np.float32), radius)
    counts = np.pad(np.ones((HEIGHT, WIDTH), dtype=np.float32), radius)
    size = 2 * radius + 1
    total = sum(
        padded[y : y + HEIGHT, x : x + WIDTH] for y in range(size) for x in range(size)
    )
    divisor = sum(
        counts[y : y + HEIGHT, x : x + WIDTH] for y in range(size) for x in range(size)
    )
    return total / divisor


def normalize(raw, method):
    if np.count_nonzero(raw > 30) < 64:
        return bytes(PIXELS)
    if method == "current":
        residual = raw.astype(np.float32) - box_mean(raw, 1)
        gain = 1.5
    elif method == "bandpass":
        smooth = box_mean(raw, 1)
        residual = smooth - box_mean(smooth, 5)
        rms = float(np.sqrt(np.float32(np.mean(residual.astype(np.float64) ** 2))))
        if rms < 0.5:
            return bytes(PIXELS)
        gain = 80 / rms
    else:
        raise ValueError(f"Unknown normalization: {method}")
    if float(residual.max() - residual.min()) < 1:
        return bytes(PIXELS)
    values = np.float32(128) + residual * np.float32(gain)
    rounded = np.copysign(np.floor(np.abs(values) + np.float32(0.5)), values)
    return np.clip(rounded, 0, 255).astype(np.uint8).tobytes()


def load_dataset(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if len(manifest.get("enrollment", [])) != 12:
        raise ValueError("Manifest must contain exactly 12 enrollment touch groups")
    loaded = {}
    enrollment_paths = set()
    probe_paths = set()

    def group(paths, used):
        if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
            raise ValueError("Each touch group must list 1..4 raw frames")
        output = []
        for value in paths:
            path = (manifest_path.parent / value).resolve()
            if path in used:
                raise ValueError(f"Frame reused across touch groups: {value}")
            used.add(path)
            if path not in loaded:
                loaded[path] = read_pgm(path)
            output.append(loaded[path])
        return output

    enrollment = [group(paths, enrollment_paths) for paths in manifest["enrollment"]]
    probes = []
    for index, probe in enumerate(manifest.get("probes", [])):
        if probe.get("label") not in {"genuine", "wrong", "blank", "noise", "unknown"}:
            raise ValueError(
                "Probe label must be genuine, wrong, blank, noise, or unknown"
            )
        probes.append(
            {
                "id": str(probe.get("id", index)),
                "label": probe["label"],
                "frames": group(probe["frames"], probe_paths),
            }
        )
    if not probes or enrollment_paths & probe_paths:
        raise ValueError("Need probes independent of the enrollment frame paths")
    calibration = (
        (manifest_path.parent / manifest["calibration"]).resolve()
        if manifest.get("calibration")
        else None
    )
    if calibration in enrollment_paths | probe_paths:
        raise ValueError("Calibration frame must be separate from enrollment/probes")
    state = (
        (manifest_path.parent / manifest["calibration_state"]).resolve()
        if manifest.get("calibration_state")
        else None
    )
    if (
        state in enrollment_paths | probe_paths
        or state == calibration
        and state is not None
    ):
        raise ValueError("Calibration state must be a separate file")
    inputs = set(loaded)
    inputs.update(p for p in (calibration, state) if p is not None)
    return {
        "calibration": read_pgm(calibration) if calibration else None,
        "calibration_state": state.read_bytes() if state else None,
        "enrollment": enrollment,
        "probes": probes,
        "provenance": {
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "input_sha256": sorted(
                hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs
            ),
            "kind": manifest.get("kind", "operator-labeled-real-captures"),
        },
    }


def run_method(
    dataset, method, engine_factory, *, normalizer=None, probe_policy="driver", vendor_layout="legacy"
):
    engine = engine_factory()
    if engine.call("ppp_param_init", [10]) != 0:
        raise RuntimeError("Sensor profile initialization failed")
    if method == "vendor" and dataset.get("calibration") is None:
        raise ValueError(
            "Vendor replay requires an explicitly supplied calibration source"
        )
    if probe_policy not in {"driver", "single-frame"}:
        raise ValueError("Unknown probe policy")
    vendor = (
        VendorPreprocessor(
            engine,
            dataset["calibration"],
            calibration_state=dataset.get("calibration_state"),
            layout=vendor_layout,
        )
        if method == "vendor"
        else None
    )
    frame_errors = []

    def candidate(raw, enrolling):
        if vendor:
            output = vendor.process(raw, enrolling=enrolling)
            if output["return_code"] != 0:
                frame_errors.append(output["return_code"])
                return None
            pixels = output["pixels"]
        else:
            pixels = normalizer(raw) if normalizer else normalize(raw, method)
        _, (quality, overlap), _ = engine.quality(pixels)
        active = raw[raw > 30]
        dynamic_range = int(active.max() - active.min()) if len(active) else 0
        rank = (quality, overlap, dynamic_range, len(active))
        return {
            "pixels": pixels,
            "rank": rank,
            "quality": quality,
            "overlap": overlap,
            "active": len(active),
            "range": dynamic_range,
        }

    maximum = engine.put(struct.pack("<i", 16))
    context = engine.call("enrolStartEx", [maximum])
    if not context:
        raise RuntimeError("enrolStartEx failed")
    engine.u.mem_write(context + 8, struct.pack("<H", 12))
    enrollment_results = []
    packed_template = None
    try:
        for touch, frames in enumerate(dataset["enrollment"], start=1):
            candidates = [candidate(raw, True) for raw in frames]
            valid = [item for item in candidates if item is not None]
            if not valid:
                return {
                    "enrollment_complete": False,
                    "failed_touch": touch,
                    "reason": "preprocessing failed",
                    "frame_errors": frame_errors,
                }
            best = max(valid, key=lambda item: item["rank"])
            status = engine.put(bytes(8))
            code = (
                engine.call(
                    "enrolAddImage",
                    [context, engine.image(best["pixels"]), 0, 0, 0, status],
                )
                & 0xFFFFFFFF
            )
            count, progress = struct.unpack("<Hi", engine.u.mem_read(context + 10, 6))
            enrollment_results.append(
                {
                    "touch": touch,
                    "return_code": code,
                    "accepted": count,
                    "progress": progress,
                    "quality": best["quality"],
                    "overlap": best["overlap"],
                    "selected_frame": candidates.index(best) + 1,
                }
            )
            if code != 0:
                return {
                    "enrollment_complete": False,
                    "failed_touch": touch,
                    "enrollment": enrollment_results,
                    "frame_errors": frame_errors,
                }
        if count != 12 or progress != 100:
            raise RuntimeError("12 submissions did not complete engine enrollment")
        master_output = engine.put(bytes(8))
        if engine.call("enrolGetTemplate", [context, master_output]) != 0:
            raise RuntimeError("enrolGetTemplate failed")
        master = u64(engine, master_output)
        size = engine.call("templateGetPackedSize", [master]) & 0xFFFFFFFF
        if not 0 < size <= 4 * 1024 * 1024:
            raise RuntimeError("Invalid packed template size")
        blob = engine.put(bytes(size))
        if engine.call("templatePack", [master, blob]) != 0:
            raise RuntimeError("templatePack failed")
        packed_template = bytes(engine.u.mem_read(blob, size))
    finally:
        engine.call("enrolFinish", [context])

    def decide(item, frame_number, phase):
        # The production wrapper unpacks/deletes for each identify call.
        unpacked = engine.put(bytes(8))
        if (
            engine.call(
                "templateUnPack", [engine.put(packed_template), size, 0, unpacked]
            )
            != 0
        ):
            raise RuntimeError("templateUnPack failed")
        template = u64(engine, unpacked)
        try:
            decision = identify(engine, template, item["pixels"])
        finally:
            engine.call("templateDelete", [template])
        # Keep return/index/score separately; production ignores the return code.
        matched = decision["matched_index"] == 0 and decision["signed_score"] > 0
        return {
            "frame": frame_number,
            "phase": phase,
            "quality": item["quality"],
            "overlap": item["overlap"],
            **decision,
            "matched": matched,
        }

    outcomes = []
    if packed_template is not None:
        for probe in dataset["probes"]:
            best = None
            best_frame = None
            attempts = []
            fast = False
            for frame_number, raw in enumerate(probe["frames"], start=1):
                item = candidate(raw, False)
                if item is None:
                    continue
                if best is None or item["rank"] > best["rank"]:
                    best = item
                    best_frame = frame_number
                if (
                    probe_policy == "driver"
                    and frame_number == 1
                    and item["active"] >= 1500
                    and item["range"] >= 500
                ):
                    attempts.append(decide(best, best_frame, "first-frame-fast-path"))
                    # Production stops the burst on positive pts, then decides again.
                    if attempts[-1]["signed_score"] > 0:
                        fast = True
                        break
            if best is not None:
                attempts.append(decide(best, best_frame, "final-best-frame"))
            outcomes.append(
                {
                    "id": probe["id"],
                    "label": probe["label"],
                    "matched": bool(attempts and attempts[-1]["matched"]),
                    "attempts": attempts,
                    "fast_path": fast,
                    "available_frames": len(probe["frames"]),
                }
            )
    counts = {}
    for label in sorted({probe["label"] for probe in outcomes}):
        labeled = [probe for probe in outcomes if probe["label"] == label]
        counts[label] = {
            "touch_groups": len(labeled),
            "matched": sum(p["matched"] for p in labeled),
        }
    return {
        "enrollment_complete": True,
        "template_bytes": size,
        "enrollment": enrollment_results,
        "probe_counts": counts,
        "probes": outcomes,
        "frame_errors": frame_errors,
    }


def compare(dataset, engine_factory, methods=("current", "bandpass", "vendor"), *, vendor_layout="legacy"):
    return {method: run_method(dataset, method, engine_factory, vendor_layout=vendor_layout) for method in methods}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=("current", "bandpass", "vendor"),
        default=["current", "bandpass", "vendor"],
    )
    parser.add_argument(
        "--native-library", type=Path, help="Use the production loader on x86-64 Linux"
    )
    args = parser.parse_args()
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Unreviewed engine DLL")
    if args.native_library:
        from native import NativeEngine

        factory = lambda: NativeEngine(DLL, args.native_library.resolve())
    else:
        from emulator import Engine

        factory = lambda: Engine(str(DLL))
    dataset = load_dataset(args.manifest)
    results = {
        "backend": "native-production-loader" if args.native_library else "emulated",
        "hardware_run": False,
        "provenance": dataset["provenance"],
        "methods": compare(dataset, factory, args.methods),
    }
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
