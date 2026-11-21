# melon-pedald 0.2 (test version)

Controls one LV2 plugin in mod-host with a Livtra NexFoot (USB MIDI).
Standard library only - no pip packages needed.

| NexFoot | Turn | Press | Hold (0.7 s) |
|---|---|---|---|
| A | parameter 1 of the page | bypass on/off | |
| B | parameter 2 | next page (wraps around) | |
| C | parameter 3 | previous plugin | **save preset** |
| D | parameter 4 | next plugin | **preset / plugin browser** |

**Browser:** turn A = move · press A = back · press B or C = presets / plugins · press D = load.
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

## LCD

The pedal state goes to the `melon-display` service (`software/melon-display`), which draws it on
the 2" screen: plugin, page, the 4 knob parameters, value pop-up when a knob moves, BYPASS bar,
GraphicEQ band graph. Install that service once; then just run the controller as usual.
`--no-lcd` turns this off. If the display service isn't running, the controller works as before.

## Remote API (phone app over Bluetooth)

The controller listens on **127.0.0.1:5601** (local only) for apps: one JSON object per line.
The Bluetooth bridge `software/melon-ble` forwards the phone's lines to it; the web UI can use the same API later.
Every LCD update also goes to the connected apps, so knob turns show up on the phone and phone edits show
up on the LCD (with the value pop-up). After a phone changes a parameter on the current page, that knob
has to "pick up" the new value again. Protocol: top of `melon_pedald/remote.py`.
`--remote-port 0` turns it off. Test it on the Pi without a phone: `python3 ~/melon-ble/melon_remote_cli.py`.
