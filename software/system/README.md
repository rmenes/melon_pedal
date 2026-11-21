# Start the pedal at boot

Three systemd services start the pedal when the Pi powers up, in this order:

```
melon-jack (JACK on the Momix) ──► melon-modhost (mod-host, port 5555) ──► melon-pedald (controller)
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

## Everyday commands

| What | Command |
|---|---|
| Controller output (what you saw in the terminal) | `journalctl -u melon-pedald -f` |
| JACK / mod-host messages, xruns | `journalctl -u melon-jack -u melon-modhost -f` |
| Status | `systemctl status melon-jack melon-modhost melon-pedald` |
| Restart everything (e.g. after copying a new controller) | `sudo systemctl restart melon-pedal.target` |
| Stop, to run things by hand again | `sudo systemctl stop melon-pedal.target` |
| No more autostart | `sudo systemctl disable melon-pedal.target` |

After copying a new `melon-pedald` with `scp`, only the controller needs a restart: `sudo systemctl restart melon-pedald`.
