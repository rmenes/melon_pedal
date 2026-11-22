# melon-display — the pedal's LCD GUI

Draws the screens from [docs/lcd-gui-design.md](../../docs/lcd-gui-design.md) on the 2.0" ST7789 (320×240 landscape). It runs as its own systemd service. The controller sends it the current state as small JSON messages, and the screen updates within ~50 ms. If the display service stops or crashes, the controller and the audio keep running.

```
controller (knobs, mod-host, presets) ──JSON over UDP 127.0.0.1:5600──► melon-display ──SPI──► ST7789
```

**Working now:** preset and plugin browser (`screen="list"`), save preset (`screen="save"`), Play screen (4 tiles in the knob corners, preset band, EDITED chip, header with bank / page dots / MIDI / CPU, **chain strip** for multi-FX presets: one chip per block, lit = on, dim = off, cream frame = the block on the knobs), bypass state, value pop-up (+ fine adjust), GraphicEQ page (band graph + compact tiles), boot screen, test pattern.
Previews (rendered by `--png`, with a stand-in font): [play](preview/play.png) · [bypass](preview/bypass.png) · [pop-up](preview/popup.png) · [fine](preview/fine.png) · [enum](preview/popup-enum.png) · [GraphicEQ](preview/eq.png) · [chain](preview/chain.png) · [chain bypassed](preview/chain-bypass.png) · [boot](preview/boot.png) · [test](preview/test.png)

**Later:** menu, settings, tuner, MIDI learn. They're in the design canvas but need controller features first.

## 1. Install on the Pi

From Windows (PowerShell), copy the folder to the Pi (use your Pi user name):

```powershell
scp -r E:\melon_pedal\software\melon-display <user>@melon-pedal.local:~/
```

On the Pi:

```bash
cd ~/melon-display
sudo bash install.sh
```

It installs the Python packages, enables SPI (asks for a reboot the first time), downloads the Fredoka and Barlow Semi Condensed fonts, and starts the `melon-display` service. The screen shows the **boot screen** ("Waiting for controller") until the controller sends its first state.

Run `sudo bash install.sh` again after copying a newer version.

Useful commands:

```bash
systemctl status melon-display         # is it running?
journalctl -u melon-display -f         # its log (bad messages are reported here)
sudo systemctl restart melon-display
```

## 2. Check the picture

Stop the service and show the test pattern:

```bash
sudo systemctl stop melon-display
cd /opt/melon-display && python3 -m melon_display --test
```

- The green arrow should point to the **back edge** (jacks). If it points to the front, use `--rotation 270`.
- Red / green / blue bars must look right. Red and blue swapped → add `--bgr`. Colours look like a photo negative → add `--no-invert`.
- Noise or stripes → lower the SPI speed, e.g. `--spi-hz 24000000`.

Try options on the command line, then put the ones that work into `/etc/default/melon-display` and run `sudo systemctl start melon-display`.

`python3 -m melon_display --demo` moves fake knobs (no controller needed). `python3 -m melon_display --png out/` renders sample screens to PNG files on any computer, without the LCD.

> Only one program can drive the LCD. If your controller or an old test script also writes to the display, stop that part first.

## 3. Connect the controller

Copy `melon_display/client.py` next to the controller (standard library only), or add `/opt/melon-display` to `sys.path`.

```python
from client import Display          # or: from melon_display.client import Display
lcd = Display()

# when a preset or plugin is loaded, or the page changes: send the whole state
lcd.update(
    bank="BANK 1",
    preset={"number": "01", "name": "Clean Sparkle", "edited": False},
    plugin="Melon GraphicEQ",
    page=1, pages=8,
    params=[   # the 4 parameters on the knobs, in knob order (K1, K2, K3, K4); None = empty tile
        {"label": "125 Hz", "value": 4.5, "min": -12, "max": 12, "unit": "dB", "default": 0},
        {"label": "160 Hz", "value": 3.0, "min": -12, "max": 12, "unit": "dB", "default": 0},
        {"label": "200 Hz", "value": -1.5, "min": -12, "max": 12, "unit": "dB", "default": 0},
        {"label": "250 Hz", "value": -3.0, "min": -12, "max": 12, "unit": "dB", "default": 0},
    ],
)

# every time a knob (or MIDI CC / web slider) changes a value
lcd.param(0, 4.6)                   # tile 0 = knob 1; also shows the value pop-up for 1 s

lcd.bypass(True)                    # footswitch
lcd.fine(True)                      # knob 3 held: fine-adjust pop-up
lcd.update(cpu=23, midi=True)       # header extras (optional)
```

Messages are fire-and-forget: `Display` never blocks and never raises, even if the service isn't running.

### Parameter fields

| Field | Meaning |
|---|---|
| `label`, `value`, `min`, `max` | required |
| `unit` | `dB`, `Hz` (shown as kHz above 1000), `%`, `ms`… |
| `default` | shows the default tick in the pop-up |
| `kind` | `float` (default), `int`, `enum` (needs `options`), `toggle` |
| `options` | enum labels, e.g. `["Sym", "Asym", "Fuzz"]`; `value` is the index |
| `log` | `true` for frequency-type parameters (arc and bar move logarithmically) |
| `decimals` | override the automatic number of decimals |
| `text` | preformatted value (send it with `param(i, v, text="…")`) |
| `band` | GraphicEQ only: band index, so the graph follows the knob |

These fields come straight from the plugin's LV2 metadata (name, minimum, maximum, default, units, `lv2:enumeration`, `lv2:integer`, `lv2:toggled`, `pprops:logarithmic`). The controller's catalog already reads them.

### GraphicEQ page

Add a `graph` for plugins that are best shown as a curve. The graph replaces the big preset band, and the tiles become compact:

```python
lcd.update(
    graph={"values": gains_31, "min": -12, "max": 12,
           "highlight": [8, 11],                            # bands on the knobs (first, last)
           "labels": [[0, "20"], [7, "100"], [17, "1k"], [27, "10k"]]},
    graph_note="GraphicEQ · bands 9–12",
    params=[{... "band": 8}, {... "band": 9}, {... "band": 10}, {... "band": 11}],
)
lcd.update(graph=None)              # back to the normal play screen
```

### Other keys for `update`

`screen` (`"play"`, `"boot"`, `"test"`), `bypass_note` (sub-line when bypassed, default "Dry signal · effect bypassed"), `boot={"steps": [["Audio", "ok"], ["Plugin host", "wait"]], "note": "…"}` (status `ok` / `wait` / `fail` / `pending`).

## Files

| File | Job |
|---|---|
| `melon_display/st7789.py` | SPI driver (spidev + gpiozero), RGB565 conversion |
| `melon_display/ui.py` | Screen drawing with Pillow (design tokens, fonts, tiles, pop-up, graph) |
| `melon_display/__main__.py` | Service: UDP listener, state, redraw at most 30 fps; `--test`, `--demo`, `--png` |
| `melon_display/client.py` | Client for the controller |
| `install.sh`, `melon-display.service`, `melon-display.default` | Installation on the Pi |
