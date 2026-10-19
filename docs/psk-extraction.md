# Recovering your sensor key on Linux

The Goodix `27c6:5e0a` sensor can have a unique key from Windows pairing.
A wrong key causes TLS errors such as `bad record MAC`. Try the Linux-only
method below first, even if Windows has been erased. Successful recovery does
not require booting Windows or pairing the sensor again.

This method comes from [Jet-Soup's contribution to issue #12](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6263682686).
They verified it on firmware `GFUSB_GM168SEC_APP_10036`. Other layouts may not
expose the same record; the tool reports an error rather than saving an
unverified key. The normal driver remains limited to x86-64 Linux.

## 1. Install the extraction dependencies

Use Python 3.10 or newer, pyusb, and python-cryptography. Run the appropriate
command for your distribution:

```sh
# Ubuntu / Debian / Mint
sudo apt install python3-usb python3-cryptography

# Fedora
sudo dnf install python3-pyusb python3-cryptography

# Arch
sudo pacman -S python-pyusb python-cryptography
```

On NixOS, enter a shell with the dependencies before the next step:

```sh
nix-shell -p 'python3.withPackages (p: [ p.pyusb p.cryptography ])'
```

The helper can use an installed OpenSSL executable instead of
python-cryptography. It checks for a crypto dependency before opening the
sensor. A missing libusb backend must also be installed through your distro.

## 2. Recover and install the key

Run from this repository on the laptop containing the sensor:

```sh
sudo systemctl stop fprintd
sudo "$(command -v python3)" tools/extract_psk_whitebox.py --out /etc/libfprint/goodix-5e0a.psk
sudo systemctl start fprintd
```

The helper reads the sensor, decrypts its whitebox record, and requires the
resulting 32-byte key's SHA-256 to match the hash read from that same sensor.
It creates the parent directory if needed and saves exactly 64 hex characters
plus a newline, with mode `0600`. It does not print the key by default.

If extraction fails, still run the `systemctl start` command to restore normal
service. Save the error text for troubleshooting; do not post the key file.

An existing output file is preserved. If you intentionally need to replace it,
repeat extraction with `--force`; the previous file remains intact if recovery
or replacement fails. Back up a successfully recovered key in private storage.
Keep the key outside the Nix store, which is world-readable.

## 3. Test a fresh enrollment

```sh
fprintd-enroll
fprintd-verify
```

After upgrading from the older matching pipeline, remove the incompatible
old prints through your desktop's fingerprint settings and enroll again.
If TLS succeeds but matching fails, key extraction is complete: continue with
the [separate hardware test](HARDWARE_TEST.md), rather than changing the key.

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

## Windows / DPAPI fallback

Use this only if Linux recovery cannot read a valid verified record. Failure
of the Linux method does not erase or change anything on the sensor.

### Original Windows installation is available

1. Stop fprintd and run `sudo python3 tools/dump_dpapi_blob.py` on Linux,
   then start fprintd again. This saves `dpapi_blob.bin` and `mcu_hash.txt`.
2. Copy those files and `tools/decrypt_psk.ps1` to the original Windows
   installation that paired this sensor.
3. Open PowerShell as Administrator in their directory and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\decrypt_psk.ps1
   ```

4. Require a matching sensor hash. If it does not match, stop and investigate;
   do not force installation of the mismatched key.
5. Copy the resulting `goodix-5e0a.psk` to Linux and install it:

   ```sh
   sudo install -D -m 600 -o root -g root goodix-5e0a.psk /etc/libfprint/goodix-5e0a.psk
   sudo systemctl restart fprintd
   ```

### Original Windows installation is gone

Linux recovery above can still work because it reads the sensor's own copy;
the erased Windows installation is not needed for that method.

If that method is unavailable and the original DPAPI master key is gone,
the DPAPI blob alone is insufficient. The remaining fallback is a temporary
Windows To Go installation with the manufacturer's Goodix driver, followed
by pairing and the DPAPI steps above. Re-pairing writes a new sensor key;
use this fallback only after reviewing the Linux recovery error. A different
Windows installation or VM cannot decrypt the old blob without its original
DPAPI keys.

## Troubleshooting

- **USB permission or busy-device error:** Stop fprintd and use sudo. Restart
  the service after the attempt.
- **Cannot determine DPAPI length / no valid record:** Keep the exact error
  and firmware version for the issue. Avoid blind offset or parameter sweeps.
- **Hash mismatch or HMAC failure:** Nothing new is written. Keep the existing
  key and investigate the layout/read; verification cannot be disabled.
- **Output exists:** Recovery is usually unnecessary if that key already
  works. Use `--force` only for an intentional verified replacement.
- **PowerShell blocked / Access Denied:** Use Administrator PowerShell and
  the documented `-ExecutionPolicy Bypass` command.
