import sys
import os
import socket
import subprocess
import time

import goodix_protocol
sys.modules['protocol'] = goodix_protocol
sys.path.insert(0, '/tmp/goodix-fp-dump')
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

SENSOR_WIDTH = 80
SENSOR_HEIGHT = 64

def save_bmp(pixels, width, height, path):
    min_val = min(pixels)
    max_val = max(pixels)
    val_range = max_val - min_val if max_val > min_val else 1

    img_8bit = [int(255 * (p - min_val) / val_range) for p in pixels]

    row_padding = (4 - (width % 4)) % 4
    file_size = 54 + 1024 + (width + row_padding) * height
    bmp = bytearray()
    bmp.extend(b'BM')
    bmp.extend(file_size.to_bytes(4, 'little'))
    bmp.extend((0).to_bytes(4, 'little'))
    bmp.extend((54 + 1024).to_bytes(4, 'little'))
    bmp.extend((40).to_bytes(4, 'little'))
    bmp.extend(width.to_bytes(4, 'little'))
    bmp.extend(height.to_bytes(4, 'little'))
    bmp.extend((1).to_bytes(2, 'little'))
    bmp.extend((8).to_bytes(2, 'little'))
    bmp.extend((0).to_bytes(4, 'little'))
    bmp.extend(((width + row_padding) * height).to_bytes(4, 'little'))
    bmp.extend((2835).to_bytes(4, 'little'))
    bmp.extend((2835).to_bytes(4, 'little'))
    bmp.extend((256).to_bytes(4, 'little'))
    bmp.extend((256).to_bytes(4, 'little'))
    for i in range(256):
        bmp.extend(bytes([i, i, i, 0]))
    for r in reversed(range(height)):
        row = img_8bit[r * width : (r + 1) * width]
        bmp.extend(bytes(row))
        bmp.extend(b'\x00' * row_padding)

    with open(path, 'wb') as f:
        f.write(bmp)

def main():
    print("=" * 60)
    print("Goodix 27c6:5e0a Fingerprint Image Capture")
    print("=" * 60)

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
            print("[+] Sensor hardware initialized and ready.")

            print("\n" + "=" * 60)
            print("👉 PLACE YOUR FINGER FIRMLY ON THE SCANNER NOW!")
            print("=" * 60 + "\n")
            time.sleep(2.0)

            print("[+] Capturing fingerprint image frame...")
            img_req = device.mcu_get_image(
                b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00",
                goodix.FLAGS_TRANSPORT_LAYER_SECURITY_DATA)

            tls_client.sendall(img_req[9:])
            time.sleep(0.2)
            decrypted = tls_server.stdout.read(7684)[:-4]

            decoded = tool.decode_image(decrypted)
            print(f"[+] Frame captured: {len(decoded)} pixels (80 x 64).")
            print(f"[+] Pixel intensity: min={min(decoded)}, max={max(decoded)}, avg={sum(decoded)/len(decoded):.1f}")
            nonzeros = sum(1 for p in decoded if p != 0)
            print(f"[+] Active pixel count: {nonzeros} / {len(decoded)}")

            tool.write_pgm(decoded, SENSOR_WIDTH, SENSOR_HEIGHT, "/home/sastauser/code/temp/goodix/fingerprint.pgm")
            save_bmp(decoded, SENSOR_WIDTH, SENSOR_HEIGHT, "/home/sastauser/code/temp/goodix/fingerprint.bmp")
            print("\n>>> SAVED TO /home/sastauser/code/temp/goodix/fingerprint.bmp <<<")
            print(">>> SUCCESS! RAW FINGERPRINT IMAGE ACQUIRED! <<<")

        finally:
            tls_client.close()
    finally:
        tls_server.terminate()

if __name__ == '__main__':
    main()
