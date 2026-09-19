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
    $CC -Wall -Wextra -Werror -o test_protocol \
      ${../tests/tier5_adversarial/test_protocol_c.c} \
      ../libfprint/drivers/goodixtls/goodix_proto.c \
      -I../libfprint/drivers/goodixtls $(pkg-config --cflags --libs gio-2.0)
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    LD_LIBRARY_PATH="$PWD/libfprint" ./test_ssm_teardown
    ./test_protocol
    runHook postCheck
  '';
  postInstall = (old.postInstall or "") + ''
    install -Dm755 test_ssm_teardown "$out/bin/test_ssm_teardown"
    install -Dm755 test_protocol "$out/bin/test_protocol"
  '';
})
