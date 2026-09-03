import sys
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
    print("Initializing device...")
    device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
    device.nop()
    device.reset(True, False, 20)
    device.read_sensor_register(0x0000, 4)
    device.read_otp()

    tls_client = socket.socket()
    tls_client.connect(("localhost", 4433))

    try:
        print("Connecting TLS...")
        tool.connect_device(device, tls_client)
        print("TLS connected successfully!")

        print("Uploading config...")
        if not device.upload_config_mcu(CONFIG_52XD):
            raise ValueError("Failed to upload config")
        print("Config uploaded successfully!")

        print("Setting drv state...")
        device.set_drv_state()

        print("Checking POV image...")
        device.mcu_get_pov_image()

        print("Switching to FDT mode...")
        device.mcu_switch_to_fdt_mode(
            b"\x0d\x01\x27\x01\x21\x01\x27\x01"
            b"\x23\x01\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00", False)
        device.mcu_switch_to_fdt_mode(
            b"\x0d\x01\x27\x01\x21\x01\x27\x01"
            b"\x23\x01\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x01", True)

        print("Writing sensor register 0x022c...")
        device.write_sensor_register(0x022c, b"\x0a\x03")

        print("Requesting MCU image frame...")
        img_req = device.mcu_get_image(
            b"\x01\x03\x27\x01\x21\x01\x27\x01\x23\x01",
            goodix.FLAGS_TRANSPORT_LAYER_SECURITY_DATA)
        print(f"Received encrypted image frame from MCU: {len(img_req)} bytes!")

        # Forward encrypted frame to openssl s_server to decrypt
        tls_client.sendall(img_req[9:])

        # Read decrypted frame from openssl stdout
        decrypted_data = tls_server.stdout.read(7684)
        print(f"Decrypted frame length: {len(decrypted_data)} bytes!")

        if len(decrypted_data) >= 7680:
            decoded_image = tool.decode_image(decrypted_data[:-4])
            print(f"Decoded {len(decoded_image)} pixels!")
            tool.write_pgm(decoded_image, SENSOR_WIDTH, SENSOR_HEIGHT, "/home/sastauser/code/temp/goodix/clear-0.pgm")
            print("Successfully saved /home/sastauser/code/temp/goodix/clear-0.pgm!")
        else:
            print("Decrypted data too short:", decrypted_data.hex()[:100])

    finally:
        tls_client.close()

finally:
    tls_server.terminate()
