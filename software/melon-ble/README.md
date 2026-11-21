# melon-ble — Bluetooth LE bridge for the phone app

Lets the **Melon Pedal Android app** (`software/android-app`) edit the pedal over Bluetooth.
It advertises as **"Melon Pedal"**, offers one GATT service and moves JSON lines between the phone and
`melon-pedald`'s remote API (127.0.0.1:5601). It does not interpret the messages, so new app features
only need changes in `melon-pedald` and the app.

```
Android app ──BLE──► melon-ble (BlueZ, D-Bus) ──TCP 127.0.0.1:5601──► melon-pedald ──► mod-host
            ◄─notify─                          ◄── events (knobs, presets…) ──
```

| | UUID | Properties |
|---|---|---|
| Service | `6d656c6f-6e70-6564-616c-000000000000` | |
| RX (phone → pedal) | `6d656c6f-6e70-6564-616c-000000000001` | write, write without response |
| TX (pedal → phone) | `6d656c6f-6e70-6564-616c-000000000002` | notify |

Messages are JSON lines ending in `\n`. A line may be split across several BLE packets
(packet size = MTU − 3; the app asks for MTU 517).

## Install on the Pi

1. Copy this folder to the Pi (e.g. `~/melon-ble`) and update `~/melon-pedald` with the new `remote.py`
   and `__main__.py`, then restart the controller: `sudo systemctl restart melon-pedald`.
2. `cd ~/melon-ble && sudo bash install.sh` (installs `bluez python3-dbus python3-gi`, adds you to the
   `bluetooth` group, starts the service with the pedal).
3. Check: `journalctl -u melon-ble -f` should show *GATT service registered* and *advertising as "Melon Pedal"*.

Test without the phone (talks to the controller directly):
`python3 ~/melon-ble/melon_remote_cli.py` → type `bypass`, `set 0 0.5`, `preset 0`, …

Test the Bluetooth side before the app is built: any BLE app such as **nRF Connect** — connect to
"Melon Pedal", enable notifications on TX, write `{"op":"hello"}` plus a newline (hex `0A`) to RX.

## Notes

- Runs on cores 0–1 at lower priority, away from the audio cores.
- If `bluetoothd` or `melon-pedald` restarts, the bridge re-registers / reconnects by itself, and a
  connected phone gets a fresh copy of the pedal state.
- **Security (v1):** any phone in range can connect and change the sound, like most BLE pedals' apps.
  Planned: pairing with a 6-digit code shown on the pedal's LCD (BlueZ agent with `DisplayOnly`
  capability + `encrypt-write` on RX).
- Wi-Fi and Bluetooth share the Pi 4's radio. Both work together, but keep Wi-Fi power saving off
  (already in the system setup).
