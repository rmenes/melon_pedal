# Melon Pedal — LCD GUI design (v0.1, 2026-11-20)

Design canvas (all screens, drawn at real 320×240 px, shown at 2×): https://claude.ai/artifact/7KPNGRSwvnVB6dZnkezoXJ · sources in [software/ui-design/](../software/ui-design/)

Display: 2.0" ST7789, used **landscape 320×240** (≈ 7.9 px/mm). **From hardware v0.5: 2.8" ILI9341, same 320×240** (≈ 5.6 px/mm, everything 1.4× larger on the panel; no layout change). Drawn by `melon-pedald`'s `display` module with Pillow, pushed over SPI ([software architecture §4](software-architecture.md#4-melon-pedald-the-pedal-controller)). **This doc supersedes software architecture §5 where they differ.**

---

## 1. Principles

1. **Corner = knob.** The four parameter tiles sit in the corner of the screen nearest their knob: **K1 top-left, K2 top-right, K3 bottom-left, K4 bottom-right** ([hardware §8.2](hardware-architecture.md#8-mechanical-layout)). Anything a knob does on a screen is labelled in the same corner or in the footer with the knob's number.
2. **Readable standing up.** Stage-critical items are ≥ 24 px (≈ 3 mm): preset name, BYPASS bar, value pop-up, tuner note. 12 px is the floor, used only for labels you read while bent over the pedal.
3. **One list pattern everywhere.** Menu, presets, plugins and settings all work the same: **K1 turn = move, K1 push = back, K4 push = open/load** (K4 turn = change value in Settings, K2 turn = bank in Presets).
4. **The footswitch never changes meaning.** Tap = bypass on every screen (and exits the tuner).
5. **Bypass state is unmistakable.** Full-width red bar, tiles dimmed to 45 %, preset number greyed.
6. **Dry signal is always explained.** Boot and plugin loading say that the relays are passing the dry guitar.

## 2. Screens

| # | Screen | Purpose / notes |
|---|---|---|
| 1 | **Play** | Header (bank, page dots, MIDI activity, Wi-Fi, CPU), preset band (number box, name 26 px, plugin · page), amber **EDITED** chip when values differ from the saved preset, 2×2 tiles. Tile = 270° arc with knob number inside + label + value + unit. Enum params show option dots instead of an arc |
| 2 | **Play — bypassed** | Red bar `BYPASS`, sub-line "Dry signal · relays in true bypass" |
| 3 | **Value pop-up** | ~1 s after a knob moves: label, value at 68 px, range bar with default tick. **Fine** (K3 held): amber `FINE ×10` chip, zoomed ruler with 0.1 steps |
| 4 | **GraphicEQ page** | 31-band graph (±12 dB, 3 px/dB), the 4 bands on the knobs highlighted, compact tiles with centre-zero bars. 8 pages |
| 5 | **Menu** | 3×2 grid: Presets, Plugins, Tuner, MIDI, Settings, System |
| 6 | **Presets** | 6 rows, ▶ marks the loaded preset, empty slots shown, bank in header (K2) |
| 7 | **Plugins** | Name + category + channel layout + control count, LOADED badge, hint to upload more at melon.local |
| 8 | **Loading** | Amber "DRY SIGNAL · LOADING" bar, progress, the swap steps from [software §3.3](software-architecture.md#3-audio-engine) |
| 9 | **Settings** | Input mode, output, MIDI channel/thru, footswitch hold, buffer, brightness, Wi-Fi, about |
| 10 | **Save preset** | Name editor (cursor box, character wheel) + 2×2 corner tiles: K1 cursor, K2 character, K3 slot, K4 push = save |
| 11 | **Tuner** | Note at 110 px, cents meter ±50 with ±3 ¢ in-tune zone, flat/sharp arrows, Hz; output muted; lime = in tune, amber = out |
| 12 | **MIDI learn** | Turn a knob to pick the parameter, move a MIDI control to bind; tiles show current CC mappings |
| 13 | **Boot** | Brand green background, melon logo, start-up checklist |

## 3. Tokens

| Token | Hex | Use |
|---|---|---|
| ground | `#0D1610` | background |
| surface | `#172A1F` | tiles, cards |
| line | `#2E4A39` | arc tracks, borders, idle dots |
| rind | `#1E3A2B` | boot screen (brand) |
| cream | `#F3ECD6` | main text |
| sage | `#93AC9A` | labels, units, hints |
| dim | `#7A9582` | pending items |
| lime | `#A6E07A` | values, selection (dark text on it), in tune |
| amber | `#FFB547` | edited, fine, loading, out of tune |
| bypass | `#C8262B` | BYPASS bar (white text) |
| flesh | `#FF7B8A` | logo only |

Fonts: **Fredoka** 500/600 (names, titles) and **Barlow Semi Condensed** 500–700 (numbers, labels). Both OFL; ship the TTFs in `software/melon-pedald/fonts/`.

Type scale (px): 110 tuner · 68 pop-up value · 26 preset name · 24 tile value · 17–18 list item · 15–16 list body · 13 secondary · 12 labels (minimum).

Layout grid: header 20–24 px · preset band 56 px · tiles 2×2 with 6 px gaps and 6 px margin · footer 22 px · corner radius 8 (tiles), 6 (rows), 12 (pop-up).

## 4. Implementation notes (Pillow)

- Draw at 320×240 RGB, convert to RGB565 for the ST7789. Arcs: draw at 2× and downscale (or use `ImageDraw.arc` on a 4× tile) for smooth edges.
- Cache rendered tiles; on a knob turn, redraw only that tile (or the pop-up) and push the dirty rectangle over SPI. Cap at ~30 fps.
- Value pop-up: show on first detent, hide 1 s after the last one.
- Tuner: needle smoothed (≈ 80 ms), redraw ~20 fps.
- Long names: ellipsis at the box width; no scrolling text on the Play screen.

## 5. Open points

- ~~Knob order~~ **Resolved 2026-11-20:** tiles follow the hardware layout (K1/K2 on top, K3/K4 below); software architecture §5.1 updated.
- Is the LCD window landscape in the lid? The design assumes yes.
- Footswitch hold default: next preset. Many players expect hold = tuner. Decide after first gigs; it's a Setting.
- "Melon Drive" and the preset names in the mock-ups are placeholders.
