#!/usr/bin/env python3
"""Offline activation envelopes from journalctl -o short-precise text.

No device access. Times are journal log intervals, not USB readiness measurements.
Only explicit start verification/enrollment blocks are analyzed. The first 0x32
Running command marker ends pre-touch timing, before any finger response.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import statistics


LINE = re.compile(
    r"^(?P<time>[A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2}\.\d{6}) "
    r"(?P<host>\S+) fprintd\[(?P<pid>\d+)\]: (?P<message>.*)$"
)
COMMAND = re.compile(r"Running command: (0x[0-9a-fA-F]{2})$")
MARKERS = {
    "candidate": "parked TLS session candidate fresh",
    "reused": "5e0a TLS session reused (",
    "cold": "5e0a warm expired: reason=",
    "warm": "5e0a warm activation: reusing MCU config",
}


def milliseconds(start, end):
    return round((end[0] - start[0]).total_seconds() * 1000, 3)


def analyze(lines, source="<input>"):
    """Return independent attempts; never pair commands across PID or actions."""
    active = {}
    results = []
    previous = {}

    def finish(key, reason):
        events = active.pop(key)
        start = events[0]
        sent = events[-1] if reason == "finger-wait-command-sent" else None
        markers = {}
        for event in events:
            for name, text in MARKERS.items():
                if text in event[2]:
                    markers.setdefault(name, event)
        path = "unknown"
        if "reused" in markers:
            path = "park-reused"
        elif "cold" in markers:
            path = "cold:" + markers["cold"][2].split("reason=", 1)[1]
        elif "warm" in markers:
            path = "warm-reactivation"
        elif "candidate" in markers:
            path = "candidate-only"
        row = {
            "source": source, "host": key[0], "pid": key[1],
            "start_line": start[1], "end_line": events[-1][1],
            "path": path, "status": reason,
            "markers": {name: {"line": event[1], "from_start_ms": milliseconds(start, event)}
                        for name, event in markers.items()},
            "to_finger_wait_sent_ms": milliseconds(start, sent) if sent else None,
            "candidate_to_reused_ms": milliseconds(markers["candidate"], markers["reused"])
            if "candidate" in markers and "reused" in markers else None,
            "reused_to_finger_wait_sent_ms": milliseconds(markers["reused"], sent)
            if "reused" in markers and sent else None,
            "commands": [],
        }
        starts = [(i, COMMAND.search(event[2]).group(1).lower())
                  for i, event in enumerate(events) if COMMAND.search(event[2])]
        for index, (i, command) in enumerate(starts):
            if sent and i == len(events) - 1:
                continue  # 0x32 is the endpoint, never its response/touch wait.
            next_i = starts[index + 1][0] if index + 1 < len(starts) else None
            window = events[i + 1:next_i]
            # TLS relay reads have their own completion logs without a Running
            # command marker. Never use one to fill a missing D0 completion.
            read_start = next((j for j, e in enumerate(window)
                               if e[2] == "goodix_read_tls()"), len(window))
            window = window[:read_start]
            # goodix_receive_done logs after resetting cmd to zero. Pair by
            # serial order, not the misleading Completed command opcode.
            completion = next((e for e in window if "Completed command:" in e[2]), None)
            ack = next((e for e in window if e[2] == "got ack"), None)
            next_event = events[next_i] if next_i is not None else None
            row["commands"].append({
                "command": command, "line": events[i][1],
                "from_start_ms": milliseconds(start, events[i]),
                "to_ack_ms": milliseconds(events[i], ack) if ack else None,
                "to_completion_ms": milliseconds(events[i], completion) if completion else None,
                "to_next_command_ms": milliseconds(events[i], next_event) if next_event else None,
                "completion_to_next_ms": milliseconds(completion, next_event)
                if completion and next_event else None,
            })
        results.append(row)

    for number, line in enumerate(lines, 1):
        match = LINE.match(line.rstrip("\n"))
        if not match:
            if re.search(r"fprintd\[\d+\]:", line):
                raise ValueError(f"{source}:{number}: expected short-precise timestamp with six decimals")
            continue
        key = (match["host"], match["pid"])
        # The format has no year. Use a leap year for within-file intervals;
        # reject backward clocks/year rollover rather than fabricate a delta.
        time = datetime.strptime("2000 " + match["time"], "%Y %b %d %H:%M:%S.%f")
        if key in previous and time < previous[key]:
            raise ValueError(f"{source}:{number}: backward timestamp or year rollover")
        previous[key] = time
        message = match["message"]
        event = (time, number, message)
        if re.match(r"start (verification|enrollment) device ", message):
            if key in active:
                finish(key, "incomplete:new-action")
            active[key] = [event]
            continue
        if key not in active:
            continue
        active[key].append(event)
        command = COMMAND.search(message)
        if command and command.group(1).lower() == "0x32":
            finish(key, "finger-wait-command-sent")
        elif any(text in message for text in (
            "Device reported verify completion", "Device reported enroll completion",
            "Device reported close completion", "main loop completed",
        )):
            finish(key, "incomplete:action-ended")
    for key in list(active):
        finish(key, "incomplete:end-of-file")
    return sorted(results, key=lambda row: row["start_line"])


def summary(rows):
    groups = {}
    for row in rows:
        if row["status"] != "finger-wait-command-sent":
            continue
        groups.setdefault(row["path"], []).append(row["to_finger_wait_sent_ms"])
    return {path: {"n": len(values), "min_ms": min(values),
                   "median_ms": round(statistics.median(values), 3), "max_ms": max(values)}
            for path, values in sorted(groups.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journals", type=Path, nargs="+", help="saved short-precise journal text files")
    args = parser.parse_args()
    rows = []
    try:
        for path in args.journals:
            with path.open(encoding="utf-8") as stream:
                rows.extend(analyze(stream, str(path)))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "measurement": "journal log envelopes, not USB readiness or physical touch latency",
        "precision": "six-decimal source timestamps; 0.001 ms displayed resolution, not accuracy",
        "scope": "first 0x32 send marker per explicit action start; missing endpoints stay incomplete",
        "attempts": rows, "summary": summary(rows),
    }, indent=2))


if __name__ == "__main__":
    main()
