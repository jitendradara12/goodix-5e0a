"""Package the offline Linux check, verifying every required source is present."""

import argparse
import hashlib
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path("legacy-experiments/milan-audit")
REQUIRED = {
    Path("LICENSE"),
    Path("windows_driver/GoodixEngineAdapter.dll"),
    Path("libfprint-driver/goodix_milan.c"),
    Path("libfprint-driver/goodix_milan.h"),
    Path("legacy-experiments/gen_dense_live.py"),
    Path("docs/ptrip7-replay-2026-10-18.md"),
    Path("docs/windows-calibration-2026-10-18.md"),
    Path("tools/extract_goodix_calibration.py"),
    Path("tools/CALIBRATION.md"),
    PROBE / "ptrip7-results/summary.json",
    PROBE / "ptrip7-instrumentation.patch",
    PROBE / "ptrip7-driver-ties.patch",
    *(
        PROBE / name
        for name in (
            "native_probe.c",
            "build-native.sh",
            "check-linux.sh",
            "native.py",
            "images.py",
            "selfcheck.py",
            "preprocess.py",
            "replay.py",
            "ptrip7_replay.py",
            "calibration_contract.py",
            "run.py",
        )
    ),
}


def make_bundle(output):
    output = Path(output).resolve()
    files = set(REQUIRED)
    files.update(
        path.relative_to(ROOT)
        for path in (ROOT / PROBE).rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".sh", ".md", ".txt", ".json", ".c", ".log", ".patch"}
    )
    files.add(Path("docs/evidence-review-2026-10-18.md"))
    for relative in files:
        if not (ROOT / relative).is_file():
            raise FileNotFoundError(f"Required bundle input missing: {relative}")
    with tempfile.TemporaryDirectory(prefix="goodix-bundle-") as temporary:
        stage = Path(temporary) / "goodix-milan-prototype"
        stage.mkdir()
        for relative in sorted(files):
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        (stage / "check-linux.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'cd "$(dirname "${BASH_SOURCE[0]}")"\n'
            "exec bash legacy-experiments/milan-audit/check-linux.sh\n"
        )
        (stage / "START-HERE.txt").write_text(
            "GOODIX OFFLINE PROTOTYPE CHECK\n\n"
            "Extract this folder on your x86-64 Linux laptop.\n"
            "Open a terminal in the extracted folder and run:\n\n"
            "    bash check-linux.sh\n\n"
            "Send back probe-output/linux-selfcheck.json and probe-output/check.log.\n"
            "If it fails, send the terminal output and check.log if available.\n\n"
            "This uses generated test images. It does not install or change your\n"
            "driver, restart fprintd, or access the sensor. No root is needed.\n"
            "On NixOS, build dependencies may be downloaded into a temporary shell.\n"
        )
        manifest = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest.append(f"{sha}  {path.relative_to(stage)}\n")
        (stage / "SHA256SUMS").write_text("".join(manifest))
        with tarfile.open(output, "w:gz") as archive:
            archive.add(stage, arcname=stage.name)
    verify_bundle(output)
    return output


def verify_bundle(path):
    with tarfile.open(path) as archive:
        members = {
            entry.name: archive.extractfile(entry).read()
            for entry in archive.getmembers()
            if entry.isfile()
        }
    prefix = "goodix-milan-prototype/"
    for relative in REQUIRED:
        if prefix + str(relative) not in members:
            raise ValueError(f"Required source missing from archive: {relative}")
    for line in members[prefix + "SHA256SUMS"].decode().splitlines():
        expected, relative = line.split("  ", 1)
        actual = hashlib.sha256(members[prefix + relative]).hexdigest()
        if actual != expected:
            raise ValueError(f"Bundle checksum mismatch: {relative}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = make_bundle(args.output)
    print(f"Built and verified {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
