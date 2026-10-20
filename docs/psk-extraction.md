# Extracting Your Sensor Key (PSK)

When Windows sets up the sensor, it locks the hardware with a unique key. If your laptop uses its own key, enrollment fails with `enroll-unknown-error` (`bad record MAC` in the logs).

Extract the key once and back up `/etc/libfprint/goodix-5e0a.psk` to safe storage.

---

## Method 1: Linux Recovery (Recommended)

Extracts and verifies the key directly on Linux without booting Windows.

### 1. Install dependencies

- **Ubuntu / Debian / Mint:** `sudo apt install python3-usb python3-cryptography`
- **Fedora:** `sudo dnf install python3-pyusb python3-cryptography`
- **Arch:** `sudo pacman -S python-pyusb python-cryptography`
- **NixOS:** `nix-shell -p 'python3.withPackages (p: [ p.pyusb p.cryptography ])'`

### 2. Extract and install the key

```bash
sudo systemctl stop fprintd
sudo "$(command -v python3)" tools/extract_psk_whitebox.py --out /etc/libfprint/goodix-5e0a.psk
sudo systemctl start fprintd
```

The script extracts the whitebox record, verifies the SHA-256 hash against your sensor, and writes `/etc/libfprint/goodix-5e0a.psk` with mode `0600`.

### 3. Verify

```bash
fprintd-enroll
```

---

## Record layout and the by-offset read

The `0xbb010002` area contains a DPAPI blob followed by a whitebox record.
On Jet-Soup's tested unit it is:

| Offset | Content |
| --- | --- |
| 0–323 | 324-byte DPAPI blob |
| 324–327 | Little-endian tag `0xbb010003` |
| 328–331 | Little-endian record length, 96 |
| 332–427 | 16-byte prefix, 48-byte AES-CBC ciphertext, 32-byte HMAC |

Reading `0xbb010003` by tag is refused on that firmware. Addressing the same
region by offset with command `0xe4` returns it. Goodix's `SecWhiteEncrypt`
derives its AES/HMAC keys from public constants and the plaintext length; the
existing `legacy-experiments/goodix_whitebox.py` implements that algorithm.

The helper parses the DPAPI structure length instead of assuming offset 324.
Discovery and all reads are bounded to 4096 bytes. It validates the record,
prefix, HMAC, padding, plaintext length, and final sensor hash before publishing
the output file. There is no option to bypass that hash check.

For a known layout that cannot be discovered automatically, `--offset` accepts
a decimal or hex offset to the record header or the payload itself. For
example, the tested header offset is `--offset 324`, and its payload offset is
`--offset 332`. Use an override only when the layout is known; a failed read
does not establish another offset. Verification remains mandatory.

The tool sends NOP and read commands only. It does not re-pair, provision,
write flash, extract templates, or change the driver. `--print-key` explicitly
prints the verified secret after it has been saved; normal use does not need it.

---

## Method 2: Windows DPAPI (Fallback)

Use this only if Linux extraction fails to recover the key.

### 1. Dump the locked blob in Linux

```bash
sudo systemctl stop fprintd
sudo python3 tools/dump_dpapi_blob.py
sudo systemctl start fprintd
```

This creates `dpapi_blob.bin` and `mcu_hash.txt`.

### 2. Decrypt on Windows

1. Copy `dpapi_blob.bin`, `mcu_hash.txt`, and `tools/decrypt_psk.ps1` to the Windows installation that originally paired the sensor.
2. Open **PowerShell as Administrator** in that folder and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\decrypt_psk.ps1
   ```
   This generates `goodix-5e0a.psk`.

### 3. Install the key in Linux

Copy `goodix-5e0a.psk` back to Linux and install it:

```bash
sudo install -D -m 600 -o root -g root goodix-5e0a.psk /etc/libfprint/goodix-5e0a.psk
sudo systemctl restart fprintd
fprintd-enroll
```

---

## Troubleshooting

- **Sensor busy or permission denied:** Stop fprintd first (`sudo systemctl stop fprintd`) and run scripts with `sudo`.
- **Existing key file:** `extract_psk_whitebox.py` will not overwrite an existing file unless you pass `--force`.
- **Windows PowerShell execution policy:** Ensure you ran PowerShell as Administrator and passed `-ExecutionPolicy Bypass`.
