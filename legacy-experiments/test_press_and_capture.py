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
        device.write_sensor_register(0x022c, b"\x05\x03")

        print("\n" + "=" * 50)
        print(">>> PLACE YOUR FINGER FIRMLY ON THE SENSOR NOW! <<<")
        print("Capturing in 5 seconds...")
        print("=" * 50)
        for i in range(5, 0, -1):
            print(f"  {i}...")
            time.sleep(1.0)
        print(">>> CAPTURING NOW! <<<")

        img_req = device.mcu_get_image(
            b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            goodix.FLAGS_TRANSPORT_LAYER_SECURITY_DATA)
        print(f"Got encrypted frame from MCU: {len(img_req)} bytes!")
        tls_client.sendall(img_req[9:])
        time.sleep(0.1)
        dec = tls_server.stdout.read(7684)
        print(f"Decrypted frame: {len(dec)} bytes!")
        pixels = tool.decode_image(dec[:-4])
        print(f"Pixels: {len(pixels)}, min={min(pixels)}, max={max(pixels)}, avg={sum(pixels)/len(pixels):.1f}")
        active = sum(1 for p in pixels if p > 30)
        print(f"Active pixels (>30): {active} / {len(pixels)}")
        tool.write_pgm(pixels, 80, 64, "/tmp/press_capture.pgm")
        print("Saved /tmp/press_capture.pgm!")
    finally:
        tls_client.close()
finally:
    tls_server.terminate()
