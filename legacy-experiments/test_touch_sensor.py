from pathlib import Path
import sys
sys.path.insert(0, ".")
import socket
import subprocess
import time

import goodix_protocol
sys.modules['protocol'] = goodix_protocol
vendor_dir = Path(__file__).resolve().parent / "vendor"
if vendor_dir.exists():
    sys.path.insert(0, str(vendor_dir))
sys.path.insert(0, "/tmp/goodix-fp-dump")
import goodix
import tool

PSK = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
CONFIG_52XD = bytes.fromhex(
    "701160712c9d2cc91ce518fd00fd00fd03ba000180ca0008008400bec38600b1"
    "b68800baba8a00b3b38c00bcbc8e00b1b19000bbbb9200b1b194000000960000"
    "00980000009a000000d2000000d4000000d6000000d800000050000105d00000"
    "00700000007200785674003412200010402a0102042200012024003200800001"
    "005c000101560024205800010232000402660000027c00005882007f082a0182"
    "072200012024001400800001405c00ea00560006145800040232000c02660000"
    "027c000058820080082a0108005c000101540000016200080464001000660000"
    "027c0000582a0108005c00e8005200080054000001660000027c00005820c50e"
)

FDT_DOWN_0 = bytes.fromhex(
    "9c0127012101270123018d8d868697978f8f9b9b929296968c8c00000503a700a100a700a30000"
)
FDT_DOWN_1 = bytes.fromhex(
    "9c0127012101270123018d8d868697978f8f9b9b929296968c8c01000503a700a100a700a30000"
)

FDT_MODE_0 = bytes.fromhex(
    "0d0127012101270123010000000000000000000000000000000000"
)
FDT_MODE_1 = bytes.fromhex(
    "0d0127012101270123010000000000000000000000000000000001"
)

print("Starting OpenSSL server...")
tls_server = subprocess.Popen([
    "openssl", "s_server", "-nocert",
    "-psk", PSK.hex(),
    "-cipher", "PSK-AES128-CBC-SHA256",
    "-tls1_2",
    "-port", "4433",
    "-quiet"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

time.sleep(0.5)

try:
    print("Connecting device...")
    device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
    device.nop()
    device.reset(True, False, 20)
    device.read_sensor_register(0x0000, 4)
    device.read_otp()

    tls_client = socket.socket()
    tls_client.connect(("localhost", 4433))

    try:
        tool.connect_device(device, tls_client)
        device.tls_successfully_established()
        device.upload_config_mcu(CONFIG_52XD)
        device.enable_chip(True)
        device.set_drv_state()
        print("[+] Device ready for touch test!")

        print("\n--- Testing FDT MODE 0 ---")
        device.mcu_switch_to_fdt_mode(FDT_MODE_0, False)
        print("FDT MODE 0 sent successfully!")

        print("\n--- Testing FDT MODE 1 (reply=True) ---")
        res_mode = device.mcu_switch_to_fdt_mode(FDT_MODE_1, True)
        print("FDT MODE 1 reply:", res_mode.hex() if res_mode else None)

        print("\n--- Testing FDT DOWN 0 ---")
        device.mcu_switch_to_fdt_down(FDT_DOWN_0, False)
        print("FDT DOWN 0 sent successfully!")

        print("\n" + "="*50)
        print("👉 TOUCH THE FINGERPRINT SCANNER NOW!")
        print("="*50)
        start_t = time.time()
        res_down = device.mcu_switch_to_fdt_down(FDT_DOWN_1, True)
        elapsed = time.time() - start_t
        print(f"Touch detected in {elapsed:.2f}s! Result: {res_down.hex() if res_down else None}")

    finally:
        tls_client.close()
finally:
    tls_server.terminate()
