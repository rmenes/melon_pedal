#!/usr/bin/env python3
"""Melon Pedal: pick the audio interface for JACK (any class-compliant USB interface or the HiFiBerry).

    melon-audio list                  show the sound cards that can be used (input + output)
    melon-audio select [--wait 30]    choose one and write /run/melon-pedal/audio.env (used by JACK and the controller)
    melon-audio hotplug               called by udev when a sound card is plugged in or removed

Choice, in this order:
  1. JACK_DEVICE in /etc/default/melon-pedal, if it is not "auto" (e.g. hw:MomixCab) and the card is present
  2. a card named in AUDIO_PREFER (comma separated card ids, e.g. "Sono,AMS22"), first one present
  3. the USB interface plugged in most recently (remembered in /run/melon-pedal/last-plugged)
  4. any other USB interface, then any other card with input and output (HiFiBerry)
Cards without an input (HDMI, the Pi's headphone jack) are ignored.

No interface at all after the wait: JACK runs on its "dummy" driver (MELON_CARD=none, silent), so mod-host,
the controller, the LCD and the Bluetooth app still work (e.g. to set up Wi-Fi). Plugging an interface in
later restarts the pedal on it (hotplug).

Per-interface settings: /etc/melon-pedal/audio.d/<card id>.conf, for example Sono.conf:
    PERIOD=128
    NPERIODS=2
    CAPTURE=system:capture_1
    PLAYBACK=system:playback_1,system:playback_2
Missing keys use JACK_RATE / JACK_PERIOD / JACK_NPERIODS from /etc/default/melon-pedal,
input 1 and outputs 1+2. Standard library only.
"""
import glob
import os
import re
import subprocess
import sys
import time

DEFAULTS = "/etc/default/melon-pedal"
CONF_DIR = "/etc/melon-pedal/audio.d"
RUN_DIR = "/run/melon-pedal"
ENV_OUT = os.path.join(RUN_DIR, "audio.env")
LAST = os.path.join(RUN_DIR, "last-plugged")


def read_kv(path):
    """KEY=value lines (shell style, quotes stripped); missing file -> {}."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def stream_channels(card_dir):
    """Max channel count per direction from a USB card's stream files: {'capture': n, 'playback': n}."""
    ch = {"capture": 0, "playback": 0}
    for path in glob.glob(os.path.join(card_dir, "stream*")):
        section = None
        try:
            lines = open(path).read().splitlines()
        except OSError:
            continue
        for line in lines:
            s = line.strip()
            if s.startswith("Playback:"):
                section = "playback"
            elif s.startswith("Capture:"):
                section = "capture"
            m = re.match(r"Channels:\s*(\d+)", s)
            if m and section:
                ch[section] = max(ch[section], int(m.group(1)))
    return ch


def cards():
    """Sound cards that have both an input and an output."""
    found = []
    try:
        text = open("/proc/asound/cards").read()
    except OSError:
        return found
    for m in re.finditer(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s*(.*)$", text, re.M):
        num, cid, desc = int(m.group(1)), m.group(2), m.group(3).strip()
        d = f"/proc/asound/card{num}"
        if not glob.glob(d + "/pcm*c") or not glob.glob(d + "/pcm*p"):
            continue
        usbid = ""
        try:
            usbid = open(d + "/usbid").read().strip()
        except OSError:
            pass
        ch = stream_channels(d) if usbid else {"capture": 2, "playback": 2}
        found.append({"num": num, "id": cid, "desc": desc, "usb": bool(usbid), "usbid": usbid,
                      "in": ch["capture"] or 2, "out": ch["playback"] or 2})
    return found


def card_of(device):
    """'hw:Sono' / 'hw:CARD=Sono,DEV=0' / 'hw:1' -> 'Sono' / '1'."""
    name = device.split(":", 1)[-1].split(",", 1)[0]
    return name.split("=", 1)[-1]


def choose(found, cfg):
    by_id = {c["id"]: c for c in found}
    by_num = {str(c["num"]): c for c in found}
    dev = cfg.get("JACK_DEVICE", "auto") or "auto"
    if dev != "auto":
        c = by_id.get(card_of(dev)) or by_num.get(card_of(dev))
        if c:
            return c, "set in JACK_DEVICE"
    for name in filter(None, (p.strip() for p in cfg.get("AUDIO_PREFER", "").split(","))):
        if name in by_id:
            return by_id[name], "AUDIO_PREFER"
    last = read_kv(LAST).get("CARD", "")
    if last in by_id:
        return by_id[last], "plugged in last"
    usb = [c for c in found if c["usb"]]
    if usb:
        return usb[0], "first USB interface"
    if found:
        return found[0], "only card with input and output"
    return None, ""


def settings(card, cfg):
    conf = read_kv(os.path.join(CONF_DIR, card["id"] + ".conf"))
    if not conf and card["usbid"]:
        conf = read_kv(os.path.join(CONF_DIR, card["usbid"].replace(":", "_") + ".conf"))
    playback_default = "system:playback_1,system:playback_2" if card["out"] >= 2 else "system:playback_1,system:playback_1"
    return {
        "JACK_DEVICE": f"hw:{card['id']}",
        "JACK_RATE": conf.get("RATE", cfg.get("JACK_RATE", "48000")),
        "JACK_PERIOD": conf.get("PERIOD", cfg.get("JACK_PERIOD", "256")),
        "JACK_NPERIODS": conf.get("NPERIODS", cfg.get("JACK_NPERIODS", "3")),
        "MELON_CAPTURE": conf.get("CAPTURE", "system:capture_1"),
        "MELON_PLAYBACK": conf.get("PLAYBACK", playback_default),
        "MELON_CARD": card["id"],
        "MELON_CARD_INFO": f"{card['desc']} ({card['in']} in / {card['out']} out)",
    }


def dummy_settings(cfg):
    """No interface: JACK's dummy driver (2 in / 2 out, no sound) keeps the rest of the pedal running."""
    return {
        "JACK_DEVICE": "dummy",
        "JACK_RATE": cfg.get("JACK_RATE", "48000"),
        "JACK_PERIOD": cfg.get("JACK_PERIOD", "256"),
        "JACK_NPERIODS": cfg.get("JACK_NPERIODS", "3"),
        "MELON_CAPTURE": "system:capture_1",
        "MELON_PLAYBACK": "system:playback_1,system:playback_2",
        "MELON_CARD": "none",
        "MELON_CARD_INFO": "No audio interface - plug one in",
    }


def write_env(values):
    os.makedirs(RUN_DIR, exist_ok=True)
    tmp = ENV_OUT + ".tmp"
    with open(tmp, "w") as f:
        for k, v in values.items():
            f.write(f'{k}="{v}"\n')
    os.chmod(tmp, 0o644)
    os.replace(tmp, ENV_OUT)


def cmd_list():
    cfg = read_kv(DEFAULTS)
    found = cards()
    if not found:
        print("No sound card with both an input and an output.")
        return 1
    chosen, why = choose(found, cfg)
    for c in found:
        mark = "*" if chosen and c["num"] == chosen["num"] else " "
        kind = f"USB {c['usbid']}" if c["usb"] else "built-in/HAT"
        print(f"{mark} hw:{c['id']:<16} {c['in']:>2} in / {c['out']:>2} out  {kind:<16} {c['desc']}")
    if chosen:
        s = settings(chosen, cfg)
        print(f"\n* = used ({why}): {s['JACK_RATE']} Hz, {s['JACK_PERIOD']} x {s['JACK_NPERIODS']}, "
              f"input {s['MELON_CAPTURE']}, output {s['MELON_PLAYBACK']}")
    return 0


def cmd_select(wait):
    cfg = read_kv(DEFAULTS)
    t0 = time.time()
    while True:
        found = cards()
        chosen, why = choose(found, cfg)
        dev = cfg.get("JACK_DEVICE", "auto") or "auto"
        # a fixed JACK_DEVICE that is not there yet: keep waiting for it (USB can be late at boot)
        if chosen and (dev == "auto" or why == "set in JACK_DEVICE" or time.time() - t0 >= wait):
            break
        if time.time() - t0 >= wait:
            write_env(dummy_settings(cfg))
            print(f"No usable audio interface after {wait} s (check 'aplay -l' and 'arecord -l'): "
                  "starting JACK without audio (dummy driver) so Bluetooth and Wi-Fi setup still work.")
            return 0
        time.sleep(1)
    s = settings(chosen, cfg)
    write_env(s)
    print(f"Audio interface: {s['JACK_DEVICE']} - {s['MELON_CARD_INFO']} [{why}] - "
          f"{s['JACK_RATE']} Hz, {s['JACK_PERIOD']} x {s['JACK_NPERIODS']}, "
          f"in {s['MELON_CAPTURE']}, out {s['MELON_PLAYBACK']}")
    return 0


def cmd_hotplug():
    """udev: remember a newly plugged USB card, and restart the pedal if the choice changed."""
    action = os.environ.get("ACTION", "")
    devpath = os.environ.get("DEVPATH", "")
    if action == "add" and devpath:
        try:
            cid = open(f"/sys{devpath}/id").read().strip()
            os.makedirs(RUN_DIR, exist_ok=True)
            with open(LAST, "w") as f:
                f.write(f"CARD={cid}\n")
        except OSError:
            pass
    active = subprocess.run(["systemctl", "is-active", "--quiet", "melon-jack.service"]).returncode == 0
    if not active:
        return 0  # boot, or the pedal was stopped by hand: start-jack.sh does the choosing
    current = read_kv(ENV_OUT).get("MELON_CARD", "")
    chosen, _ = choose(cards(), read_kv(DEFAULTS))
    if chosen and chosen["id"] == current:
        return 0
    if not chosen and current == "none":
        return 0  # already running without an interface (e.g. an HDMI card changed)
    subprocess.run(["logger", "-t", "melon-audio",
                    f"audio interface changed ({current or 'none'} -> {chosen['id'] if chosen else 'none'}), "
                    "restarting the pedal"])
    subprocess.run(["systemctl", "--no-block", "restart", "melon-pedal.target"])
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[1] == "list":
        return cmd_list()
    if argv[1] == "select":
        wait = 30
        if "--wait" in argv:
            wait = int(argv[argv.index("--wait") + 1])
        return cmd_select(wait)
    if argv[1] == "hotplug":
        return cmd_hotplug()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
