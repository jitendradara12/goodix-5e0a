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

print("--- Reading Sensor Register 0x0000 ---")
try:
    reg0 = device.read_sensor_register(0x0000, 4)
    print("Reg 0x0000:", reg0.hex())
except Exception as e:
    print("Failed to read reg 0x0000:", e)

print("--- Reading PSK status ---")
for flag in [0xbb020001, 0xbb020003, 0xbb020007]:
    try:
        reply = device.preset_psk_read(flag, 32, 0)
        print(f"preset_psk_read({hex(flag)}): success={reply[0]}, flags={hex(reply[1]) if len(reply)>1 else None}, data={reply[2].hex() if len(reply)>2 else None}")
    except Exception as e:
        print(f"preset_psk_read({hex(flag)}) failed: {e}")

