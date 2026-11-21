# Melon Plugins on the pedal

`melon-pedald` loads every Melon LV2 plugin it finds in `~/.lv2` (no list to edit).
`install-melon-plugins.sh` builds the missing ones natively on the Pi and installs them there.

    git clone https://github.com/rmenes/melon_plugins ~/melon_plugins   # once (or git pull)
    ./install-melon-plugins.sh --list     # installed / MISSING
    ./install-melon-plugins.sh            # build + install the missing ones
    sudo systemctl restart melon-pedald

- Build time: a few minutes per plugin once JUCE is built; **Rack** is much longer (NeuralAudio, built with `-j1`).
- Rebuild everything after a `git pull`: `./install-melon-plugins.sh --all`.
- A release zip from GitHub (`Melon-Plugins-<version>-Linux-arm64.zip`) can be installed instead: `./install-melon-plugins.sh --zip <file>`.

## Plugins that need more pedal work

| Plugin | Works on the pedal | Missing |
|---|---|---|
| Multi Delay, Shifter, Simple Gate | Yes (knobs, presets) | — |
| Tuner | Audio (pass-through / mute) and its settings | The note and cents are not sent to the host, so the LCD and app can't show them yet |
| Rack | Gate, EQ, levels, cabinet switches | Choosing the NAM/AIDA-X models and IRs: they are file paths in the plugin state, set from the desktop GUI |
