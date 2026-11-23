"""Wi-Fi setup from the app: status, scan, connect, forget (NetworkManager via nmcli).

Everything runs on one background thread, one job at a time, because connecting can
take 20-30 s and must never block the pedal (knobs, MIDI, presets keep working).
Results go to the apps as {"ev":"wifi", ...} through the callback.

Passwords are only passed to NetworkManager, never logged or sent back to the app.
The pedal's user needs permission to manage NetworkManager without sudo:
software/system/setup-wifi-control.sh installs a polkit rule for the `netdev` group.

  ev "wifi" fields (each message carries the ones that changed):
    status   {"device":"wlan0"|null,"connected":bool,"ssid","signal":0-100,"ip","hostname","user"}
             ip = IPv4 address on Wi-Fi; user = the account the pedal runs as (for "ssh user@ip")
    saved    ["Home", "Studio", ...]            networks the pedal remembers
    networks [{"ssid","signal","secure","known","active"}, ...]   after a scan
    busy     "Connecting to Studio…" | null
    result   {"ok":bool,"msg":"..."}            after connect / forget
"""
import queue
import getpass
import socket
import subprocess
import threading

NMCLI = "nmcli"


class WifiError(RuntimeError):
    pass


def split_terse(line):
    """Split one `nmcli -t` line: fields are separated by ':', and ':' / '\\' inside a field are escaped."""
    fields, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def nm(*args, timeout=15, check=True):
    try:
        r = subprocess.run([NMCLI, *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise WifiError("NetworkManager (nmcli) is not installed")
    except subprocess.TimeoutExpired:
        raise WifiError("NetworkManager did not answer in time")
    if check and r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        msg = msg[-1] if msg else f"nmcli failed ({r.returncode})"
        if "Not authorized" in msg or "Insufficient privileges" in msg:
            msg = "No permission to change Wi-Fi (run software/system/setup-wifi-control.sh on the pedal)"
        raise WifiError(msg.removeprefix("Error: "))
    return r.stdout


def wifi_device():
    for line in nm("-t", "-f", "DEVICE,TYPE,STATE", "device").splitlines():
        f = split_terse(line)
        if len(f) >= 3 and f[1] == "wifi":
            return f[0], f[2]
    return None, None


def visible(dev, rescan="no"):
    """[{"ssid","signal","security","active"}] strongest first, one entry per SSID."""
    out = nm("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
             "ifname", dev, "--rescan", rescan, timeout=30)
    best = {}
    for line in out.splitlines():
        f = split_terse(line)
        if len(f) < 4 or not f[1]:
            continue                      # hidden networks have no name
        try:
            sig = int(f[2])
        except ValueError:
            sig = 0
        n = {"ssid": f[1], "signal": sig, "security": f[3].strip(), "active": f[0].strip() == "*"}
        old = best.get(n["ssid"])
        if old is None or n["active"] or (sig > old["signal"] and not old["active"]):
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda n: (not n["active"], -n["signal"]))


def saved_profiles():
    """{connection name: ssid} for every saved Wi-Fi profile."""
    names = [f[0] for f in (split_terse(l) for l in nm("-t", "-f", "NAME,TYPE", "connection", "show").splitlines())
             if len(f) >= 2 and f[1] in ("802-11-wireless", "wifi")]
    profiles = {}
    for name in names:
        ssid = nm("-g", "802-11-wireless.ssid", "connection", "show", "id", name, check=False).strip()
        profiles[name] = ssid or name
    return profiles


def _user():
    try:
        return getpass.getuser()
    except Exception:
        return None


def status():
    dev, state = wifi_device()
    st = {"device": dev, "connected": False, "ssid": None, "signal": None, "ip": None,
          "hostname": socket.gethostname(), "user": _user()}
    if dev and state == "connected":
        st["connected"] = True
        active = next((n for n in visible(dev) if n["active"]), None)
        if active:
            st["ssid"], st["signal"] = active["ssid"], active["signal"]
        ips = nm("-g", "IP4.ADDRESS", "device", "show", dev, check=False).strip()
        st["ip"] = ips.split(" | ")[0].split("/")[0] if ips else None
    return st


class Wifi:
    def __init__(self, notify):
        self.notify = notify              # callback(dict) -> sends {"ev":"wifi", ...} to the apps
        self.jobs = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="wifi").start()

    # ---- called from the remote API (returns at once)
    def request(self, op, msg):
        self.jobs.put((op, dict(msg)))

    # ---- worker
    def _run(self):
        while True:
            op, msg = self.jobs.get()
            try:
                if op == "wifi_status":
                    self._send_status()
                elif op == "wifi_scan":
                    self._scan()
                elif op == "wifi_connect":
                    self._connect(str(msg.get("ssid", "")), msg.get("password"), bool(msg.get("hidden")))
                elif op == "wifi_forget":
                    self._forget(str(msg.get("ssid", "")))
            except WifiError as e:
                self.notify({"busy": None, "result": {"ok": False, "msg": str(e)}})
            except Exception as e:        # never let the worker die
                print(f"! wifi {op}: {e}")
                self.notify({"busy": None, "result": {"ok": False, "msg": f"{op}: {e}"}})

    def _send_status(self, **extra):
        msg = {"status": status(), "saved": sorted(set(saved_profiles().values()), key=str.lower)}
        msg.update(extra)
        self.notify(msg)

    def _scan(self):
        dev, _ = wifi_device()
        if not dev:
            raise WifiError("No Wi-Fi adapter found")
        self.notify({"busy": "Scanning…"})
        try:
            nets = visible(dev, rescan="yes")
        except WifiError:                 # "scanning not allowed right now": use the last results
            nets = visible(dev, rescan="auto")
        known = set(saved_profiles().values())
        self._send_status(busy=None, networks=[
            {"ssid": n["ssid"], "signal": n["signal"], "secure": bool(n["security"] and n["security"] != "--"),
             "security": n["security"], "known": n["ssid"] in known, "active": n["active"]} for n in nets])

    def _connect(self, ssid, password, hidden):
        if not ssid or len(ssid.encode()) > 32:
            raise WifiError("Network name must be 1 to 32 characters")
        if password is not None:
            password = str(password)
            if password == "":
                password = None
            elif not 8 <= len(password) <= 63:
                raise WifiError("Wi-Fi passwords have 8 to 63 characters")
        dev, _ = wifi_device()
        if not dev:
            raise WifiError("No Wi-Fi adapter found")
        self.notify({"busy": f"Connecting to {ssid}…", "result": None})
        print(f"wifi: connecting to {ssid!r} (app)")

        sec = ""
        if not hidden:
            match = next((n for n in visible(dev, rescan="auto") if n["ssid"] == ssid), None)
            if match is None:
                raise WifiError(f"{ssid} is not in range (scan again, or add it as a hidden network)")
            sec = match["security"]
        profiles = saved_profiles()
        existing = next((name for name, s in profiles.items() if s == ssid), None)

        if existing:
            if password:
                nm("connection", "modify", "id", existing, *self._security_args(sec, password))
            name, created = existing, False
        else:
            if password is None and sec and sec != "--":
                raise WifiError(f"{ssid} needs a password")
            name = ssid if ssid not in profiles else f"{ssid} (melon)"
            args = ["connection", "add", "type", "wifi", "ifname", dev, "con-name", name, "ssid", ssid,
                    "connection.autoconnect", "yes"]
            if hidden:
                args += ["802-11-wireless.hidden", "yes"]
            if password:
                args += self._security_args(sec, password)
            nm(*args)
            created = True

        try:
            nm("--wait", "40", "connection", "up", "id", name, timeout=50)
        except WifiError as e:
            if created:                   # don't keep a profile that doesn't work
                nm("connection", "delete", "id", name, check=False)
            nm("device", "connect", dev, check=False, timeout=40)     # back to a known network if any
            text = str(e)
            if "Secrets were required" in text or "802-1x" in text or "password" in text.lower():
                text = "Wrong password?"
            self._send_status(busy=None, result={"ok": False, "msg": f"Could not connect to {ssid}: {text}"})
            return
        st = status()
        where = f" · {st['ip']}" if st.get("ip") else ""
        print(f"wifi: connected to {ssid!r}{where}")
        self._send_status(busy=None, result={"ok": True, "msg": f"Connected to {ssid}{where}"})

    @staticmethod
    def _security_args(sec, password):
        # WPA3-only networks need SAE; WPA2 and WPA2/WPA3 mixed networks work with WPA-PSK
        mgmt = "sae" if ("WPA3" in sec and "WPA2" not in sec and "WPA1" not in sec) else "wpa-psk"
        return ["wifi-sec.key-mgmt", mgmt, "wifi-sec.psk", password]

    def _forget(self, ssid):
        names = [name for name, s in saved_profiles().items() if s == ssid]
        if not names:
            raise WifiError(f"{ssid} is not saved")
        for name in names:
            nm("connection", "delete", "id", name)
        print(f"wifi: forgot {ssid!r} (app)")
        self._send_status(busy=None, result={"ok": True, "msg": f"Forgot {ssid}"})
