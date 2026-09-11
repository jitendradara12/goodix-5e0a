#!/usr/bin/env python3
"""Ticket 67: generate a dense-contact synthetic 12-bit frame proxy.

No genuine dense live capture exists in-repo (/dev/shm/live_frame.raw is gone;
experiments/fingerprint.pgm is sparse striped rows, windows_unpacked.pgm is a
partial-contact band). This script synthesizes experiments/live_dense_pad.pgm
(64x80 P2 12-bit, row-major, same layout as fingerprint.pgm) calibrated so its
driver-visible statistics land inside the live journal windows:

  live wire stats (tickets 17/35/18): active=5120, min_v 416..631,
    max_v 2500..2763, range ~2056..2276, h_corr 0.944..0.958,
    v_corr 0.815..0.841, h_lag4 0.563..0.695
  live residual stats (ticket 66 run 2): min -416..-389, max +286..+323,
    range ~677..713
  live linear-baseline yield (ticket 65): probes 16..22 minutiae

Model: slow pressure drift (DC paraboloid + tilt, the field the 3x3
high-pass removes) + horizontal ridge sinusoid (period ~2.6 px, matching the
2-3 px ridge width at sensor scale) with smooth phase distortion (creates
natural endings/bifurcations) + a few explicit ridge-ending cuts + ADC noise.
Deterministic (fixed seed) so the benchmark is reproducible.

Wire format note: driver decodes 12-bit pixels then gates active = (v > 30);
DC baseline ~1500 keeps every pixel active, as in live frames.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random

W = 64
H = 80
MAXV = 4095
SEED = 67

# Knobs tuned so linear-baseline minutiae land in the live 16..22 window.
# Ridge period 5 px: at ~0.1 mm/px raw pitch a 0.5 mm ridge period spans 5 px
# (ticket 67 s2.1 "2-3 px wide" is the half-period). This is also what the
# live lag-1 correlations demand: h_corr 0.944..0.958 with v_corr 0.815..0.841
# is only jointly possible if vertical lag-1 stays positively correlated,
# i.e. cos(2*pi/lambda) > 0, so lambda > 4 px.
RIDGE_PERIOD = 5.0
RIDGE_AMP = 300.0
DC_BASE = 1500.0
NOISE_SIGMA = 22.0
N_ENDINGS = 14


def build_phase(seed: int) -> list[float]:
    rng = random.Random(seed)
    # Smooth low-frequency phase distortion: sum of incommensurate sinusoids
    # with random phases. Strong enough to spawn endings/bifurcations.
    comps = []
    for _ in range(6):
        fx = rng.uniform(0.02, 0.09)
        fy = rng.uniform(0.02, 0.09)
        ph = rng.uniform(0.0, 2.0 * math.pi)
        amp = rng.uniform(0.5, 1.1)
        comps.append((fx, fy, ph, amp))
    phase = [0.0] * (W * H)
    for y in range(H):
        for x in range(W):
            # Arch flow: ridge lines run mostly horizontally with curvature.
            arch = 0.010 * (x - W / 2) ** 2 / W
            distort = sum(
                amp * math.sin(2.0 * math.pi * (fx * x + fy * y) + ph)
                for fx, fy, ph, amp in comps
            )
            phase[y * W + x] = 2.0 * math.pi * ((y + arch) / RIDGE_PERIOD) + distort
    return phase


def build_dc() -> list[float]:
    # Elliptical pressure paraboloid + tilt: the slow field removed by 3x3.
    dc = [0.0] * (W * H)
    for y in range(H):
        for x in range(W):
            dx = (x - W / 2) / (W / 2)
            dy = (y - H / 2) / (H / 2)
            dc[y * W + x] = (
                DC_BASE
                + 576.0 * (1.0 - 0.55 * (dx * dx + dy * dy))
                + 378.0 * dx
                - 270.0 * dy
            )
    return dc


def ridge_endings_mask(seed: int) -> list[float]:
    # Explicit ridge endings: N_ENDINGS short vertical cuts that erase one
    # ridge crest over ~2 px, forcing a genuine minutia each.
    rng = random.Random(seed + 1)
    mask = [1.0] * (W * H)
    for _ in range(N_ENDINGS):
        cx = rng.uniform(6, W - 6)
        cy = rng.uniform(6, H - 6)
        length = rng.uniform(1.5, 3.0)
        for y in range(H):
            for x in range(W):
                d = math.hypot(x - cx, (y - cy) * 1.4)
                if d < length:
                    mask[y * W + x] = 0.0
    return mask


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default="experiments/live_dense_pad.pgm")
    args = ap.parse_args()
    seed = args.seed
    rng = random.Random(seed + 2)
    phase = build_phase(seed)
    dc = build_dc()
    mask = ridge_endings_mask(seed)
    pix: list[int] = []
    for i in range(W * H):
        ridge = RIDGE_AMP * math.sin(phase[i]) * mask[i]
        noise = rng.gauss(0.0, NOISE_SIGMA)
        v = int(round(dc[i] + ridge + noise))
        pix.append(max(0, min(MAXV, v)))

    active = sum(1 for v in pix if v > 30)
    print(f"seed={seed} active={active} min={min(pix)} max={max(pix)} "
          f"range={max(pix) - min(pix)} nonzero={sum(1 for v in pix if v)}")

    with open(args.out, "w", encoding="ascii") as f:
        f.write(f"P2\n{W} {H}\n{MAXV}\n")
        f.write(" ".join(map(str, pix)) + "\n")
    raw = open(args.out, "rb").read()
    print(f"wrote {args.out} sha256={hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
