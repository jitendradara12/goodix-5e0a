# Goodix 27c6:5e0a Linux Driver

Linux fingerprint driver for Goodix 27c6:5e0a sensors (found in laptops like the Realme Book Prime).

Requires x86-64 Linux and firmware `GFUSB_GM168SEC_APP_10036`. Other sensors,
firmware revisions and per-unit capture settings are not automatically supported.

Runs as a libfprint module and loads Goodix's Windows engine (`GoodixEngineAdapter.dll`) via a PE loader.

## Install

```bash
git clone https://github.com/jitendradara12/goodix-5e0a.git
cd goodix-5e0a
./install.sh
./install.sh --integrate
sudo systemctl restart fprintd
fprintd-enroll
```

See `./install.sh --help` for custom DLL paths or uninstalling.

### Upgrading from the previous matching pipeline

Enroll your fingers again after upgrading to the band-pass/native-raster driver.
Old saved prints use incompatible image processing and are rejected. Remove
them through your desktop's fingerprint settings, then enroll again. With the
command-line tools, `fprintd-delete "$USER"` removes your existing fingerprints;
follow it with `fprintd-enroll` to create a new enrollment.

The corrected processing is enabled by default; no experiment flag or Windows
calibration export is needed. See [validation and scope](docs/native-raster-validation.md).

### NixOS

```nix
inputs.goodix.url = "github:jitendradara12/goodix-5e0a";

# configuration.nix
imports = [ inputs.goodix.nixosModules.default ];
services.fprintd.goodix.pamServices = true;
```

## Login Setup (PAM)

- **Fedora / RHEL:** Handled automatically by `./install.sh --integrate`.
- **Ubuntu / Debian:** Install `libpam-fprintd` and run `sudo pam-auth-update`.
- **Arch:** Add `pam_fprintd.so` to `/etc/pam.d/system-local-login` and `/etc/pam.d/sudo`.

## Enroll Fails?

Many laptops lock the sensor with a unique hardware key during Windows setup.
For `bad record MAC` / TLS failures, start with the **[Linux-only key recovery
instructions](docs/psk-extraction.md)**. The helper verifies the recovered key
against your sensor before saving it; Windows is a fallback when that record
cannot be recovered.

Successful recovery proves the key matches the sensor; it does not test TLS,
capture or accuracy. If TLS succeeds but matching fails, see the separate
**[hardware test](docs/HARDWARE_TEST.md)**.
It includes a current-settings regression run and Jet-Soup's capture candidate;
the latter is not enabled in the normal driver.

## License and Credits

- huge thanks to @ptrip7 for their help on the native raster experiments
- Thanks to @Jet-Soup for discovering and contributing Linux-only PSK recovery,
  documenting the record layout, and supplying their Windows-derived capture settings.
- Driver code: LGPL-2.1-or-later ([LICENSE](LICENSE)).
- `GoodixEngineAdapter.dll`: Proprietary Goodix binary included for research.
