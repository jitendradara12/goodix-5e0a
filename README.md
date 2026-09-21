# Goodix 27c6:5e0a Linux driver

Linux fingerprint driver for Goodix 27c6:5e0a sensors, found in laptops like the Realme Book Prime.

Runs as a libfprint module. It loads Goodix's Windows engine, `GoodixEngineAdapter.dll`, inside the process via a PE loader. This proprietary dependency prevents upstreaming.

## Installation

Run `install.sh` for all distributions except NixOS. See `./install.sh --help` for custom DLL paths or uninstalling.

```bash
git clone https://github.com/jitendradara12/goodix-5e0a.git
cd goodix-5e0a
./install.sh
sudo systemctl restart fprintd
./install.sh --integrate
fprintd-enroll
fprintd-verify
```

### SELinux on Fedora and RHEL

Install the policy module before running fprintd:

```bash
cd packaging/selinux
checkmodule -M -m -o goodix-engine.mod goodix-engine.te
semodule_package -o goodix-engine.pp -m goodix-engine.mod
sudo semodule -i goodix-engine.pp
```

### PAM login setup

Logging in requires the PAM module.

- Ubuntu and Debian: install `libpam-fprintd`, run `sudo pam-auth-update`, and enable fingerprint authentication.
- Fedora and RHEL: run `./install.sh --integrate` (installs nothing; enables `with-fingerprint` via authselect).
- Arch: add `pam_fprintd.so` to `/etc/pam.d/system-local-login` and `/etc/pam.d/sudo`.

## NixOS

Add the repository to your flake inputs and import the module:

```nix
inputs.goodix.url = "github:jitendradara12/goodix-5e0a";

# configuration.nix
imports = [ inputs.goodix.nixosModules.default ];
services.fprintd.goodix.pamServices = true;
```

Set `services.fprintd.goodix.dllFile = ./path/to/dll;` to supply a custom engine DLL.

## Development

Run tests with `bash tests/run_all_tests.sh`. The sensor is not required.

## Known limits

- Fingerprint unlock fails right after waking from S3 sleep. Type your password instead.
- Encryption keys and calibration tables come from one tested laptop. Other units might have different factory provisioning and fail the handshake.
- Keep password login enabled and enroll more than one finger.

## License

Driver code is LGPL-2.1-or-later. See [LICENSE](LICENSE).

`windows_driver/GoodixEngineAdapter.dll` is a proprietary Goodix binary included for research.
