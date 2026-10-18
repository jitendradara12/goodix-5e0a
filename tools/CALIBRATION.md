# Goodix calibration export helper

This recovers an existing Windows calibration cache for the laptop that
produced the issue #12 captures. It does not use the scanner, change a driver,
modify the source file, or require another fingerprint scan.

1. Find `C:\ProgramData\Goodix\goodix.dat` on that laptop's Windows
   installation. `ProgramData` is a hidden folder; the full path can be entered
   directly in File Explorer. If the file is absent, report that and stop.
2. Copy the file somewhere accessible from Linux, or use its existing mounted
   Windows path. Keep the original Windows cache unchanged.
3. In the extracted helper folder, run with Python 3:

   ```sh
   python3 extract_goodix_calibration.py /path/to/goodix.dat --out goodix-calibration.zip
   ```

   From the repository root, the script is `tools/extract_goodix_calibration.py`.
   It uses only Python's standard library. No package installation is needed.
4. Return the resulting `goodix-calibration.zip`, confirming that the cache is
   from the same laptop/sensor as the captures. If the tool reports an error,
   return that error instead. There is no need to share the full source cache.

The output ZIP contains `background_raw.pgm`, optional `calibration_state.bin`,
and `calibration.json` with hashes and format information. OTP, FDT and
navigation record payloads are omitted. An existing output ZIP is never
overwritten; choose another output name if one already exists.

The helper validates the reviewed Windows cache format and checksums. The
cache's availability, freshness and compatibility with the Linux capture
settings still need to be established. A successful export is an input for
the offline comparison, not a claim that matching is fixed.

The exporter preserves `ImageBase` sample order. Its 64×80 PGM header does not
establish alignment with the Linux driver's frames. In ptrip7's export, Windows
stores 64 rows of 80 samples: align it to the driver's canonical raster with
`out[y*64+x] = in[x*80+y]`. The replay tool exposes that explicit conversion as
`--windows-background-layout transpose`; the original export remains unchanged.
Do not transpose or otherwise edit the opaque `calibration_state.bin`.

The October 19 offline comparison also identified a separate matcher raster
issue. See [the calibration and raster report](../docs/calibration-raster-2026-10-19.md)
before treating calibration alone as the fix. Existing exports remain usable;
contributors do not need to export again for these metadata clarifications.
