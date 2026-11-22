# Melon Pedal — PoC enclosure (USB audio interface)

3D-printable box for the proof of concept: Raspberry Pi 4 + external USB audio interface, LCD, 4 encoders,
footswitch and LED in the top. Spec: project doc `04-poc-usb-interface.md`.

![render](render-poc-hero.png)

Concept renders: [hero](render-poc-hero.png) · [back](render-poc-back.png) · [top](render-poc-top.png) (`render_poc.py`, numpy + Pillow; the LCD shows `software/melon-display/preview/chain.png`; the USB interface is a generic stand-in). STL check: [preview](preview-poc.png).

| File | What |
|---|---|
| `melon-poc-shell.stl` | Top panel + 4 walls. **Print upside down** (top on the bed): every wall cut-out is open at the bottom, so no supports are needed |
| `melon-poc-plate.stl` | Bottom plate with the Pi 4 standoffs and vents. Print flat |
| `render_poc.py` | Concept renders (ray marcher, ~5 min per view at 1600 × 1000) |
| `make_poc_enclosure.py` | Generator: every size is a parameter at the top. `python3 make_poc_enclosure.py --preview` (numpy, scipy, matplotlib) |

**Outside:** 65 W × 120 D × 40 H mm (plate included). Inside 60.2 × 115.2 × 34.6 mm. Walls and top 2.4 mm, plate 3 mm.

## Layout
- **Top, front to back:** footswitch Ø12.2 (reinforcing ring underneath) · LED bezel Ø6.0 · 2.0" LCD window
  42 × 32 with a 1 mm locating pocket underneath for the module board (58.5 × 35.5) · 4 × EC11 Ø7.2 in a
  2 × 2 grid (28 mm across, 20 mm front to back; knobs 1–2 front row, 3–4 back row).
- **Pi 4:** 85 mm side along the depth, USB/Ethernet at the back, USB-C/micro-HDMI on the right, GPIO header
  along the left wall. Board on 3 mm standoffs.
- **Back wall:** open cut-out for the 4 USB ports + Ethernet (audio interface and boot drive plug in here).
- **Right wall:** open cut-out for USB-C power + both micro-HDMI; vents in the rear half.
- **Left wall and plate:** vents (wall slots are plain rectangles so they print without supports: their top is a 2.6 mm bridge) (plate slots under the SoC). No room for a fan: use a heatsink and check
  `vcgencmd measure_temp` under a full chain.

## Assembly
1. Melt **2 × M3 heat-set inserts** (M3 × 5.7, Ø4.0 hole) into the two front corner columns, from below.
2. Pi onto the plate: **2 × M2.5 × 6** from above through the Pi's front holes into the front standoffs.
3. Mount the footswitch, LED, encoders and LCD in the top and wire them to the GPIO header.
4. Lower the shell over the Pi (the cut-outs are open at the bottom, so the ports slide in).
5. From below: **2 × M3 × 8** into the inserts, **2 × M2.5 × 16** through the plate, the rear standoffs and
   the Pi's rear holes into the pillars that hang from the top. The screw holes are counterbored.

## Print
PETG or ASA (PLA softens near a warm Pi). 0.2 mm layers, 4+ walls, 5 top/bottom layers, 30–40 % infill.
Each part is several overlapping closed shells; PrusaSlicer, OrcaSlicer, Bambu Studio and Cura merge them
(Cura: *Union overlapping volumes* on, the default).

## Measure before printing
- **LCD module:** board size (pocket 58.5 × 35.5) and where the visible area sits on it (window centred by default).
- **LED bezel** hole (6.0) and **footswitch** thread (12.2).
- **Rear encoders:** their pins end about 2 mm above the Pi's USB ports. Trim or bend them and add Kapton tape.
- **EC11 anti-rotation tab:** snap it off (no slot is printed).
- **Inserts:** some kits want a 4.2 mm hole (`INSERT_HOLE`).

Change a value in `make_poc_enclosure.py` and run it again to regenerate the STLs.
