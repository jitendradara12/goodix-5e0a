#!/usr/bin/env python3
"""Replay one captured ChicagoH frame through structural/contrast variants."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

WIDTH = 64
HEIGHT = 80
BLOCKS = 80
BLOCK_BYTES = 132
ACTIVE_BYTES = 96
WIRE_BYTES = BLOCKS * BLOCK_BYTES + 4


def unpack_12bit(data: bytes) -> list[int]:
    pixels: list[int] = []
    for offset in range(0, len(data), 6):
        chunk = data[offset : offset + 6]
        if len(chunk) < 6:
            break
        pixels.extend(
            [
                ((chunk[0] & 0x0F) << 8) | chunk[1],
                (chunk[3] << 4) | (chunk[0] >> 4),
                ((chunk[5] & 0x0F) << 8) | chunk[2],
                (chunk[4] << 4) | (chunk[5] >> 4),
            ]
        )
    return pixels


def decode_frame(frame: bytes) -> tuple[list[int], int]:
    if len(frame) != WIRE_BYTES:
        raise ValueError(f"expected {WIRE_BYTES} bytes, got {len(frame)}")

    packed = bytearray()
    padding_nonzero = 0
    for block in range(BLOCKS):
        start = block * BLOCK_BYTES
        packed.extend(frame[start : start + ACTIVE_BYTES])
        padding = frame[start + ACTIVE_BYTES : start + BLOCK_BYTES]
        padding_nonzero += sum(value != 0 for value in padding)
    return unpack_12bit(bytes(packed)), padding_nonzero


def box_highpass(pixels: list[int], radius: int) -> list[int]:
    integral = [[0] * (WIDTH + 1) for _ in range(HEIGHT + 1)]
    for y in range(HEIGHT):
        row_sum = 0
        for x in range(WIDTH):
            row_sum += pixels[y * WIDTH + x]
            integral[y + 1][x + 1] = integral[y][x + 1] + row_sum

    residuals: list[float] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            x0, x1 = max(0, x - radius), min(WIDTH, x + radius + 1)
            y0, y1 = max(0, y - radius), min(HEIGHT, y + radius + 1)
            total = (
                integral[y1][x1]
                - integral[y0][x1]
                - integral[y1][x0]
                + integral[y0][x0]
            )
            local_mean = total / ((x1 - x0) * (y1 - y0))
            residuals.append(pixels[y * WIDTH + x] - local_mean)

    minimum = min(residuals)
    return [round(value - minimum) for value in residuals]


def write_pgm(path: Path, pixels: list[int]) -> None:
    path.write_text(
        f"P2\n{WIDTH} {HEIGHT}\n4095\n" + " ".join(map(str, pixels)) + "\n",
        encoding="ascii",
    )


def run_nbis(binary: Path, pixels: list[int]) -> str:
    replay_path = Path("/tmp/live_touch.pgm")
    previous = replay_path.read_bytes() if replay_path.exists() else None
    try:
        write_pgm(replay_path, pixels)
        result = subprocess.run(
            [str(binary)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        if previous is None:
            replay_path.unlink(missing_ok=True)
        else:
            replay_path.write_bytes(previous)

    marker = "[64x80 Direct Inverted]"
    return next(line.strip() for line in result.stdout.splitlines() if marker in line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path)
    parser.add_argument(
        "--nbis-binary",
        type=Path,
        default=Path("experiments/test_geometry_unpack2"),
    )
    args = parser.parse_args()

    pixels, padding_nonzero = decode_frame(args.raw.read_bytes())
    print(
        f"wire_bytes={WIRE_BYTES} decoded={len(pixels)} nonzero={sum(value != 0 for value in pixels)} "
        f"padding_nonzero={padding_nonzero} min={min(pixels)} max={max(pixels)}"
    )
    print(f"raw: {run_nbis(args.nbis_binary, pixels)}")
    for radius in (1, 2, 3, 4, 5, 6, 8, 10, 12):
        enhanced = box_highpass(pixels, radius)
        print(f"highpass-r{radius}: {run_nbis(args.nbis_binary, enhanced)}")


if __name__ == "__main__":
    main()
