# Goodix 27c6:5e0a Linux driver

Linux fingerprint driver for Goodix 27c6:5e0a sensors, found in laptops like the Realme Book Prime.

The driver runs as a libfprint module with fprintd. It loads Goodix's Windows engine, `GoodixEngineAdapter.dll`, inside the process through a custom PE loader. Because it depends on this binary, upstream libfprint cannot include it.

## Installation

For all distributions other than NixOS, run `install.sh`.

```bash
git clone https://github.com/jitendradara12/goodix-5e0a.git
cd goodix-5e0a
./install.sh
sudo systemctl restart fprintd
fprintd-enroll
fprintd-verify
```

The script builds the driver and installs fprintd. It does not touch your PAM configuration or overwrite system packages.

Useful flags:

- `--check` inspects system state and reports missing packages without making changes.
- `--dll /path/to/GoodixEngineAdapter.dll` loads a custom engine DLL instead of the bundled copy.
- `--uninstall` removes all files installed by this script.

### SELinux on Fedora and RHEL

SELinux blocks fprintd from writing to the memory buffer needed by the loader. Install the policy module before running fprintd:

```bash
cd packaging/selinux
checkmodule -M -m -o goodix-engine.mod goodix-engine.te
semodule_package -o goodix-engine.pp -m goodix-engine.mod
sudo semodule -i goodix-engine.pp
```

### PAM login setup

Enrolling prints stores them, but logging in with them requires the PAM module.

- Ubuntu and Debian: install `libpam-fprintd`, run `sudo pam-auth-update`, and enable fingerprint authentication.
- Fedora and RHEL: run `sudo dnf install fprintd-pam && sudo authselect enable-feature with-fingerprint && sudo authselect apply-changes`.
- Arch: add `pam_fprintd.so` to `/etc/pam.d/system-local-login` and `/etc/pam.d/sudo`.

## NixOS

Add the repository to your flake inputs and import the module:

```nix
# flake.nix
inputs.goodix.url = "github:jitendradara12/goodix-5e0a";

# configuration.nix
imports = [ inputs.goodix.nixosModules.default ];
services.fprintd.goodix.pamServices = true;
```

The module uses the bundled DLL by default. Set `services.fprintd.goodix.dllFile = ./path/to/dll;` to supply your own.

## Development

Run tests with:

```bash
bash tests/run_all_tests.sh
```

These software tests do not require the physical sensor.

## Known limits

- Fingerprint unlock fails right after waking from S3 sleep. Type your password instead.
- Encryption keys and calibration tables come from one tested laptop. Other units might have different factory provisioning and fail the handshake.
- Keep password login enabled and enroll more than one finger.

## License

Linux driver code is licensed under LGPL-2.1-or-later. See [LICENSE](LICENSE) for details.

The files in `windows_driver/`, including `GoodixEngineAdapter.dll`, are proprietary binaries from Goodix, included for compatibility research.
