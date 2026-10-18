#!/usr/bin/env bash
# Build only an offline library; no sensor/service/install operations.
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
case "$(uname -sm)" in
  'Linux x86_64') ;;
  *) echo 'This build needs an x86-64 Linux machine.' >&2; exit 1 ;;
esac
command -v pkg-config >/dev/null || { echo 'Install pkg-config and GLib development files.' >&2; exit 1; }
output=${1:-/tmp/libgoodix-milan-probe.so}
read -r -a glib_flags <<< "$(pkg-config --cflags --libs glib-2.0)"
"${CC:-cc}" -O2 -g -fPIC -shared -Wall -Wextra -Wno-unused-parameter \
  "$root_dir/legacy-experiments/milan-audit/native_probe.c" \
  -o "$output" "${glib_flags[@]}" -lm
printf '%s\n' "$output"
