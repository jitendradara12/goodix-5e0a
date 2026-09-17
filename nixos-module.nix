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
      description = "Enable fingerprint authentication in login/sudo/sddm/hyprlock/swaylock.";
    };
    dllFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Path to GoodixEngineAdapter.dll to install to /var/lib/fprint/GoodixEngineAdapter.dll.";
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
    services.udev.extraRules = ''
      SUBSYSTEM=="usb", ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5e0a", MODE="0666", TAG+="uaccess"
    '';

    # 3. Opt in to PAM fingerprint authentication across system auth services.
    security.pam.services = lib.mkIf cfg.pamServices {
      login.fprintAuth = true;
      sudo.fprintAuth = true;
      hyprlock.fprintAuth = lib.mkDefault true;
      swaylock.fprintAuth = lib.mkDefault true;
      sddm.fprintAuth = lib.mkDefault true;
    };

    systemd.tmpfiles.rules = lib.mkIf (cfg.dllFile != null) [
      "C /var/lib/fprint/GoodixEngineAdapter.dll 0444 root root - ${cfg.dllFile}"
    ];
  };
}
