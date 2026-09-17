# 98: SELinux-enforcing enroll failure — fprintd denied `write` to `memfd:goodix_engine`

**What to build:** Make enroll work on SELinux-enforcing distros (Fedora/RHEL) instead of failing with a misleading `failed to load GoodixEngineAdapter.dll`. Either ship/apply SELinux policy for the engine loader, avoid the denied `memfd:write`, or at minimum surface the real `errno` + detect and document it.

**Blocked by:** None.
**Status:** ready-for-agent
**Owns:** `libfprint-driver/goodix_milan.c` loader, `goodix-5e0a-integration.patch` sync, `install.sh`, README troubleshooting, portability test lane.

## Environment (failing run, 2026-09-17)

- Host: `sastalinux`, Fedora 44 (`fprintd-1.94.5-5.fc44`, `libfprint-1.94.100-1.fc44` via dnf), x86_64, systemd, `getenforce` = `Enforcing`.
- Install route: `./install.sh` → private `/opt/goodix-libfprint` + drop-in `/etc/systemd/system/fprintd.service.d/90-goodix.conf`:
  ```
  Environment=LD_LIBRARY_PATH=/opt/goodix-libfprint/lib
  Environment=GOODIX_ENGINE_DLL_PATH=/opt/goodix-libfprint/GoodixEngineAdapter.dll
  ```
- Device: Goodix `27c6:5e0a` (Milan/ChicagoH path, `goodixtls5e0a`).
- DLL present and readable, correct PE image:
  ```
  -rw-r--r--. unconfined_u:object_r:usr_t:s0 /opt/goodix-libfprint/GoodixEngineAdapter.dll (1.3M)
  file: PE32+ executable for MS Windows 6.00 (DLL), x86-64, 6 sections
  ```

## Repro

```bash
sudo systemctl restart fprintd
fprintd-enroll
# Enrolling right-index-finger finger.
# Enroll result: enroll-stage-passed   (first touch)
# Enroll result: enroll-unknown-error  (every subsequent attempt)
```

## Observed journal signatures (confirm)

`journalctl -u fprintd -b 0` — sensor path healthy, engine never inits, on every PID (10995, 11124, 11226, 11339):

```
5e0a USB reset taken (dirty close, boot_seq=1)
5e0a: failed to load GoodixEngineAdapter.dll
Goodix Milan engine init returned FALSE; will retry on demand
5e0a warm expired: reason=cold-start
5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
5e0a D32 reply: status=0x02 len=16 bytes=[02 00 3f 00 ...]
5e0a D32 touch confirmed: mask=0x3f energy=~1500-1900
5e0a scan_on_read_img: declen=10564
5e0a row-major frame: active_px=5120 nonzero=5120 min=~300-900 max=~2700-3100 geometry=64x80 (WxH)
5e0a frame 1/4 ... 4/4: ... range=~2100-2400 quality=0 overlap=0 score-proxy=0
5e0a best frame N/4: ... (submitting)
5e0a: failed to load GoodixEngineAdapter.dll
Device reported an error during enroll: Failed to start Milan enrollment context
```

`journalctl --grep="AVC|denied"` — one denial per load attempt, same scontext/tcontext every time:

```
audit[10995]: AVC avc: denied { write } for pid=10995 comm="fprintd"
  path=2F6D656D66643A676F6F6469785F656E67696E65202864656C6574656429
  dev="tmpfs" scontext=system_u:system_r:fprintd_t:s0
  tcontext=system_u:object_r:tmpfs_t:s0 tclass=file permissive=0
```

Hex path decodes to `/memfd:goodix_engine (deleted)`:

```python
bytes.fromhex('2F6D656D66643A676F6F6469785F656E67696E65202864656C6574656429')
# b'/memfd:goodix_engine (deleted)'
```

## Root cause

`libfprint-driver/goodix_milan.c:775-779` (`load_pe_file`):

```c
int mfd = memfd_create("goodix_engine", MFD_CLOEXEC);
if (mfd < 0) { free(img); return -1; }
if (write(mfd, img, sizeofimage) != (ssize_t)sizeofimage) {
    close(mfd); free(img); return -1;
}
```

The `write()` to the memfd is what SELinux denies (`fprintd_t → tmpfs_t:file write`). `load_pe_file` returns `-1` → `goodix_milan_init()` logs the generic `g_warning("5e0a: failed to load GoodixEngineAdapter.dll")` (`goodix_milan.c:899`) and returns `FALSE` → `goodix5e0a.c:2038` reports `Failed to start Milan enrollment context` → client sees `enroll-unknown-error`.

This is why the current troubleshooting is misleading: the file *is* readable and `GOODIX_ENGINE_DLL_PATH` *is* correct, but README §Troubleshooting (`failed to load ... Check file readability and GOODIX_ENGINE_DLL_PATH`) points the user at exactly those two things. The loader also discards `errno`, so the journal never shows `EACCES`/SELinux vs. missing-file vs. corrupt-PE.

NixOS is unaffected (no SELinux); every Fedora/RHEL/CentOS install via `install.sh` with `Enforcing` hits this. `install.sh` has zero SELinux handling (no `semanage`/`audit2allow`/policy module, no Enforcing detection/warning).

## Why this is a repo bug, not a local misconfig

1. Default-deny stock policy: `fprintd_t` writing to a `tmpfs_t` memfd is not allowed out of the box. Any new user on an enforcing distro reproduces it.
2. W^X-via-memfd design (tickets 72/73) assumed anonymous-memfd + split `PROT_READ|PROT_EXEC` / `PROT_READ|PROT_WRITE` mappings would work everywhere; it was validated where SELinux is absent.
3. Failure is silent-by-design: generic warning, no `errno`, no path, no `memfd_create/write/mmap` step label. The AVC line is the only ground truth and lives in a different log stream most users never check.

## Suggested fix directions (maintainer picks)

- **A (preferred): ship SELinux policy.** Generate with `ausearch -m avc -ts recent | audit2allow`, e.g. `allow fprintd_t tmpfs_t:file { read write map }` (+ `execute` if the exec mapping trips next — expect a second denial wave on `mmap PROT_EXEC` once `write` is allowed). Ship a `.te`/`.pp` + `install.sh` apply on dnf/zypper systems, uninstall removal, and a tier1 test asserting the module source allows exactly the memfd rule.
- **B: avoid memfd.** Anonymous `MAP_PRIVATE` mappings filled with `memcpy` instead of `memfd + write + mmap(MAP_FIXED)` would sidestep `tmpfs:file write` entirely, at the cost of revisiting the ticket-72 W^X rationale. Needs a security note if chosen.
- **C (minimum, do regardless): observability + docs.**
  - Log `__func__`, step (`memfd_create/write/mmap`), target path, `errno`/`strerror`, and `getenforce` hint in the `failed to load` path; distinguish "file not readable" from "PE mapping failed".
  - `install.sh`: detect `getenforce == Enforcing` on SELinux distros and warn/fail with the `audit2allow` recipe instead of a green "installed" message.
  - README troubleshooting: add the SELinux/memfd row with `journalctl --grep="AVC|denied"` + `python3 -c` hex-decode snippet + temporary `sudo setenforce 0` confirm step.

## Acceptance

- [ ] Fresh Fedora (Enforcing) `install.sh` → `fprintd-enroll` completes 12 touches without `Failed to start Milan enrollment context`.
- [ ] No new denials: `journalctl -b 0 --grep="AVC|denied"` clean across enroll + verify, or denials explicitly covered by the shipped module.
- [ ] Loader failure logs include step + path + errno (manual fault injection: chmod 000 DLL, corrupt DLL, Enforcing on/off).
- [ ] `bash tests/run_all_tests.sh` green; new tier1 test covers SELinux artifact (policy source present / installer warning) and patch sync if `goodix_milan.c` changed.
- [ ] Hardware verify per protocol (hands-off 20s silent; press-hold 20s advances) on the enforcing distro; record PIDs, `getenforce`, `ls -Z`, and journal excerpts in this ticket before closing.

## Predicted signatures

- Confirm (policy/fix works): `Goodix Milan engine init` success (no `returned FALSE`), enroll proceeds past stage 1 through 12 touches, zero `denied { write } ... goodix_engine` AVCs.
- Falsify (still broken): identical `failed to load` + `Failed to start Milan enrollment context` + `denied { write }` triple on next enroll; or `write` allowed but a *new* `denied { execute/map }` on the `PROT_EXEC` mmap step (expected second wave — fix the policy, not the verdict).
- Inconclusive-because-[flaw]: tested with `setenforce 0` only (workaround, not a fix); or tested on NixOS/permissive (wrong population — SELinux not exercised).

## Evidence collected this run

- `journalctl -u fprintd -b 0` full enroll cycles (PIDs 10995/11124/11226/11339), TLS ready + 4/4 frames each attempt.
- `journalctl --grep="AVC|denied"` 11-line denial series, all `fprintd_t → tmpfs_t:file write`, all `memfd:goodix_engine`.
- `ls -Z`, `file`, drop-in `90-goodix.conf`, `getenforce=Enforcing` outputs as quoted above.
- Code refs: `goodix_milan.c:775-779` (memfd+write), `:899` (generic warning), `goodix5e0a.c:2038` (enrollment context error).

## Workaround for users (until fixed)

```bash
# confirm SELinux is the cause (temporary, do not leave permissive):
sudo setenforce 0
fprintd-enroll   # should now advance past stage 1
sudo setenforce 1
# permanent (needs audit log access):
sudo ausearch -m avc -ts recent | audit2allow -M fprintd-goodix
sudo semodule -i fprintd-goodix.pp
```
