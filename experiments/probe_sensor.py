import sys
import os

# Mock protocol module for goodix.py
import goodix_protocol
sys.modules['protocol'] = goodix_protocol

sys.path.insert(0, '/tmp/goodix-fp-dump')
import goodix
import usb.core

def probe():
    print("=== Probing Goodix 27c6:5e0a ===")
    dev = usb.core.find(idVendor=0x27c6, idProduct=0x5e0a)
    if dev is None:
        print("Device 27c6:5e0a not found on USB bus!")
        return False

    print(f"Device found: Bus {dev.bus}, Address {dev.address}")
    # Let USBProtocol claim interface cleanly

    proto = goodix_protocol.USBProtocol(0x27c6, 0x5e0a)
    device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)

    print("\n--- 1. Testing NOP ---")
    try:
        device.nop()
        print("NOP success!")
    except Exception as e:
        print("NOP failed:", e)

    print("\n--- 2. Querying Firmware Version ---")
    try:
        fw = device.firmware_version()
        print(f"Firmware Version: {fw}")
    except Exception as e:
        print("Firmware Version query failed:", e)

    print("\n--- 3. Reading OTP ---")
    try:
        otp = device.read_otp()
        print(f"OTP ({len(otp)} bytes): {otp.hex()}")
    except Exception as e:
        print("Read OTP failed:", e)

    print("\n--- 4. Querying MCU State ---")
    try:
        state = device.query_mcu_state(b"\x00\x00", False)
        print("MCU State response:", state)
    except Exception as e:
        print("MCU State query failed:", e)

    return True

if __name__ == '__main__':
    probe()
