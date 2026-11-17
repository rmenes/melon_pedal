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

### Other possible later optimizations
- Width: a smaller compute board (CM4/CM5 or Pi Zero 2 W) could reach true Boss width (~73 mm).
- Combined custom HAT (codec + front-end + MIDI) to remove the HiFiBerry entirely.
