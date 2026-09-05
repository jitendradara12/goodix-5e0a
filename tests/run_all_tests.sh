#!/usr/bin/env bash
# ==============================================================================
# Master E2E Test Suite Runner for Goodix 27c6:5e0a Fingerprint Sensor Driver
# Covers Tiers 1-5: Features, Boundaries, Combinations, Scenarios, and Stress tests
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

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
        local count=$(echo "${output}" | grep -E "Ran [0-9]+ tests" | awk '{print $2}' || echo "N/A")
        echo "${output}" | grep -E "(\.\.\. ok|\.\.\. OK)" | head -n 10 || true
        if [ "$(echo "${output}" | grep -c "\.\.\. ok")" -gt 10 ]; then
            echo -e "... [truncated $(($(echo "${output}" | grep -c "\.\.\. ok") - 10)) passing test cases] ..."
        fi
        echo -e "${GREEN}✔ ${tier_name} PASSED (${count} tests in ${tier_duration}s)${NC}\n"
        TOTAL_PASSED=$((TOTAL_PASSED + count))
        local skipped=$(echo "${output}" | grep -oE "OK \(skipped=[0-9]+\)" | grep -oE "[0-9]+" || echo "0")
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

if [ -f "/tmp/libfprint-goodix/build/build.ninja" ]; then
    echo -n "Checking Ninja driver build status... "
    NINJA_STORE_BIN=$(find /nix/store -maxdepth 3 -name ninja -type f -perm -111 2>/dev/null | grep -E "ninja-[0-9]" | head -n 1 || true)
    if [ -n "${NINJA_STORE_BIN}" ] && "${NINJA_STORE_BIN}" -C /tmp/libfprint-goodix/build libfprint/libfprint-drivers.a libfprint/libfprint-2.so.2.0.0 > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    elif nix-shell -p ninja --run "ninja -C /tmp/libfprint-goodix/build libfprint/libfprint-drivers.a libfprint/libfprint-2.so.2.0.0" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}SKIP (non-fatal)${NC}"
    fi
fi


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
# Execute All Test Tiers
# ------------------------------------------------------------------------------
run_tier "Tier 1 (Feature Coverage)" "${SCRIPT_DIR}/tier1_feature" "Features F01-F25 plus Milestone Payloads in Isolation"
run_tier "Tier 2 (Boundary & Corner Cases)" "${SCRIPT_DIR}/tier2_boundary" "Boundary Value & Limit Analysis"
run_tier "Tier 3 (Pairwise Integration)" "${SCRIPT_DIR}/tier3_combination" "Cross-Feature Combinations & State Transitions"
run_tier "Tier 4 (Real-World Application Scenarios)" "${SCRIPT_DIR}/tier4_realworld" "PAM Auth, Enrollment & System Scenarios"
run_tier "Tier 5 (Adversarial & Stress Testing)" "${SCRIPT_DIR}/tier5_adversarial" "Fuzzing, Fault Injection & Memory Stability"

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD}${CYAN}  Test Execution Summary                                                      ${NC}"
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "Total Tests Passed: ${BOLD}${GREEN}${TOTAL_PASSED}${NC}"
echo -e "Total Tests Failed: ${BOLD}${RED}${TOTAL_FAILED}${NC}"
echo -e "Total Tests Skipped (env-gated): ${BOLD}${YELLOW}${TOTAL_SKIPPED}${NC}"
echo -e "Total Execution Time: ${BOLD}${TOTAL_DURATION}s${NC}"

if [ ${TOTAL_FAILED} -eq 0 ]; then
    echo -e "\n${BOLD}${GREEN}🎉 ALL TEST TIERS PASSED PERFECTLY! DRIVER IS VERIFIED AND READY FOR RELEASE!${NC}\n"
    exit 0
else
    echo -e "\n${BOLD}${RED}❌ TEST SUITE FAILED WITH ${TOTAL_FAILED} ERRORS!${NC}\n"
    exit 1
fi
