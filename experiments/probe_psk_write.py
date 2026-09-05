from pathlib import Path
import sys
import goodix_protocol
sys.modules['protocol'] = goodix_protocol
vendor_dir = Path(__file__).resolve().parent / "vendor"
if vendor_dir.exists():
    sys.path.insert(0, str(vendor_dir))
sys.path.insert(0, "/tmp/goodix-fp-dump")
import goodix

device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
device.nop()
print("NOP: ok", flush=True)

HOST_KEY = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
assert len(HOST_KEY) == 32
print(f"HOST_KEY: {HOST_KEY.hex()} len={len(HOST_KEY)}", flush=True)

try:
    ok = device.preset_psk_write(0xbb020001, HOST_KEY, 32, 0)
except Exception as e:
    print(f"WRITE_0xe0_SLICED: REJECT/ERROR {e}", flush=True)
    ok = False
print(f"WRITE_0xe0_SLICED: accept={ok}", flush=True)

read_data = None
try:
    reply = device.preset_psk_read(0xbb020001, 32, 0)
except Exception as e:
    print(f"READ_BACK: exception {e}", flush=True)
else:
    if not reply[0]:
        print("READ_BACK: mcu-error-reply", flush=True)
    else:
        print(f"READ_BACK: flags={hex(reply[1])} data={reply[2].hex()}", flush=True)
        read_data = reply[2]

if read_data is None:
    print("VERDICT: unreadable", flush=True)
elif read_data == HOST_KEY:
    print("VERDICT: latched", flush=True)
else:
    print(f"VERDICT: still-factory data={read_data.hex()}", flush=True)
