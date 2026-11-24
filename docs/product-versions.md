# Melon Pedal — product versions (plan, 2026-11-24)

Three versions are planned, from the simplest to the most complete. Only V1 and V2 exist as designs today; V3 is a first sketch.

![Three versions to scale](images/three-versions.png)

| | V1 · Proof of concept | V2 · HiFiBerry wedge | V3 · Floor unit |
|---|---|---|---|
| Size | 65 × 120 × 40 mm | 100 × 135 mm, 40 → 65 mm high | ≈ 240 × 170 mm, 45 → 70 mm (estimate) |
| Audio | External USB interface (iOne, Zoom AMS-22/24, Audient Sono…) | HiFiBerry DAC2 ADC Pro + I/O board (buffers, relays, MIDI) | 6 in / 8 out multichannel board (option B), two balanced outputs |
| Screen | 2.0" ST7789 | **2.8" ILI9341 320×240** (v0.5) | 5" 800×480 |
| Controls | 4 encoders (2 × 2 at the back), 1 footswitch | 4 encoders (2 × 2 at the back), 1 footswitch | 4 encoders, 4 footswitches |
| Power | USB-C | 9 V pedal supply | 9 V supply **or battery** |
| Pi | Pi 4 | Pi 4 | **Pi 5** (multichannel board, 5" screen) |
| Docs | `04-poc-usb-interface.md`, `hardware/enclosure/usb-audio/` | `hardware-architecture.md`, `hardware/enclosure/hifiberry-wedge/` | this page |

## V3 decisions so far

**Audio board: option B, 6 in / 8 out.** Candidates (check availability before committing):
- **ezsound-6x8** (TI PCM3168, 6 in / 8 out, 96 kHz, isolated from the Pi; driver in Raspberry Pi OS). Raspberry Pi 5; was at the tester stage in late 2026. Best fit so far.
- **Audio Injector Octo** (Cirrus CS42448, 6 in / 8 out, TDM over the Pi's I2S). Older Kickstarter product; availability uncertain. The CS42448 chip itself has had sourcing problems.

**Channel plan (uses all 8 outputs):**

| | Inputs (6) | Outputs (8) |
|---|---|---|
| Main | Guitar (Hi-Z buffer) | Amp L / R (6.35 mm) |
| PA | | **Balanced L / R: male XLR + balanced 6.35 mm TRS per channel, same driver** |
| FX loop | Return L / R | Send L / R |
| Extra | AUX in L / R on **XLR/TRS combo jacks** (mic, line or a second instrument) | Headphones L / R |

- Balanced outputs: line driver per channel on the I/O board (DRV134 / THAT1646, or an op-amp differential stage), ground-lift switch. Combo jacks are always female XLR, so they go on the AUX inputs, not on the outputs (proposal 2026-11-24, to confirm).
- Not audio: 2 × expression pedal (I2C ADC), MIDI in/out, 9 V DC, USB-C for charging, optional USB-A for an external interface (the software already supports any class-compliant interface).
- **Back panel:** about 14 connectors do not fit in one row on 240 mm: two rows (the back is ~70 mm tall), some on a side panel, or a slightly wider box.

**Battery:** 4 × 18650 (2S2P, ≈ 44 Wh, ≈ 5 h), in a bay with a hatch in the floor, away from the Pi's heat, with a proper 2S charger/protection module (USB-C) and a temperature sensor. A battery monitor on I2C shows % on the screen and app and shuts down cleanly when low. See [battery options](images/battery-options.png) for why a battery doesn't fit V2 without a bigger box.

Concept renders: [`hardware/enclosure/v3-floor`](../hardware/enclosure/v3-floor/README.md).

**Next:** confirm the screen size (assumed 121 × 76 mm module, 108 × 65 mm visible), the audio board, and the back-panel layout; then a first enclosure generator like V2's.
