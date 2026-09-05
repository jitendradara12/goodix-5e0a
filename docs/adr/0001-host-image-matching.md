# Host-side image matching, not match-on-chip

The sensor streams raw frames and the host enrolls, stores, and matches with the in-tree NBIS minutiae extractor and Bozorth3 matcher; the driver subclass is an image device with a press scan type, eight enrollment stages, and a match threshold of twelve.

## Considered Options

- **Match-on-chip**: rejected — the firmware exposes no template store, enroll, or match commands, only capture and finger-detect primitives, and every upstream Goodix match-on-chip driver would need on-chip storage this unit lacks.
- **Custom host matcher**: rejected — a novel matcher would be a second invention to sell upstream alongside a new driver; the in-tree matcher already clears the threshold on hardware captures.

## Consequences

The merge request must argue an image driver with software matching, and needs pixel-compared capture tests rather than enroll/verify/storage protocol tests.
