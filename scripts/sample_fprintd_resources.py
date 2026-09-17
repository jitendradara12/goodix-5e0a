#!/usr/bin/env python3
"""Read-only Linux process counters; never activates fprintd or claims a device.

Two endpoint samples are not a memory peak/average or evidence of no claims.
Exit 0 means complete counters, 1 means incomplete counters, 130 interrupted.
The idle-baseline verdict always requires separate, full-interval evidence.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time


def parse_stat(text):
    # comm can contain whitespace and ')'; fields after the final ')' are numeric
    # except state. utime/stime/starttime are Linux stat fields 14/15/22.
    left = text.index("(")
    right = text.rindex(")")
    fields = text[right + 1:].split()
    result = {
        "pid": int(text[:left].strip()),
        "comm": text[left + 1:right],
        "state": fields[0],
        "user_ticks": int(fields[11]),
        "system_ticks": int(fields[12]),
        "starttime_ticks": int(fields[19]),
    }
    if result["pid"] <= 0 or any(result[key] < 0 for key in
                                  ("user_ticks", "system_ticks", "starttime_ticks")):
        raise ValueError("invalid process counters")
    return result


def parse_kib(text, key):
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] == key + ":":
            if len(fields) != 3 or fields[2] != "kB" or int(fields[1]) < 0:
                raise ValueError("invalid memory counter")
            return int(fields[1])  # Linux proc kB means 1024 bytes.
    raise ValueError("missing " + key)


def service_pid():
    # show reads manager state; unlike D-Bus calls to fprintd, it cannot activate it.
    result = subprocess.run(
        ["systemctl", "show", "fprintd.service", "--property=MainPID", "--value"],
        capture_output=True, text=True, check=True, timeout=5,
    )
    pid = int(result.stdout.strip())
    if pid <= 0:
        raise ProcessLookupError("fprintd has no MainPID")
    return pid


def error_reason(exc):
    if isinstance(exc, PermissionError):
        return "permission-denied"
    if isinstance(exc, (FileNotFoundError, ProcessLookupError)):
        return "missing-or-process-exited"
    if isinstance(exc, (ValueError, IndexError)):
        return "malformed-or-missing-counter"
    return type(exc).__name__ + ": " + str(exc)


def snapshot(resolve_pid, proc_root=Path("/proc")):
    sample = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "pid": None,
        "stat": None,
        "rss_kib": None,
        "pss_kib": None,
        "no_timeout_argument": None,
        "identity_valid": False,
        "errors": [],
    }

    def attempt(label, operation):
        try:
            return operation()
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            sample["errors"].append(label + ": " + error_reason(exc))
            return None

    sample["pid"] = attempt("pid", resolve_pid)
    if sample["pid"] is None:
        return sample
    base = proc_root / str(sample["pid"])
    before = attempt("stat", lambda: parse_stat((base / "stat").read_text()))
    sample["monotonic_seconds"] = time.monotonic()
    sample["stat"] = before
    if before is None:
        return sample
    sample["rss_kib"] = attempt(
        "rss_kib", lambda: parse_kib((base / "status").read_text(), "VmRSS"))
    sample["pss_kib"] = attempt(
        "pss_kib", lambda: parse_kib((base / "smaps_rollup").read_text(), "Pss"))
    argv = attempt("cmdline", lambda: (base / "cmdline").read_bytes().split(b"\0"))
    if argv is not None:
        sample["no_timeout_argument"] = b"--no-timeout" in argv or b"-t" in argv
    after = attempt("stat-recheck", lambda: parse_stat((base / "stat").read_text()))
    if after is not None:
        sample["identity_valid"] = (
            before["pid"] == after["pid"] == sample["pid"]
            and before["starttime_ticks"] == after["starttime_ticks"]
            and before["state"] not in ("Z", "X", "x")
            and after["state"] not in ("Z", "X", "x")
        )
        if not sample["identity_valid"]:
            sample["errors"].append("identity: changed-or-process-exited-during-snapshot")
    return sample


def summarize(before, after, ticks_per_second):
    report = {
        "before": before,
        "after": after,
        "clock_ticks_per_second": ticks_per_second,
        "elapsed_seconds": None,
        "identity": "unavailable",
        "cpu_user_seconds": None,
        "cpu_system_seconds": None,
        "cpu_total_seconds": None,
        "cpu_percent_one_core": None,
        "resource_sample": "incomplete",
        "idle_baseline": "inconclusive-because-no-claims-not-established",
        "wakeups": {"value": None, "reason": "not-measured"},
        "power": {"value": None, "reason": "not-measured"},
        "errors": [],
    }
    if after is None:
        report["errors"].append("interrupted")
        report["idle_baseline"] = "inconclusive-because-interrupted"
        return report
    report["elapsed_seconds"] = elapsed = (
        after["monotonic_seconds"] - before["monotonic_seconds"])
    if before["pid"] is not None and after["pid"] is not None:
        if before["pid"] != after["pid"]:
            report["identity"] = "pid-changed"
        elif before["stat"] is not None and after["stat"] is not None:
            if before["stat"]["starttime_ticks"] != after["stat"]["starttime_ticks"]:
                report["identity"] = "starttime-changed-pid-reused"
            elif before["identity_valid"] and after["identity_valid"]:
                report["identity"] = "unchanged"
    if report["identity"] != "unchanged":
        report["idle_baseline"] = "inconclusive-because-process-identity-not-stable"
        return report
    user = after["stat"]["user_ticks"] - before["stat"]["user_ticks"]
    system = after["stat"]["system_ticks"] - before["stat"]["system_ticks"]
    if user < 0 or system < 0 or elapsed <= 0 or ticks_per_second <= 0:
        report["errors"].append("invalid-counter-delta-or-clock")
    else:
        report["cpu_user_seconds"] = user / ticks_per_second
        report["cpu_system_seconds"] = system / ticks_per_second
        report["cpu_total_seconds"] = (user + system) / ticks_per_second
        report["cpu_percent_one_core"] = report["cpu_total_seconds"] / elapsed * 100
        if all(sample[key] is not None for sample in (before, after)
               for key in ("rss_kib", "pss_kib")):
            report["resource_sample"] = "complete"
    if report["resource_sample"] != "complete":
        report["idle_baseline"] = "inconclusive-because-metrics-unavailable"
    elif not all(sample["no_timeout_argument"] for sample in (before, after)):
        report["idle_baseline"] = "inconclusive-because-no-timeout-argument-not-established"
    return report


def positive_interval(value):
    interval = float(value)
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("interval must be finite and positive")
    return interval


def positive_pid(value):
    pid = int(value)
    if pid <= 0:
        raise argparse.ArgumentTypeError("PID must be positive")
    return pid


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=positive_interval, default=20.0,
                        help="seconds between endpoint reads (default: 20)")
    parser.add_argument("--pid", type=positive_pid,
                        help="sample this fixed PID instead of querying systemd at each endpoint")
    args = parser.parse_args(argv)
    resolver = (lambda: args.pid) if args.pid is not None else service_pid
    ticks = os.sysconf("SC_CLK_TCK")
    before = snapshot(resolver)
    interrupted = False
    # No reason to wait if the initial process cannot be identified.
    if before["identity_valid"]:
        try:
            time.sleep(args.interval)
            after = snapshot(resolver)
        except KeyboardInterrupt:
            after = None
            interrupted = True
    else:
        after = before
    report = summarize(before, after, ticks)
    report["requested_interval_seconds"] = args.interval
    report["selection"] = "fixed-pid" if args.pid is not None else "fprintd.service MainPID"
    report["notes"] = [
        "RSS/PSS are endpoint values, not interval averages or peaks.",
        "CPU includes process threads, excludes children; 100% equals one core.",
        "Zero CPU delta means less than counter resolution, not zero work.",
        "No claims, suspend, wakeups, power or stock-daemon baseline are measured.",
        "Review independent full-interval claim evidence before calling this an idle baseline.",
    ]
    print(json.dumps(report, indent=2, allow_nan=False))
    return 130 if interrupted else (0 if report["resource_sample"] == "complete" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
