# Goodix 27c6:5e0a Linux driver

Linux fingerprint support for the Goodix 27c6:5e0a sensor, Goodix "Milan" / ChicagoH, GF3658-class, found in the Realme Book Prime / Book Slim / Book Enhanced.

Built as a libfprint driver with fprintd. Matching runs the vendor Windows engine, `GoodixEngineAdapter.dll`, in-process through a small PE loader. This proprietary dependency prevents upstream inclusion in libfprint.

## Status and known limits

Enrollment, verification and PAM authentication for sudo/login work on the developer's Realme Book Prime running NixOS. **This is early/beta software. Keep password login available and enroll at least two fingers.** Non-NixOS installs are newer and less exercised; if verification fails there, see the limits below before assuming you did something wrong.

- Fingerprint unlock immediately after S3 resume is unreliable. A known idle-dispatch defect remains unresolved; see [ticket 95](.scratch/goodix-5e0a/issues/95-closed-batch-hardware-verification.md). Use your password after suspend.
- The latest labeled hardware batch had **0/2 first-try genuine matches**. Earlier batches were fine. Two samples do not establish an overall error rate, but they do rule out a reliability promise.
- The TLS PSK and DAC/threshold tables came from **one unit**. Other units may have different MCU provisioning. Whether the PSK is per-unit or per-model is unconfirmed ([ticket 59](.scratch/goodix-5e0a/issues/59-closed-per-device-psk-file-override.md)); another unit showed different DAC values ([ticket 57](.scratch/goodix-5e0a/issues/57-closed-dynamic-fdt-manual-thresholds.md)). Different provisioning may cause activation or TLS-handshake failure. There is currently no supported provisioning override.
- Linux x86-64 only, because of the PE loader and Windows engine.

## How it works

The driver opens a TLS 1.2 PSK channel to the sensor and uses hardware FDT touch detection. Enrollment takes 12 touches. It normalizes the 64×80 frames with a 3×3 local-mean residual, then passes them to the real Goodix Milan engine loaded from the Windows DLL for enrollment and matching.

## What's in this repo

- `libfprint-driver/`: driver sources (single source of truth).
- `goodix-5e0a-integration.patch`: Meson/hwdb registration and fprintd compatibility (version and retry enum) — applied by the flake and install.sh; driver sources are copied in from `libfprint-driver/`.
- `libfprint-goodix.nix`, `nixos-module.nix`, `flake.nix`: first-party Nix packaging and integration.
- `install.sh`: installer for other Linux distributions (any distro with `--no-deps`; staging builds for non-systemd systems with `--build-only`; `--check` reports runtime and desktop-integration gaps without changing anything).
- `packaging/selinux/`: SELinux policy for the engine memfd on enforcing distros (Fedora/RHEL).
- `windows_driver/`: the vendor DLL.
- `legacy-experiments/` and `.scratch/`: archived research and reverse-engineering provenance. **DO NOT run these scripts casually.** Some poke the sensor directly and can brick device state. The engineering log lives in `.scratch/goodix-5e0a/issues/` — one ticket per experiment, each with predicted signatures and confirm/falsify verdicts (`.scratch/goodix-5e0a/96-review-log.md` records the review trail for the portability work).
- `tests/`: software tests.

## The DLL and legal notice

**`GoodixEngineAdapter.dll` and the other `windows_driver/` files are proprietary Goodix binaries**, copied from a Windows driver installation for interoperability research. No license to redistribute them is claimed or implied. If you are Goodix or a rights holder and want them removed, open an issue or email the maintainer; they will be removed. The Linux-side code is LGPL-2.1-or-later, like libfprint. The embedded PSK was captured from the developer's own unit.

## Install — any distro

Requirements: Linux x86_64 with the build tools and libraries listed in [Manual dependencies](#manual-dependencies), and the sensor connected over USB (`lsusb` must show `27c6:5e0a`). NixOS uses the first-party module below; every other distro uses `install.sh`.

**The engine DLL ships in this repo** (`windows_driver/GoodixEngineAdapter.dll`, from the developer's unit — see the legal notice). You do not need to obtain one. If your laptop shipped a different Goodix engine version and you prefer your own copy: take it from a Windows dual-boot (`C:\Windows\System32\WinDriver\` or the Goodix driver folders), or unpack your vendor's Windows driver installer on any machine (e.g. `7z x VendorSetup.exe`) and pass it with `--dll`.

On NixOS, skip to [NixOS / flake](#nixos--flake) — `install.sh` refuses to run there.

```bash
git clone https://github.com/jitendradara12/goodix-5e0a.git
cd goodix-5e0a
./install.sh                        # or: ./install.sh --dll /path/to/GoodixEngineAdapter.dll
```

The installer installs everything it needs, including `fprintd` itself (its package also ships the `fprintd-enroll`/`fprintd-verify` commands used below). It does not replace your system libfprint, does not touch PAM or USB permissions, and does not restart services. `./install.sh --uninstall` removes only files this script installed.

Flags:

- `--no-deps`: skip package-manager calls on any distro (including ones without a recipe). The installer then only checks that tools and libraries are present and tells you exactly what is missing.
- `--build-only DIRECTORY`: compile the pinned fork into a staging tree without sudo, systemd, or package installation. For non-systemd distros (Void, Artix, Alpine/musl is NOT supported — x86_64 glibc assumptions in the PE loader) and packagers. Integrate the staged tree with your init/service manager yourself; the daemon needs `LD_LIBRARY_PATH` and `GOODIX_ENGINE_DLL_PATH` pointing at the staged files, set on the D-Bus-activated fprintd unit.
- `--check`: read-only report of sensor, fprintd, SELinux, and PAM state. Changes nothing.
- `--dll FILE`: use a specific engine copy (see above).

```bash
sudo systemctl restart fprintd   # 'not active' is normal: fprintd is dbus-activated
fprintd-enroll
fprintd-verify
```

### SELinux (Fedora/RHEL, enforcing)

Stock policy denies fprintd write access to the memfd the loader uses, so enroll fails with `failed to load GoodixEngineAdapter.dll` even though the DLL is readable. Build and install the shipped minimal policy (see [packaging/selinux/README.md](packaging/selinux/README.md)):

```bash
cd packaging/selinux
checkmodule -M -m -o goodix-engine.mod goodix-engine.te
semodule_package -o goodix-engine.pp -m goodix-engine.mod
sudo semodule -i goodix-engine.pp
```

The installer warns when it detects Enforcing. Do not `setenforce 0` as a fix.

### PAM / desktop integration

`fprintd-enroll` stores prints; fingerprint login needs the PAM module, which is intentionally not touched by the installer. Keep a password session open while configuring.

- Debian/Ubuntu: `sudo apt install libpam-fprintd`, then `sudo pam-auth-update` and tick **Fingerprint authentication**.
- Fedora/RHEL (authselect-managed):
  ```bash
  sudo dnf install fprintd-pam
  sudo authselect enable-feature with-fingerprint
  sudo authselect apply-changes
  ```
  Then log out/in; the **Fingerprint Login** row appears in GNOME Settings > Users.
- Arch: add `pam_fprintd.so` to `/etc/pam.d/sudo` and `/etc/pam.d/system-local-login`.
- Anything else: install your distro's pam_fprintd module and enable it in your auth stack.

`./install.sh --check` reports which of these are missing on your system.

### Manual dependencies

Build tools: `git meson ninja pkg-config gcc g++`. Libraries (pkg-config names): `glib-2.0 gusb libusb-1.0 pixman-1 nss nspr openssl gobject-introspection-1.0`. Runtime: `fprintd` and a root-run D-Bus/systemd activation of it (or manual service configuration via `--build-only`).

**Non-NixOS installation is new and end-to-end unverified** — treat it as beta and keep password login working.

## NixOS / flake

Add the input to your flake, then import the module in your NixOS configuration with `goodix` available from the flake inputs:

The module uses the DLL bundled in `windows_driver/` by default. Set `services.fprintd.goodix.dllFile` to use a different engine copy, or `null` to manage it manually.

```nix
# flake.nix
inputs.goodix.url = "github:jitendradara12/goodix-5e0a";

# In your NixOS configuration (add the input to specialArgs, e.g.
#   specialArgs = { inherit inputs; };
# or reference it fully-qualified as shown):
imports = [ inputs.goodix.nixosModules.default ];
# Optional: use a different GoodixEngineAdapter.dll (default: the bundled one)
# services.fprintd.goodix.dllFile = ./secrets/GoodixEngineAdapter.dll;
# Optional: fingerprint for login/sudo/sddm/hyprlock/swaylock (default: false)
services.fprintd.goodix.pamServices = true;
```

With `dllFile = null`, place the DLL manually in `/var/lib/fprint/`. The module adds a restrictive USB rule for the sensor (0660 + uaccess; the package's shipped rules file is empty for this device). The module keeps fprintd resident because daemon idle-exit destroys parked TLS sessions. `pamServices` sets the fingerprint default for those five services only; other PAM services keep standard NixOS behavior, and explicit per-service settings override it.

At runtime the DLL search order is `/var/lib/fprint` → `/run/current-system/sw/lib` → `/etc/goodix` → `/usr/lib/goodix` → `/usr/local/lib`. Override it with `GOODIX_ENGINE_DLL_PATH`, set in the fprintd service environment.

## Supported hardware

Realme Book Prime is tested. The USB sensor must be `27c6:5e0a`, with firmware string `GFUSB_GM168SEC_APP_10036`; activation otherwise fails with `Invalid device firmware`. The sensor raster is 64×80 at approximately 500 dpi. Other Goodix models are **not supported**. A matching USB ID alone does not resolve the per-unit provisioning limits above.

## Troubleshooting

- Check detection with `lsusb -d 27c6:5e0a`. Where the engine DLL lives depends on install route: `/opt/goodix-libfprint/GoodixEngineAdapter.dll` (install.sh), `/var/lib/fprint/GoodixEngineAdapter.dll` (NixOS with `dllFile = null`), or the store path shown by `journalctl -u fprintd | grep -m1 GOODIX`.
- Follow logs with `journalctl -u fprintd -f`. For debug output, use `sudo systemctl edit fprintd` to add `Environment=G_MESSAGES_DEBUG=all` under `[Service]`, then `sudo systemctl restart fprintd`. Remove that temporary setting when finished; systemd does not inherit environment variables from the restart command.
- `failed to load GoodixEngineAdapter.dll` at device open means the engine did not load. Check file readability and `GOODIX_ENGINE_DLL_PATH` in the service environment. On SELinux-enforcing systems the real cause is usually the memfd denial above; the loader now also logs the failing step and errno, so follow that message before anything else.
- `Invalid device firmware` means the required firmware string does not match. This driver does not support that firmware.
- Activation/TLS-handshake failures on another unit may be provisioning differences; there is no supported PSK or DAC/threshold override.
- After suspend, use your password. Immediate fingerprint unlock is a known issue.
- After driver updates, use `fprintd-delete "$USER"` and re-enroll with `fprintd-enroll`. Templates are not portable across engine versions.

## Development

```bash
bash tests/run_all_tests.sh
```

These are software tests; no hardware is needed. Some tiers need Nix for the native harness; see [scripts/README-native-tests.md](scripts/README-native-tests.md). Driver sources live only in `libfprint-driver/`; the flake and install.sh copy them into the fork and apply `goodix-5e0a-integration.patch` on top.

## License

Linux-side code: **LGPL-2.1-or-later**. See [LICENSE](LICENSE) for the full LGPL v2.1 text. Vendor DLLs remain proprietary; see [the DLL and legal notice](#the-dll-and-legal-notice).
