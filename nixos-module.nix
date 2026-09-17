# NixOS Module for Goodix 27c6:5e0a Fingerprint Scanner
# Import this into your /etc/nixos/configuration.nix or flake.nix

{ config, pkgs, lib, ... }:

let
  cfg = config.services.fprintd.goodix;
  # The flake.nix overlay exposes this same package; plain imports need no overlay.
  libfprint-goodix = pkgs.callPackage ./libfprint-goodix.nix {};
  fprintd-goodix = pkgs.fprintd.override {
    libfprint = libfprint-goodix;
  };
in
{
  options.services.fprintd.goodix = {
    pamServices = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Default fingerprint authentication for login/sudo/sddm/hyprlock/swaylock. Other PAM services retain NixOS defaults; explicit per-service settings override this option.";
    };
    dllFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = ./windows_driver/GoodixEngineAdapter.dll;
      description = "Vendor engine used by fprintd. Null keeps manual DLL lookup. Path contents enter the world-readable Nix store.";
    };
  };

  config = {
    # 1. Enable fprintd with our custom Goodix 27c6:5e0a driver
    services.fprintd = {
      enable = true;
      package = fprintd-goodix;
    };

    # The daemon's 30s idle exit destroys parked TLS before the driver's 300s TTL.
    # Reset the packaged unit's ExecStart in the NixOS drop-in, then keep it resident.
    systemd.services.fprintd.serviceConfig.ExecStart = [
      ""
      "${config.services.fprintd.package}/libexec/fprintd --no-timeout"
    ];

    # 2. Install udev rules for the scanner
    services.udev.packages = [ libfprint-goodix ];
    # 2. USB access rule. The shipped libfprint rules file is empty for 5e0a
    # (built with udev hwdb disabled), so the module provides it explicitly.
    # fprintd runs as root; 0660 + uaccess instead of world-writable 0666.
    services.udev.extraRules = ''
      SUBSYSTEM=="usb", ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5e0a", MODE="0660", TAG+="uaccess"
    '';

    # 3. Opt in to PAM fingerprint authentication across system auth services.
    security.pam.services = lib.genAttrs
      [ "login" "sudo" "hyprlock" "swaylock" "sddm" ]
      (_: { fprintAuth = lib.mkDefault cfg.pamServices; });

    # An explicit store path follows configuration updates and rollbacks, unlike
    # copy-once tmpfiles rules that leave an older engine in /var/lib/fprint.
    systemd.services.fprintd.environment = lib.mkIf (cfg.dllFile != null) {
      GOODIX_ENGINE_DLL_PATH = toString cfg.dllFile;
    };
  };
}
