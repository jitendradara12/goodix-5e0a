# 22 — Base/511 compile-link isolation (5e0a extern in shared path)

**What to build:** Remove the 5e0a coupling from the shared base scan path so
any `-Ddrivers=` selection links: move or drop the `goodix5e0a_last_declen`
write + `5e0a`-prefixed log in `scan_on_read_img`
(`libfprint-driver/goodix5xx.c:32,348,350`; sole definition in
`libfprint-driver/goodix5e0a.c:33`). The 5e0a driver keeps its own declen
logging (`goodix5e0a.c:372-373`, frame-stats line `:700-701` reads the
5e0a-owned copy), so 5e0a journal output is unchanged by construction.

**Blocked by:** None (meson builds only — no hardware, no finger, no daemon).

**Status:** ready-for-agent

## Settled facts (verified by reading, do not re-litigate)
1. `goodix5xx.c:32` declares `extern guint32 goodix5e0a_last_declen;` and
   `:348` writes it unconditionally in shared `scan_on_read_img`, with no
   device-type branch — while serving 511/52xd/5e0a through the `cls` vtable.
2. The only definition is `goodix5e0a.c:33`. Any driver selection excluding
   `goodixtls5e0a` (e.g. `-Ddrivers=goodixtls511`) links `goodix5xx.o`
   against a missing symbol → undefined reference at link time. Our pinned
   derivation builds `-Ddrivers=goodixtls5e0a` only, so it is unaffected
   today; upstream CI (per-driver single builds) and 511 users are not.
3. This is also an upstream-split prerequisite: shared code must not name
   one subclass's symbols.

## Proposed change (one variable)
Delete the extern declaration (`:32`), the write (`:348`), and the
5e0a-prefixed `g_message` (`:350`) from the shared path. Suggested
replacement: nothing (subclass path already logs declen at
`goodix5e0a.c:373` and frame stats at `:700`). Do NOT touch anything else
in the same build. Regenerate the unified patch from base + re-sync
deployed copies (SHA parity per ticket 19 §5); F25 + SHA pin will fail
until then — expected, not a regression.

## Predicted signatures (no hardware needed)
- Confirm branch: `meson setup -Ddrivers=goodixtls511`, `-Ddrivers=all`,
  and `-Ddrivers=goodixtls5e0a` all configure + compile clean; a 5e0a
  hardware smoke run shows identical journal lines except the removed base
  `scan_on_read_img: declen=` duplicate (subclass `:373` line remains).
- Falsify branch: any link error remains, or 5e0a journal loses declen
  observability → revert and report the exact failing command + output.

## Acceptance
Paste the three meson build results (configure + compile tail lines) plus,
if a scanner host is available, one verify run journal grep per AGENTS.md.
Conclude only confirmed / falsified / inconclusive-because-[flaw] + the
single next experiment.
