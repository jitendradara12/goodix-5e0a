# Goodix Driver TODOs & Deferred Items

These are the TODO and task comments originally stripped from `libfprint/drivers/goodixtls/` during the slop cleanup:

## Protocol & Architecture TODOs

1. **`libfprint/drivers/goodixtls/goodix.c:69`**
   ```c
   // TODO remove every GDestroyNotify
   ```
   *Context*: Historical note on simplifying callback memory ownership by removing `GDestroyNotify` parameters from send/receive functions.

2. **`libfprint/drivers/goodixtls/goodix.c:70`**
   ```c
   // TODO add cmd timeouts
   ```
   *Context*: Ensure every protocol command has a bounded watchdog timer so SSM doesn't hang if hardware drops a reply (partially completed with `GOODIX_TIMEOUT`).

3. **`libfprint/drivers/goodixtls/goodix.c:191`**
   ```c
   GUINT16_FROM_LE (*(guint16 *) (data + sizeof (guint8))), // TODO
   ```
   *Context*: Payload length decoding and unaligned memory access in packet header parsing.

4. **`libfprint/drivers/goodixtls/goodix.c:357`**
   ```c
   gboolean valid_checksum, valid_null_checksum; // TODO implement checksum.
   ```
   *Context*: Verify checksum calculation on incoming packet payloads.

5. **`libfprint/drivers/goodixtls/goodix.c:364`**
   ```c
   // TODO implement protocol assembling.
   ```
   *Context*: Multi-packet message reassembly when payload spans multiple USB packets.

6. **`libfprint/drivers/goodixtls/goodix.c:402`**
   ```c
   gboolean valid_checksum; // TODO implement checksum.
   ```
   *Context*: Incoming protocol message checksum verification.

7. **`libfprint/drivers/goodixtls/goodix.c:1113`**
   ```c
   // todo: work out why it always times out for this but not the python driver
   ```
   *Context*: Investigation note regarding timing differences in TLS establishment between the Python prototype and C driver.

---

## Ponytail / Shortcut Comments

1. **`goodix.c:130`**: `/* ponytail: NOP silence = buffer already empty */`
2. **`goodix.c:615`**: `// ponytail: fail loudly so the waiting SSM aborts instead of hanging`
3. **`goodix.c:654`**: `/* ponytail: flush, not a handshake — silence is success (see tolerant ... */`
4. **`goodix.c:1130`**: `// ponytail: reuse 2-byte helper for the 01 00 payload (goodix.py:611-622)`
5. **`goodix.h:28`**: `/* ponytail: NOP is a flush — the MCU is routinely silent on it ... */`
