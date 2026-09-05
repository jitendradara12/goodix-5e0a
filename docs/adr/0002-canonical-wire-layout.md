# Canonical wire layout and raster geometry

Each wire frame is eighty blocks with a fixed active prefix and deterministic zero padding plus a short footer, decoded in block order into the natural raster and then upscaled twofold with inverted polarity for capacitive ridges.

## Considered Options

- **Contiguous first-bytes unpack**: rejected — it swallowed padding bytes as pixels and pinned every frame to the same active count regardless of touch.
- **Strided column extraction with transpose**: rejected — slicing across true scanlines inverted correlation and collapsed minutiae to near zero on hardware.
- **Alternate geometries from sibling families**: rejected — they sheared scanlines and never matched the padding-zero evidence.

## Consequences

The decoder must strip padding per block and preserve block order; any future geometry change needs correlation plus minutiae evidence against the canonical baseline, not visual inspection.
