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

print("Starting OpenSSL s_server with PSK...")
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
    print("Connecting to Goodix device...")
    device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
    device.nop()

    print("Resetting sensor...")
    res = device.reset(True, False, 20)
    print("Reset result:", res)

    print("Reading chip ID (reg 0x0000)...")
    chip_id = device.read_sensor_register(0x0000, 4)
    print("Chip ID:", chip_id.hex())

    print("Reading OTP...")
    otp = device.read_otp()
    print("OTP len:", len(otp))

    print("Connecting to local TLS server...")
    tls_client = socket.socket()
    tls_client.connect(("localhost", 4433))

    try:
        print("Initiating TLS handshake with Goodix MCU...")
        tool.connect_device(device, tls_client)
        print(">>> TLS HANDSHAKE SUCCESSFULLY ESTABLISHED! <<<")

        # Test sending TLS_SUCCESSFULLY_ESTABLISHED if needed
        # Or checking device state
        print("Device is now in encrypted TLS mode!")

    finally:
        tls_client.close()

finally:
    print("Terminating TLS server...")
    tls_server.terminate()
