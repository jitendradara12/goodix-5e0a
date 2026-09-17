# Evaluation-only checks. No system build, activation or hardware access.
# Run: nix-instantiate --eval --strict tests/tier1_feature/test_f96_nixos_module.nix
let
  pkgs = import <nixpkgs> {};
  eval = settings: (import (pkgs.path + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos-module.nix { system.stateVersion = "26.05"; } settings ];
  }).config;
  default = eval {};
  manual = eval { services.fprintd.goodix.dllFile = null; };
  custom = eval { services.fprintd.goodix.dllFile = ../../LICENSE; };
  optIn = eval { services.fprintd.goodix.pamServices = true; };
  pamOff = default.security.pam.services;
  pamOn = optIn.security.pam.services;
in
assert default.services.fprintd.goodix.dllFile == ../../windows_driver/GoodixEngineAdapter.dll;
assert default.systemd.services.fprintd.environment.GOODIX_ENGINE_DLL_PATH
  == toString ../../windows_driver/GoodixEngineAdapter.dll;
assert !(manual.systemd.services.fprintd.environment ? GOODIX_ENGINE_DLL_PATH);
assert custom.systemd.services.fprintd.environment.GOODIX_ENGINE_DLL_PATH == toString ../../LICENSE;
# Effective PAM: NixOS enables fprintAuth whenever fprintd is enabled, so the
# option must set an explicit false, not merely omit the assignment.
assert pamOff.login.fprintAuth == false;
assert pamOff.sudo.fprintAuth == false;
assert pamOff.hyprlock.fprintAuth == false;
assert pamOn.login.fprintAuth == true;
assert pamOn.sudo.fprintAuth == true;
assert pamOn.sddm.fprintAuth == true;
# The module must ship its own restrictive USB rule (0660 + uaccess, not 0666):
# the package's rules file is empty for 5e0a because hwdb generation is disabled.
assert pkgs.lib.hasInfix
  ''SUBSYSTEM=="usb", ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5e0a", MODE="0660", TAG+="uaccess"''
  default.services.udev.extraRules;
assert !(pkgs.lib.hasInfix ''MODE="0666"'' default.services.udev.extraRules);
true
