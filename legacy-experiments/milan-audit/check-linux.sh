#!/usr/bin/env bash
# Offline prototype check. Never installs/restarts a driver or reads USB.
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root_dir"
case "$(uname -sm)" in
  'Linux x86_64') ;;
  *) echo 'Run this check on the x86-64 Linux laptop.' >&2; exit 1 ;;
esac

dependencies_ready() {
  command -v cc >/dev/null && command -v pkg-config >/dev/null &&
    pkg-config --exists glib-2.0 && python3 -c 'import numpy' >/dev/null 2>&1
}
if ! dependencies_ready; then
  if command -v nix-shell >/dev/null && [[ ${GOODIX_PROBE_ENV_READY:-0} != 1 ]]; then
    export GOODIX_PROBE_ENV_READY=1
    exec nix-shell -p gcc pkg-config glib.dev 'python3.withPackages (p: [ p.numpy ])' \
      --run 'bash legacy-experiments/milan-audit/check-linux.sh'
  fi
  echo 'Need a C compiler, pkg-config, GLib development files, Python 3, and NumPy.' >&2
  echo 'Send this output back; no system changes have been made.' >&2
  exit 1
fi

output_dir="$root_dir/probe-output"
mkdir -p "$output_dir"
library="$output_dir/libgoodix-milan-probe.so"
if ! bash legacy-experiments/milan-audit/build-native.sh "$library" > "$output_dir/check.log" 2>&1; then
  tail -n 100 "$output_dir/check.log" >&2
  exit 1
fi
if ! python3 legacy-experiments/milan-audit/selfcheck.py \
  --native-library "$library" --out "$output_dir/linux-selfcheck.json" \
  >> "$output_dir/check.log" 2>&1; then
  tail -n 100 "$output_dir/check.log" >&2
  exit 1
fi
echo 'Offline prototype check passed. The installed driver and sensor were not used.'
echo "Send back $output_dir/linux-selfcheck.json and $output_dir/check.log"
