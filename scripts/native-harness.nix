# Reuse the driver's pinned source, patch, Meson flags and dependencies.
{ pkgs ? import <nixpkgs> {} }:
let
  driver = pkgs.callPackage ../libfprint-goodix.nix {};
in driver.overrideAttrs (old: {
  pname = "goodix-native-harness";
  postBuild = (old.postBuild or "") + ''
    $CC -o test_ssm_teardown \
      ${../tests/tier5_adversarial/test_ssm_teardown_c.c} \
      ../tests/test-device-fake.c \
      -I.. -I../libfprint -I../tests -I. -Ilibfprint \
      libfprint/libfprint-private.a libfprint/libnbis.a \
      -Llibfprint -Wl,-rpath,$out/lib -lfprint-2 \
      $(pkg-config --cflags --libs gio-2.0 gusb) -lm
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    LD_LIBRARY_PATH="$PWD/libfprint" ./test_ssm_teardown
    runHook postCheck
  '';
  postInstall = (old.postInstall or "") + ''
    install -Dm755 test_ssm_teardown "$out/bin/test_ssm_teardown"
  '';
})
