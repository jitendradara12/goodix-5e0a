"""Build and supervise an isolated current/Jet-Soup hardware test.

No installed library, permanent unit, account, PAM file or existing print is
changed. A root-only runtime drop-in binds a new storage directory over the
daemon's /var/lib/fprint. Its identity and loaded library are verified before
enrollment. An independent systemd recovery timer bounds interruption damage.
"""

import argparse
import datetime as dt
import hashlib
import io
import json
import mmap
import os
from pathlib import Path
import platform
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("/run/goodix-5e0a-experiment")
DRIVER_BASE = Path("/var/lib")
DROPIN = Path("/run/systemd/system/fprintd.service.d/zzzz-goodix-experiment.conf")
REPORTS = Path("/var/tmp/goodix-5e0a-reports")
FINGER = "right-index-finger"
REPORT_FILES = ("session.json", "events.jsonl", "driver.txt")


def command(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)


def output(args):
    return command(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def property_value(name):
    return output(["systemctl", "show", "fprintd.service", "-p", name, "--value"])


def interruption(signum, _frame):
    raise KeyboardInterrupt(f"signal {signum}")


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def daemon_path():
    match = re.search(r"(?:^|[ {])path=([^ ;}]+)", property_value("ExecStart"))
    if not match or not Path(match[1]).is_file():
        raise RuntimeError("Cannot identify fprintd's executable; send this error, do not modify the service")
    return match[1]


def preflight():
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This test requires the x86-64 Linux fingerprint laptop")
    for tool in ("systemctl", "systemd-run", "journalctl", "fprintd-enroll", "fprintd-verify", "git", "bash", "sudo"):
        if not shutil.which(tool):
            raise RuntimeError(f"Missing {tool}; send this error rather than installing a workaround")
    if property_value("LoadState") != "loaded":
        raise RuntimeError("fprintd.service is not loaded")
    if property_value("User") not in ("", "root"):
        raise RuntimeError("This experiment currently supports a root-run fprintd only")
    if property_value("BindPaths") or property_value("BindReadOnlyPaths"):
        raise RuntimeError("Existing service mount overrides need review before this experiment")
    if RUNTIME.exists() or DROPIN.exists() or DROPIN.is_symlink():
        raise RuntimeError("An experiment is already present. Run: bash tools/test-hardware.sh --restore")
    daemon_path()


def isolation_probe(directory):
    """An actual systemd namespace probe, without starting fprintd or USB code."""
    prints = directory / "prints"
    prints.mkdir(mode=0o700, exist_ok=True)
    nonce = secrets.token_hex(12)
    (prints / ".isolation-token").write_text(nonce)
    code = ("import os,pathlib,sys; p=pathlib.Path('/var/lib/fprint'); "
            "q=pathlib.Path(sys.argv[1]); "
            "assert (p.stat().st_dev,p.stat().st_ino)==(q.stat().st_dev,q.stat().st_ino); "
            "assert (p/'.isolation-token').read_text()==sys.argv[2]; "
            "(p/'.probe-write').write_text('private')")
    command(["systemd-run", "--quiet", "--wait", "--pipe", "--collect",
             "--unit=goodix-isolation-" + nonce,
             "--property=Type=exec", "--property=ProtectSystem=strict",
             f"--property=BindPaths={prints}:/var/lib/fprint",
             "--property=ReadWritePaths=/var/lib/fprint", sys.executable, "-c", code, prints, nonce])
    if (prints / ".probe-write").read_text() != "private":
        raise RuntimeError("Storage namespace probe did not reach private storage")
    (prints / ".probe-write").unlink()
    (prints / ".isolation-token").unlink()


def driver_directory(nonce):
    if not re.fullmatch(r"[0-9a-f]{16}", nonce):
        raise RuntimeError("Invalid experiment identifier")
    return DRIVER_BASE / ("goodix-5e0a-experiment-" + nonce)


def executable_mapping_probe(library):
    """Check executable file mappings without loading code or opening USB."""
    try:
        with library.open("rb") as source:
            with mmap.mmap(source.fileno(), 0, flags=mmap.MAP_PRIVATE,
                           prot=mmap.PROT_READ | mmap.PROT_EXEC):
                pass
    except OSError as error:
        raise RuntimeError(f"Test library cannot be mapped executable at {library}; "
                           "no service change was made") from error


def dropin_text(daemon, nonce):
    driver = driver_directory(nonce)
    return (f"# goodix disposable experiment {nonce}\n[Service]\n"
            f"Environment=LD_LIBRARY_PATH={driver}/lib\n"
            f"Environment=GOODIX_ENGINE_DLL_PATH={driver}/GoodixEngineAdapter.dll\n"
            "Environment=G_MESSAGES_DEBUG=all\n"
            "Environment=STATE_DIRECTORY=/var/lib/fprint\n"
            "UnsetEnvironment=GOODIX_5E0A_NATIVE_RASTER GOODIX_5E0A_DUMP_DIR GOODIX_REPLAY_DIR GOODIX_PROBE_FILE GOODIX_VENDOR_TAIL GOODIX_QUALITY_SWEEP\n"
            f"BindPaths={RUNTIME}/prints:/var/lib/fprint\n"
            "ReadWritePaths=/var/lib/fprint\n"
            f"ExecStart=\nExecStart={daemon} --no-timeout\n")


def verify_runtime(pid, driver):
    proc = Path("/proc") / str(pid)
    expected, observed = (RUNTIME / "prints").stat(), (proc / "root/var/lib/fprint").stat()
    if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
        raise RuntimeError("Live daemon storage is not isolated; aborting before enrollment")
    env = dict(item.split(b"=", 1) for item in (proc / "environ").read_bytes().split(b"\0") if b"=" in item)
    for key, value in {"STATE_DIRECTORY": "/var/lib/fprint",
                       "LD_LIBRARY_PATH": str(driver / "lib")}.items():
        if env.get(key.encode()) != value.encode():
            raise RuntimeError(f"Driver process is missing expected {key}")
    maps = (proc / "maps").read_text()
    if str(driver / "lib/libfprint-2.so") not in maps:
        raise RuntimeError("Daemon did not load the experimental libfprint; aborting")
    if str(driver / "GoodixEngineAdapter.dll") != env.get(b"GOODIX_ENGINE_DLL_PATH", b"").decode():
        raise RuntimeError("Daemon is missing its test engine path")


class Client:
    def __init__(self, args, event):
        self.event = event
        self.lines = []
        self.pending = queue.Queue()
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, start_new_session=True)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for line in self.process.stdout:
            self.pending.put(line.rstrip())

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                line = self.pending.get(timeout=min(.1, max(.001, end - time.monotonic())))
            except queue.Empty:
                continue
            self.lines.append(line)
            # Client output is displayed, but only enumerated result tokens are saved.
            print(line, flush=True)
            match = re.search(r"(?:Enroll|Verify) result: ([a-z-]+)(?: \((done|not done)\))?", line)
            if match:
                self.event("client-result", status=match[1], done=match[2])

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.pump(.05)

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while self.process.poll() is None and time.monotonic() < end:
            self.pump(.2)
        self.reader.join(timeout=1)
        self.pump(.05)
        if self.process.poll() is None:
            raise RuntimeError("Fingerprint client timed out")
        return self.process.returncode


def guided_test(event, clients):
    input("\nUse your RIGHT INDEX finger for this test. Keep it lifted. Press Enter to begin: ")
    enroll = Client(["fprintd-enroll", "-f", FINGER], event)
    clients.append(enroll)
    deadline = time.monotonic() + 30
    while not any("Enrolling " in line for line in enroll.lines):
        enroll.pump(.2)
        if enroll.process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("Enrollment did not start; no hardware verdict")
    event("hands off", duration_seconds=20)
    print("HANDS OFF: leave the sensor untouched for 20 seconds.", flush=True)
    enroll.pump(20)
    hands_off_results = [line for line in enroll.lines if "Enroll result:" in line]
    if hands_off_results:
        event("hands-off-activity", statuses=hands_off_results)
    if enroll.process.poll() is not None:
        raise RuntimeError("Enrollment ended during hands-off phase")
    event("holding", duration_seconds=20)
    before_hold = len(enroll.lines)
    print("HOLDING: press and hold your right index finger steadily for 20 seconds.", flush=True)
    enroll.pump(20)
    holding_advances = sum("Enroll result: enroll-stage-passed" in line or "Enroll result: enroll-completed" in line
                           for line in enroll.lines[before_hold:])
    event("holding-end")
    event("holding-advances", count=holding_advances)
    print("Now LIFT. Continue separate placements of that SAME finger until enrollment completes.", flush=True)
    rc = enroll.wait(480)
    if rc != 0 or "Enroll result: enroll-completed" not in enroll.lines:
        raise RuntimeError("Fresh enrollment did not complete")
    event("enrollment-completed")
    results = []
    for label in ("genuine", "wrong"):
        explanation = "that SAME right index finger" if label == "genuine" else "a DIFFERENT finger (not the enrolled index)"
        input(f"\nNext: five attempts using {explanation}. Lift between attempts. Press Enter: ")
        for attempt in range(1, 6):
            print(f"{label.upper()} {attempt}/5: lift, then touch with {explanation}.", flush=True)
            event("verify-start", label=label, attempt=attempt)
            client = Client(["fprintd-verify", "-f", FINGER], event)
            clients.append(client)
            client.wait(45)
            statuses = [line for line in client.lines if re.fullmatch(r"Verify result: verify-(?:match|no-match) \(done\)", line)]
            if len(statuses) != 1:
                raise RuntimeError("Verification did not produce one completed decision")
            matched = statuses[0] == "Verify result: verify-match (done)"
            results.append({"label": label, "attempt": attempt, "matched": matched})
            event("verify-end", **results[-1])
            if label == "wrong" and matched:
                return {"verdict": "falsified", "reason": "wrong-finger-matched", "attempts": results}
            time.sleep(2)
    verdict = "confirmed" if not hands_off_results and holding_advances == 1 and all(r["matched"] == (r["label"] == "genuine") for r in results) else "falsified"
    return {"verdict": verdict, "scope": "this unit and this guided run only",
            "attempts": results, "hands_off_activity": bool(hands_off_results), "holding_advances": holding_advances}


def filtered_journal(start):
    # Whitelist numerical summaries, never packet dumps, pixels, templates or keys.
    text = output(["journalctl", "-u", "fprintd.service", "--since", "@" + str(start),
                   "-o", "short-iso-precise", "--no-pager"])
    safe = []
    formats = (
        r"D32 touch confirmed: mask=0x[0-9a-fA-F]{2} energy=\d+",
        r"(?:best )?frame \d+/\d+: (?:declen=\d+ active=\d+ range=\d+ )?quality=\d+ overlap=\d+(?: range=\d+)? score-proxy=\d+(?: \(submitting\))?",
        r"row-major frame: active_px=\d+ nonzero=\d+ min=\d+ max=\d+ geometry=\d+x\d+ \(WxH\)",
        r"Milan verify: match=[01] pts=-?\d+",
        r"Milan identify: match=[01] idx=-?\d+ pts=-?\d+ \(gallery=\d+ usable=\d+\)",
        r"Milan enrollAddImage: res=-?\d+ enrolled=\d+ progress=\d+% \(stage \d+/\d+\)",
        r"Milan enrollment committed successfully! \(template size: \d+ bytes\)",
        r"enrollment stage \d+ waiting for next touch, arming FDT DOWN",
        r"enrollment touch rejected by Milan engine \(res=-?\d+\)",
        r"optimistic fast-path match on frame 1: pts=\d+, skipping remaining burst",
    )
    allowed = re.compile(r"5e0a (?:" + "|".join(formats) + ")")
    for line in text.splitlines():
        match = allowed.search(line)
        if match:
            # Drop hostname, process prefix and any unrecognized trailing data.
            prefix = line.split()[0] if re.match(r"\d{4}-\d{2}-\d{2}T", line) else ""
            safe.append((prefix + " " + match.group(0)).strip())
    return "\n".join(safe) + "\n"


def restore():
    """Idempotent recovery, also used by the independent 30-minute timer."""
    if not RUNTIME.exists():
        return
    if not (RUNTIME / "manifest.json").exists():
        # Recovery from interruption during the first atomic manifest write.
        if not DROPIN.exists() and {p.name for p in RUNTIME.iterdir()} <= {"manifest.json.tmp"}:
            shutil.rmtree(RUNTIME)
            return
        raise RuntimeError("Incomplete recovery manifest; preserving runtime files for review")
    manifest = json.loads((RUNTIME / "manifest.json").read_text())
    if DROPIN.exists() and DROPIN.read_text() != manifest["dropin"]:
        raise RuntimeError("Experiment drop-in changed; preserving it for manual review")
    if manifest.get("service_changed"):
        command(["systemctl", "stop", "fprintd.service"])
    if DROPIN.exists():
        DROPIN.unlink()
        try:
            DROPIN.parent.rmdir()
        except OSError:
            pass  # Keep any other runtime drop-ins.
    command(["systemctl", "daemon-reload"])
    if manifest.get("service_changed"):
        if manifest["was_active"]:
            command(["systemctl", "start", "fprintd.service"])
        elif property_value("ActiveState") != "inactive":
            raise RuntimeError("Normal service state was not restored")
    timer = manifest.get("timer")
    if timer:
        subprocess.run(["systemctl", "stop", timer + ".timer"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Older /run-only sessions have no external driver directory.
    if manifest.get("driver_directory"):
        driver = driver_directory(manifest["nonce"])
        if str(driver) != manifest["driver_directory"] or driver.is_symlink():
            raise RuntimeError("Unexpected driver staging path; preserving it for review")
        if driver.exists():
            marker = driver / ".session-owner"
            if marker.is_file() and marker.read_text() == manifest["nonce"]:
                shutil.rmtree(driver)
            elif not any(driver.iterdir()):
                driver.rmdir()  # Interrupted between mkdir and ownership marker.
            else:
                raise RuntimeError("Driver staging ownership changed; preserving it for review")
    shutil.rmtree(RUNTIME)


def root_session(stage, metadata):
    preflight()
    daemon = daemon_path()
    nonce = secrets.token_hex(8)
    driver = driver_directory(nonce)
    if driver.exists() or driver.is_symlink():
        raise RuntimeError("Driver staging directory already exists; no service change was made")
    event_path = RUNTIME / "events.jsonl"

    def event(phase, **fields):
        with event_path.open("a") as f:
            f.write(json.dumps({"timestamp": timestamp(), "phase": phase, **fields}) + "\n")
        print(timestamp(), phase, flush=True)

    manifest = {"nonce": nonce, "was_active": property_value("ActiveState") == "active",
                "service_changed": False, "dropin": dropin_text(daemon, nonce),
                "driver_directory": str(driver)}
    clients = []
    info = {**metadata, "started": timestamp(), "hardware_run": False,
            "verdict": "inconclusive-because-interrupted", "storage_isolated": False,
            "restored": False, "next_experiment": "review this bundle before requesting another run"}
    start = time.time()
    report_path = REPORTS / ("goodix-test-" + nonce + ".zip")
    report_data = {}
    runtime_owned = False
    try:
        RUNTIME.mkdir(mode=0o700)
        runtime_owned = True
        write_json(RUNTIME / "manifest.json", manifest)
        shutil.copyfile(__file__, RUNTIME / "recover.py")
        prints = RUNTIME / "prints"
        prints.mkdir(mode=0o700)
        isolation_probe(RUNTIME)
        driver.mkdir(mode=0o700)
        (driver / ".session-owner").write_text(nonce)
        (driver / "lib").mkdir()
        for path in sorted((stage / "lib").glob("libfprint-2.so*")):
            shutil.copyfile(path.resolve(), driver / "lib" / path.name)
        if not (driver / "lib/libfprint-2.so.2").is_file():
            raise RuntimeError("Build stage has no libfprint-2.so.2")
        shutil.copyfile(stage / "GoodixEngineAdapter.dll", driver / "GoodixEngineAdapter.dll")
        if shutil.which("chcon"):
            subprocess.run(["chcon", "-R", "-t", "lib_t", str(driver)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        executable_mapping_probe(driver / "lib/libfprint-2.so.2")
        timer = "goodix-test-restore-" + nonce
        manifest["timer"] = timer
        write_json(RUNTIME / "manifest.json", manifest)
        command(["systemd-run", "--quiet", "--on-active=30m", "--unit=" + timer,
                 sys.executable, RUNTIME / "recover.py", "--restore"])
        DROPIN.parent.mkdir(parents=True, exist_ok=True)
        temporary_override = RUNTIME / "override.conf"
        temporary_override.write_text(manifest["dropin"])
        # Atomic, refuses to replace any existing override; both paths are /run.
        os.link(temporary_override, DROPIN)
        # Write recovery intent before the first service mutation.
        manifest["service_changed"] = True
        write_json(RUNTIME / "manifest.json", manifest)
        command(["systemctl", "daemon-reload"])
        event("experimental-service-start")
        info["hardware_run"] = True
        command(["systemctl", "restart", "fprintd.service"])
        pid = int(property_value("MainPID"))
        if pid <= 0:
            raise RuntimeError("Experimental daemon did not start")
        verify_runtime(pid, driver)
        info["storage_isolated"] = True
        event("storage-and-library-verified")
        info.update(guided_test(event, clients))
    except (Exception, KeyboardInterrupt) as error:
        info["verdict"] = "inconclusive-because-session-failed-or-interrupted"
        info["error"] = type(error).__name__ + ": " + str(error)
        print(info["error"], file=sys.stderr)
    finally:
        # Ignore repeat interrupts while restoring the service.
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        for client in clients:
            try:
                client.stop()
            except Exception as error:
                info["client_cleanup_error"] = type(error).__name__
        try:
            report_data["driver.txt"] = filtered_journal(start)
        except Exception as error:
            info["journal_error"] = type(error).__name__
        report_data["events.jsonl"] = event_path.read_text() if runtime_owned and event_path.exists() else ""
        try:
            if runtime_owned:
                restore()
            info["restored"] = True
        except Exception as error:
            info["restore_error"] = str(error)
            print("RESTORE REQUIRED: sudo python3 /run/goodix-5e0a-experiment/recover.py --restore", file=sys.stderr)
        info["finished"] = timestamp()
        report_data["session.json"] = json.dumps(info, indent=2) + "\n"
        REPORTS.mkdir(mode=0o711, exist_ok=True)
        with report_path.open("xb") as f:
            os.fchmod(f.fileno(), 0o600)
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
                for name in REPORT_FILES:
                    z.writestr(name, report_data.get(name, ""))
            os.fchown(f.fileno(), int(os.environ.get("SUDO_UID", 0)), int(os.environ.get("SUDO_GID", 0)))
        print(f"\nResult: {info['verdict']}\nRestored: {info['restored']}\nSend only this file: {report_path}", flush=True)
    return 0 if info["restored"] and info["verdict"] in ("confirmed", "falsified") else 1


def build_and_run(check_only=False, prepare_only=None, capture_settings="current"):
    if os.geteuid() == 0:
        raise RuntimeError("Run as your normal user; the runner asks for sudo after building")
    preflight()
    if check_only:
        print("Read-only preflight passed. No service, storage or sensor operation occurred.")
        return 0
    if output(["git", "-C", ROOT, "status", "--porcelain", "--untracked-files=no"]):
        raise RuntimeError("Use a clean checkout of this PR; existing edits are preserved")
    revision = output(["git", "-C", ROOT, "rev-parse", "HEAD"])
    if prepare_only and prepare_only.exists():
        raise RuntimeError("Prepare-only destination already exists")
    with tempfile.TemporaryDirectory(prefix="goodix-test-build-") as tmp:
        tmp = Path(tmp)
        source = tmp / "source"
        source.mkdir()
        data = subprocess.check_output(["git", "-C", str(ROOT), "archive", "HEAD"])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            # git archive contains repository-owned relative paths only.
            for member in archive.getmembers():
                if Path(member.name).is_absolute() or ".." in Path(member.name).parts or member.issym() or member.islnk():
                    raise RuntimeError("Unexpected archive path/link")
            archive.extractall(source)
        patch = source / "experiments/jet-soup-capture.patch" if capture_settings == "jet-soup" else None
        if patch:
            command(["git", "apply", "--no-index", "--check", patch], cwd=source)
            command(["git", "apply", "--no-index", patch], cwd=source)
        print("Building the test driver separately. No installation or package-manager changes.", flush=True)
        os_release = Path("/etc/os-release").read_text()
        with (tmp / "build.log").open("w") as log:
            if re.search(r"^ID=nixos$", os_release, re.M):
                result = subprocess.run(["nix", "build", "path:" + str(source) + "#libfprint-goodix",
                                         "--no-link", "--no-write-lock-file", "--print-out-paths"],
                                        stdout=subprocess.PIPE, stderr=log, text=True, check=False)
                if result.returncode == 0:
                    prefix = Path(result.stdout.strip().splitlines()[-1])
                    stage = tmp / "driver"
                    stage.mkdir()
                    shutil.copytree(prefix / "lib", stage / "lib", symlinks=True)
                    shutil.copyfile(source / "windows_driver/GoodixEngineAdapter.dll", stage / "GoodixEngineAdapter.dll")
            else:
                result = subprocess.run(["bash", str(source / "install.sh"), "--build-only", str(tmp / "stage")],
                                        stdout=log, stderr=subprocess.STDOUT, check=False)
                stage = tmp / "stage/opt/goodix-libfprint"
        if result.returncode != 0:
            print((tmp / "build.log").read_text()[-8000:], file=sys.stderr)
            raise RuntimeError("Build failed before any service change; send the error above")
        metadata = {"revision": revision, "experiment": "bandpass80-" + capture_settings, "capture_settings": capture_settings,
                    "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest() if patch else None,
                    "library_sha256": hashlib.sha256((stage / "lib/libfprint-2.so.2").read_bytes()).hexdigest(),
                    "kernel": platform.release(), "architecture": platform.machine()}
        meta = tmp / "metadata.json"
        write_json(meta, metadata)
        if prepare_only:
            shutil.copytree(stage, prepare_only, symlinks=True)
            shutil.copyfile(meta, prepare_only / "metadata.json")
            print(f"Build-only check passed: {prepare_only}. No service, storage or sensor operation occurred.")
            return 0
        print("Build passed. The temporary session needs sudo; existing prints stay isolated.", flush=True)
        return subprocess.call(["sudo", sys.executable, str(ROOT / "tools/hardware_session.py"),
                                "--session", str(stage), "--metadata", str(meta)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-settings", choices=("current", "jet-soup"), default="current",
                        help="current: owner regression; jet-soup: wire-only capture candidate")
    parser.add_argument("--check", action="store_true", help="Read-only prerequisites; no sensor or service changes")
    parser.add_argument("--prepare-only", type=Path, help="Build into a new directory, without sudo/service/sensor operations")
    parser.add_argument("--restore", action="store_true", help="Restore an interrupted runtime experiment")
    parser.add_argument("--isolation-check", action="store_true", help="Root: test only namespace isolation, without fprintd/USB")
    parser.add_argument("--session", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--metadata", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interruption)
    if args.restore:
        if os.geteuid() != 0:
            return subprocess.call(["sudo", sys.executable, str(Path(__file__).resolve()), "--restore"])
        restore()
        print("Normal setup restored; no active experiment remains.")
        return 0
    if args.isolation_check:
        if os.geteuid() != 0:
            raise RuntimeError("Run --isolation-check with sudo")
        with tempfile.TemporaryDirectory(prefix="goodix-isolation-", dir="/run") as tmp:
            isolation_probe(Path(tmp))
        print("Actual systemd storage-isolation probe passed. fprintd and USB were not used.")
        return 0
    if args.session:
        if os.geteuid() != 0 or not args.metadata:
            raise RuntimeError("Internal session requires sudo and metadata")
        return root_session(args.session, json.loads(args.metadata.read_text()))
    return build_and_run(args.check, args.prepare_only, args.capture_settings)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f"Test stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
