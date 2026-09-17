{ lib, stdenv, fetchFromGitHub, meson, ninja, pkg-config, glib, libusb1, gusb, pixman, openssl, nss, nspr, gobject-introspection }:

stdenv.mkDerivation {
  pname = "libfprint-goodix";
  version = "1.94.5-goodixtls-5e0a";

  src = fetchFromGitHub {
    owner = "goodix-fp-linux-dev";
    repo = "libfprint";
    rev = "c343b6934e40dcd40a5f9e3095810d98f1175a4d";
    hash = "sha256-6llzCeVOtv0HRaNdB8mMzZCA8RBZtGkSCErsXwKE/vk=";
  };

  # Upstream integration only (meson registration, small core fixes).
  # Driver sources are copied from libfprint-driver/ below, so there is no
  # second embedded copy to keep in sync (replaces the 6k-line patch).
  patches = [
    ./goodix-5e0a-integration.patch
  ];

  postPatch = ''
    cp ${./libfprint-driver}/*.c ${./libfprint-driver}/*.h libfprint/drivers/goodixtls/
  '';

  nativeBuildInputs = [
    meson
    ninja
    pkg-config
    gobject-introspection
  ];

  buildInputs = [
    glib
    libusb1
    gusb
    pixman
    openssl
    nss
    nspr
  ];

  mesonFlags = [
    "-Ddrivers=goodixtls5e0a"
    "-Dgtk-examples=false"
    "-Ddoc=false"
    "-Dudev_rules=enabled"
    "-Dudev_rules_dir=${placeholder "out"}/lib/udev/rules.d"
    # udev_hwdb is disabled because 27c6:5e0a is managed dynamically by our custom udev rules
    # and requires exclusive TLS driver ownership without upstream hwdb whitelisting conflicts.
    "-Dudev_hwdb=disabled"
  ];

  meta = with lib; {
    description = "libfprint fork with support for the Goodix 27c6:5e0a TLS fingerprint scanner (x86-64 only)";
    license = licenses.lgpl21Plus;
    platforms = [ "x86_64-linux" ];
  };
}
