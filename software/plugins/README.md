# Melon Plugins on the pedal

`melon-pedald` loads every Melon LV2 plugin it finds in `~/.lv2` (no list to edit).
`install-melon-plugins.sh` builds the missing ones natively on the Pi and installs them there.

    git clone https://github.com/rmenes/melon_plugins ~/melon_plugins   # once (or git pull)
    ./install-melon-plugins.sh --list     # installed / MISSING
    ./install-melon-plugins.sh            # build + install the missing ones
    sudo systemctl restart melon-modhost  # mod-host reads the installed plugins only at start

- Restart **melon-modhost**, not only melon-pedald: the controller rescans `~/.lv2` and lists a new plugin, but mod-host
  only knows the plugins that were installed when it started, and refuses the new one with **error -101** (invalid URI).
  Restarting melon-modhost also restarts the controller, which comes back to the same sound.
- Build time: a few minutes per plugin once JUCE is built.
- **Melon Rack is excluded from the pedal** (too heavy for the Pi 4). The script never builds it, skips it in release zips, and removes an old `Melon Rack.lv2` from `~/.lv2`. Amp and cab will come later from simpler Melon Plugins (NAM Loader, IR Loader).
- Rebuild everything after a `git pull`: `./install-melon-plugins.sh --all`.
- A release zip from GitHub (`Melon-Plugins-<version>-Linux-arm64.zip`) can be installed instead: `./install-melon-plugins.sh --zip <file>`.

## Plugins that need more pedal work

| Plugin | Works on the pedal | Missing |
|---|---|---|
| Multi Delay, Shifter, Simple Gate | Yes (knobs, presets) | — |
| Tuner | Audio (pass-through / mute) and its settings | The note and cents are not sent to the host, so the LCD and app can't show them yet |
