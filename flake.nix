{
  description = "Goodix 27c6:5e0a fingerprint driver (libfprint + fprintd) with Windows-engine loader";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: let
    systems = [ "x86_64-linux" ];
    forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
  in {
    overlays.default = final: prev: { libfprint-goodix = final.callPackage ./libfprint-goodix.nix {}; };
    packages = forAll (pkgs: rec {
      libfprint-goodix = pkgs.callPackage ./libfprint-goodix.nix {};
      default = libfprint-goodix;
    });
    nixosModules.default = ./nixos-module.nix;
  };
}
