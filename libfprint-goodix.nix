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

  patches = [
    ./0001-Add-driver-support-for-Goodix-27c6-5e0a.patch
  ];

  postPatch = ''
    if ! grep -q "1.94.9" meson.build; then
      sed -i "s/1.94.5/1.94.9/" meson.build
    fi
    if ! grep -q "FP_DEVICE_RETRY_TOO_FAST" libfprint/fp-device.h; then
      sed -i "s/FP_DEVICE_RETRY_REMOVE_FINGER,/FP_DEVICE_RETRY_REMOVE_FINGER,\n  FP_DEVICE_RETRY_TOO_FAST,/" libfprint/fp-device.h
    fi
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
    description = "libfprint fork with support for Goodix 27c6:5e0a TLS fingerprint scanner";
    license = licenses.lgpl21Plus;
    platforms = platforms.linux;
  };
}
