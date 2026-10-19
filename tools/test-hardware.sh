#!/usr/bin/env bash
# Build separately, test with private enrollments, restore the original service.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$root/tools/hardware_session.py" "$@"
