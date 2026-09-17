# Goodix 27c6:5e0a Linux driver

Linux fingerprint support for the Goodix 27c6:5e0a sensor, Goodix "Milan" / ChicagoH, GF3658-class, found in the Realme Book Prime / Book Slim / Book Enhanced.

Built as a libfprint driver with fprintd. Matching runs the vendor Windows engine, `GoodixEngineAdapter.dll`, in-process through a small PE loader. This proprietary dependency prevents upstream inclusion in libfprint.

## Status and known limits

Enrollment, verification and PAM authentication for sudo/login work on the developer's Realme Book Prime running NixOS. **This is early/beta software. Keep password login available and enroll at least two fingers.**

- Fingerprint unlock immediately after S3 resume is unreliable. A known idle-dispatch defect remains unresolved; see [ticket 95](.scratch/goodix-5e0a/issues/95-closed-batch-hardware-verification.md). Use your password after suspend.
- The latest labeled hardware batch had **0/2 first-try genuine matches**. Earlier batches were fine. Two samples do not establish an overall error rate, but they do rule out a reliability promise.
- The TLS PSK and DAC/threshold tables came from **one unit**. Other units may have different MCU provisioning. Whether the PSK is per-unit or per-model is unconfirmed ([ticket 59](.scratch/goodix-5e0a/issues/59-closed-per-device-psk-file-override.md)); another unit showed different DAC values ([ticket 57](.scratch/goodix-5e0a/issues/57-closed-dynamic-fdt-manual-thresholds.md)). Different provisioning may cause activation or TLS-handshake failure. There is currently no supported provisioning override.
- Linux x86-64 only, because of the PE loader and Windows engine.

## How it works

The driver opens a TLS 1.2 PSK channel to the sensor and uses hardware FDT touch detection. Enrollment takes 12 touches. It normalizes the 64×80 frames with a 3×3 local-mean residual, then passes them to the real Goodix Milan engine loaded from the Windows DLL for enrollment and matching.

## What's in this repo

- `libfprint-driver/`: driver sources.
- `0001-*.patch`: the same sources as a patch against the pinned libfprint fork.
- `libfprint-goodix.nix`, `nixos-module.nix`, `flake.nix`: first-party Nix packaging and integration.
- `install.sh`: installer for other Linux distributions.
- `windows_driver/`: the vendor DLL.
- `legacy-experiments/` and `.scratch/`: archived research and reverse-engineering provenance. **DO NOT run these scripts casually.** Some poke the sensor directly and can brick device state.
- `tests/`: software tests.

## The DLL and legal notice

**`GoodixEngineAdapter.dll` and the other `windows_driver/` files are proprietary Goodix binaries**, copied from a Windows driver installation for interoperability research. No license to redistribute them is claimed or implied. If you are Goodix or a rights holder and want them removed, open an issue or email the maintainer; they will be removed. The Linux-side code is LGPL-2.1-or-later, like libfprint. The embedded PSK was captured from the developer's own unit.

## Install — any distro

Requirements: Linux x86_64, `sudo`, the sensor connected over USB (`lsusb` must show `27c6:5e0a`), and `GoodixEngineAdapter.dll`.

Get the DLL from your Windows dual-boot installation. Search `C:\Windows\System32\WinDriver\` or the Goodix driver folders for `GoodixEngineAdapter.dll`. Alternatively, extract it from your laptop vendor's Windows fingerprint driver installer. Put it in `./windows_driver/` after cloning, or pass its location with `--dll`.

```bash
git clone https://github.com/jitendradara12/goodix-5e0a.git
cd goodix-5e0a
sudo ./install.sh            # or: sudo ./install.sh --dll /path/to/GoodixEngineAdapter.dll
```

The installer:

- Installs build dependencies using apt, dnf, pacman or zypper.
- Clones the pinned libfprint fork, applies the patch and builds with Meson into `/usr/local`.
- Installs udev rules and the DLL at `/var/lib/fprint/GoodixEngineAdapter.dll`.
- Reloads udev and fixes up `ldconfig` so the new library is found.

Then enroll and test. The package providing the fprintd CLI differs by distro; install it if these commands are missing.

```bash
sudo systemctl restart fprintd
fprintd-enroll
fprintd-verify
```

Most distros ship `pam_fprintd` with fprintd. Enable fingerprint authentication in your auth stack: `pam-auth-update` on Ubuntu/Debian, `authselect enable-feature with-fingerprint` on Fedora, or edit `/etc/pam.d/sudo` and `/etc/pam.d/system-local-login` on Arch following its PAM guidance. Keep a password-authenticated session open while changing PAM.

**This libfprint build contains ONLY the `goodixtls5e0a` driver.** It replaces your system libfprint for fingerprint authentication, so other fingerprint readers would stop working. The target laptops have only this sensor.

## NixOS / flake

Add the input to your flake, then import the module in your NixOS configuration with `goodix` available from the flake inputs:

```nix
# flake.nix
inputs.goodix.url = "github:jitendradara12/goodix-5e0a";

# In your NixOS configuration:
imports = [ goodix.nixosModules.default ];
services.fprintd.enable = true; # Already set up by the module
services.fprintd.goodix.dllFile = ./secrets/GoodixEngineAdapter.dll;
services.fprintd.goodix.pamServices = true; # Opt-in for login/sudo/sddm/hyprlock/swaylock
```

Omit `dllFile` if you place the DLL manually in `/var/lib/fprint/`. The module keeps fprintd resident because daemon idle-exit destroys parked TLS sessions, and adds the `uaccess` udev rule.

At runtime the DLL search order is `/var/lib/fprint` → `/run/current-system/sw/lib` → `/etc/goodix` → `/usr/lib/goodix` → `/usr/local/lib`. Override it with `GOODIX_ENGINE_DLL_PATH`, set in the fprintd service environment.

## Supported hardware

Realme Book Prime is tested. The USB sensor must be `27c6:5e0a`, with firmware string `GFUSB_GM168SEC_APP_10036`; activation otherwise fails with `Invalid device firmware`. The sensor raster is 64×80 at approximately 500 dpi. Other Goodix models are **not supported**. A matching USB ID alone does not resolve the per-unit provisioning limits above.

## Troubleshooting

- Check detection with `lsusb -d 27c6:5e0a` and DLL placement with `ls /var/lib/fprint/GoodixEngineAdapter.dll`.
- Restart and follow logs with `sudo G_MESSAGES_DEBUG=all systemctl restart fprintd`, then `journalctl -u fprintd -f`. Note that systemd does not pass the command's environment to the service; for actual debug output, set `Environment=G_MESSAGES_DEBUG=all` in a temporary `[Service]` override using `sudo systemctl edit fprintd`, then restart it.
- `failed to load GoodixEngineAdapter.dll` at device open means the engine did not load. Check file readability and `GOODIX_ENGINE_DLL_PATH` in the service environment.
- `Invalid device firmware` means the required firmware string does not match. This driver does not support that firmware.
- Activation/TLS-handshake failures on another unit may be provisioning differences; there is no supported PSK or DAC/threshold override.
- After suspend, use your password. Immediate fingerprint unlock is a known issue.
- After driver updates, use `fprintd-delete "$USER"` and re-enroll with `fprintd-enroll`. Templates are not portable across engine versions.

## Development

```bash
bash tests/run_all_tests.sh
```

These are software tests; no hardware is needed. Some tiers need Nix for the native harness; see [scripts/README-native-tests.md](scripts/README-native-tests.md). Keep the patch synchronized: `libfprint-driver/` sources are byte-embedded in `0001-*.patch`, checked by `test_f25`.

## License

Linux-side code: **LGPL-2.1-or-later**. See [LICENSE](LICENSE) for the full LGPL v2.1 text. Vendor DLLs remain proprietary; see [the DLL and legal notice](#the-dll-and-legal-notice).
