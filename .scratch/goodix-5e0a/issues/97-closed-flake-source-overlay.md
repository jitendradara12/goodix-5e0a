# 97: Replace the patch-driver-sync mechanism with a flake source overlay

**What to build:** The 6000-line patch exists to inject `libfprint-driver/`
into the fork and register the driver in meson. Proven equivalent mechanism:
the flake copies `libfprint-driver/` into the fork's goodixtls dir (verified
byte-identical) and applies only the irreducible integration changes
(meson registration + 4 upstream core fixes). The patch/test duality
(test_f25 byte-sync) is replaced by a directory-identity test.

**Blocked by:** None.
**Status:** closed
**Owns:** flake.nix src, libfprint.patch regeneration, install.sh build
steps, affected tests.

Predicted signatures (software branch):
- Fresh tarball build via new flake produces a working derivation; driver
  dir in the built source is byte-identical to libfprint-driver/.
- test_f25's sync invariant is replaced by directory identity; suite green.
- install.sh produces the same staged tree as before (same seds, same patch
  core).

- [x] Ticket opened.
- [x] libfprint.patch (core-only) regenerated from real fork apply — 115 lines,
      6 sections, verified against a real fetchFromGitHub checkout.
- [x] flake src overlay implemented (`cp ${./libfprint-driver}` in postPatch).
- [x] install.sh switched to copy+core-patch (fixture caught missing mkdir -p;
      fixed).
- [x] Tests updated: f25 byte-sync + f21 old-mechanism tests deleted (invariant
      structurally gone); tier5 guard now asserts the integration patch never
      embeds goodixtls sources (<20KB); f22 asserts patch+copy wiring.
- [x] Equivalence proof: old mechanism (full 6k patch + seds) vs new mechanism
      (core patch + copy + seds) produce byte-identical fork trees — the only
      diff was the test harness's own .git dir.
- [x] Full suite green: 359/359, 0 fail (2 deleted test files: -13 tests;
      native harness ran, 0 skips). nix flake check: all checks passed.
      Fresh derivation built: libfprint-2.so.2 present.
- [ ] Hardware: next nixos-rebuild on the Realme deploys this path; the
      pending 2-phase protocol (ticket 96 record) then covers both tickets.

## Decisions

- Keep the patch for the 4 upstream core fixes + meson registration; it is
  irreducible there.
- Driver sources live only in `libfprint-driver/` (single source of truth);
  the patch and the Nix overlay both consume it.
- No git submodules; a tiny src-overlay mkDerivation stays boring.

## Verdict (closed 2026-09-21, sastalinux Fedora 44)

Confirm — the copy+core-patch mechanism is deployed live via `install.sh`: engine `Milan_v_3.02.00.20` loads, TLS ready, 10 prints enrolled via CLI. Suite 350/350 green incl. f22 wiring + tier5 guard. Flake check + fresh derivation build passed earlier per record above; no nixos-rebuild deploy on this host (not NixOS).
