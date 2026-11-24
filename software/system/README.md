# Start the pedal at boot

Three systemd services start the pedal when the Pi powers up, in this order:

```
melon-jack (JACK on the chosen interface) ──► melon-modhost (mod-host, port 5555) ──► melon-pedald (controller)
                                                                     melon-display (screen) runs beside them
```

`melon-pedal.target` groups them, so one command starts, stops or restarts all of them.

- If the Momix appears late after boot, JACK waits up to 30 s for it.
- If one part crashes, it restarts after 2–3 s, and the parts that depend on it restart too (JACK restarts → mod-host → controller).
- If the NexFoot isn't plugged in, the controller retries every 3 s, so plugging it in later just works.
- JACK and mod-host run with real-time priority on CPU cores 2–3, and the CPU runs at full speed. The controller and the display use cores 0–1.

## Install

Copy this folder to the Pi (PowerShell):

```powershell
scp -r E:\melon_pedal\software\system rmenes@melon-pedal.local:~/melon-system
```

Stop anything you started by hand, then install:

```bash
pkill -f 'python3 -m melon_pedald'; pkill mod-host; pkill jackd
cd ~/melon-system && sudo bash install.sh
```

It expects the controller in `~/melon-pedald` (as now). Reboot once to check that everything comes up by itself: `sudo reboot`.

## Settings

`/etc/default/melon-pedal`: audio interface (`JACK_DEVICE=hw:MomixCab`), sample rate, buffer (`JACK_PERIOD=256`, `JACK_NPERIODS=3`) and extra controller options (`PEDALD_ARGS="--preset 1"`). After a change: `sudo systemctl restart melon-pedal.target`.

## Audio interface (automatic)

With `JACK_DEVICE=auto` in `/etc/default/melon-pedal`, the pedal uses any class-compliant USB audio interface:

- At start, `melon-audio select` picks the interface: the USB interface plugged in last, else the first USB one, else the HiFiBerry. Cards without an input (HDMI, headphone jack) are ignored.
- Plug in or remove an interface while the pedal runs: a udev rule (`90-melon-audio.rules`) re-checks, and restarts the pedal (a few seconds of silence) only if the choice changed.
- `AUDIO_PREFER=Sono,AMS22` sets an order when several are plugged in. A fixed `JACK_DEVICE=hw:MomixCab` still works.
- Per-interface buffer and ports: `/etc/melon-pedal/audio.d/<card id>.conf` (`PERIOD`, `NPERIODS`, `RATE`, `CAPTURE`, `PLAYBACK`). Examples are installed for the Momix, the HiFiBerry and the Audient Sono. Default: input 1, outputs 1 + 2.
- See what it found: `/usr/local/lib/melon-pedal/melon-audio list` (`*` marks the one in use).

**Limits:** switches on the interface itself can't be set by software. Turn **direct monitoring off** and **loopback off** (Zoom AMS), or mute the input in the interface's own mixer app (Audient Sono, set once from a Windows/Mac computer). Interfaces that need a vendor driver don't work.

## Everyday commands

| What | Command |
|---|---|
| Controller output (what you saw in the terminal) | `journalctl -u melon-pedald -f` |
| JACK / mod-host messages, xruns | `journalctl -u melon-jack -u melon-modhost -f` |
| Status | `systemctl status melon-jack melon-modhost melon-pedald` |
| Which audio interface is used | `/usr/local/lib/melon-pedal/melon-audio list` |
| Restart everything (e.g. after copying a new controller) | `sudo systemctl restart melon-pedal.target` |
| Stop, to run things by hand again | `sudo systemctl stop melon-pedal.target` |
| No more autostart | `sudo systemctl disable melon-pedal.target` |

After copying a new `melon-pedald` with `scp`, only the controller needs a restart: `sudo systemctl restart melon-pedald`.
