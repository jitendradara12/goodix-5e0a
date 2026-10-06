# 109 — Per-device PSK override and DPAPI extraction tools (Issue #10)

**What was built:**
1. Implemented `/etc/libfprint/goodix-5e0a.psk` read-only override loader in `libfprint-driver/goodix5e0a.c`. When present, reads 64 hex characters (32 bytes) and overrides `xx_cls->psk` dynamically during `dev_open`. Falls back to canonical static key if absent.
2. Added `tools/dump_dpapi_blob.py`: Linux read-only USB dumper that reads slot `0xbb010002` (DPAPI sealed blob -> `dpapi_blob.bin`) and slot `0xbb020001` (MCU PSK hash -> `mcu_hash.txt`) without modifying hardware state.
3. Added `tools/decrypt_psk.ps1`: Windows PowerShell script that decrypts `dpapi_blob.bin` via `CryptUnprotectData` under SYSTEM privileges, validates against `mcu_hash.txt`, and generates `goodix-5e0a.psk`.

**Blocked by:** None. Supersedes Ticket 59 shelving based on GitHub Issue #10 external hardware evidence.

**Status:** closed

**Verdict:** Closed (software-complete, test suite 356/356 green). Closes external blocker for users with non-default machine PSK.
