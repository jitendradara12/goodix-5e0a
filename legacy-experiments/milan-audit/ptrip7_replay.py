"""Reproduce issue #12's ptrip7 dataset and compare fixed preprocessing methods.

Runs offline through the native production loader, one process per experiment.
The archive's all-data FPN estimate is never used for a held-out comparison.
Vendor results use a clearly labeled enrollment-only proxy, NOT a measured
no-finger background. They cannot establish the calibrated vendor path's limit.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from native import NativeEngine
from replay import box_mean, normalize, read_pgm, run_method
from run import DLL, DLL_SHA256

ARCHIVE_SHA256 = "328c3c7a79bf8338b52e565ec743c713ab7d55c66a805cd300583c696c4f55c0"
SOURCE = (
    "https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6249714294"
)
METHODS = ("current", "bandpass", "fpn-bandpass-s0-std60", "vendor-enrollment-estimate")
WINDOWS_METHOD = "vendor-windows-cache"
CACHE_FPN_METHODS = ("cache-fpn-bandpass-std60", "cache-fpn-scaled-bandpass-std60")


def frames(directory):
    return sorted(directory.glob("*_raw.pgm"))


def selection(root, scenario):
    if scenario == "labeled":
        # touch_01 precedes enrollment activation; journal has 12 checks for 02..13.
        enrollment = [frames(root / "enroll" / f"touch_{i:02}") for i in range(2, 14)]
        probes = []
        for directory, label in (("genuine", "genuine"), ("impostor", "wrong")):
            for touch in sorted((root / directory).glob("touch_*")):
                probes.append(
                    {
                        "id": f"{directory}/{touch.name}",
                        "label": label,
                        "paths": frames(touch),
                    }
                )
        policy = "driver"
    else:
        all_frames = frames(root / "session1_left_little_aborted_enroll")
        if len(all_frames) != 96:
            raise ValueError("Expected 96 frames in session 1")
        touches = [all_frames[i : i + 4] for i in range(0, 96, 4)]
        training, test = (
            (touches[:12], touches[12:])
            if scenario == "fold1"
            else (touches[12:], touches[:12])
        )
        enrollment = training
        probes = [
            {
                "id": f"touch_{(int(p.stem.split('_')[1]) + 3) // 4:02}/{p.name}",
                "label": "genuine",
                "paths": [p],
            }
            for group in test
            for p in group
        ]
        policy = "single-frame"
    if len(enrollment) != 12 or any(len(group) != 4 for group in enrollment):
        raise ValueError("Expected 12 complete enrollment touch groups")
    enrollment_paths = {p for group in enrollment for p in group}
    test_paths = {p for probe in probes for p in probe["paths"]}
    if enrollment_paths & test_paths:
        raise ValueError("Train/test path overlap")
    # Distinct paths alone do not establish independence.
    train_hashes = {
        hashlib.sha256(p.read_bytes()).hexdigest() for p in enrollment_paths
    }
    test_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in test_paths}
    if train_hashes & test_hashes:
        raise ValueError("Train/test byte-identical frame overlap")
    dataset = {
        "calibration": None,
        "enrollment": [[read_pgm(p) for p in group] for group in enrollment],
        "probes": [
            {
                "id": p["id"],
                "label": p["label"],
                "frames": [read_pgm(f) for f in p["paths"]],
            }
            for p in probes
        ],
    }
    provenance = {
        "enrollment": [
            [str(p.relative_to(root)) for p in group] for group in enrollment
        ],
        "probes": [
            {
                "id": p["id"],
                "label": p["label"],
                "frames": [str(f.relative_to(root)) for f in p["paths"]],
            }
            for p in probes
        ],
        "input_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(enrollment_paths | test_paths)
        },
        "probe_policy": policy,
        "calibration": "none; optional proxy derived only from listed enrollment frames",
    }
    return dataset, policy, provenance


def estimate_fpn(enrollment):
    residuals = [
        raw.astype(np.float32) - box_mean(raw, 1)
        for group in enrollment
        for raw in group
    ]
    return np.mean(residuals, axis=0, dtype=np.float64).astype(np.float32)


def fpn_bandpass(raw, fpn):
    corrected = raw.astype(np.float32) - fpn
    residual = corrected - box_mean(corrected, 5)
    rms = float(np.sqrt(np.float32(np.mean(residual.astype(np.float64) ** 2))))
    if rms < 0.5:
        return bytes(5120)
    values = np.float32(128) + residual * np.float32(60 / rms)
    rounded = np.copysign(np.floor(np.abs(values) + np.float32(0.5)), values)
    return np.clip(rounded, 0, 255).astype(np.uint8).tobytes()


def synthetic_controls(dataset):
    """Processing controls, reported separately from real wrong-finger attempts."""
    rng = np.random.default_rng(20261018)
    fpn = estimate_fpn(dataset["enrollment"])
    noise = rng.normal(0, 80, (80, 64))
    controls = (
        ("flat2048", "blank", np.full((80, 64), 2048)),
        ("independent-noise-sigma80", "noise", 2048 + noise),
        ("estimated-fixed-pattern-plus-noise", "noise", 2048 + fpn + noise),
    )
    for name, label, raw in controls:
        raw = np.clip(np.floor(raw + 0.5), 0, 4095).astype(np.uint16)
        dataset["probes"].append(
            {"id": f"synthetic/{name}", "label": label, "frames": [raw]}
        )
    return "PCG64 seed 20261018; flat, Gaussian sigma80, enrollment-FPN + same noise"


def inventory(root):
    counts = {}
    mismatches = []
    residuals = []
    inputs = {}
    for path in sorted(root.rglob("*_raw.pgm")):
        raw = read_pgm(path)
        method = "current" if "session1_" in str(path.relative_to(root)) else "bandpass"
        saved = (
            read_pgm(path.with_name(path.name.replace("_raw", "_norm")), 255)
            .astype(np.uint8)
            .tobytes()
        )
        if normalize(raw, method) != saved:
            mismatches.append(str(path.relative_to(root)))
        counts[method] = counts.get(method, 0) + 1
        residuals.append(raw.astype(np.float32) - box_mean(raw, 1))
        inputs[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    if counts != {"bandpass": 117, "current": 96} or mismatches:
        raise ValueError(f"Dataset/normalization mismatch: {counts}, {mismatches}")
    fpn = np.mean(residuals, axis=0)
    correlations = [float(np.corrcoef(fpn.ravel(), r.ravel())[0, 1]) for r in residuals]
    return {
        "source": SOURCE,
        "archive_sha256": ARCHIVE_SHA256,
        "normalized_frames_byte_identical": counts,
        "raw_frame_count": len(residuals),
        "raw_sha256": inputs,
        "fpn_residual_std": float(fpn.std()),
        "residual_correlation_min_mean_max": [
            min(correlations),
            float(np.mean(correlations)),
            max(correlations),
        ],
        "labeled_genuine_expected_matches": [2, 3, 4, 5, 7],
        "labeled_wrong_expected_matches": [],
        "limitations": [
            "Five successful genuine touches contain only frame 1; later frames were never captured.",
            "The supplied FPN uses all 213 frames including probes; it is excluded from candidate evaluation.",
            "No measured no-finger background or native calibration data was supplied.",
            "Only one person and two fingers; wrong-finger rejection here is not a general error-rate estimate.",
            "Session 1's folds measure 96 correlated frame probes, not 96 independent touches.",
        ],
    }


def worker(args):
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Unreviewed engine DLL")
    dataset, policy, provenance = selection(args.dataset, args.scenario)
    if args.scenario == "labeled":
        provenance["synthetic_controls"] = synthetic_controls(dataset)
    class AuditEngine(NativeEngine):
        def image(self, pixels, w=64, h=80, bits=8):
            if args.matcher_layout == "profile10":
                pixels = np.frombuffer(pixels, dtype=np.uint8).reshape(80, 64).T.copy().tobytes()
                w, h = 80, 64
            return super().image(pixels, w, h, bits)

    factory = lambda: AuditEngine(DLL, args.native_library)
    provenance["matcher_layout"] = args.matcher_layout
    normalizer = None
    method = args.method
    if method in (WINDOWS_METHOD, *CACHE_FPN_METHODS):
        if args.windows_calibration is None:
            raise ValueError("vendor-windows-cache requires --windows-calibration")
        root = args.windows_calibration.resolve()
        metadata_path = root / "calibration.json"
        metadata = json.loads(metadata_path.read_text())
        if metadata.get("format") != "goodix-windows-calibration-export-v1":
            raise ValueError("Unknown Windows calibration export format")
        exported = metadata.get("export_sha256", {})
        if "background_raw.pgm" not in exported:
            raise ValueError("Windows export is missing its background checksum")
        for name, expected in exported.items():
            if name not in {"background_raw.pgm", "calibration_state.bin"}:
                raise ValueError("Unexpected file in Windows calibration export")
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                raise ValueError(
                    f"Windows calibration export checksum mismatch: {name}"
                )
        dataset["calibration"] = read_pgm(root / "background_raw.pgm")
        if args.windows_background_layout == "transpose":
            dataset["calibration"] = np.ascontiguousarray(
                dataset["calibration"].reshape(64, 80).T
            )
        dataset["calibration_state"] = (
            (root / "calibration_state.bin").read_bytes()
            if "calibration_state.bin" in exported and args.windows_state == "load"
            else None
        )
        provenance["calibration"] = {
            "source": "Windows cached ImageBase and optional CaliData; unit/configuration provenance must be confirmed",
            "export_metadata_sha256": hashlib.sha256(
                metadata_path.read_bytes()
            ).hexdigest(),
            "source_sha256": metadata["source_sha256"],
            "export_sha256": exported,
            "calibration_state_loaded": dataset["calibration_state"] is not None,
            "background_layout": args.windows_background_layout,
            "vendor_layout": args.vendor_layout,
        }
        if method in CACHE_FPN_METHODS:
            background = dataset["calibration"].astype(np.float32)
            fpn = background - box_mean(background, 1)
            gain = 1.0
            if method == "cache-fpn-scaled-bandpass-std60":
                # Fit one scalar on enrollment only. No probe labels/scores enter.
                target = estimate_fpn(dataset["enrollment"]).astype(np.float64)
                x = fpn.astype(np.float64) - np.mean(fpn, dtype=np.float64)
                target -= target.mean()
                denominator = float(np.sum(x * x))
                if denominator <= 0:
                    raise ValueError("No background residual variance for gain fit")
                gain = float(np.sum(x * target) / denominator)
                if not np.isfinite(gain) or gain <= 0:
                    raise ValueError("Invalid fitted calibration gain")
            provenance["background_fpn_gain"] = gain
            provenance["background_fpn_gain_fit"] = (
                "single least-squares scalar fitted to 48 enrollment residuals only"
                if method == "cache-fpn-scaled-bandpass-std60" else "fixed unit gain"
            )
            normalizer = lambda raw: fpn_bandpass(raw, fpn * np.float32(gain))
            method = "cache-fpn"
        else:
            method = "vendor"
    if method in {"fpn-bandpass-s0-std60", "vendor-enrollment-estimate"}:
        fpn = estimate_fpn(dataset["enrollment"])
        provenance["fpn_estimator"] = "mean 3x3 residual of enrollment frames only"
        provenance["fpn_std"] = float(fpn.std())
        if method == "fpn-bandpass-s0-std60":
            normalizer = lambda raw: fpn_bandpass(raw, fpn)
        else:
            dataset["calibration"] = np.clip(np.floor(fpn + 2048.5), 0, 4095).astype(
                np.uint16
            )
            provenance["calibration"] = (
                "enrollment-only residual estimate + 2048; exploratory proxy, not measured background"
            )
            method = "vendor"
    result = run_method(
        dataset, method, factory, normalizer=normalizer, probe_policy=policy,
        vendor_layout=args.vendor_layout,
    )
    output = {
        "hardware_run": False,
        "backend": "native-production-loader",
        "scenario": args.scenario,
        "method": args.method,
        "dll_sha256": DLL_SHA256,
        "provenance": provenance,
        "result": result,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"{args.scenario}-{args.method}.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                "scenario": args.scenario,
                "method": args.method,
                "enrollment_complete": result["enrollment_complete"],
                "counts": result.get("probe_counts"),
                "failed_touch": result.get("failed_touch"),
                "frame_error_codes": sorted(set(result.get("frame_errors", []))),
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--native-library", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=("labeled", "fold1", "fold2"))
    parser.add_argument("--method", choices=(*METHODS, WINDOWS_METHOD, *CACHE_FPN_METHODS))
    parser.add_argument("--windows-background-layout", choices=("as-exported", "transpose"), default="as-exported")
    parser.add_argument("--windows-state", choices=("load", "omit"), default="load")
    parser.add_argument("--vendor-layout", choices=("legacy", "profile10"), default="legacy")
    parser.add_argument("--matcher-layout", choices=("canonical", "profile10"), default="canonical",
                        help="Offline geometry diagnostic only; production remains 64x80")
    parser.add_argument(
        "--windows-calibration",
        type=Path,
        help="Extracted calibration-export directory from this same sensor",
    )
    args = parser.parse_args()
    args.dataset = args.dataset.resolve()
    args.native_library = args.native_library.resolve()
    args.out_dir = args.out_dir.resolve()
    if args.scenario:
        worker(args)
        return
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "inventory.json").write_text(
        json.dumps(inventory(args.dataset), indent=2) + "\n"
    )
    for scenario in ("labeled", "fold1", "fold2"):
        methods = (*METHODS, WINDOWS_METHOD) if args.windows_calibration else METHODS
        for method in methods:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--dataset",
                str(args.dataset),
                "--native-library",
                str(args.native_library),
                "--out-dir",
                str(args.out_dir),
                "--scenario",
                scenario,
                "--windows-background-layout", args.windows_background_layout,
                "--windows-state", args.windows_state,
                "--vendor-layout", args.vendor_layout,
                "--matcher-layout", args.matcher_layout,
                "--method",
                method,
            ]
            if args.windows_calibration:
                command += [
                    "--windows-calibration",
                    str(args.windows_calibration.resolve()),
                ]
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
