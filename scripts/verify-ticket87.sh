#!/usr/bin/env bash
# User-only: claims the sensor and requests sudo for service debug/PAM checks.
set -euo pipefail
export LC_ALL=C
source "$(dirname -- "${BASH_SOURCE[0]}")/verify-common.sh"
verify_init ticket87
verify_setup

# Hands-off, steady-hold and PAM phases were covered in the previous run.
mark 'targeted close/reopen check; prior safety phases not repeated'
verify ttl-first
# Close/reopen routing, not TTL: the daemon exits after ~30s idle.
mark '5-second gap start; lift finger, no other authentication or suspend'
sleep 5
mark '5-second gap end'
verify ttl-second
printf '\nDo not infer success from matching alone; journal must show parked reuse.\n'
