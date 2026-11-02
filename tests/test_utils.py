"""
Shared Test Utilities and Constants for Goodix 27c6:5e0a Driver Tests.
Provides authoritative reference implementations of:
- USB Bulk packet framing (GoodixPack, GoodixProtocol)
- Checksum algorithms (additive 8-bit, 0xaa-sum complement, 0x88 null)
- 12-bit nibble unpacking (6 bytes -> 4 pixels)
- Linear squashing & normalization (12-bit -> 8-bit grayscale)
"""

import struct
from typing import Tuple, List

# ==============================================================================
# Hardware Constants & Sensor Geometry
# ==============================================================================

EP_OUT_CHUNK_SIZE = 64

SENSOR_WIDTH = 64
SENSOR_HEIGHT = 80
FRAME_PIXELS = SENSOR_WIDTH * SENSOR_HEIGHT  # 5120
FRAME_BLOCKS = 80
FRAME_BLOCK_BYTES = 132
FRAME_BLOCK_ACTIVE_BYTES = 96
RAW_FRAME_BYTES = FRAME_BLOCKS * FRAME_BLOCK_ACTIVE_BYTES  # 7680
WIRE_FRAME_BYTES = FRAME_BLOCKS * FRAME_BLOCK_BYTES + 4  # 10564

FLAGS_MSG_PROTOCOL = 0xA0
NULL_CHECKSUM = 0x88

CMD_MCU_SWITCH_TO_FDT_DOWN = 0x32
CMD_MCU_SWITCH_TO_FDT_UP = 0x34
CMD_MCU_SWITCH_TO_FDT_MODE = 0x36

FINGER_EXPOSURE_PAYLOAD = bytes.fromhex("01000000000000000000")

CANONICAL_PSK = bytes.fromhex(
    "d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab"
)

CANONICAL_REG_022C_GAIN = bytes([0x05, 0x03])

# ==============================================================================
# Reference Protocol Encoders and Decoders
# ==============================================================================

def calc_pack_checksum(data: bytes, length: int) -> int:
    """Additive 8-bit checksum for GoodixPack headers."""
    return sum(data[:length]) & 0xFF

def calc_protocol_checksum(data: bytes, length: int) -> int:
    """0xAA - sum(data) checksum for GoodixProtocol packets."""
    return (0xAA - sum(data[:length])) & 0xFF

def encode_pack(flags: int, payload: bytes, pad_data: bool = True) -> bytes:
    """Encodes GoodixPack: [flags:1B][length:2B LE][chk:1B][payload:NB] + optional padding."""
    payload_len = len(payload)
    hdr = struct.pack("<BH", flags, payload_len)
    chk = calc_pack_checksum(hdr, len(hdr))
    packed = hdr + bytes([chk]) + payload
    if pad_data and len(packed) % EP_OUT_CHUNK_SIZE != 0:
        pad_len = EP_OUT_CHUNK_SIZE - (len(packed) % EP_OUT_CHUNK_SIZE)
        packed += b"\x00" * pad_len
    return packed

def encode_protocol(cmd: int, payload: bytes, calc_checksum: bool = True, pad_data: bool = True) -> bytes:
    """
    Encodes GoodixProtocol: [cmd:1B][length:2B LE][payload:NB][chk:1B] + optional padding.
    Note: length field = payload_len + 1 (includes checksum byte).
    """
    payload_len = len(payload)
    wire_len = payload_len + 1
    hdr = struct.pack("<BH", cmd, wire_len)
    body = hdr + payload
    if calc_checksum:
        chk = calc_protocol_checksum(body, len(body))
    else:
        chk = NULL_CHECKSUM
    packet = body + bytes([chk])
    if pad_data and len(packet) % EP_OUT_CHUNK_SIZE != 0:
        pad_len = EP_OUT_CHUNK_SIZE - (len(packet) % EP_OUT_CHUNK_SIZE)
        packet += b"\x00" * pad_len
    return packet

def decode_protocol(data: bytes) -> Tuple[bool, int, bytes, bool, bool]:
    """
    Decodes GoodixProtocol.
    Returns (success, cmd, payload, valid_checksum, valid_null_checksum).
    """
    if len(data) < 4:
        return False, 0, b"", False, False
    cmd, wire_len = struct.unpack("<BH", data[:3])
    if wire_len < 1:
        return False, cmd, b"", False, False
    payload_len = wire_len - 1
    if len(data) < 3 + payload_len + 1:
        return False, cmd, b"", False, False
    payload = data[3 : 3 + payload_len]
    chk_byte = data[3 + payload_len]
    expected_chk = calc_protocol_checksum(data[: 3 + payload_len], 3 + payload_len)
    valid_chk = (chk_byte == expected_chk)
    valid_null = (chk_byte == NULL_CHECKSUM)
    return True, cmd, payload, valid_chk, valid_null

# ==============================================================================
# Pixel Decoding & Normalization
# ==============================================================================

def decode_12bit_frame(raw_frame: bytes) -> List[int]:
    """
    Unpacks 12-bit sensor array from raw byte stream.
    6 bytes -> 4 12-bit pixels (0..4095).
    """
    frame_size = len(raw_frame)
    start = 0
    if frame_size >= 13 and (frame_size - 13) % 6 == 0:
        start = 8
        end = frame_size - 5
    elif frame_size % 6 == 0:
        end = frame_size
    else:
        end = frame_size - 4 if frame_size >= 4 else frame_size

    pixels = []
    i = start
    while i + 6 <= end and len(pixels) < FRAME_PIXELS:
        chunk = raw_frame[i : i + 6]
        p0 = ((chunk[0] & 0x0F) << 8) | chunk[1]
        p1 = (chunk[3] << 4) | (chunk[0] >> 4)
        p2 = ((chunk[5] & 0x0F) << 8) | chunk[2]
        p3 = (chunk[4] << 4) | (chunk[5] >> 4)
        pixels.extend([p0, p1, p2, p3])
        i += 6
    return pixels

def pack_12bit_frame(pixels: List[int]) -> bytes:
    """
    Inverse helper: Packs a list of 12-bit pixels (multiples of 4) into raw 6-byte blocks.
    """
    out = bytearray()
    for idx in range(0, len(pixels), 4):
        p0, p1, p2, p3 = pixels[idx : idx + 4]
        b0 = (p0 >> 8 & 0x0F) | ((p1 & 0x0F) << 4)
        b1 = p0 & 0xFF
        b2 = p2 & 0xFF
        b3 = (p1 >> 4) & 0xFF
        b4 = (p3 >> 4) & 0xFF
        b5 = (p2 >> 8 & 0x0F) | ((p3 & 0x0F) << 4)
        out.extend([b0, b1, b2, b3, b4, b5])
    return bytes(out)

def decode_chicagoh_frame(raw_frame: bytes) -> List[int]:
    """Strip each ChicagoH block's zero pad and decode the natural 64x80 raster."""
    if len(raw_frame) < WIRE_FRAME_BYTES:
        return []

    packed = bytearray()
    for block in range(FRAME_BLOCKS):
        start = block * FRAME_BLOCK_BYTES
        packed.extend(raw_frame[start : start + FRAME_BLOCK_ACTIVE_BYTES])
    return decode_12bit_frame(bytes(packed))

def squash_frame_linear(pixels: List[int]) -> List[int]:
    """
    Normalizes 12-bit pixels (0..4095) to 8-bit grayscale (0..255).
    Matches goodixtls5xx_squash_frame_linear.
    """
    if not pixels:
        return []
    min_val = min(pixels)
    max_val = max(pixels)
    val_range = max_val - min_val
    if val_range == 0:
        return [0] * len(pixels)
    return [((p - min_val) * 255) // val_range for p in pixels]
