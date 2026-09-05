# 32 — Upstream foundation batch 1: LGPL headers on new files

**What to build:** Add LGPL-2.1-or-later header blocks (sibling format from
`goodix511.c:1-19`, adapted authorship: reverse-engineered 5e0a port) to the
two new files that lack them: `libfprint-driver/goodix5e0a.c` and
`libfprint-driver/goodix5e0a.h`. Comment-only, zero behavior bytes. First
slice of UPSTREAM.md §6 (legal posture) + specs gap 4 groundwork.

**Blocked by:** None. Explicitly NOT in this batch (later tickets): uncrustify
pass (tool not in env — verify before promising), replay harness/traces,
logical-commit split (needs commit permission), secret-provenance MR text
(needs the 26 story finalized — now available).

**Status:** closed

**Verdict (2026-09-05): CONFIRMED.** Independent audit: header blocks
comment-only insertions, LGPL paragraphs byte-identical to sibling format,
driver build clean, patch→disk delta exactly the two header blocks. Patch
regen `bd98a585…` synced + pins rolled; f25 green post-regen (below). No
hardware run per acceptance (comments only).

## Predicted signatures

- Confirm: `git diff --stat` shows 2 files, comment lines only;
  `gcc -fsyntax-only`-style compile (or the standard ninja driver build)
  clean; full suite green; patch regen + pins per usual.
- Falsify: any non-comment byte changes → revert the hunk.

## Acceptance

Review (comment-only audit) + build + suite + patch regen. No hardware run
(behavior identical by construction — comments only).
