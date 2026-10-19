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
sudo python3 tools/extract_psk_whitebox.py --out /etc/libfprint/goodix-5e0a.psk
sudo systemctl start fprintd
```

The script extracts the whitebox record, verifies the SHA-256 hash against your sensor, and writes `/etc/libfprint/goodix-5e0a.psk` with mode `0600`.

### 3. Verify

```bash
fprintd-enroll
```

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
