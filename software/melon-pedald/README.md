# melon-pedald 0.4 (test version)

Controls a **multi-FX chain** of LV2 plugins in mod-host (up to 10 blocks in series, see
`docs/multifx-design.md`) with a Livtra NexFoot (USB MIDI), the LCD and the phone app.
Standard library only - no pip packages needed (`python3-jack-client` is optional, for the live DSP meter).

The knobs, the LCD and the app's Sound screen always work on the **selected block**.

| NexFoot | Turn | Press | Hold (0.7 s) |
|---|---|---|---|
| A | parameter 1 of the page | bypass the whole pedal | |
| B | parameter 2 | next page (wraps around) | **select the next block** |
| C | parameter 3 | **selected block on/off** | **save preset** |
| D | parameter 4 | next plugin in the selected block | **preset / plugin browser** |

**Browser:** turn A = move · press A = back · press B = presets / plugins · press D = load.
In the **plugins** tab: press D = replace the selected block · press **C = add as a new block**
(it goes to its category's place: Gate → Pitch/Synth → Comp → Drive → Amp → Cab → Mod → Delay → Reverb → EQ).
**Save:** turn A = cursor · turn B = letter · turn C = slot (24 slots, 4 banks of 6) · press D = save · press A = cancel.

If a knob does the wrong thing, check which CC it really sends with
`aseqdump -p "Nexfoot MIDI:1"` and pass them in A,B,C,D order: `--press-cc 21,25,26,27`, `--turn-cc 57,68,74,89`.
The NexFoot sends value 0 when a knob is pressed and 127 when it is released; for a controller that does the opposite, add `--press-high`.

Presets are kept in `~/.config/melon-pedald/presets.json` (change with `--presets`).
`--preset 3` starts with preset 3. The screen shows **EDITED** when you change a loaded preset.

Knobs "pick up" a parameter once they pass its current value (no jumps);
the terminal tells you which way to turn.

## Run on the Pi

Session 1 - JACK (Momix or iOne):

    jackd -d alsa -d hw:MomixCab -r 48000 -p 256 -n 3

Session 2 - mod-host in socket mode (not `-i`):

    unset DISPLAY
    mod-host -n -p 5555

Session 3 - the controller:

    cd ~/melon-pedald
    python3 -m melon_pedald --list          # plugins and parameters
    python3 -m melon_pedald                 # start (first Melon plugin)
    python3 -m melon_pedald --plugin chorus

Options: `--capture system:capture_2` (other input), `--midi-port "Nexfoot MIDI:1"`,
`--match ""` (all LV2 plugins, not just Melon), `-v` (show mod-host commands),
`--fake --stdin` (test without mod-host or controller).

## Multi-FX chain

- Every block is its own mod-host instance (`effect_0` … `effect_9`); the blocks are connected in series.
  Moving a block only changes the JACK connections. At start the controller removes instances left by an
  earlier run.
- Block on/off = mod-host's bypass of that instance. Global bypass (press A) bypasses every block.
- **DSP limit:** before a block is added (or the selected block gets another plugin), the predicted load is
  `1.1 + 1.1 × sum of the block costs` (blocks that are off count too). Over **85 %** the change is refused
  with a message (and a tip to set Melon NAM's Model Size to Light). Costs come from `dsp_bench.py`'s
  `plugin_costs.json` (`/data/plugin_costs.json`, else `~/plugin_costs.json`, or `--costs FILE`); plugins
  that were never benched count 10 %. Melon NAM: 41 % Full, 9 % Light, ~1 % without a model.
- With `python3-jack-client` installed the controller also reads the live JACK load (client `melon-dsp`):
  it is used for the limit too, shown in the app, and a block that causes overload or xruns within 1.5 s
  of being added is removed again. `--no-dsp-meter` turns it off.
- **Presets** (version 2) store the whole chain: plugins, values, files, on/off and the selected block.
  Version 1 presets load as a chain of one block. Loading a preset with the same plugins in the same order
  only sends the values (no gap); otherwise the chain is rebuilt.
- Test without a Pi: `python3 -m unittest tests/test_chain.py -v` (fake plugins and a fake mod-host).

## LCD

The pedal state goes to the `melon-display` service (`software/melon-display`), which draws it on
the 2" screen: plugin, page, the 4 knob parameters, value pop-up when a knob moves, BYPASS bar,
GraphicEQ band graph. Install that service once; then just run the controller as usual.
`--no-lcd` turns this off. If the display service isn't running, the controller works as before.

## Melon Tuner

Page 1 is the tuner screen: needle, note, cents and Hz, the strings of the selected tuning,
and the output state (**LIVE**, **MUTED** or **BYPASS**). Knob 1 turn = *Mute when engaged*,
press A = bypass (the tuner keeps reading in bypass). Push 2 = settings (tuning, reference,
threshold, smoothing, output). Defaults: chromatic, A4 = 440 Hz.

The reading comes from the plugin's read-only `readout` parameter (detected Hz), which mod-host
passes to its **feedback port** (`mod-host -f 5556`; the controller uses `--port` + 1,
change with `--feedback-port`). The log says `tuner: readings arriving from mod-host` once it works.

## Remote API (phone app over Bluetooth)

The controller listens on **127.0.0.1:5601** (local only) for apps: one JSON object per line.
The Bluetooth bridge `software/melon-ble` forwards the phone's lines to it; the web UI can use the same API later.
Every LCD update also goes to the connected apps, so knob turns show up on the phone and phone edits show
up on the LCD (with the value pop-up). After a phone changes a parameter on the current page, that knob
has to "pick up" the new value again. Protocol: top of `melon_pedald/remote.py`.
`--remote-port 0` turns it off. Test it on the Pi without a phone: `python3 ~/melon-ble/melon_remote_cli.py`
(chain commands: `plugins`, `add i [pos]`, `rm b`, `move b to`, `on b`, `off b`, `sel b`).
