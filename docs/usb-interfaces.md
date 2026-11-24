# Melon Pedal — USB audio interfaces (PoC / USB-audio build)

Re-checked 2026-11-23 against the Zoom manuals. Status: **decision pending** between the Zoom AMS-22 and AMS-24. The PreSonus AudioBox iOne remains the current PoC interface; the HiFiBerry DAC2 ADC Pro stays the target for the final build.

## Requirements (lesson from the Momix, 2026-11-21)
The Momix's direct monitoring can't be switched off, so the dry guitar always leaks into the output, and its input clips. Any interface for the pedal must have:
1. **Direct monitoring that can be turned off** (hardware switch preferred).
2. **A real Hi-Z guitar input** with enough headroom (≥ +8 dBu).
3. **Class-compliant USB** (works with iPad/phone without drivers → ALSA sees it).
4. Ideally **stereo 1/4" line outputs** at a usable level.

## Candidates
| Interface | Size | Direct monitor | Guitar input | Outputs | Verdict |
|---|---|---|---|---|---|
| PreSonus AudioBox iOne | — | — | Hi-Z | Stereo | Current PoC interface |
| Momix | — | **Always on** | Clips | — | Rejected |
| IK iRig HD X | very small | On headphone out (unclear if it can be disabled) | 1 MΩ, +9 dBu | **Mono** 1/4" amp out (−2 dBu, 3.3 kΩ) + 3.5 mm phones | Skipped: mono out, unclear monitoring |
| **Zoom AMS-22** | 68 × 57.7 × 46 mm, 85 g | Hardware switch | Combo Mic/Hi-Z (**1 MΩ**, +11 dBu) | 2 × impedance-balanced 1/4" TRS L/R, **−2 dBu** max (+ separate headphone out) | **Candidate:** smallest, best guitar input; output level close to the v0.4 build's |
| **Zoom AMS-24** | 94.5 × 74 × 46 mm, 134 g | Hardware switch | Hi-Z switch on input 1 (330 kΩ, +8.5 dBu) | 2 × impedance-balanced 1/4" TRS L/R, **+10 dBu** max (+ 2 headphone outs) | **Candidate:** pick it if the pedal will feed line-level gear (FX return, mixer, FRFR) |
| Focusrite Scarlett Solo 4th Gen | ~ iOne size | Hardware button | Hi-Z | Stereo line | Best Linux support (scarlett2 driver, kernel ≥ 6.8), not compact |
| Arturia MiniFuse 1 | 154 × 100 × 43 mm | Button | Hi-Z | 2 × balanced 1/4" | Not compact |

## AMS-22 vs AMS-24
- **Guitar input:** AMS-22 is better: 1 MΩ / +11 dBu vs 330 kΩ / +8.5 dBu (330 kΩ may cost a little top end with passive pickups; a buffered pedal in front fixes it).
- **Outputs:** both have 2 × impedance-balanced 1/4" TRS L/R outputs (100 Ω) plus headphone jacks. Maximum level at 0 dBFS: **AMS-24 +10 dBu, AMS-22 −2 dBu** (12 dB less). The −2 dBu is the AMS-22's TRS L/R outputs, not its headphone out (20 mW + 20 mW into 32 Ω).
- **Gain staging:** at unity gain the clean ceiling is the lower of the input and output limits: about −2 dBu on the AMS-22, +8.5 dBu on the AMS-24. Hard picking on hot pickups can pass −2 dBu, so with the AMS-22 set the level a few dB under the dry guitar. The AMS-22 is weak into line-level gear (+4 dBu nominal).
- **Context from v0.4:** the output buffer divides the HiFiBerry output by 4 (−12 dB), about −3.5 dBu max (assuming the PCM5122's 2.1 V RMS full scale). So the final build has about the same output ceiling as the AMS-22. For more headroom in v0.4, change that divider (e.g. ÷2 → about +3 dBu).
- **Same on both:** USB Audio Class 2.0 (driver only on Windows), 24-bit/96 kHz, EIN −120 dBu, hardware DIRECT MONITOR and LOOPBACK switches, USB bus power plus a separate USB-C DC 5 V port.
- **Power:** AMS-22 170 mA (1.8 W max); AMS-24 380 mA (5 W max), also runs on 2 × AA. Both fit the Pi 4's USB budget with the boot drive.
- **AMS-24 only:** second combo input (mic/line, no Hi-Z), stereo link, 4 playback channels (Headphone B separate in MUSIC mode), MUSIC/STREAMING switch.
- **AMS-22 only:** 3.5 mm stereo line in (fixed gain). The manual doesn't say whether it reaches USB.
- **Price (US list, 2026):** AMS-22 ~US$100, AMS-24 ~US$150.
- **Size:** both are 46 mm tall, so the interface sits next to the pedal rather than inside a 40 mm PoC box.
- **Verdict:** into the front of a guitar amp both work. AMS-22 if size matters (and it has the better guitar input); AMS-24 if the output will feed line-level gear.

## Acceptance test on the Pi (either model)
Neither is confirmed on a Raspberry Pi yet; buy from a shop that accepts returns.
1. `aplay -l` and `arecord -l` both list it.
2. JACK starts at 48 kHz, 128 frames × 3 periods, no xruns over a few minutes of playing.
3. Switches: **LOOPBACK off** (when on, the Pi's playback is mixed back into its own input → feedback loop through the plugins), 48 V off. AMS-24 only: **MUSIC** mode and the Hi-Z switch on GUITAR.
4. Direct monitoring **off** → only the processed signal at the outputs (plugin bypassed vs. a clearly audible effect). The manuals don't spell out the OFF behaviour, so this check matters.
