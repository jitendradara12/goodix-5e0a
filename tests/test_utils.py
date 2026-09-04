"""
Shared Test Utilities, Constants, and Mock Framework for Goodix 27c6:5e0a Driver Tests.
Provides authoritative reference implementations of:
- USB Bulk packet framing (GoodixPack, GoodixProtocol)
- Checksum algorithms (additive 8-bit, 0xaa-sum complement, 0x88 null)
- 12-bit nibble unpacking (6 bytes -> 4 pixels)
- Linear squashing & normalization (12-bit -> 8-bit grayscale)
- Bilinear demosaicing (80x64 raw -> 160x128 FpImage)
- Emulated Goodix 27c6:5e0a hardware state machine
"""

import struct
import io
import time
from typing import Tuple, List, Optional, Dict, Any

# ==============================================================================
# Canonical Constants
# ==============================================================================

VENDOR_ID = 0x27C6
PRODUCT_ID = 0x5E0A
INTERFACE_NUM = 0
EP_OUT = 0x01
EP_IN = 0x83
EP_OUT_CHUNK_SIZE = 64
EP_IN_MAX_BUF_SIZE = 0x10000

FIRMWARE_VERSION_STR = "GFUSB_GM168SEC_APP_10036"
PSK_FLAGS = 0xBB020001
RESET_NUMBER = 2048
CHIP_ID_VAL = bytes([0x27, 0xc6, 0x5e, 0x0a])

SENSOR_WIDTH = 64
SENSOR_HEIGHT = 80
FRAME_PIXELS = SENSOR_WIDTH * SENSOR_HEIGHT  # 5120
FRAME_BLOCKS = 80
FRAME_BLOCK_BYTES = 132
FRAME_BLOCK_ACTIVE_BYTES = 96
RAW_FRAME_BYTES = FRAME_BLOCKS * FRAME_BLOCK_ACTIVE_BYTES  # 7680
WIRE_FRAME_BYTES = FRAME_BLOCKS * FRAME_BLOCK_BYTES + 4  # 10564
IMAGE_OUT_WIDTH = 128
IMAGE_OUT_HEIGHT = 160
IMAGE_OUT_PIXELS = IMAGE_OUT_WIDTH * IMAGE_OUT_HEIGHT  # 20480

FLAGS_MSG_PROTOCOL = 0xA0
FLAGS_TLS = 0xB0
FLAGS_TLS_DATA = 0xB2
NULL_CHECKSUM = 0x88

CMD_NOP = 0x00
CMD_MCU_GET_IMAGE = 0x20
CMD_MCU_SWITCH_TO_FDT_DOWN = 0x32
CMD_MCU_SWITCH_TO_FDT_UP = 0x34
CMD_MCU_SWITCH_TO_FDT_MODE = 0x36
CMD_NAV_0 = 0x50
CMD_MCU_SWITCH_TO_IDLE_MODE = 0x70
CMD_WRITE_SENSOR_REGISTER = 0x80
CMD_READ_SENSOR_REGISTER = 0x82
CMD_UPLOAD_CONFIG_MCU = 0x90
CMD_SET_POWERDOWN_SCAN_FREQUENCY = 0x94
CMD_ENABLE_CHIP = 0x96
CMD_RESET = 0xA2
CMD_READ_OTP = 0xA6
CMD_FIRMWARE_VERSION = 0xA8
CMD_SET_POV_CONFIG = 0xAC
CMD_QUERY_MCU_STATE = 0xAE
CMD_ACK = 0xB0
CMD_SET_DRV_STATE = 0xC4
CMD_REQUEST_TLS_CONNECTION = 0xD0
CMD_MCU_GET_POV_IMAGE = 0xD2
CMD_TLS_SUCCESSFULLY_ESTABLISHED = 0xD4
CMD_PRESET_PSK_WRITE = 0xE0
CMD_PRESET_PSK_READ = 0xE4

FINGER_EXPOSURE_PAYLOAD = bytes.fromhex("01000000000000000000")

CANONICAL_PSK = bytes.fromhex(
    "d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab"
)

CANONICAL_CONFIG_52XD = bytes.fromhex(
    "701160712c9d2cc91ce518fd00fd00fd03ba000180ca0008008400bec38600b1"
    "b68800baba8a00b3b38c00bcbc8e00b1b19000bbbb9200b1b194000000960000"
    "00980000009a000000d2000000d4000000d6000000d800000050000105d00000"
    "00700000007200785674003412200010402a0102042200012024003200800001"
    "005c000101560024205800010232000402660000027c00005882007f082a0182"
    "072200012024001400800001405c00ea00560006145800040232000c02660000"
    "027c000058820080082a0108005c000101540000016200080464001000660000"
    "027c0000582a0108005c00e8005200080054000001660000027c00005820c50e"
)

CANONICAL_FDT_MODE = bytes.fromhex(
    "0d0127012101270123010000000000000000000000000000000000"
)

CANONICAL_FDT_DOWN = bytes.fromhex(
    "9c012701210127012301a5a59e9eafafa7a7b3b3aaaaaeaea4a401000503a700a100a700a30000"
)

CANONICAL_FDT_UP = bytes.fromhex(
    "9c012701210127012301a5a59e9eafafa7a7b3b3aaaaaeaea4a400000503a700a100a700a30000"
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

def decode_pack(data: bytes) -> Tuple[bool, int, bytes, bool]:
    """
    Decodes GoodixPack.
    Returns (success, flags, payload, valid_checksum).
    """
    if len(data) < 4:
        return False, 0, b"", False
    flags, length = struct.unpack("<BH", data[:3])
    hdr_chk = data[3]
    valid_chk = (calc_pack_checksum(data[:3], 3) == hdr_chk)
    if len(data) < 4 + length:
        return False, flags, b"", valid_chk
    payload = data[4 : 4 + length]
    return True, flags, payload, valid_chk

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
# Pixel Decoding, Normalization & Demosaicing
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

def process_frame_demosaic(squashed: List[int], width: int = SENSOR_WIDTH, height: int = SENSOR_HEIGHT) -> List[int]:
    """Bilinearly upscale a row-major 64x80 image to 128x160."""
    out_w = width * 2
    out_h = height * 2
    out_img = [0] * (out_w * out_h)

    for y in range(out_h):
        src_y = max(0.0, (y + 0.5) * 0.5 - 0.5)
        y0 = int(src_y)
        y1 = min(y0 + 1, height - 1)
        y_frac = src_y - y0

        for x in range(out_w):
            src_x = max(0.0, (x + 0.5) * 0.5 - 0.5)
            x0 = int(src_x)
            x1 = min(x0 + 1, width - 1)
            x_frac = src_x - x0
            top = squashed[y0 * width + x0] * (1.0 - x_frac) + squashed[y0 * width + x1] * x_frac
            bottom = squashed[y1 * width + x0] * (1.0 - x_frac) + squashed[y1 * width + x1] * x_frac
            out_img[y * out_w + x] = max(0, min(255, round(top * (1.0 - y_frac) + bottom * y_frac)))

    return out_img

def process_raw_frame(pix: List[int], width: int = SENSOR_WIDTH, height: int = SENSOR_HEIGHT) -> List[int]:
    """Locally flatten, normalize, and upscale the 64x80 raster to 128x160."""
    active_pixels = [value for value in pix if value > 30]
    min_v = min(active_pixels, default=0)
    max_v = max(active_pixels, default=0)
    val_range = (max_v - min_v) if max_v > min_v else 1

    if len(active_pixels) < 64 or val_range < 8:
        return [0] * (width * height * 4)

    residuals = []
    for y in range(height):
        for x in range(width):
            neighbors = [
                pix[yy * width + xx]
                for yy in range(max(0, y - 1), min(height, y + 2))
                for xx in range(max(0, x - 1), min(width, x + 2))
            ]
            residuals.append(pix[y * width + x] - sum(neighbors) / len(neighbors))

    residual_min = min(residuals)
    residual_range = max(residuals) - residual_min
    if residual_range < 1.0:
        return [0] * (width * height * 4)

    normalized = [
        max(0, min(255, int(((value - residual_min) * 255.0) / residual_range)))
        for value in residuals
    ]
    return process_frame_demosaic(normalized, width, height)

# ==============================================================================
# Mock Goodix MCU & Sensor Simulator
# ==============================================================================

class MockGoodixMCU:
    """
    In-memory hardware simulator for Goodix 27c6:5e0a MCU.
    Simulates:
    - USB endpoint transfers (EP 0x01 OUT, EP 0x83 IN)
    - Chip ID register 0x0000, Gain register 0x022c
    - Firmware version string response
    - Reset counter (2048)
    - PSK preset flags
    - MCU config upload (256B)
    - Hardware FDT state transitions (FDT_MODE, FDT_DOWN, FDT_UP)
    - Frame acquisition & TLS frame encryption simulation
    """

    def __init__(self, nop_replies: bool = False):
        self.reset_count = 0
        self.chip_enabled = False
        self.driver_state = 0
        self.mcu_config = None
        self.fdt_mode = None
        self.fdt_down_active = False
        self.fdt_up_active = False
        self.nop_replies = nop_replies
        self.registers: Dict[int, bytes] = {
            0x0000: CHIP_ID_VAL,
            0x022C: CANONICAL_REG_022C_GAIN,
        }
        self.in_queue = bytearray()
        self.is_connected = True
        self.tls_established = False
        self.touch_pending = False
        self.release_pending = False

    def simulate_touch_event(self):
        """Simulate physical finger touch on sensor."""
        self.touch_pending = True

    def simulate_release_event(self):
        """Simulate physical finger release from sensor."""
        self.release_pending = True

    def handle_out_packet(self, data: bytes) -> bytes:
        """Process incoming command packet from host (EP 0x01) and produce reply (EP 0x83)."""
        ok, flags, pack_payload, valid_pack_chk = decode_pack(data)
        if not ok:
            return b""

        if flags == FLAGS_MSG_PROTOCOL:
            p_ok, cmd, payload, valid_proto_chk, is_null = decode_protocol(pack_payload)
            if not p_ok:
                return b""
            return self._handle_protocol_command(cmd, payload)
        elif flags in (FLAGS_TLS, FLAGS_TLS_DATA):
            return self._handle_tls_data(pack_payload)
        return b""

    def _handle_protocol_command(self, cmd: int, payload: bytes) -> bytes:
        if cmd == CMD_NOP:
            # On-wire hardware fact: Goodix 5e0a MCU never replies to NOP.
            # Timeout is treated as success (buffer clean / drained).
            if self.nop_replies:
                ack = bytes([CMD_NOP, 0x01])  # always_true
                return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))
            return b""

        elif cmd == CMD_RESET:
            self.reset_count += 1
            # Return reset count 2048 (LE uint16)
            reset_reply = struct.pack("<H", RESET_NUMBER)
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, reset_reply))

        elif cmd == CMD_READ_SENSOR_REGISTER:
            # Payload: multiples(1), addr(2), len(1)
            if len(payload) >= 4:
                addr = struct.unpack("<H", payload[1:3])[0]
                length = payload[3]
                val = self.registers.get(addr, bytes([0] * length))
                return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, val[:length]))
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, b"\x00\x00\x00\x00"))

        elif cmd == CMD_WRITE_SENSOR_REGISTER:
            if len(payload) >= 5:
                addr = struct.unpack("<H", payload[1:3])[0]
                val = payload[3:5]
                self.registers[addr] = val
            ack = bytes([CMD_WRITE_SENSOR_REGISTER, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_FIRMWARE_VERSION:
            fw_bytes = FIRMWARE_VERSION_STR.encode("ascii") + b"\x00"
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, fw_bytes))

        elif cmd == CMD_READ_OTP:
            otp_data = b"\x00" * 32
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_OTP, otp_data))

        elif cmd == CMD_PRESET_PSK_READ:
            # Flags (4B LE) + PSK (32B)
            reply = struct.pack("<I", PSK_FLAGS) + CANONICAL_PSK
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, reply))

        elif cmd == CMD_UPLOAD_CONFIG_MCU:
            self.mcu_config = payload
            ack = bytes([CMD_UPLOAD_CONFIG_MCU, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_ENABLE_CHIP:
            self.chip_enabled = (payload[0] != 0) if payload else True
            ack = bytes([CMD_ENABLE_CHIP, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_MCU_SWITCH_TO_FDT_MODE:
            self.fdt_mode = payload
            ack = bytes([CMD_MCU_SWITCH_TO_FDT_MODE, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_MCU_SWITCH_TO_FDT_DOWN:
            self.fdt_down_active = True
            # FDT Down returns touch detection interrupt
            reply = bytes([0x01])  # Touch detected
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, reply))

        elif cmd == CMD_MCU_SWITCH_TO_FDT_UP:
            self.fdt_up_active = True
            reply = bytes([0x00])  # Release detected
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, reply))

        elif cmd == CMD_QUERY_MCU_STATE:
            reply = bytes([0x00, 0x01, 0x00, 0x00])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_QUERY_MCU_STATE, reply))

        elif cmd == CMD_REQUEST_TLS_CONNECTION:
            self.tls_established = True
            reply = bytes([0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, reply))

        elif cmd == CMD_SET_POV_CONFIG:
            ack = bytes([CMD_SET_POV_CONFIG, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_SET_DRV_STATE:
            ack = bytes([CMD_SET_DRV_STATE, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_MCU_GET_POV_IMAGE:
            # 0xd2 POV image query
            test_pixels = [(i % 4096) for i in range(FRAME_PIXELS)]
            raw_bytes = pack_12bit_frame(test_pixels)
            return encode_pack(FLAGS_TLS_DATA, raw_bytes)

        elif cmd == CMD_TLS_SUCCESSFULLY_ESTABLISHED:
            ack = bytes([CMD_TLS_SUCCESSFULLY_ESTABLISHED, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_NAV_0:
            ack = bytes([CMD_NAV_0, 0x01])
            return encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ACK, ack))

        elif cmd == CMD_MCU_GET_IMAGE:
            # Generate synthetic raw frame
            test_pixels = [(i % 4096) for i in range(FRAME_PIXELS)]
            raw_bytes = pack_12bit_frame(test_pixels)
            # Frame reply over TLS data
            return encode_pack(FLAGS_TLS_DATA, raw_bytes)

        return b""

    def _handle_tls_data(self, data: bytes) -> bytes:
        # Echo or TLS frame response
        test_pixels = [((r * 50 + c * 30) % 4000) for r in range(SENSOR_HEIGHT) for c in range(SENSOR_WIDTH)]
        raw_bytes = pack_12bit_frame(test_pixels)
        return encode_pack(FLAGS_TLS_DATA, raw_bytes)
