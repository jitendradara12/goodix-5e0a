# NixOS Module for Goodix 27c6:5e0a Fingerprint Scanner
# Import this into your /etc/nixos/configuration.nix or flake.nix

{ config, pkgs, lib, ... }:

let
  libfprint-goodix = pkgs.callPackage ./libfprint-goodix.nix {};
  fprintd-goodix = pkgs.fprintd.override {
    libfprint = libfprint-goodix;
  };
in
{
  # 1. Enable fprintd with our custom Goodix 27c6:5e0a driver
  services.fprintd = {
    enable = true;
    package = fprintd-goodix;
  };

  # 2. Install udev rules for the scanner
  services.udev.packages = [ libfprint-goodix ];
  services.udev.extraRules = ''
    SUBSYSTEM=="usb", ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5e0a", MODE="0666", TAG+="uaccess"
  '';

  # 3. Enable PAM fingerprint authentication across system auth services
  security.pam.services = {
    login.fprintAuth = true;
    sudo.fprintAuth = true;
    hyprlock.fprintAuth = lib.mkDefault true;
    swaylock.fprintAuth = lib.mkDefault true;
    sddm.fprintAuth = lib.mkDefault true;
  };
}
