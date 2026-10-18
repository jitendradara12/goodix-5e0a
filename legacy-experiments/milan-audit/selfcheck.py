"""Exercise the preprocessing prototype on explicitly synthetic controls."""

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

import numpy as np
from preprocess import GuardedBuffer, VendorPreprocessor
from replay import compare, load_dataset, read_pgm, run_method
from run import DLL, DLL_SHA256, ROOT


def write_pgm(path, pixels, *, binary=False):
    if binary:
        path.write_bytes(b"P5\n64 80\n4095\n" + pixels.astype(">u2").tobytes())
    else:
        path.write_text("P2\n64 80\n4095\n" + " ".join(map(str, pixels.flat)) + "\n")


def pattern(seed):
    spec = importlib.util.spec_from_file_location(
        "pattern_generator", ROOT / "legacy-experiments/gen_dense_live.py"
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.RIDGE_PERIOD = 10.0
    phase = np.array(generator.build_phase(seed)).reshape(80, 64)
    mask = np.array(generator.ridge_endings_mask(seed)).reshape(80, 64)
    return 300 * np.sin(phase) * mask


def build_dataset(directory):
    rng = np.random.default_rng(113)
    calibration = np.full((80, 64), 1500, dtype=np.uint16)
    write_pgm(directory / "calibration.pgm", calibration)
    enrolled = pattern(67)
    other = pattern(68)
    groups = []
    for touch in range(12):
        shifted = np.roll(
            enrolled, ((touch % 3) - 1, (touch // 3) % 3 - 1), axis=(0, 1)
        )
        pixels = np.clip(1500 + shifted + rng.normal(0, 22, (80, 64)), 0, 4095).astype(
            np.uint16
        )
        name = f"enroll-{touch}.pgm"
        write_pgm(directory / name, pixels, binary=bool(touch % 2))
        groups.append([name])
    probes = []
    raw_probes = {
        "genuine": np.clip(
            1500
            + np.roll(enrolled, (1, -1), axis=(0, 1))
            + rng.normal(0, 22, (80, 64)),
            0,
            4095,
        ).astype(np.uint16),
        "wrong": np.clip(1500 + other + rng.normal(0, 22, (80, 64)), 0, 4095).astype(
            np.uint16
        ),
        "blank": calibration,
        "noise": np.clip(1500 + rng.normal(0, 100, (80, 64)), 0, 4095).astype(
            np.uint16
        ),
    }
    for label, pixels in raw_probes.items():
        name = f"probe-{label}.pgm"
        write_pgm(directory / name, pixels)
        probes.append({"id": label, "label": label, "frames": [name]})
    manifest = {
        "kind": "synthetic-10px-ridge-controls-not-human-accuracy",
        "calibration": "calibration.pgm",
        "enrollment": groups,
        "probes": probes,
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def input_and_guard_checks(directory, factory):
    frame = np.arange(5120, dtype=np.uint16).reshape(80, 64) % 4096
    for binary in (False, True):
        path = directory / "roundtrip.pgm"
        write_pgm(path, frame, binary=binary)
        np.testing.assert_array_equal(read_pgm(path), frame)
    path.write_bytes(b"P5\n64 80\n4095\n\0")
    try:
        read_pgm(path)
    except ValueError:
        pass
    else:
        raise AssertionError("Truncated binary image accepted")
    engine = factory()
    buffer = GuardedBuffer(engine, bytes(4))
    engine.u.mem_write(buffer.address + 4, b"\0")
    try:
        buffer.check()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Buffer guard did not detect overwrite")
    processor = VendorPreprocessor(engine, np.full((80, 64), 1500, dtype=np.uint16))
    for invalid in (
        np.zeros((64, 80), dtype=np.uint16),
        np.full((80, 64), 4096),
        np.full((80, 64), 1500.5),
    ):
        try:
            processor.process(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed raw input accepted")
    return {
        "pgm_roundtrip_p2_p5": True,
        "truncated_input_rejected": True,
        "guard_overwrite_detected": True,
        "invalid_raw_input_rejected": True,
    }


def calibration_state_checks(dataset, factory):
    background = dataset["calibration"]
    raw = dataset["probes"][0]["frames"][0]
    processor = VendorPreprocessor(factory(), background)
    before = processor.process(raw)
    assert before["return_code"] == 0
    state = processor.save_state()
    restored = VendorPreprocessor(factory(), background, calibration_state=state)
    after = restored.process(raw)
    assert after == before, "Restored vendor state changed the synthetic output"
    try:
        VendorPreprocessor(factory(), background, calibration_state=state[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong-size calibration state accepted")
    for index in (0, 0x22490):
        damaged = bytearray(state)
        damaged[index] ^= 1
        try:
            VendorPreprocessor(factory(), background, calibration_state=bytes(damaged))
        except RuntimeError as error:
            assert "rejected with 0x80" in str(error), error
        else:
            raise AssertionError(
                "Corrupt/version-mismatched calibration state accepted"
            )
    return {
        "calibration_state_bytes": len(state),
        "saved_state_sha256": hashlib.sha256(state).hexdigest(),
        "save_load_output_identical": True,
        "wrong_size_rejected": True,
        "vendor_crc_and_version_rejections": True,
        "guarded_buffers": True,
    }, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--native-library", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Unreviewed engine DLL")
    if args.native_library:
        from native import NativeEngine

        factory = lambda: NativeEngine(DLL, args.native_library.resolve())
    else:
        from emulator import Engine

        factory = lambda: Engine(str(DLL))
    with tempfile.TemporaryDirectory(prefix="milan-prototype-") as temporary:
        directory = Path(temporary)
        path = build_dataset(directory)
        dataset = load_dataset(path)
        checks = input_and_guard_checks(directory, factory)
        checks["calibration_state"], state = calibration_state_checks(dataset, factory)
        results = compare(dataset, factory)
        (directory / "calibration-state.bin").write_bytes(state)
        manifest = json.loads(path.read_text())
        manifest["calibration_state"] = "calibration-state.bin"
        path.write_text(json.dumps(manifest))
        restored = run_method(load_dataset(path), "vendor", factory)
        assert restored == results["vendor"], "State-loaded manifest replay differs"
        checks["calibration_state"]["manifest_replay_identical"] = True
    vendor = results["vendor"]
    assert vendor["enrollment_complete"], "Vendor synthetic enrollment failed"
    assert vendor["probe_counts"]["genuine"]["matched"] == 1, (
        "Vendor positive control failed"
    )
    for label in ("wrong", "blank", "noise"):
        assert vendor["probe_counts"][label]["matched"] == 0, (
            f"Vendor {label} control matched"
        )
    assert not vendor["frame_errors"], "Vendor preprocessing returned errors"
    output = {
        "backend": "native-production-loader" if args.native_library else "emulated",
        "kind": "synthetic-controls-not-human-accuracy",
        "hardware_run": False,
        "checks": checks,
        "methods": results,
    }
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    for method, result in results.items():
        print(
            method,
            "enrollment",
            result["enrollment_complete"],
            result.get("probe_counts", {}),
            flush=True,
        )
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
