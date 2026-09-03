import sys, socket, subprocess, time
import goodix_protocol
sys.modules["protocol"] = goodix_protocol
sys.path.insert(0, "/tmp/goodix-fp-dump")
import goodix, tool

PSK = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
CONFIG_WBDI = bytes.fromhex(
    "701160712c9d2cc91ce518fd00fd00fd03ba000180ca0008008400bec38600b1"
    "b68800baba8a00b3b38c00bcbc8e00b1b19000bbbb9200b1b194000000960000"
    "00980000009a000000d2000000d4000000d6000000d800000050000105d00000"
    "00700000007200785674003412200010402a0102042200012024003200800001"
    "005c000101560024205800010232000402660000027c00005882007f082a0182"
    "072200012024001400800001405c000001560006145800040232000c02660000"
    "027c00005882007f082a0108005c000101540000016200080464001000660000"
    "027c0000582a0108005c00fb005200080054000001660000027c0000582002fc"
)
FDT_DOWN_1 = bytes.fromhex(
    "9c0127012101270123018d8d868697978f8f9b9b929296968c8c01000503a700a100a700a30000"
)

tls_server = subprocess.Popen([
    "openssl", "s_server", "-nocert",
    "-psk", PSK.hex(), "-cipher", "PSK-AES128-CBC-SHA256",
    "-tls1_2", "-port", "4433", "-quiet"
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
        device.upload_config_mcu(CONFIG_WBDI)
        device.enable_chip(True)

        print("\n" + "="*60)
        print(">>> TOUCH AND HOLD YOUR FINGER ON SENSOR NOW (5 sec timeout) <<<")
        print("="*60)
        start_t = time.time()
        # Wait up to 5 seconds for finger touch
        touch_detected = False
        while time.time() - start_t < 5.0:
            res = device.mcu_switch_to_fdt_down(FDT_DOWN_1, False)
            if res:
                print(f"[+] Touch detected via FDT DOWN: {res.hex()}")
                touch_detected = True
                break
            time.sleep(0.1)

        if not touch_detected:
            print("[*] No touch detected via FDT DOWN, proceeding to capture anyway...")

        img_req = device.mcu_get_image(
            b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            goodix.FLAGS_TRANSPORT_LAYER_SECURITY_DATA)
        tls_client.sendall(img_req[9:])
        time.sleep(0.2)
        dec = tls_server.stdout.read(7684)[:-4]
        print(f"[+] Decrypted frame length: {len(dec)} bytes")

        # 1. Windows exact 0x18004ea50 unpacking
        out_win = [0] * (80 * 64)
        pixel_index = 0
        for i in range(0, len(dec), 6):
            chunk = dec[i:i+6]
            vals = [
                ((chunk[0] & 0xf) << 8) | chunk[1],
                (chunk[3] << 4) | (chunk[0] >> 4),
                ((chunk[5] & 0xf) << 8) | chunk[2],
                (chunk[4] << 4) | (chunk[5] >> 4),
            ]
            for v in vals:
                row = pixel_index % 64
                col = pixel_index // 64
                out_win[row * 80 + col] = v
                pixel_index += 1

        # 2. Extract 19 dense columns
        cols = [4*k + 3 for k in range(19)]
        dense_19 = []
        for y in range(64):
            for c in cols:
                dense_19.append(out_win[y * 80 + c])

        # 3. Bilinear / linear interpolated across 80 columns (width 80, height 64)
        interp_80 = []
        for y in range(64):
            row_samples = [out_win[y * 80 + c] for c in cols]
            for x in range(80):
                # map x in 0..79 to pos in 0..18
                pos = x * 18.0 / 79.0
                k = int(pos)
                frac = pos - k
                if k >= 18:
                    val = row_samples[18]
                else:
                    val = row_samples[k] * (1.0 - frac) + row_samples[k+1] * frac
                interp_80.append(val)

        # 4. Enlarge 2x (width 160, height 128) per aes3500 hack
        interp_160x128 = []
        for y in range(128):
            orig_y = y / 2.0
            y0 = int(orig_y)
            y1 = min(63, y0 + 1)
            y_frac = orig_y - y0
            for x in range(160):
                pos = x * 18.0 / 159.0
                k = int(pos)
                frac = pos - k
                k1 = min(18, k + 1)
                top = out_win[y0 * 80 + cols[k]] * (1.0 - frac) + out_win[y0 * 80 + cols[k1]] * frac
                bot = out_win[y1 * 80 + cols[k]] * (1.0 - frac) + out_win[y1 * 80 + cols[k1]] * frac
                val = top * (1.0 - y_frac) + bot * y_frac
                interp_160x128.append(val)

        def save_pgm(path, w, h, data_list):
            min_v = min(data_list)
            max_v = max(data_list)
            rng = max_v - min_v if max_v > min_v else 1
            scaled = bytes([int((v - min_v) * 255.0 / rng) for v in data_list])
            with open(path, "wb") as f:
                f.write(f"P5\n{w} {h}\n255\n".encode() + scaled)

        save_pgm("finger_win_80x64.pgm", 80, 64, out_win)
        save_pgm("finger_dense_19x64.pgm", 19, 64, dense_19)
        save_pgm("finger_interp_80x64.pgm", 80, 64, interp_80)
        save_pgm("finger_interp_160x128.pgm", 160, 128, interp_160x128)

        print("\nSaved all test PGM images!")

    finally:
        tls_client.close()
finally:
    tls_server.terminate()
