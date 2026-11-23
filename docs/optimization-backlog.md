# Melon Effects Pedal — Optimization backlog

Decision (2026-11-17): build the **v0.3 design as-is first** (~100 × 135 × 65 mm body, ~82 mm total height with knobs, HiFiBerry jacks kept). Optimize after the first build reveals the real challenges.

## Ideas parked for later

### Height reduction to Boss height (~58 mm total)
| Change | Saves |
|---|---|
| Desolder unused RCA + 3.5 mm jacks from the HiFiBerry DAC2 ADC Pro (audio is wired via headers) | ~8–10 mm |
| Low-profile knobs (~10 mm instead of ~15 mm) | ~5 mm |
| Tighten clearance between Pi/HAT stack and lid control board | ~8–10 mm |
| **Result** | 47 mm body + 10 mm knobs ≈ 58 mm |

Stack budget for the slim version: floor + standoffs + Pi PCB ~7 mm · HAT on 12 mm spacers ~20 mm · clearance ~3 mm · control board ~12 mm · lid ~3 mm.
Watch-out: less internal air, so verify Pi temperature under full plugin load (vents + optional 30 mm fan).

![Height comparison](images/height-comparison.png)

### Even lower: 40 mm body (checked 2026-11-17, not planned)
Possible only on paper, with ~1–2 mm margin: 2 mm aluminium plate, 3 mm Pi standoffs, HiFiBerry RCA + 3.5 mm jacks desoldered, a flat control board (~10.5 mm below the top). The LCD and knobs 1/3 sit over the HAT, knob 2 ~4 mm above the Pi USB stack. No room for the 30 mm fan; cooling relies on the aluminium plate. Comfortable 40 mm needs a lower stack (CM4/CM5 carrier or a combined custom HAT).
Enclosure: change `H_TOTAL`, `PLATE_T`, `PI_STANDOFF` in `hardware/enclosure/hifiberry-wedge/make_enclosure.py` (v0.2 wedge: `H_FRONT`, `H_BACK`, `PI_STANDOFF`) and check the cross-sections.

### Other possible later optimizations
- Width: a smaller compute board (CM4/CM5 or Pi Zero 2 W) could reach true Boss width (~73 mm).
- Combined custom HAT (codec + front-end + MIDI) to remove the HiFiBerry entirely.

### Automatic USB audio interface support (added 2026-11-23)
Goal: the pedal recognizes and uses any **class-compliant** USB audio interface automatically, with a manual override menu on the pedal LCD and in the Android app. Fits the current services (`melon-jack` → `melon-modhost` → `melon-pedald`); no architecture change.

**Automatic detection**
1. A udev rule notifies `melon-pedald` when a USB audio device is plugged in or removed. Cards are identified by ALSA name (e.g. `hw:CARD=AMS22`), not by card number, which changes between boots.
2. The daemon reads each card's input/output channel counts and supported sample rates from ALSA.
3. JACK can't switch devices while running, so the daemon restarts `melon-jack` → `melon-modhost`, then reloads the current plugin and preset. Expect a few seconds of dropout; the output is muted during the switch (no relays on the USB build).
4. Device priority: a newly plugged USB interface wins; with none, fall back to the HiFiBerry if present. If the active interface is unplugged, fall back the same way instead of leaving JACK dead.
5. Default routing: input 1 → plugin (mono), or inputs 1 + 2 in stereo mode; plugin → outputs 1 + 2.
6. Per-interface settings (ports, buffer size, periods) are saved in `/data`, keyed by USB vendor/product ID, and restored on reconnect. Needed because interfaces differ (Momix needed 256 × 3; HiFiBerry target 128 × 2).

**Manual menu (pedal LCD + Android app over BLE)**
- Settings → Audio: device, input channel(s), output pair, mono/stereo, buffer size.

**Known limits (to state in the user documentation)**
- Interface hardware switches can't be controlled by software (e.g. Zoom AMS DIRECT MONITOR, LOOPBACK, MUSIC/STREAMING, Hi-Z). The user must set them: direct monitor off, loopback off. Possible extra: warn when the dry input appears to leak into the output.
- Interfaces that need a vendor driver (not class-compliant) are not supported.
