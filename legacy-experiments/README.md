# Research archive

These are historical experiments, not supported tools or release tests. Some
scripts send commands directly to the sensor; do not run them casually. Use
`bash tests/run_all_tests.sh` for the supported software checks.

The production driver uses the Milan engine. Obsolete NBIS/Bozorth matching,
minutiae and preprocessing probes, their replay helper and benchmark output
were removed during cleanup. Their source remains in Git; for example,
`git show f91b1eb:legacy-experiments/test_match.c` retrieves the old match probe.

Remaining probes include evidence for engine contracts and archived capture
formats used by tests. They may require private captures, obsolete build paths,
or manual setup. Their presence does not establish current hardware reliability.
