# 119 — PR #15 merge audit

**Status:** superseded

**Verdict:** falsified for merge readiness: the cold activation ladder bypassed OTP.

**Successor:** [120 — OTP activation](120-ready-for-hardware-verify-otp-activation.md). The following is the original audit record; its helper tests did not establish activation reachability.

Changes:
- Keep image-command calibration in each device's transport state; rebuild all packets from defaults on recalibration or invalid OTP.
- Select Jet-Soup's extra wire settings using all four known channel values. Preserve ninth bits and the verified config checksum.
- Execute the production C decoder, packet builder and transport setter in tests, including malformed reads, recalibration and independent device instances.
- Retain the historical wire patch for comparison. Both old runner flags now test the normal automatic driver; remove the obsolete separate candidate CI build.
- Check enrollment contents as well as print counts, fail on listing errors, restore the original inactive service state, and label both libraries and private storage under SELinux. No permissive-policy workaround is applied.
- Give the recovery timer an owned-session expiry path, with process-start identity checks. A live or wedged test cannot disable timed cleanup merely by retaining its PID.
- Start the enrollment release deadline for rejected low-quality touches as well as accepted touches, closing an unbounded-hold path.
- Detect hands-off capture activity even when the enrollment client reports no advance.
- Keep the 2,000-code-line architecture budget while excluding comments, so documentation does not encourage compressed statements.

Validation: focused recovery/calibration/session tests, the required native Linux suite (two existing missing-image-fixture skips), runner/install/cleanup fixtures, and native driver plus downstream fprintd builds passed. SELinux failure handling is software tested; a new Fedora enforcing run was not performed.

Existing hardware evidence remains revision-specific: maintainer `e92209e`, bundle `6f55ee4e9111c617`, confirmed 5/5 genuine and 5/5 wrong-finger rejections, quiet hands-off, one hold advance, 7/0/7 storage counts. Jet-Soup `07a5ad5` demonstrated automatic capture selection, but the completed bundle `77abe5d8e69d3fc7` was **falsified** (4/5 genuine, 5/5 rejections); `69953408d66da05e` was **inconclusive-because-client-timeout**. Their comment additionally reports 5/5 genuine and one rejection before that aborted run. Do not relabel either ZIP as a strict confirmed run.

Single next hardware experiment, if further verification is requested: one standard no-flags run on Jet-Soup's unit. Confirm: silent hands-off, one hold advance, 5/5 genuine, 5/5 rejections, bounded bursts and unchanged original storage. Falsify: hands-off captures, repeated hold advances, a wrong-finger match, failed genuine trials, or storage changes; interrupted/incomplete measurements remain inconclusive with the flaw recorded.
