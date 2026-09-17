#!/usr/bin/env bash
# ==============================================================================
# Master E2E Test Suite Runner for Goodix 27c6:5e0a Fingerprint Sensor Driver
# Runs software tests in Tiers 1, 4, and 5; does not verify hardware.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/legacy-experiments:${PYTHONPATH:-}"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

TOTAL_EXECUTED=0
TOTAL_PASSED=0
TOTAL_FAILED=0
TOTAL_SKIPPED=0
START_TIME=$(date +%s)

echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD}${CYAN}  Goodix 27c6:5e0a Fingerprint Sensor Driver - Master E2E Test Runner        ${NC}"
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "Project Root: ${ROOT_DIR}"
echo -e "Test Directory: ${SCRIPT_DIR}"
echo -e "Date: $(date -u '+%Y-%m-%d %H:%M:%SZ')\n"

run_tier() {
    local tier_name="$1"
    local tier_dir="$2"
    local description="$3"

    echo -e "${BOLD}${BLUE}▶ Running ${tier_name}: ${description}${NC}"
    echo -e "${CYAN}------------------------------------------------------------------------------${NC}"

    local tier_start=$(date +%s)
    local output
    local status=0

    set +e
    output=$(python3 -m unittest discover -s "${tier_dir}" -v 2>&1)
    status=$?
    set -e

    local tier_end=$(date +%s)
    local tier_duration=$((tier_end - tier_start))

    if [ ${status} -eq 0 ]; then
        local count skipped executed passed
        count=$(echo "${output}" | sed -nE 's/^Ran ([0-9]+) tests? in .*/\1/p')
        if [[ ! "$count" =~ ^[0-9]+$ ]]; then
            echo "Missing unittest test count for ${tier_name}"
            echo "${output}"
            return 1
        fi
        skipped=$(echo "${output}" | sed -nE 's/^OK \(.*skipped=([0-9]+).*\)$/\1/p')
        skipped=${skipped:-0}
        # unittest's Ran count includes skips; executed tests exclude them.
        executed=$((count - skipped))
        passed=$(echo "${output}" | grep -c '\.\.\. ok$' || true)
        echo "${output}" | grep -E "(\.\.\. ok|\.\.\. OK)" | head -n 10 || true
        if [ "$(echo "${output}" | grep -c "\.\.\. ok")" -gt 10 ]; then
            echo -e "... [truncated $(($(echo "${output}" | grep -c "\.\.\. ok") - 10)) passing test cases] ..."
        fi
        echo -e "${GREEN}✔ ${tier_name} PASSED (${count} tests: ${passed} passed, ${skipped} skipped; ${executed} executed in ${tier_duration}s)${NC}\n"
        TOTAL_EXECUTED=$((TOTAL_EXECUTED + executed))
        TOTAL_PASSED=$((TOTAL_PASSED + passed))
        TOTAL_SKIPPED=$((TOTAL_SKIPPED + skipped))
    else
        echo -e "${RED}✖ ${tier_name} FAILED in ${tier_duration}s${NC}"
        echo "${output}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
        return 1
    fi
}

# ------------------------------------------------------------------------------
# Pre-flight / Build System Checks
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}▶ Pre-flight: Build System & Nix Derivation Evaluation${NC}"
echo -e "${CYAN}------------------------------------------------------------------------------${NC}"

export GOODIX_NATIVE_TESTS="${GOODIX_NATIVE_TESTS:-required}"
unset GOODIX_NATIVE_HARNESS # Never reuse an inherited or temporary binary.
case "$GOODIX_NATIVE_TESTS" in
    required)
        echo 'Building required native harness...'
        GOODIX_NATIVE_HARNESS=$(bash "$ROOT_DIR/scripts/build_native_harness.sh")
        export GOODIX_NATIVE_HARNESS
        [[ -x "$GOODIX_NATIVE_HARNESS" ]] || { echo 'Required native harness unavailable'; exit 1; }
        ;;
    skip)
        echo 'SKIP native harness (explicit GOODIX_NATIVE_TESTS=skip; not a required-lane pass)'
        ;;
    *)
        echo 'GOODIX_NATIVE_TESTS must be required or skip' >&2
        exit 1
        ;;
esac


if ! command -v nix-instantiate >/dev/null 2>&1; then
    echo -e "${YELLOW}SKIP nix pre-flight (nix-instantiate not installed, non-fatal)${NC}"
else
    echo -n "Evaluating libfprint-goodix Nix derivation... "
    nix-instantiate --eval -E "let pkgs = import <nixpkgs> {}; in pkgs.callPackage ${ROOT_DIR}/libfprint-goodix.nix {}" > /dev/null 2>&1 && echo -e "${GREEN}OK${NC}" || (echo -e "${RED}FAIL${NC}" && exit 1)

    echo -n "Evaluating NixOS module configuration... "
    nix-instantiate --parse "${ROOT_DIR}/nixos-module.nix" > /dev/null 2>&1 && echo -e "${GREEN}OK${NC}" || (echo -e "${RED}FAIL${NC}" && exit 1)
fi

echo ""

# ------------------------------------------------------------------------------
# Execute Active Streamlined Test Tiers
# ------------------------------------------------------------------------------
run_tier "Tier 1 (Feature Coverage)" "${SCRIPT_DIR}/tier1_feature" "Features F01-F77, Protocols & Boundary Checks"
run_tier "Tier 4 (Real-World Application Scenarios)" "${SCRIPT_DIR}/tier4_realworld" "PAM Auth, Enrollment & System Integration"
run_tier "Tier 5 (Adversarial & Stress Testing)" "${SCRIPT_DIR}/tier5_adversarial" "Hardware Contracts, Fault Injection & Wire Decoding Equivalence"

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD}${CYAN}  Test Execution Summary                                                      ${NC}"
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "Total Tests Executed: ${BOLD}${TOTAL_EXECUTED}${NC}"
echo -e "Total Tests Passed: ${BOLD}${GREEN}${TOTAL_PASSED}${NC}"
echo -e "Total Tiers Failed: ${BOLD}${RED}${TOTAL_FAILED}${NC}"
echo -e "Total Tests Skipped: ${BOLD}${YELLOW}${TOTAL_SKIPPED}${NC}"
echo -e "Total Execution Time: ${BOLD}${TOTAL_DURATION}s${NC}"

if [ ${TOTAL_FAILED} -eq 0 ]; then
    echo -e "\n${BOLD}${GREEN}Software test suite completed without failures. See skipped count above.${NC}"
    echo -e "Hardware verification and release readiness are not established by this suite.\n"
    exit 0
else
    echo -e "\n${BOLD}${RED}Software test suite failed: ${TOTAL_FAILED} tier(s) failed.${NC}\n"
    exit 1
fi
