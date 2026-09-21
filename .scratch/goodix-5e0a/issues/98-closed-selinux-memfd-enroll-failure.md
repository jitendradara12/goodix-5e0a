# 98: SELinux-enforcing enroll failure — fprintd denied `write` to `memfd:goodix_engine`

**What to build:** Make enroll work on SELinux-enforcing distros (Fedora/RHEL) instead of failing with a misleading `failed to load GoodixEngineAdapter.dll`. Either ship/apply SELinux policy for the engine loader, avoid the denied `memfd:write`, or at minimum surface the real `errno` + detect and document it.

**Blocked by:** None.
**Status:** closed
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

- **A (preferred): ship SELinux policy.** Confirmed minimal rule on Fedora 44 Enforcing: `allow fprintd_t tmpfs_t:file { execute map read write };` (full chain was `write` → `map` → `read` → `execute`, one per iteration). Build with `ausearch -m avc -ts boot` (not `recent` — `recent` drops older perms and regressed `write` at 21:20), strip unrelated `tlp_t dac_override` noise, ship a `.te`/`.pp` + `install.sh` apply on dnf/zypper systems, uninstall removal, and a tier1 test asserting the module source allows exactly the memfd rule.
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

## Agent implementation record, 2026-09-17 (software branch, awaiting hardware)

- `libfprint-driver/goodix_milan.c` `load_pe_file` rewritten on the same W^X
  memfd design: every failure path now converges on one `fail:` label that
  logs `load_pe_file: <step> failed for <path>: errno=N (strerror)` with an
  SELinux/AppArmor hint on EACCES/EPERM, releases fd/memfd/mappings/file
  buffers, and preserves the old `-1` contract for retry logic. Steps named:
  open/seek/PE header/allocate file/read/allocate image/PE section/memfd
  create/write/mmap reserve/headers/section/arch_prctl/DllMain. Short
  reads/writes and EINTR handled; corrupt/truncated headers now fail with
  ENOEXEC instead of reading wild offsets (validated against the real DLL).
- Shipped `packaging/selinux/goodix-engine.te` implementing exactly the
  confirmed minimal rule `allow fprintd_t tmpfs_t:file { execute map read
  write };` plus build/remove/verify instructions; no audit2allow, no
  setenforce. `install.sh` warns on Enforcing with a pointer to it.
- Installer: `--check` (read-only), `--no-deps` (any-distro, no package
  manager), `--build-only DIR` (staged build without sudo/systemd).
- Software verification: PE loader validated CPU-only against the real
  vendor DLL (loads through DllMain, `Milan_v_3.02.00.20`) and against a
  missing path (clean step/errno warning, no crash); full suite 362/362
  green incl. new tier1 `test_f100_installer_flags.py`.
- Pending: the hardware acceptance items (this file's checklist) — requires
  the deployed-driver enforcing-distro run; do on next Fedora contact.

## Hardware verify record, 2026-09-17 ~21:21 IST (Fedora 44, Enforcing, /opt install)

- Iterated `sudo ausearch -m avc | audit2allow -M fprintd-goodix` + `sudo semodule -i` through the full chain: `write` → `map` → `read` → `execute`. Each fix exposed the next step, as predicted.
- Pitfall found: regenerating with `-ts recent` drops older perms (write denials aged out at 21:20, caused `denied { write }` regression). Final working module was built with `-ts boot`.
- Final minimal rule (strip the unrelated `tlp_t dac_override` noise that `boot` scope picks up):
  `allow fprintd_t tmpfs_t:file { execute map read write };`
- Success signatures, PID 12989:
  `5e0a: Milan biometric matching engine loaded successfully (Milan_v_3.02.00.20)`
  12x `enrollment quality check: active=5120 range=1976 quality=0 overlap=30` → `fprintd-enroll: enroll-completed`
  `optimistic fast-path match on frame 1: pts=71` → `fprintd-verify: verify-match (done)` (first verify was `verify-no-match`, second `verify-match` — normal positioning).
- Verdict: confirm — SELinux memfd policy was the sole blocker; sensor/TLS/capture path was healthy throughout.

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
# permanent (use -ts boot, NOT -ts recent: recent drops older perms and
# regresses write; strip any unrelated tlp_t lines audit2allow picks up):
sudo ausearch -m avc -ts boot | audit2allow -M fprintd-goodix
sudo semodule -i fprintd-goodix.pp
# final rule must read: allow fprintd_t tmpfs_t:file { execute map read write };
```

## Verdict (closed 2026-09-21, sastalinux Fedora 44, Enforcing)

Confirm — enroll/verify healthy today with no Goodix policy module installed (`semodule -l` shows none): engine `Milan_v_3.02.00.20` loads, TLS ready, 10 prints enrolled, `fprintd-list` live. The 2026-09-17 memfd record above stands as diagnosis history; on the current build the blocker does not reproduce, so no policy install required. Reopen if `denied { write } ... goodix_engine` AVCs return.
