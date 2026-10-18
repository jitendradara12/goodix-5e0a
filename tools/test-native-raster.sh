#!/usr/bin/env bash
# Disposable issue-12 experiment. Builds unprivileged; no installation.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$root/tools/native_raster_session.py" "$@"
