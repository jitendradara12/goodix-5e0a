# Research archive

These are historical experiments, not supported tools or release tests. Some
scripts send commands directly to the sensor; do not run them casually. Use
`bash tests/run_all_tests.sh` for the supported software checks.

The production driver uses the Milan engine, not NBIS/Bozorth. Three obsolete,
unreferenced Bozorth programs (`test_bozorth.c`, `test_bozorth_verify.c`, and
`test_norm_bozorth.c`) were removed during cleanup. Their source remains in Git;
for example, `git show c7f422e:legacy-experiments/test_bozorth.c` retrieves it.

Remaining probes include evidence for engine contracts and archived capture
formats used by tests. They may require private captures, obsolete build paths,
or manual setup. Their presence does not establish current hardware reliability.
