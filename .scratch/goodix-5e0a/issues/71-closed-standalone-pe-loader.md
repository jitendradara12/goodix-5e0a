# 71 — Standalone In-Process PE Loader for GoodixEngineAdapter.dll

**What to build:**
Create a standalone Linux CLI test harness (`experiments/test_goodix_loader.c`) that loads `/home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll` into memory natively (no Wine) using the in-process PE loader technique from `/tmp/ft9201-libfprint/src/ft_engine.c`.
The loader maps sections (`R-X` code, `R-W` data), sets up the `%gs` Windows TEB via `arch_prctl(ARCH_SET_GS)`, resolves UCRT and Win32 imports to libc shims, executes `DllMain`, and resolves exported functions (`getAlgorithmVersion`, `enrolStart`, `identifyImage`).

**Blocked by:** 70 (closed).

**Status:** closed (verdict: confirmed — Milan engine loaded natively in-process on Linux, successor 72)

---

## 1. Problem & Architecture

1. **The Match-on-Host Aperture Bottleneck**:
   - Tickets 1–70 solved hardware transport, TLS 1.2 PSK, and raw $64 \times 80$ frame capture.
   - However, NIST Bozorth3 cannot reliably discriminate $64 \times 80$ micro-aperture prints without either high FAR (70% false accept with 8 fingers) or high FRR (failing genuine casual touches).
2. **The In-Process PE Loader Solution**:
   - `GoodixEngineAdapter.dll` contains Goodix's proprietary `Milan_Flat_V1.06.15` / `Milan_v_3.02.00.20` matching engine with template stitching.
   - On x86-64 Linux, glibc uses `%fs` for TLS, leaving `%gs` free for the Windows Thread Environment Block (TEB).
   - Mapping code and data via separate memory permissions (`R-X` and `R-W`) ensures complete compliance with systemd's `MemoryDenyWriteExecute=yes`.
3. **Scope for Ticket 71**:
   - Pure standalone experiment in `experiments/test_goodix_loader.c`.
   - Zero changes to the production driver or test suite.
   - Proves `GoodixEngineAdapter.dll` can be initialized and its exported functions called cleanly from Linux C code.

---

## 2. Invariants & Guardrails (AGENTS.md)

- Standalone experiment only: no modifications to `libfprint-driver/goodix5e0a.c` or `.h`.
- Driver invariants (`0x32` timeout 0, `0x34` finite guard, park TTLs, non-reissuing `CANCELLED`) remain completely untouched.
- Clean memory handling: no W^X mapping violations.

---

## 3. Implementation Steps

1. Port PE parser and memory mapping from `/tmp/ft9201-libfprint/src/ft_engine.c`.
2. Implement required imports for `GoodixEngineAdapter.dll`:
   - UCRT functions: `api-ms-win-crt-string-*`, `api-ms-win-crt-heap-*`, `api-ms-win-crt-stdio-*`, `api-ms-win-crt-math-*` (redirect to libc).
   - KERNEL32: critical sections, thread IDs, heap allocation, `arch_prctl` TEB setup.
   - ADVAPI32: `CryptAcquireContextW`, `CryptGenRandom`, registry stubs.
   - WS2_32 / WINMM: dummy returns / timeGetTime.
3. Call `DllMain(base, DLL_PROCESS_ATTACH, NULL)`.
4. Resolve `getAlgorithmVersion` export and invoke it.

---

## 4. Acceptance Criteria & Predicted Signatures

- [x] Harness compiles with gcc: `gcc -O2 -o experiments/test_goodix_loader experiments/test_goodix_loader.c -lm`.
- [x] Running `./experiments/test_goodix_loader`:
  - Logs `[loader] TEB installed in %gs`.
  - Logs `[loader] DllMain returned 1`.
  - Resolves `getAlgorithmVersion` and prints Milan version string (e.g. `Milan_v_...`).
  - Resolves `WbioQueryEngineInterface` and returns version `0x3`.
  - Exits with return code 0.

---

## 5. Verification Evidence (2026-09-14)

### Execution Log:
```text
=== Ticket 71: Goodix In-Process Loader Test ===
Target DLL: /home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll
[loader] Registered 191 shims
[loader] PE parsed: ImageBase=0x180000000, SizeOfImage=0x1f7000, Entry RVA=0x72670, Sections=6
[loader] file-backed image mapped @ 0x180000000 (W^X satisfied)
[loader] TLS template 8 bytes wired
[loader] TEB installed in %gs
[loader] calling entry (DllMain) @ 0x180072670 ...
[loader] DllMain returned 1

=== Testing Goodix Algorithm Version Export ===
[loader] Found getAlgorithmVersion @ 0x180078ed0
[loader] getAlgorithmVersion() returned 0
[loader] Milan Version String: "Milan_v_3.02.00.20"

=== Testing WinBio Engine Interface Export ===
[loader] Found WbioQueryEngineInterface @ 0x18005b3f0
[loader] WbioQueryEngineInterface returned 0, iface=0x180130400
[loader] WinBio Engine Interface Version: 0x3

[SUCCESS] Ticket 71 VERIFIED: GoodixEngineAdapter.dll loaded and executed natively on Linux!
```

### Full Test Suite Run:
- Command: `bash tests/run_all_tests.sh`
- Result: `459 passed, 0 failed, 1 skipped (env-gated) in 19s`. Zero regressions.

### Verdict:
**CONFIRMED**. `GoodixEngineAdapter.dll` executes natively in-process on Linux with zero Wine and complete W^X safety. Successor: Ticket 72 (`72-ready-for-agent-offline-milan-shootout.md`).

