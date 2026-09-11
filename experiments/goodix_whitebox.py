#!/usr/bin/env python3
"""Goodix WhiteBox Encryption Implementation.

Reverse-engineered from Goodix Windows driver:
  - Binary: wbdi.dll
  - Function: SecWhiteEncrypt at 0x180005f30 (seccipher.c)
  - Callers: PresetPskWriteKey at 0x180039d50 (pskunify.c) -> PresetPskWriteG at 0x180097edc (geneva.c)

Algorithm (Two-Hash Derivation):
  1. Input: raw PSK (typically 32 bytes).
  2. Nonce = struct.pack("<I", len(psk)) (4 bytes LE).
  3. Hash1 = SHA256(Nonce + b"123GOODIX") (32 bytes).
  4. Prefix = Hash1[0:16] with byte 15 low nibble replaced:
     prefix[15] = (hash1[15] & 0xf0) | (len(psk) & 0x0f)
  5. Hash2 = SHA256(Prefix + bytes(48) + WB_CONSTANT) (32 bytes).
     where WB_CONSTANT = 5cba6e25819518de2d53e96dc0347ab0 (16 bytes).
  6. AES Key = Hash2[0:16], AES IV = Prefix (16 bytes).
  7. Ciphertext = AES-128-CBC-Encrypt(Key, IV, PKCS#7(psk)).
     Since len(psk) == 32 (multiple of 16), PKCS#7 appends a 16-byte block of \\x10.
     Ciphertext length is 48 bytes.
  8. HMAC Key = Hash2 (full 32 bytes).
  9. HMAC = HMAC-SHA256(HMAC Key, Ciphertext) (32 bytes).
  10. Result = Prefix (16B) + Ciphertext (48B) + HMAC (32B) = 96 bytes (0x60).
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

WB_SALT = b"123GOODIX"
WB_CONSTANT = bytes.fromhex("5cba6e25819518de2d53e96dc0347ab0")

# Known test vector (32 zero bytes)
KNOWN_PSK = bytes(32)
KNOWN_OUTPUT = bytes.fromhex(
    "ec35ae3abb45ed3f12c4751f1e5c2cc05b3c5452e9104d9f2a3118644f37a04b"
    "6fd66b1d97cf80f1345f76c84f03ff30bb51bf308f2a9875c41e6592cd2a2f9e"
    "60809b17b5316037b69bb2fa5d4c8ac31edb3394046ec06bbdacc57da6a756c5"
)


# ============================================================================
# Modular Cryptographic Helper Functions (Requirement R4 & Ticket 63)
# ============================================================================

def derive_hash1(data_len: int) -> bytes:
    """Compute first SHA-256 hash over 4-byte LE length and salt."""
    nonce = struct.pack("<I", data_len)
    return hashlib.sha256(nonce + WB_SALT).digest()


def mutate_byte15(hash1: bytes, data_len: int) -> bytes:
    """Extract first 16 bytes of hash1 and replace byte 15 low nibble with data_len & 0x0F."""
    prefix = bytearray(hash1[:16])
    prefix[15] = (prefix[15] & 0xF0) | (data_len & 0x0F)
    return bytes(prefix)


def derive_hash2(prefix: bytes) -> bytes:
    """Derive second 32-byte hash from prefix, 48 zero bytes, and WB_CONSTANT."""
    hash2_input = prefix + bytes(48) + WB_CONSTANT
    return hashlib.sha256(hash2_input).digest()


def derive_keys(prefix: bytes):
    """Derive AES-128 key (16 bytes) and HMAC key (32 bytes) from prefix."""
    hash2 = derive_hash2(prefix)
    return hash2[:16], hash2


def compute_hmac(key: bytes, ciphertext: bytes) -> bytes:
    """Compute HMAC-SHA256 over ciphertext."""
    return hmac.new(key, ciphertext, hashlib.sha256).digest()


# Backward-compatible & test helper aliases
compute_hash1 = derive_hash1
_compute_hash1 = derive_hash1
mutate_hash1_byte15 = mutate_byte15
_mutate_prefix = mutate_byte15
derive_prefix = lambda l: mutate_byte15(derive_hash1(l), l)
compute_hash2 = derive_hash2
_derive_hash2 = derive_hash2
_derive_keys = derive_keys
_compute_hmac = compute_hmac


# ============================================================================
# Low-level AES-128-CBC Primitives
# ============================================================================

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
        try:
            res = subprocess.run(cmd, input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return res.stdout
        except subprocess.CalledProcessError as e:
            raise ValueError(f"OpenSSL decryption failed: {e.stderr.decode(errors='replace').strip()}") from e


# ============================================================================
# SecWhiteEncrypt & SecWhiteDecrypt
# ============================================================================

def sec_white_encrypt(data: bytes) -> bytes:
    """Encrypt data using Goodix SecWhiteEncrypt algorithm (AES-128-CBC + HMAC-SHA256)."""
    input_len = len(data)

    # Step 1 & 2: hash1 = SHA256(LE32(input_len) || "123GOODIX")
    hash1 = derive_hash1(input_len)

    # Step 3: prefix = hash1[0:16] with byte 15 low nibble replaced by input_len & 0x0F
    prefix = mutate_byte15(hash1, input_len)

    # Step 4: hash2 = SHA256(prefix || 48 zero bytes || WB_CONSTANT)
    aes_key, hmac_key = derive_keys(prefix)
    iv = prefix

    # Step 5: AES-128-CBC with PKCS#7 padding
    ciphertext = _aes_128_cbc_encrypt(aes_key, iv, data)

    # Step 6: HMAC-SHA256 over ciphertext with 32-byte hash2
    mac = compute_hmac(hmac_key, ciphertext)

    # Step 7: Output layout: 16B Prefix (IV) + Ciphertext + 32B HMAC
    return prefix + ciphertext + mac


def sec_white_decrypt(encrypted: bytes, expected_len: int = None) -> bytes:
    """Decrypt and verify Goodix WhiteBox encrypted payload.

    Args:
        encrypted: Encrypted blob (prefix || ciphertext || HMAC).
        expected_len: Optional expected plaintext length in bytes. If None,
                      inferred from wire length for canonical sizes (16, 32, 48, 64).

    Returns:
        Decrypted plaintext data.

    Raises:
        ValueError: If payload length is invalid, ciphertext is not a multiple of 16,
                    HMAC verification fails, or prefix mismatch is detected.
    """
    if len(encrypted) < 64:
        raise ValueError(f"Encrypted payload too short: {len(encrypted)} < 64")

    if expected_len is not None:
        min_wire = 16 + ((expected_len // 16) + 1) * 16 + 32
        if len(encrypted) < min_wire:
            raise ValueError(f"Encrypted payload too short: {len(encrypted)} < {min_wire}")

    prefix = encrypted[:16]
    ciphertext = encrypted[16:-32]
    expected_mac = encrypted[-32:]

    # Ticket 62: Reject ciphertext length not a multiple of 16 before decryption
    if len(ciphertext) % 16 != 0:
        raise ValueError(f"Ciphertext length {len(ciphertext)} is not a multiple of 16")

    # Determine plaintext length for prefix verification
    if expected_len is not None:
        data_len = expected_len
    else:
        ct_len_map = {32: 16, 48: 32, 64: 48, 80: 64}
        if len(ciphertext) in ct_len_map:
            data_len = ct_len_map[len(ciphertext)]
        else:
            data_len = prefix[15] & 0x0F

    # Verify prefix with actionable hex error message
    hash1 = derive_hash1(data_len)
    expected_prefix = mutate_byte15(hash1, data_len)
    if prefix != expected_prefix:
        raise ValueError(
            f"Prefix mismatch: expected {expected_prefix.hex()}, got {prefix.hex()}"
        )

    # Derive keys and verify HMAC
    aes_key, hmac_key = derive_keys(prefix)
    calc_mac = compute_hmac(hmac_key, ciphertext)
    if not hmac.compare_digest(calc_mac, expected_mac):
        raise ValueError("HMAC verification failed")

    return _aes_128_cbc_decrypt(aes_key, prefix, ciphertext)


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
    # 1. Authoritative Known Answer Test (KAT) with 32 zero bytes (Ticket 63)
    h1 = derive_hash1(32)
    assert h1.hex() == "ec35ae3abb45ed3f12c4751f1e5c2ccc412608157f318e4d4693589753d088f0", "KAT hash1 mismatch!"
    pfx = mutate_byte15(h1, 32)
    assert pfx.hex() == "ec35ae3abb45ed3f12c4751f1e5c2cc0", "KAT prefix mismatch!"
    h2 = derive_hash2(pfx)
    assert h2.hex() == "b7e7f234c4e98b9eef95bfe665bacad2b80a0a33ed2dde8a98be21f02942ad7f", "KAT hash2 mismatch!"
    k, hmac_k = derive_keys(pfx)
    assert k.hex() == "b7e7f234c4e98b9eef95bfe665bacad2", "KAT aes_key mismatch!"
    assert hmac_k.hex() == "b7e7f234c4e98b9eef95bfe665bacad2b80a0a33ed2dde8a98be21f02942ad7f", "KAT hmac_key mismatch!"

    # Anti-regression assert: single-hash derivation does not match aes_key
    assert k != h1[:16], "Single-hash derivation regression detected!"

    kat_enc = sec_white_encrypt(KNOWN_PSK)
    assert kat_enc == KNOWN_OUTPUT, "KAT vector encryption mismatch!"
    kat_dec = sec_white_decrypt(KNOWN_OUTPUT)
    assert kat_dec == KNOWN_PSK, "KAT vector decryption mismatch!"
    print("SecWhiteEncrypt KAT vector verified: PASS.")

    # 2. Multi-size round-trip verification (Tickets 63 & 64)
    for psk_len, exp_wire in [(16, 80), (32, 96), (48, 112), (64, 128)]:
        test_psk = bytes([i % 256 for i in range(psk_len)])
        wb = sec_white_encrypt(test_psk)
        assert len(wb) == exp_wire, f"Size {psk_len} produced wire length {len(wb)}, expected {exp_wire}"
        recovered = sec_white_decrypt(wb)
        assert recovered == test_psk, f"Round-trip mismatch for {psk_len}-byte PSK"
        print(f"Multi-size round-trip {psk_len}B (wire {exp_wire}B): PASS.")

    # 3. Canonical PSK and Payload chunking
    psk = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
    enc = sec_white_encrypt(psk)
    dec = sec_white_decrypt(enc)
    assert dec == psk, "Canonical PSK round-trip failed!"
    print("SecWhiteEncrypt canonical PSK round-trip verified: PASS.")

    payload = build_psk_write_payload(psk)
    chunks = chunk_psk_write_payload(payload)
    print(f"Full payload: {len(payload)} bytes, split into {len(chunks)} chunk(s).")
    for i, c in enumerate(chunks):
        tot, clen, coff = struct.unpack("<III", c[:12])
        print(f"  Chunk {i}: total={tot}, chunk_len={clen}, offset={coff}, wire_len={len(c)}")
