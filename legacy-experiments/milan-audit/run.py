"""Reproduce the October 18 evidence audit without a sensor or Windows.

Only synthetic images/templates recovered from Git are used. No captures,
templates, keys, or other data are written to the sensor or system services.
"""

import argparse
import hashlib
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from preprocess import VendorPreprocessor

ROOT = Path(__file__).resolve().parents[2]
DLL = ROOT / "windows_driver/GoodixEngineAdapter.dll"
DLL_SHA256 = "9990ab24af01b8c5c575c73cf7a95a7d675655adfb4183b6c030de2912ec23de"
ARCHIVE = "e6f67c7^"


def archived(path):
    return subprocess.check_output(["git", "show", f"{ARCHIVE}:{path}"], cwd=ROOT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture_provenance():
    """Regenerate files using the checked-in generator's actual CLI."""
    result = {}
    for seed, filename in [
        (67, "live_dense_pad.pgm"),
        (68, "live_dense_pad_seed68.pgm"),
    ]:
        data = archived(f"legacy-experiments/{filename}")
        with tempfile.TemporaryDirectory(prefix="milan-synthetic-") as directory:
            out = Path(directory) / "generated.pgm"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "legacy-experiments/gen_dense_live.py"),
                    "--seed",
                    str(seed),
                    "--out",
                    str(out),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            regenerated = out.read_bytes()
        assert data == regenerated, "Archived fixture no longer matches generator"
        result[str(seed)] = {
            "sha256": digest(data),
            "synthetic_identity_confirmed": True,
        }
    return result


def read_pgm(data):
    parts = data.split()
    assert parts[:4] == [b"P2", b"64", b"80", b"4095"]
    return np.array([int(v) for v in parts[4:]], dtype=np.float32).reshape(80, 64)


def normalize(raw):
    """Driver's clipped-edge 3x3 residual, midpoint 128, gain 1.5.

    np.rint uses ties-to-even; C roundf uses ties-away-from-zero. Use the
    latter here so fixtures exercise the same byte values as the driver.
    """
    padded = np.pad(raw, 1)
    counts = np.pad(np.ones_like(raw), 1)
    mean = sum(padded[y : y + 80, x : x + 64] for y in range(3) for x in range(3))
    mean /= sum(counts[y : y + 80, x : x + 64] for y in range(3) for x in range(3))
    values = np.float32(128) + (raw - mean) * np.float32(1.5)
    rounded = np.copysign(np.floor(np.abs(values) + np.float32(0.5)), values)
    return np.clip(rounded, 0, 255).astype(np.uint8).tobytes()


def u64(engine, address):
    return struct.unpack("<Q", engine.u.mem_read(address, 8))[0]


def identify(engine, template, pixels):
    image = engine.image(pixels)
    index = engine.put(struct.pack("<i", -999))
    score = engine.put(struct.pack("<i", -999))
    details = engine.put(bytes(8))
    templates = engine.put(struct.pack("<Q", template))
    result = engine.call(
        "identifyImage", [image, 0, templates, 1, index, score, details, 0, 0, 0, 0]
    )
    signed_score = struct.unpack("<i", engine.u.mem_read(score, 4))[0]
    return {
        "return_code": result & 0xFFFFFFFF,
        "matched_index": struct.unpack("<i", engine.u.mem_read(index, 4))[0],
        "signed_score": signed_score,
        "current_driver_pts": max(signed_score, 0),
        "details": list(struct.unpack("<II", engine.u.mem_read(details, 8))),
    }


def matching_and_lifetime():
    from emulator import Engine

    engine = Engine(str(DLL))
    assert engine.call("ppp_param_init", [10]) == 0
    blob = archived("legacy-experiments/milan_dense_pad.tpl")
    output = engine.put(bytes(8))
    assert engine.call("templateUnPack", [engine.put(blob), len(blob), 0, output]) == 0
    template = u64(engine, output)
    patterns = {
        "seed67": normalize(
            read_pgm(archived("legacy-experiments/live_dense_pad.pgm"))
        ),
        "seed68": normalize(
            read_pgm(archived("legacy-experiments/live_dense_pad_seed68.pgm"))
        ),
        "flat": bytes([128]) * 5120,
        "white_noise": np.random.default_rng(123)
        .integers(0, 256, 5120, dtype=np.uint8)
        .tobytes(),
        "sine_period10": np.clip(
            128 + 110 * np.sin(np.mgrid[:80, :64][0] * 2 * np.pi / 10), 0, 255
        )
        .astype(np.uint8)
        .tobytes(),
    }
    outcomes = {}
    for name, pixels in patterns.items():
        _, quality_overlap, _ = engine.quality(pixels)
        outcomes[name] = {
            "quality": quality_overlap[0],
            "overlap": quality_overlap[1],
            **identify(engine, template, pixels),
        }
    # Independent saved-log anchors from ticket 72; fail if emulation disagrees.
    assert (outcomes["seed67"]["quality"], outcomes["seed67"]["overlap"]) == (18, 98)
    assert (outcomes["seed68"]["quality"], outcomes["seed68"]["overlap"]) == (19, 100)
    assert outcomes["seed67"]["signed_score"] == 100
    assert outcomes["seed67"]["matched_index"] == 0
    assert outcomes["seed68"]["matched_index"] == -1
    assert outcomes["flat"]["matched_index"] == -1
    assert outcomes["white_noise"]["matched_index"] == -1
    # Successful identify retains the INNER template at this binary-specific RVA.
    identify(engine, template, patterns["seed67"])
    inner = u64(engine, template)
    last_match_address = engine.base + 0x135C48
    assert u64(engine, last_match_address) == inner
    engine.call("templateDelete", [template])
    lifetime = {
        "root_freed": template in engine.freed,
        "inner_freed": inner in engine.freed,
        "last_match_global_still_references_freed_inner": u64(
            engine, last_match_address
        )
        == inner,
    }
    assert all(lifetime.values())
    return outcomes, lifetime


def vendor_preprocessor():
    from emulator import Engine

    engine = Engine(str(DLL))
    assert engine.call("ppp_param_init", [10]) == 0
    quality = engine.put(bytes(8))
    output = engine.image(bytes(5120))
    engine.u.mem_write(output + 20, struct.pack("<I", 5120))
    rows = np.mgrid[:80, :64][0]
    raw = (1500 + 300 * np.sin(rows * 2 * np.pi / 10)).astype("<u2")
    source = engine.image(raw.tobytes(), bits=16)
    engine.u.mem_write(source + 20, struct.pack("<I", raw.nbytes))
    # Second argument: enrollment-purpose flag. Third: optional 0x4c98-byte
    # feature output. Disable that output instead of guessing a buffer size.
    purpose = engine.put(bytes(4))
    args = [source, purpose, 0, output, quality, 0, 0]
    uncalibrated = engine.call("preprocessor", args)
    assert uncalibrated == 0x80
    flat = np.full((80, 64), 1500, dtype="<u2")
    processor = VendorPreprocessor(engine, flat)
    processed = processor.process(raw)
    pixels = processed["pixels"]
    array = np.frombuffer(pixels, dtype=np.uint8)
    assert processed["return_code"] == 0 and array.std() > 1
    _, qo, _ = engine.quality(pixels)
    return {
        "without_calibration_return": uncalibrated,
        "calibration_initialization_return": 0,
        "preprocessor_return": processed["return_code"],
        "output_min": int(array.min()),
        "output_max": int(array.max()),
        "output_std": float(array.std()),
        "quality": qo[0],
        "overlap": qo[1],
        "buffers_checked": True,
        "optional_feature_output": False,
        "boundary": "Synthetic flat calibration and sine input; enrollment-purpose flag 0, optional feature output NULL; no accuracy claim",
    }


def windows_calls():
    import pefile

    data = archived("legacy-experiments/windows_driver/wbdi.dll")
    pe = pefile.PE(data=data)
    edges = {
        0x36E64: (0xC8450, "preprocess_init_calidata"),
        0x36F0A: (0xC84F0, "preprocess_load_calidata"),
        0x371BE: (0xC8D80, "preprocessor_init"),
        0x31466: (0xC8B10, "preprocessor"),
    }
    calls = []
    for call, (target, name) in edges.items():
        instruction = pe.get_data(call, 5)
        assert instruction[0] == 0xE8
        assert call + 5 + struct.unpack("<i", instruction[1:])[0] == target
        calls.append({"call_rva": hex(call), "target_rva": hex(target), "target": name})
    return {
        "sha256": digest(data),
        "direct_calls": calls,
        "boundary": "Calls are present in archived vendor code; not a new trace of a running Windows session",
    }


def filter_response():
    rows = []
    for period in [5, 8, 10]:
        omega = 2 * math.pi / period
        mean3 = (1 + 2 * math.cos(omega)) / 3
        mean11 = sum(math.cos(k * omega) for k in range(-5, 6)) / 11
        current = 1 - mean3
        bandpass = mean3 * (1 - mean11)
        rows.append(
            {
                "ridge_period_px": period,
                "current_amplitude": current,
                "bandpass_amplitude": bandpass,
                "bandpass_to_current": bandpass / current,
            }
        )
    return {
        "boundary": "Interior axis-aligned sinusoid, before gain/clipping or target-std scaling",
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    assert digest(DLL.read_bytes()) == DLL_SHA256, (
        "Unreviewed DLL: RVA assertions are version-specific"
    )
    provenance = fixture_provenance()
    outcomes, lifetime = matching_and_lifetime()
    result = {
        "engine_sha256": DLL_SHA256,
        "method": "Real x86-64 DLL instructions in Unicorn; malloc/free/memset shims; diagnostic logger and cookie check bypassed; DllMain omitted",
        "synthetic_fixture_provenance": provenance,
        "matching": outcomes,
        "post_match_template_lifetime": lifetime,
        "vendor_preprocessor_smoke": vendor_preprocessor(),
        "archived_windows_calls": windows_calls(),
        "filter_response": filter_response(),
        "hardware_run": False,
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
