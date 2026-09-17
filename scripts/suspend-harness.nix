# Offline suspend/resume lifecycle harness. Compiles the real driver with
# transport/completion hooks mocked; no USB, sensor or suspend involved.
{ pkgs ? import <nixpkgs> {} }:
let driver = pkgs.callPackage ../libfprint-goodix.nix {}; in
driver.overrideAttrs (old: {
  pname = "goodix-suspend-harness";
  postBuild = (old.postBuild or "") + ''
    $CC -o test_suspend_recovery \
      ${../tests/tier5_adversarial/test_suspend_recovery_c.c} \
      ../tests/test-device-fake.c \
      -I.. -I../libfprint -I../tests -I. -Ilibfprint \
      -I../tests/fixtures/lifecycle \
      -DGOODIX_5E0A_C_INCLUDE='"libfprint/drivers/goodixtls/goodix5e0a.c"' \
      libfprint/libfprint-drivers.a libfprint/libfprint-private.a libfprint/libnbis.a \
      -Llibfprint -Wl,-rpath,$out/lib -lfprint-2 \
      $(pkg-config --cflags --libs gio-2.0 gusb openssl) -lm
    $CC -o test_idle_suspend_dispatch \
      ${../tests/tier5_adversarial/test_idle_suspend_dispatch_c.c} \
      ../tests/test-device-fake.c \
      -I.. -I../libfprint -I../tests -I. -Ilibfprint \
      libfprint/libfprint-private.a libfprint/libnbis.a \
      -Llibfprint -Wl,-rpath,$out/lib -lfprint-2 \
      $(pkg-config --cflags --libs gio-2.0 gusb) -lm
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    LD_LIBRARY_PATH="$PWD/libfprint" ./test_suspend_recovery
    LD_LIBRARY_PATH="$PWD/libfprint" ./test_idle_suspend_dispatch
    runHook postCheck
  '';
  postInstall = (old.postInstall or "") + ''
    install -Dm755 test_suspend_recovery "$out/bin/test_suspend_recovery"
    install -Dm755 test_idle_suspend_dispatch "$out/bin/test_idle_suspend_dispatch"
  '';
})
