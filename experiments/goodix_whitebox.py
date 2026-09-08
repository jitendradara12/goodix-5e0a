#!/usr/bin/env python3
"""Goodix WhiteBox Encryption Implementation.

Reverse-engineered from Goodix Windows driver:
  - Binary: wbdi.dll
  - Function: SecWhiteEncrypt at 0x180001000 (seccipher.c)
  - Callers: PresetPskWriteKey at 0x180039d50 (pskunify.c) -> PresetPskWriteG at 0x180097edc (geneva.c)

Algorithm:
  1. Input: raw PSK (32 bytes).
  2. Seed = struct.pack("<I", len(psk)) + b"123GOODIX" (13 bytes).
  3. Digest = SHA256(seed) (32 bytes).
  4. Mutate byte 15 of Digest:
     digest[15] = ((digest[15] ^ len(psk)) & 0x0f) ^ digest[15]
  5. AES Key = digest[0:16], AES IV = digest[0:16].
  6. Ciphertext = AES-128-CBC-Encrypt(Key, IV, PKCS#7(psk)).
     Since len(psk) == 32 (multiple of 16), PKCS#7 appends a 16-byte block of \x10.
     Ciphertext length is 48 bytes.
  7. HMAC Key = digest (full 32 bytes, with byte 15 mutated).
  8. HMAC = HMAC-SHA256(HMAC Key, Ciphertext) (32 bytes).
  9. Result = IV (16B) + Ciphertext (48B) + HMAC (32B) = 96 bytes (0x60).
"""

import hashlib
import hmac
import struct
import subprocess

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    HAVE_CRYPTOGRAPHY = True
except ImportError:
    HAVE_CRYPTOGRAPHY = False


def _aes_128_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if HAVE_CRYPTOGRAPHY:
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()
    else:
        cmd = ["openssl", "enc", "-aes-128-cbc", "-K", key.hex(), "-iv", iv.hex()]
        res = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return res.stdout


def _aes_128_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    if HAVE_CRYPTOGRAPHY:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded_data) + unpadder.finalize()
    else:
        cmd = ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", iv.hex()]
        res = subprocess.run(cmd, input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return res.stdout


def sec_white_encrypt(data: bytes) -> bytes:
    """Encrypt data using Goodix SecWhiteEncrypt algorithm (AES-128-CBC + HMAC-SHA256)."""
    input_len = len(data)

    # 1. 4-byte little-endian length + "123GOODIX"
    seed = struct.pack("<I", input_len) + b"123GOODIX"
    digest = bytearray(hashlib.sha256(seed).digest())

    # 2. Mutate byte 15
    digest[15] = ((digest[15] ^ input_len) & 0x0F) ^ digest[15]

    # 3. First 16 bytes of mutated digest are AES Key and IV
    key = bytes(digest[:16])
    iv = bytes(digest[:16])

    # 4. AES-128-CBC with PKCS#7 padding
    ciphertext = _aes_128_cbc_encrypt(key, iv, data)

    # 5. HMAC-SHA256 over ciphertext with mutated 32-byte digest as key
    hmac_key = bytes(digest)
    mac = hmac.new(hmac_key, ciphertext, hashlib.sha256).digest()

    # 6. Output layout: 16B IV + 48B Ciphertext + 32B HMAC = 96 bytes
    return iv + ciphertext + mac


def sec_white_decrypt(encrypted: bytes) -> bytes:
    """Decrypt and verify Goodix WhiteBox encrypted payload."""
    if len(encrypted) < 96:
        raise ValueError(f"Encrypted payload too short: {len(encrypted)} < 96")

    iv = encrypted[:16]
    ciphertext = encrypted[16:-32]
    expected_mac = encrypted[-32:]

    # For 32-byte PSK, input length is 32
    input_len = 32
    seed = struct.pack("<I", input_len) + b"123GOODIX"
    digest = bytearray(hashlib.sha256(seed).digest())
    digest[15] = ((digest[15] ^ input_len) & 0x0F) ^ digest[15]

    key = bytes(digest[:16])
    if iv != key:
        raise ValueError("IV does not match derived IV")

    hmac_key = bytes(digest)
    calc_mac = hmac.new(hmac_key, ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(calc_mac, expected_mac):
        raise ValueError("HMAC verification failed")

    return _aes_128_cbc_decrypt(key, iv, ciphertext)


def build_psk_write_payload(psk: bytes, sealed_blob: bytes = b"") -> bytes:
    """Build the full unchunked payload for GOODIX_CMD_PRESET_PSK_WRITE (0xe0).

    Layout:
      - 10-byte Magic Header: 56 a5 bb 95 6b 7c 8d 9e 00 00
      - TLV1 (Host-Sealed Blob, tag 0xbb010002):
          [tag (4B LE)] [len (4B LE)] [data]
      - TLV2 (WhiteBox Encrypted PSK, tag 0xbb010003):
          [tag (4B LE)] [len (4B LE)] [96B WhiteBox payload]
    """
    magic = bytes([0x56, 0xA5, 0xBB, 0x95, 0x6B, 0x7C, 0x8D, 0x9E, 0x00, 0x00])

    # TLV1: Tag 0xbb010002
    tlv1 = struct.pack("<II", 0xBB010002, len(sealed_blob)) + sealed_blob

    # TLV2: Tag 0xbb010003
    encrypted_psk = sec_white_encrypt(psk)
    assert len(encrypted_psk) == 96
    tlv2 = struct.pack("<II", 0xBB010003, len(encrypted_psk)) + encrypted_psk

    return magic + tlv1 + tlv2


def chunk_psk_write_payload(full_payload: bytes, chunk_size: int = 256):
    """Split full payload into chunks with 12-byte Goodix chunk header.

    Chunk header (12 bytes LE):
      uint32_t total_len
      uint32_t chunk_len
      uint32_t chunk_offset
      uint8_t  chunk_data[chunk_len]
    """
    total_len = len(full_payload)
    chunks = []
    offset = 0
    while offset < total_len:
        chunk_len = min(chunk_size, total_len - offset)
        chunk_data = full_payload[offset:offset + chunk_len]
        hdr = struct.pack("<III", total_len, chunk_len, offset)
        chunks.append(hdr + chunk_data)
        offset += chunk_len
    return chunks


if __name__ == "__main__":
    psk = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
    enc = sec_white_encrypt(psk)
    dec = sec_white_decrypt(enc)
    assert dec == psk, "Round-trip failed!"
    print("SecWhiteEncrypt self-test PASSED (round-trip verified).")
    payload = build_psk_write_payload(psk)
    chunks = chunk_psk_write_payload(payload)
    print(f"Full payload: {len(payload)} bytes, split into {len(chunks)} chunk(s).")
    for i, c in enumerate(chunks):
        tot, clen, coff = struct.unpack("<III", c[:12])
        print(f"  Chunk {i}: total={tot}, chunk_len={clen}, offset={coff}, wire_len={len(c)}")
