# Goodix 27c6:5e0a

Reverse-engineered host driver for the Goodix fingerprint sensor in some Realme Book laptops, built to become an upstream `libfprint` image driver.

## Language

### Sensor and firmware

**Sensor**:
The Goodix USB fingerprint device as seen by the host.
_Avoid_: scanner, reader

**MCU**:
The microcontroller on the sensor that runs the firmware and answers commands.
_Avoid_: chip (means the silicon, not the firmware actor)

**ChicagoH**:
The firmware and configuration family this sensor unit belongs to.
_Avoid_: 52xD (a different, older family used only as a prototype reference)

**Provisioning**:
One-time setup data uploaded to the MCU so later captures arrive at full size.
_Avoid_: calibration (reserved below for the 511-family optical step this sensor skips)

**OTP priming**:
An activation read that wakes the MCU security registers before the encrypted session starts.
_Avoid_: OTP calibration, OTP write

### Touch detection

**FDT DOWN**:
The MCU command that asks whether a finger is present.
_Avoid_: touch interrupt, touch wait

**FDT UP**:
The MCU command pair that confirms the finger has lifted.
_Avoid_: release interrupt

**Channel energy**:
The touch metric summed across the FDT reply channels; the sole gate for real touch.
_Avoid_: status byte (never used for gating), threshold heuristic

**Touch gating**:
Refusing to capture until channel energy proves a real finger is present.
_Avoid_: polling loop, noise gate

**Empty air**:
The sensor untouched or barely touched; must yield silence, never a template.
_Avoid_: ambient noise, weak print

### Frames and images

**Wire frame**:
The full decrypted byte blob delivered per capture, including padding and footer.
_Avoid_: image (reserved for the processed result), declen (the length measurement, not the thing)

**Canonical layout**:
The proven wire structure of eighty blocks with a fixed active prefix and zero padding plus a short footer.
_Avoid_: contiguous dump, strided columns (both falsified predecessors)

**Raster geometry**:
The natural pixel grid the wire blocks decode into before any scaling.
_Avoid_: scaled image, transposed layout

**Image pipeline**:
Local-contrast flattening plus upscaling that turns the raw raster into the grayscale image handed to the matcher.
_Avoid_: squashing, demosaicing (older pipeline stages, retired)

### Matching

**Minutiae**:
Ridge endings and bifurcations extracted on the host from a captured image.
_Avoid_: template (on-chip storage, which this sensor does not do)

**Bozorth3 score**:
The host match score of a probe image against one gallery print, compared against the match threshold.
_Avoid_: confidence, similarity

**Gallery**:
The enrolled prints stored on the host; a probe is compared against each entry.
_Avoid_: template store

**Probe**:
The single fresh capture being enrolled or verified.
_Avoid_: sample, frame

**Enrollment floor**:
The minimum minutiae count for accepting a touch into the gallery; faint touches are retried, never stored.
_Avoid_: quality threshold (overloaded with the match threshold)

### Sessions and transport

**Activation session**:
The ordered bring-up from flush through reset, identification, OTP priming, firmware check, provisioning, and encrypted-session establishment.
_Avoid_: init sequence, handshake (one step of it)

**Scan session**:
One touch-gated capture cycle from session check through finger-down, image read, and finger-up release.
_Avoid_: verification (the match decision that follows it)

**TLS-PSK transport**:
The encrypted channel negotiated with a pre-shared key before any capture.
_Avoid_: TLS handshake (one step), POV (a retired provisioning handshake this sensor ships without)

### System integration

**Device claim**:
Exclusive D-Bus ownership of the sensor by one authentication client at a time.
_Avoid_: lock, session

**Instant release**:
Completing the scan session and reporting finger lift immediately after a verification capture, instead of waiting on physical lift.
_Avoid_: fast path, low latency mode

### Evidence verdicts

**Frozen**:
Proven on hardware and not to be re-litigated without new journal-backed reason.
_Avoid_: done, stable

**Verified**:
Proven on deployed-driver hardware runs with pasted journal evidence.
_Avoid_: tested (the hermetic suite alone never verifies)

**Superseded**:
Replaced by a successor ticket; its instructions must not be followed.
_Avoid_: closed, old

**Falsified**:
Disproven on hardware; the hypothesis is dead.
_Avoid_: failed, buggy
