# Ticket 100 — repo-wide code audit

Status: closed (+verdict)

Scope: full-repo audit of `libfprint-driver/`, the packaging (`.nix`, integration
patch, `install.sh`), `scripts/`, and `tests/`, at commit `fd8314646b4703054d0df8bee71ba69bc914c1de`.
No hardware, no sensor access, no sudo. Audit only: findings, then fixes that are
safe to make without a deployed-driver run.

## Verdict

The original audit fixed 16 defects (including two PE-loader bounds bugs, the
USB read-loop CPU spin, and the teardown GError issue). The independent PR-review
follow-ups below additionally close the zero-timeout waiter, stale-retry-source,
OOM sort, export metadata, logging, and reporting gaps. Sixteen unrelated items
remain recorded as **not-fixed-on-purpose** with their reasons.
Software suite after review follow-ups: **371 executed / 371 passed / 8 skipped**
(`GOODIX_NATIVE_TESTS=skip GOODIX_SUSPEND_TESTS=skip bash tests/run_all_tests.sh`).

## Verification chain (executed, not claimed)

- `GOODIX_NATIVE_TESTS=skip GOODIX_SUSPEND_TESTS=skip bash tests/run_all_tests.sh`
  → 371 executed, 371 passed, 8 skipped. Native/suspend harnesses and
  fixture-dependent checks account for the skips; `nix-build` is absent.
- A review reran `gcc -fsyntax-only -Wall -Wextra` for the pre-follow-up
  `goodix_milan.c` against a GLib stand-in: no errors, but 292 pre-existing
  `-Wunused-parameter` shim-table warnings (same profile on the base revision).
  For the follow-up changes, the extracted `sh_qsort` and `get_export` routines
  compiled in a standalone harness and passed merge-sort, forced-OOM fallback,
  PROT_NONE metadata-read, and export-boundary checks. Real GLib/GUsb/OpenSSL
  headers are not installed here, so the full driver files could not be built.
- `sh_qsort` was replaced with a bottom-up merge sort. The merge is stable;
  unlike the old non-adjacent-swap bubble sort, it can reorder tied elements
  relative to that implementation. A standalone differential test confirmed
  sorted output, and separate trials confirmed the merge's stable tie order;
  200 000 elements sorted in 0.028 s (3.33 M comparisons) versus about
  2 x 10^10 comparisons for the old quadratic sort. An in-place stable
  insertion-sort fallback now preserves sorting if scratch allocation fails.
- Brace/paren balance checked on every modified file against `HEAD`.

---

## A. Fixed — correctness / crash

### A1. PE export table: several `u32` bound checks overflowed (security boundary)

`goodix_milan.c:get_export` parses headers from a DLL whose provenance is only
as good as `GOODIX_ENGINE_DLL_PATH` / the search paths. Several checks were
computed in `u32`:

- `if (e + 24 + 112 + 8 > g_sizeofimage)` — an `e_lfanew` near 2^32 wraps the sum.
- `exprva + 40`, `names + nnames * 4`, `ords + nnames * 2`, `fns + ord * 4 + 4`
  — a large `NameCount` makes `nnames * 4` wrap to 0, so the bound check passes
  and the subsequent reads walk off the mapping.
- `*(u32*)(g_image + 0x3c)` itself was read with no minimum-image-size check.

All offset arithmetic is widened, the `e_lfanew` read is bounded by the
minimum image size, and the export-directory RVA check includes all four bytes
it reads. Export metadata is read from a fully backed zero-filled image copy,
not from `g_image`'s intentionally `PROT_NONE` holes.

### A2. PE section mapping: `u32` underflow and wrap

`goodix_milan.c:load_pe_file` mapped each section with
`if (vaddr + seglen > sizeofimage) seglen = sizeofimage - vaddr;`. With a
`VirtualAddress` at or past `SizeOfImage` the subtraction underflows in `u32`
and `mmap` gets a near-4 GiB length; `seglen = (seglen + 0xfff) & ~0xfffu` also
wrapped to 0 for sections within a page of 4 GiB. The round-up and both bounds
are now `u64`, and an out-of-range `vaddr` is skipped rather than clamped. The
header mapping is likewise clamped to `sizeofimage` so it cannot overshoot the
`PROT_NONE` reservation.

### A3. `sh_qsort` was an O(n^2) bubble sort on the engine's hot path

Replaced with a stable bottom-up merge sort (sorted-output, stability, and
timing evidence above). The old bubble sort was *not* stable: its non-adjacent
swaps could reorder equal elements, so outputs can differ when keys tie.
`calloc(n, s)` checks the scratch allocation size; if it fails, an in-place
stable insertion sort preserves the old guarantee that the caller receives a
sorted array (at quadratic cost only on OOM).

### A4. `sh_FlsAlloc` walked off the slot table

`TlsAlloc` bounded `g_tls_next` at 1088; `FlsAlloc` did not. Past that point
`FlsGetValue`/`FlsSetValue` silently dropped every value because their `i < 1088`
guards rejected the index. Both now share `TLS_SLOT_MAX` / `TLS_INDEX_INVALID`.

### A5. `sh_Sleep` overflowed and was not restartable

`usleep(ms * 1000)` wraps for `ms` past ~71 minutes, and `usleep` is removed
from POSIX. Now `nanosleep` with an `EINTR` loop.

### A6. `sh_CryptGenRandom` reported a CSPRNG outage on a short read

A single `read()` was compared against the full length. Now loops until filled.

### A7. `fdt_down`/`fdt_up` prepend: unchecked `malloc` + `guint16` truncation

`goodix_send_mcu_switch_to_fdt_{down,up}` did `malloc(...)` then `memcpy` with no
NULL check, and computed `length + 1` in `guint16`, so a 0xFFFF payload was sent
as length 0. The prepend is now skipped (falling through to send the caller's
buffer unchanged, which keeps `free_func` ownership intact) on either miss.

### A8. Base scan hook could hand a NULL image to libfprint core

`goodix5xx.c:scan_on_read_img` called `fpi_image_device_image_captured (img_dev, img)`
even when `img` was NULL — which happens when a subclass sets neither
`process_raw_frame` nor `process_frame`, or when `process_raw_frame` declines a
frame (5e0a's does, when normalisation fails). The scan is now failed instead.
The header's stale "takes ownership of the raw raster" contract was corrected:
the base frees the raster, and returning NULL rejects the frame.

---

## B. Fixed — resource / lifecycle / reporting

### B1. Read loop spun the main thread on a permanently failing device

`goodix_receive_data_cb` resubmitted `goodix_receive_data()` straight from the
USB completion callback. A device that errors on every submission (unplugged
mid-claim, stalled endpoint) therefore ran a tight loop at 100% CPU in fprintd's
main thread. Retries now go through a 100 ms `fpi_device_add_timeout`. After
`GOODIX_READ_ERROR_MAX` (5) consecutive failures, the loop stops and completes
any armed command with `G_IO_ERROR_FAILED`. This also covers FDT and TLS reply
commands that intentionally have no timeout; ordinary timed commands retain
their existing timeout as a second line of defense.

### B2. `goodix_dev_deinit` handed a non-NULL `*error` to `g_usb_device_release_interface`

A shutdown error, if one is reported, must not be passed into the following
release call: GUsb treats a pre-set `GError` as a critical and skips the
release. Deinit now passes NULL to the release call when `*error` is already
set, still attempts the release, and returns failure if either shutdown or
release failed. Currently `goodix_tls_server_deinit()` is best-effort and
always returns TRUE without setting `error`, so the shutdown-error branch is
defensive rather than reachable today. Both `goodix5e0a.c:dev_close` and
`goodix5xx.c:dev_deinit` benefit.

### B3. Error codes were raw `errno` / byte counts, not enum members

Three sites built `g_error_new (g_io_error_quark (), <int>, ...)` where the int
was a byte count or a raw `read()` status (-1 / 0), producing an invalid
`GIOErrorEnum`. One site used `g_set_error (error, G_FILE_ERROR, errno, ...)`,
i.e. an errno value where a `GFileError` was expected. All four now map through
`G_IO_ERROR_FAILED` / `G_IO_ERROR_CONNECTION_CLOSED` / `g_file_error_from_errno()`,
and the messages carry the count that used to be the code.

### B4. `goodix_dev_init` leaked the cancellable on a second open

`priv->transfer_cancel_tkn = g_cancellable_new ()` overwrote the previous
pointer, dropping its only reference along with any in-flight transfer's. Now
`g_clear_object`'d first. Review follow-up also destroys a pending `read_retry`
source during init rather than orphaning it and allowing an extra read later.

### B5. "Completed command: 0x%02x" always printed 0x00

`goodix_receive_done` logged `priv->cmd` *after* `goodix_reset_state()` had
cleared it. The command is now snapshotted before the reset.

### B6. Ticket-84 fast path re-derived the match decision

`goodix5e0a_keep_best_frame`'s optimistic path gated on `match_pts > 0` (verify)
and `matched_idx >= 0 && match_pts > 0` (identify), instead of using the engine
verdict. In the authoritative deliver tail, verify gates on the verify engine's
return value; identify gates on the identify engine's return value and validates
its winner index against the usable gallery. The duplicate identify paths also
had two copies of the gallery read and engine call.

The fast path cannot itself grant access — it only skips the remaining burst, and
deliver still decides — but a fast path that re-derives the decision is one edit
away from becoming a false-accept hole, and a spurious positive degrades FRR by
submitting frame 1 instead of the best of 4.

Fixed by making `goodix5e0a_identify_best_frame()` the single reader of the
gallery and the single caller of `identifyImage`, and by gating both fast paths
on the engine's verdict. The two divergent blocks (83 non-blank lines) collapsed
into one shared helper plus two three-line call sites. That mattered:
The compactness guard is `tests/tier1_feature/test_f13_no_polling.py`
(`assertLess(nonblank_lines, 2000)`). Before the refactor the source had 1996
nonblank lines; the shared-helper refactor plus the identify journal fix leaves
it at 1998, still below the production limit.

### B7. Milan engine lazy-init was check-then-act outside the mutex

`goodix_milan_enroll_start`, `_verify_image` and `_identify_image` read
`g_milan_available` and called `goodix_milan_init(NULL)` before taking
`g_milan_mutex`; every other entry point locked first. Both now lock before the
check (`GRecMutex` is recursive, so `goodix_milan_init` remains safe to call).

### B8. `goodix5e0a_capture_payload` was a writable exported global

A 10-byte hardware ground-truth table with external linkage in a shared library,
mutated by nothing. Now `static const`.

### B9. `data_to_str` was dead exported API

Defined in `goodix.c`, declared in `goodix.h`, zero callers anywhere in the tree
(including `legacy-experiments/`). Removed from both.

### B10. `goodix5e0a_last_declen` was a file-scope global

Single-TU use only; now `static`.

### B11. Packaging advertised the wrong version

`libfprint-goodix.nix` said `1.94.5-goodixtls-5e0a` while
`goodix-5e0a-integration.patch` sets the meson project version to 1.94.9 — which
is what the built library self-reports (`Initializing FpContext (libfprint
version 1.94.9)`, ticket 85 journal) and what fprintd's pkg-config check reads.
Aligned to `1.94.9-goodixtls-5e0a`.

---

## C. Not fixed on purpose (with reasons)

| # | Finding | Why not fixed here |
|---|---|---|
| C1 | `goodixtls5xx_scan_start()` has **zero callers** repo-wide. With it, `scan_run_state`, `scan_on_read_img`, `scan_get_img`, the calibration SSM, `linear_subtract_inplace`, `goodixtls5xx_squash_frame_linear`, and 5e0a's `process_raw_frame` + `goodix5e0a_axis_correlation` (~370 lines) are unreachable in the 5e0a build. | It is documented base-class API for future 5xx devices (`goodix5xx.h:33`), and `test_m2_driver_refactoring` asserts on `process_raw_frame`'s demosaicing output. Deleting it is a design decision, not an audit fix. **Recommendation:** either wire 511 up to it or mark the block as unexercised future API — and note that deleting 5e0a's copy would release ~120 lines of the 2000-line budget. |
| C2 | `goodix511.c` / `goodix511.h` are copied into the build tree by `libfprint-goodix.nix`'s `postPatch` but never compiled (`-Ddrivers=goodixtls5e0a`). | Harmless (meson compiles only what the selected driver references), but it does overwrite the fork's 511 sources with this checkout's. Narrow the copy to the `goodixtls5e0a` source set if 511 ever diverges. |
| C3 | `goodix5e0a.h` defines every byte table (including the 32-byte PSK) as `static const` in a header → one copy per including TU, and `-Wunused-const-variable` noise for tables a TU does not touch. | One TU today. Move to `extern const` in the header + one definition in a `.c` if the file is ever included twice. |
| C4 | `goodix5e0a_capture_payload` (goodix.c) duplicates `goodix_5e0a_img_payload` (goodix5e0a.h). | Required: `goodix.c` is the 511/5e0a shared core and does not include `goodix5e0a.h`. Verified byte-identical and now guarded by `test_m3_audit_hardening`. |
| C5 | `goodix_tls_server_deinit` ignores its `GError **`. | Silenced with `(void) error` + a comment. Changing the signature ripples into `goodix.h`, `goodix5xx.c` and `goodixtls.h` for no behaviour change. |
| C6 | Non-NixOS installer has no `--no-timeout` override. | Already a disclosed limitation (ticket 88); the module does override it. |
| C7 | `--build-only DIR` leaves a partially populated `DIR` if the final `cp -R` fails. | Cosmetic; nothing is installed and the message says nothing was installed. |
| C8 | The bundled `windows_driver/GoodixEngineAdapter.dll` is world-readable once installed (0644 under `/opt`, and world-readable in the Nix store). | Disclosed in both `nixos-module.nix` and the installer output. Any fix (0600 + group `fprintd`) needs a hardware run to confirm the daemon can still read it. |
| C9 | `m_identifyImage`'s return code is ignored in favour of `matched_idx`/`match_score`. | Fail-closed already: the sentinels (-999) survive an error return and the gate yields no-match. Asserting on the return code too would be belt-and-braces; it needs a hardware run to confirm the engine never returns 0 with a valid-looking index. |
| C10 | Enrollment/`enrolAddImage` return code is used, but `progress_pct` is read from a hardcoded context offset (`+12`) alongside `+8`/`+10`. | Reverse-engineered ABI offsets with ticket-72 precedent. Documented in place; no safer alternative without the vendor headers. |
| C11 | `goodix_receive_pack` accumulates `DATA` chunks into `g_realloc`'d `priv->data` with no cap. | Bounded in practice by the MCU image size and by the 1 s command timeout; a cap would be a protocol-behaviour change needing hardware. |
| C12 | `tests/` is overwhelmingly source-text assertions. | Appropriate for a driver that cannot be exercised in CI, and the repo already documents that hardware readiness is not established by the suite. The new tests follow the same convention. |
| C13 | `flake.nix` input is unpinned (no `flake.lock`). | Rejected before, in ticket 96, with a reason. Not revisited. |
| C14 | `install.sh` does not verify the DLL's integrity (no hash). | Worth adding once a canonical hash is published; today the DLL's provenance is the user's Windows install. |
| C15 | Nix `postPatch` copies `*.c`/`*.h` with a bare glob; a future non-source file in `libfprint-driver/` would be silently ignored (and an empty match would make `cp` fail). | Low impact; a `cp` of an explicit list would be marginally safer. |
| C16 | `scripts/verify-common.sh` `verify_init` runs before the `set -euo pipefail` the callers install. | Existing convention across all three verify scripts; changing it risks altering their (hardware-run) behaviour. |

---

## D. Change list

| File | Change |
|---|---|
| `libfprint-driver/goodix.c` | A7, B1, B2, B3, B4, B5, B8, B9; review follow-up completes armed reads on retry exhaustion, destroys stale retry sources, and preserves failure status from deinit |
| `libfprint-driver/goodix.h` | B9 |
| `libfprint-driver/goodix5e0a.c` | B6, B10; review follow-up preserves the Milan identify journal line for unusable galleries |
| `libfprint-driver/goodix5xx.c` | A8 |
| `libfprint-driver/goodix5xx.h` | A8 (contract comment) |
| `libfprint-driver/goodix_milan.c` | A1–A7, B7; review follow-up validates the exact export-RVA width, parses through a fully backed image copy, and sorts in-place on OOM |
| `libfprint-driver/goodixtls.c` | B3 |
| `libfprint-goodix.nix` | B11 |
| `tests/tier1_feature/test_f77_multi_finger_gallery.py` | B6: single gallery reader / single engine call; assert no-match journal preservation |
| `tests/tier1_feature/test_f84_optimistic_verify_fast_path.py` | B6: fast path must use the engine verdict; corrected verify-vs-identify gate description |
| `tests/tier5_adversarial/test_m1_c1_lifecycle_adversarial.py` | B1: bounded backoff completes the armed command and init destroys stale retry sources |
| `tests/tier5_adversarial/test_m3_audit_hardening.py` | **new** — 24 source guards, including follow-up coverage for B4, B10, B11, sort OOM fallback, export metadata safety, and identify logging |

## E. Honest limits

- No full compilation of `goodix.c` / `goodix5e0a.c` / `goodix5xx.c` or the
  entire `goodix_milan.c` translation unit (libfprint, GUsb, GLib and OpenSSL
  headers are absent). The native CI lane (`GOODIX_NATIVE_TESTS=required`) needs
  `nix-build` and was not available. The changed `sh_qsort` and `get_export`
  functions were compiled and exercised in an extracted standalone harness.
- No hardware run, so no claim is made about latency, FRR/FAR, suspend, or the
  parked-TLS TTL. Driver changes are source-guarded and the available software
  suite passes; the harness did not load the real vendor DLL.
- `sh_qsort` was tested against a stand-in comparator, not the real engine's
  comparator inside the loaded DLL.
