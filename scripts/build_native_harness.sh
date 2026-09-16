#!/usr/bin/env bash
# Requires the configured, built libfprint tree at /tmp/libfprint-goodix.
# Builds only a fake-device test binary; never claims fingerprint hardware.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

nix-shell -p pkg-config glib gusb --run '
  gcc -o /tmp/test_ssm_teardown \
    tests/tier5_adversarial/test_ssm_teardown_c.c \
    /tmp/libfprint-goodix/tests/test-device-fake.c \
    -I/tmp/libfprint-goodix \
    -I/tmp/libfprint-goodix/libfprint \
    -I/tmp/libfprint-goodix/tests \
    -I/tmp/libfprint-goodix/build \
    -I/tmp/libfprint-goodix/build/libfprint \
    /tmp/libfprint-goodix/build/libfprint/libfprint-private.a \
    /tmp/libfprint-goodix/build/libfprint/libnbis.a \
    -L/tmp/libfprint-goodix/build/libfprint \
    -Wl,-rpath,/tmp/libfprint-goodix/build/libfprint \
    -lfprint-2 $(pkg-config --cflags --libs gio-2.0 gusb) -lm
'
