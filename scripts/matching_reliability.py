#!/usr/bin/env python3
r"""Offline matching report; stdlib only, no sensor or service operations.

One sample is one complete, isolated verification claim, not one log line.
First-touch means the first reported result in that claim, a proxy rather
than a physical-contact count. A retry before a match is not first-touch success.
Client match/no-match lines require '(done)'. Journal report_verify_status
match/no-match is terminal in this driver's format and needs no client marker.
Different terminal decisions or any retry after a terminal decision indicate
mixed claims and are excluded. Identical adjacent decisions are treated as duplicates.

Collection imports saved plain-text fprintd-verify output and/or journal excerpts:
  python3 scripts/matching_reliability.py collect --samples samples.jsonl \
    --id trial-01 --label genuine --finger finger-a --contact steady \
    --results trial-01.txt --journal trial-01-journal.txt
  python3 scripts/matching_reliability.py report samples.jsonl

Use a fresh ID and an isolated log window for each claim. Label 'genuine' only
when the presented finger is known to match the selected enrollment; 'wrong'
means a known different finger. Finger/contact are operator labels, not inferred.
Missing finger/contact or 'unknown' labels exclude a sample from rates. Pass
--cancelled for interrupted claims even if a result appeared before interruption.
The collector does not run verification, journalctl, or privileged commands. It
stores only labels and normalized outcomes, never raw log lines, scores, images,
or templates. Keep labels anonymous. Input logs remain untouched.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re


STATUSES = {
    "verify-match": "match",
    "verify-no-match": "no-match",
    "verify-retry-scan": "retry",
    "verify-swipe-too-short": "retry",
    "verify-finger-not-centered": "retry",
    "verify-remove-and-retry": "retry",
    "verify-disconnected": "error",
    "verify-unknown-error": "error",
    "verify-cancelled": "cancelled",
    "verify-canceled": "cancelled",
}
STATUS_RE = re.compile(
    r"(?:report_verify_status:\s*result\s+|Verify result:\s*)(verify-[a-z-]+)\b"
)
MILAN_RE = re.compile(r"Milan verify:\s*match=([01])\b")
FIELDS = {"id", "label", "finger", "contact", "cancelled", "results", "journal", "milan"}
OUTCOMES = {"match", "no-match", "retry", "error", "cancelled", "incomplete"}


def collapse(values):
    """Repeated identical statuses cannot create extra samples or retries."""
    result = []
    for value in values:
        if not result or value != result[-1]:
            result.append(value)
    return result


def parse_evidence(text):
    statuses, milan = [], []
    for line in text.splitlines():
        status = STATUS_RE.search(line)
        if status:
            # An unfamiliar status is not a match or a biometric rejection.
            outcome = STATUSES.get(status[1], "error")
            if (status[0].startswith("Verify result:") and
                    outcome in {"match", "no-match"} and
                    not re.match(r"\s+\(done\)", line[status.end():])):
                outcome = "incomplete"
            statuses.append(outcome)
        match = MILAN_RE.search(line)
        if match:
            milan.append("match" if match[1] == "1" else "no-match")
    return collapse(statuses), collapse(milan)


def validate(sample):
    if not isinstance(sample, dict) or set(sample) != FIELDS:
        raise ValueError("sample must contain exactly: " + ", ".join(sorted(FIELDS)))
    for field in ("id", "finger", "contact"):
        value = sample[field]
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
            raise ValueError(f"{field} must be a short anonymous token")
    if sample["label"] not in ("genuine", "wrong", "unknown"):
        raise ValueError("label must be genuine, wrong, or unknown")
    if type(sample["cancelled"]) is not bool:
        raise ValueError("cancelled must be boolean")
    for field in ("results", "journal", "milan"):
        values = sample[field]
        allowed = {"match", "no-match"} if field == "milan" else OUTCOMES
        if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values):
            raise ValueError(f"invalid normalized {field} outcomes")
        sample[field] = collapse(values)
    return sample


def assess(sample):
    results, journal, milan = (collapse(sample[key]) for key in ("results", "journal", "milan"))
    statuses = results or journal
    first = statuses[0] if statuses else "missing"
    final = statuses[-1] if statuses else "missing"
    reason = None
    if sample["cancelled"] or "cancelled" in results + journal:
        reason = "cancelled"
    elif "error" in results + journal:
        reason = "error"
    elif "incomplete" in results + journal:
        reason = "incomplete"
    elif any(s in {"match", "no-match"}
             for sequence in (results, journal) for s in sequence[:-1]):
        reason = "mixed-claims"
    elif len(milan) > 1:
        reason = "conflicting-milan"
    elif results and journal and results != journal:
        reason = "conflicting-statuses"
    # Compare the result sequence, not scores or the number of debug messages.
    elif milan and collapse(s for s in statuses if s in {"match", "no-match"}) != milan:
        reason = "conflicting-milan" if statuses else "missing-status"
    elif final not in {"match", "no-match"}:
        reason = "incomplete"
    evidence = "status-only"
    if journal and milan and reason is None:
        evidence = "journal-and-milan-consistent"
    elif journal:
        evidence = "journal-status"
    if reason:
        outcome = reason
    elif (sample["label"] == "unknown" or sample["finger"] == "unknown" or
          sample["contact"] == "unknown"):
        outcome = "unknown-" + first
    elif first == "retry":
        outcome = "retry-first"
    elif sample["label"] == "genuine":
        outcome = "genuine-match" if first == "match" else "genuine-miss"
    else:
        outcome = "wrong-finger-acceptance" if first == "match" else "wrong-finger-rejection"
    exclusion = reason
    if not exclusion and (sample["label"] == "unknown" or
                          sample["finger"] == "unknown" or sample["contact"] == "unknown"):
        exclusion = "unknown-label"
    return {"id": sample["id"], "first": first, "final": final, "outcome": outcome,
            "excluded": exclusion, "evidence": evidence}


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def summarize(samples):
    rows = [assess(sample) for sample in samples]
    eligible = [(s, r) for s, r in zip(samples, rows) if r["excluded"] is None]
    genuine = [r for s, r in eligible if s["label"] == "genuine"]
    wrong = [r for s, r in eligible if s["label"] == "wrong"]
    genuine_decisions = [r for r in genuine if r["first"] in {"match", "no-match"}]
    wrong_decisions = [r for r in wrong if r["first"] in {"match", "no-match"}]
    return {
        "attempts": len(samples),
        "outcomes": dict(sorted(Counter(r["outcome"] for r in rows).items())),
        "excluded": dict(sorted(Counter(r["excluded"] for r in rows if r["excluded"]).items())),
        "genuine_first_touch_success": fraction(sum(r["first"] == "match" for r in genuine), len(genuine)),
        "genuine_first_decision_miss": fraction(sum(r["first"] == "no-match" for r in genuine_decisions), len(genuine_decisions)),
        "wrong_finger_first_decision_rejection": fraction(sum(r["first"] == "no-match" for r in wrong_decisions), len(wrong_decisions)),
        "wrong_finger_first_touch_rejection": fraction(sum(r["first"] == "no-match" for r in wrong), len(wrong)),
    }


def load_samples(path):
    samples = {}
    duplicates = 0
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                sample = validate(json.loads(line))
                previous = samples.get(sample["id"])
                if previous is not None:
                    if previous != sample:
                        raise ValueError("conflicting duplicate sample ID " + sample["id"])
                    duplicates += 1
                else:
                    samples[sample["id"]] = sample
            except (ValueError, TypeError) as error:
                raise ValueError(f"sample line {number}: {error}") from error
    return list(samples.values()), duplicates


def report(samples, duplicates=0):
    groups = {}
    for sample in samples:
        key = (sample["label"], sample["finger"], sample["contact"])
        groups.setdefault(key, []).append(sample)
    return {
        "definition": "One attempt per unique claim ID; first-touch is first reported status, not physical touch count.",
        "limitations": "Incomplete/conflicting/error/cancelled/unknown-label samples excluded. Retry-first completed claims count against first-touch success, not as genuine misses. Rates describe this sample only; hardware accuracy remains unverified.",
        "duplicate_samples_ignored": duplicates,
        "summary": summarize(samples),
        "groups": [{"label": key[0], "finger": key[1], "contact": key[2], **summarize(value)}
                   for key, value in sorted(groups.items())],
        "samples": [assess(sample) for sample in samples],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    reporting = commands.add_parser("report", help="report normalized JSONL samples as JSON")
    reporting.add_argument("samples", type=Path)
    collecting = commands.add_parser("collect", help="import one isolated saved claim; never claims hardware")
    collecting.add_argument("--samples", type=Path, required=True)
    collecting.add_argument("--id", required=True)
    collecting.add_argument("--label", choices=("genuine", "wrong", "unknown"), default="unknown")
    collecting.add_argument("--finger", default="unknown", help="anonymous presented-finger label")
    collecting.add_argument("--contact", default="unknown", help="operator-labeled contact, e.g. steady or light")
    collecting.add_argument("--cancelled", action="store_true", help="claim was interrupted or timed out")
    collecting.add_argument("--results", type=Path, help="saved fprintd-verify text for this claim only")
    collecting.add_argument("--journal", type=Path, help="saved plain-text journal for this claim only")
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            samples, duplicates = load_samples(args.samples)
            print(json.dumps(report(samples, duplicates), indent=2))
        else:
            results, _ = parse_evidence(args.results.read_text(encoding="utf-8") if args.results else "")
            journal, milan = parse_evidence(args.journal.read_text(encoding="utf-8") if args.journal else "")
            sample = validate({"id": args.id, "label": args.label, "finger": args.finger,
                               "contact": args.contact, "cancelled": args.cancelled,
                               "results": results, "journal": journal, "milan": milan})
            samples, _ = load_samples(args.samples) if args.samples.exists() else ([], 0)
            if any(s["id"] == args.id for s in samples):
                raise ValueError("sample ID already exists; use a fresh ID for a new claim")
            # ponytail: sequential operator collection; no concurrent writers.
            separator = ""
            if args.samples.exists() and args.samples.stat().st_size:
                with args.samples.open("rb") as stream:
                    stream.seek(-1, 2)
                    if stream.read(1) != b"\n":
                        separator = "\n"
            with args.samples.open("a", encoding="utf-8") as stream:
                stream.write(separator + json.dumps(sample) + "\n")
            print(json.dumps(assess(sample), indent=2))
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
