#!/usr/bin/env python3
"""Talks to melon-pedald's remote API from a terminal on the Pi (no phone needed).

  python3 melon_remote_cli.py
  > set 3 -2.5        parameter 3 (0-based) to -2.5
  > bypass            toggle bypass          > bypass on / bypass off
  > page 2            knob page 3 on the pedal
  > plugin 4          load plugin 4          > preset 0   load preset slot 0 (= 1-01)
  > save 5 My Tone    save into slot 5
  > get               ask for everything again
  > {"op": ...}       any raw JSON line
Events from the pedal are printed as they arrive.
"""
import json
import socket
import sys
import threading

HOST, PORT = "127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 5601


def main():
    s = socket.create_connection((HOST, PORT))
    gen = [0]

    def reader():
        buf = b""
        while True:
            d = s.recv(65536)
            if not d:
                print("\n(connection closed)")
                break
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = json.loads(line)
                if "gen" in msg:
                    gen[0] = msg["gen"]
                if msg.get("ev") == "plugin":
                    print(f"< plugin {msg['name']} (gen {msg['gen']})")
                    for i, c in enumerate(msg["controls"]):
                        print(f"    {i:>2} {c['l']:<20} {c['min']} .. {c['max']} {c.get('u', '')} [{c['k']}]")
                else:
                    print("<", json.dumps(msg)[:300])

    threading.Thread(target=reader, daemon=True).start()

    def send(m):
        s.sendall((json.dumps(m) + "\n").encode())

    send({"op": "hello", "app": "cli", "proto": 1})
    for line in sys.stdin:
        w = line.strip().split(maxsplit=2)
        if not w:
            continue
        try:
            if w[0].startswith("{"):
                s.sendall(line.strip().encode() + b"\n")
            elif w[0] == "set":
                send({"op": "set", "gen": gen[0], "i": int(w[1]), "v": float(w[2])})
            elif w[0] == "bypass":
                send({"op": "bypass"} if len(w) == 1 else {"op": "bypass", "on": w[1] == "on"})
            elif w[0] == "page":
                send({"op": "page", "n": int(w[1])})
            elif w[0] == "plugin":
                send({"op": "load_plugin", "i": int(w[1])})
            elif w[0] == "preset":
                send({"op": "load_preset", "slot": int(w[1])})
            elif w[0] == "save":
                send({"op": "save_preset", "slot": int(w[1]), "name": w[2] if len(w) > 2 else ""})
            elif w[0] == "get":
                send({"op": "get", "what": "all"})
            else:
                print("? set i v | bypass [on|off] | page n | plugin i | preset slot | save slot name | get | {json}")
        except (IndexError, ValueError):
            print("? wrong arguments")


if __name__ == "__main__":
    main()
