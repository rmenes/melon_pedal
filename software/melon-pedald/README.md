# melon-pedald 0.1 (test version)

Controls one LV2 plugin in mod-host with a Livtra NexFoot (USB MIDI).
Standard library only - no pip packages needed.

| NexFoot | Turn | Press |
|---|---|---|
| A | parameter 1 of the page | bypass on/off |
| B | parameter 2 | previous page |
| C | parameter 3 | next page |
| D | parameter 4 | next plugin |

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
