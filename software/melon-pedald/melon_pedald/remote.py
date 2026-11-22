"""Remote-control API for apps: the Bluetooth bridge (melon-ble) today, the web UI later.

JSON lines over TCP, local only (127.0.0.1:5601). One JSON object per line.

  app -> pedal   {"op": ...}
    hello        {"op":"hello","app":"android","proto":1}   -> hello, plugins, presets, plugin, state
    get          {"op":"get","what":"all"|"state"|"plugin"|"plugins"|"presets"}
    set          {"op":"set","gen":3,"i":5,"v":-2.5}        parameter i of the selected block's plugin
    bypass       {"op":"bypass","on":true}                   ("on" missing = toggle)
    page         {"op":"page","n":2}                         knob page on the pedal (0-based)
    load_plugin  {"op":"load_plugin","i":4}                  put plugin i into the selected block
    add_block    {"op":"add_block","i":4,"pos":2}            add plugin i as a new block (pos missing =
                                                             its category's place in the chain)
    remove_block {"op":"remove_block","b":3}                 blocks are 0-based positions in the chain
    move_block   {"op":"move_block","b":3,"to":1}
    block_on     {"op":"block_on","b":3,"on":false}          ("on" missing = toggle)
    select_block {"op":"select_block","b":3}                 the block on the knobs / Sound screen
    load_preset  {"op":"load_preset","slot":0}               0-23
    save_preset  {"op":"save_preset","slot":0,"name":"Crunch"}
    lib_list     {"op":"lib_list","gen":3,"i":8,"folder":"Marshall"}  folder of a library control ("" = top)
    set_file     {"op":"set_file","gen":3,"i":8,"path":"Marshall/JCM800.nam"}   path null = no file
    wifi_status  {"op":"wifi_status"}                        -> ev "wifi" (status, saved)
    wifi_scan    {"op":"wifi_scan"}                          -> ev "wifi" (busy, then networks)
    wifi_connect {"op":"wifi_connect","ssid":"Studio","password":"...","hidden":false}
    wifi_forget  {"op":"wifi_forget","ssid":"Studio"}

  pedal -> app   {"ev": ...}
    hello        {"ev":"hello","proto":1,"name":"Melon Pedal","version":"0.3"}
    plugins      {"ev":"plugins","list":[{"i","name","uri","n"}],"current":i}
    presets      {"ev":"presets","bank_size":6,"slots":[null | {"name","plugin_name","plugin"}]}
    plugin       {"ev":"plugin","gen":3,"i":4,"name","uri","controls":[{"l","min","max","d","u","k","log","o"}]}
                 k = "float" | "int" | "toggle" | "enum";  o = [[value,label],...] for enums
                 lib = "NAM" | "IR" for Melon NAM / Melon Cab file controls (model_index / ir_index)
    state        {"ev":"state","gen":3,"slot":0|null,"edited":bool,"bypass":bool,"page":0,"pages":8,
                  "mode":"play"|"browse"|"save","values":[...],
                  "files":[null | "Marshall/JCM800.nam", ...],    chosen file per control (lib controls)
                  "cur":2, "chain":[{"b","i","name","uri","cat","on","cost"}],
                  "dsp":{"predicted","limit","load","peak","xruns"}}   values/files/plugin = selected block;
                                                             i = plugin index; cost and dsp in % of the JACK period
    param        {"ev":"param","gen":3,"i":5,"v":-2.5}       a knob, MIDI or another app moved it
    bypass       {"ev":"bypass","on":true}
    lib_list     {"ev":"lib_list","gen":3,"i":8,"folder":"Marshall","dirs":[["Plexi",12],...],
                  "files":["JCM800.nam",...],"current":"Marshall/JCM800.nam"|null,"total":24}
    wifi         {"ev":"wifi","status":{...},"saved":[...],"networks":[...],"busy":"...","result":{"ok","msg"}}
                 only the fields that changed; see wifi.py. Wi-Fi jobs run on their own thread.
    error        {"ev":"error","msg":"..."}

`gen` goes up every time another block is selected or the selected block gets another plugin,
so a "set" meant for the previous one is ignored instead of landing on the wrong parameter.
A refused chain change (full chain, not enough DSP) answers {"ev":"error","msg":...}.

The hub plugs in as a wrapper around Display: every place that already updates
the LCD also updates the apps, so the pedal logic needs no other changes.
"""
import json
import queue
import socket
import threading

from .presets import BANK_SIZE, CHARSET, NAME_LEN, SLOTS
from .wifi import Wifi

WIFI_OPS = ("wifi_status", "wifi_scan", "wifi_connect", "wifi_forget")

PROTO = 1
VERSION = "0.4"


def _kind(c):
    if c.choices:
        return "enum"
    if c.toggled:
        return "toggle"
    return "int" if c.integer else "float"


def control_info(c, lib=None):
    d = {"l": c.label, "min": c.minimum, "max": c.maximum, "d": c.default, "k": _kind(c)}
    if lib:
        d["lib"] = lib
    if c.unit:
        d["u"] = c.unit
    if c.logarithmic:
        d["log"] = True
    if c.choices:
        d["o"] = [[v, lab] for v, lab in c.choices]
    return d


def _clamp(c, v):
    lo, hi = min(c.minimum, c.maximum), max(c.minimum, c.maximum)
    v = min(max(float(v), lo), hi)
    if c.choices:
        v = min((cv for cv, _ in c.choices), key=lambda cv: abs(cv - v))
    elif c.toggled:
        v = c.maximum if v >= (c.minimum + c.maximum) / 2 else c.minimum
    elif c.integer:
        v = float(round(v))
    return v


class _Client:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.out = queue.Queue(maxsize=2000)
        self.alive = True

    def send(self, msg):
        if not self.alive:
            return
        try:
            self.out.put_nowait(json.dumps(msg, separators=(",", ":")) + "\n")
        except queue.Full:          # client stuck: drop it rather than slow the pedal down
            self.close()

    def writer(self):
        while self.alive:
            line = self.out.get()
            if line is None:
                break
            try:
                self.sock.sendall(line.encode())
            except OSError:
                break
        self.close()

    def close(self):
        if self.alive:
            self.alive = False
            try:
                self.out.put_nowait(None)
            except queue.Full:
                pass
            try:
                self.sock.close()
            except OSError:
                pass


class RemoteHub:
    def __init__(self, host="127.0.0.1", port=5601, name="Melon Pedal"):
        self.addr = (host, port)
        self.name = name
        self.pedal = None
        self.display = None          # the real LCD Display
        self.clients = []
        self.clients_lock = threading.Lock()
        self.gen = 0
        self._plugin = None          # (block, plugin) last announced
        self._presets_sig = None
        self._mode_sent = None
        self.wifi = None

    # ------------------------------------------------------------------ setup
    def wrap(self, display):
        self.display = display
        return _HubDisplay(display, self)

    def start(self, pedal):
        self.pedal = pedal
        self.wifi = Wifi(lambda m: self.broadcast({"ev": "wifi", **m}))
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(self.addr)
        srv.listen(4)
        threading.Thread(target=self._accept, args=(srv,), daemon=True, name="remote-accept").start()
        print(f"remote API on {self.addr[0]}:{self.addr[1]}")

    def _accept(self, srv):
        while True:
            sock, addr = srv.accept()
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client = _Client(sock, addr)
            with self.clients_lock:
                self.clients.append(client)
            threading.Thread(target=client.writer, daemon=True).start()
            threading.Thread(target=self._reader, args=(client,), daemon=True).start()

    def _reader(self, client):
        buf = b""
        try:
            while client.alive:
                chunk = client.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle(client, line)
                if len(buf) > 65536:
                    buf = b""
        except OSError:
            pass
        finally:
            client.close()
            with self.clients_lock:
                if client in self.clients:
                    self.clients.remove(client)

    # ------------------------------------------------------------ messages out
    def broadcast(self, msg):
        with self.clients_lock:
            clients = list(self.clients)
        for c in clients:
            c.send(msg)

    def msg_plugins(self):
        p = self.pedal
        return {"ev": "plugins", "current": p.idx,
                "list": [{"i": i, "name": pl.name, "uri": pl.uri, "n": len(pl.controls)}
                         for i, pl in enumerate(p.plugins)]}

    def msg_presets(self):
        slots = []
        for i in range(SLOTS):
            pr = self.pedal.presets.get(i)
            slots.append({"name": pr["name"], "plugin_name": pr.get("plugin_name", ""),
                          "plugin": pr["plugin"]} if pr else None)
        return {"ev": "presets", "bank_size": BANK_SIZE, "slots": slots}

    def msg_plugin(self):
        p = self.pedal
        pl = p.plugin
        return {"ev": "plugin", "gen": self.gen, "i": p.idx, "name": pl.name, "uri": pl.uri,
                "controls": [control_info(c, self._lib_name(c)) for c in pl.controls]}

    def _lib_name(self, c):
        from .library import LIB_PARAMS
        return LIB_PARAMS.get(c.short_id) if self.pedal.lib_of(c) is not None else None

    def msg_state(self):
        p = self.pedal
        self._mode_sent = p.mode
        return {"ev": "state", "gen": self.gen, "slot": p.slot, "edited": p.edited,
                "bypass": p.bypassed, "page": p.page, "pages": p.pages,
                "mode": "browse" if p.mode == "files" else p.mode,
                "values": [p.values.get(c.key, c.default) for c in p.plugin.controls],
                "files": [p.files.get(c.key) for c in p.plugin.controls],
                "cur": p.cur, "chain": self._chain(), "dsp": p.dsp()}

    def _chain(self):
        p = self.pedal
        index = {id(pl): i for i, pl in enumerate(p.plugins)}
        return [{"b": n, "i": index.get(id(b.plugin)), "name": b.plugin.name, "uri": b.plugin.uri,
                 "cat": b.category, "on": b.on, "cost": round(p.costs.cost(b), 1)}
                for n, b in enumerate(p.chain)]

    def _sync(self):
        """Called whenever the LCD gets a full page: tell apps what changed."""
        p = self.pedal
        if p is None or not p.values:
            return
        key = (id(p.block), p.plugin)
        if key != self._plugin:
            self._plugin = key
            self.gen += 1
            self.broadcast(self.msg_plugins())
            self.broadcast(self.msg_plugin())
        sig = json.dumps(self.msg_presets()["slots"])
        if sig != self._presets_sig:
            self._presets_sig = sig
            self.broadcast(self.msg_presets())
        self.broadcast(self.msg_state())

    def mode_changed(self):
        """Pedal opened its browser / save screen: apps show it (only once per change)."""
        if self.pedal is not None and self.pedal.mode != self._mode_sent:
            self.broadcast(self.msg_state())

    def param_changed(self, control, value):
        p = self.pedal
        try:
            i = p.plugin.controls.index(control)
        except (AttributeError, ValueError):
            return
        self.broadcast({"ev": "param", "gen": self.gen, "i": i, "v": value})

    # ------------------------------------------------------------- messages in
    def _handle(self, client, line):
        try:
            msg = json.loads(line)
            op = msg.get("op")
        except (ValueError, AttributeError):
            return client.send({"ev": "error", "msg": "bad json"})
        p = self.pedal
        if op in WIFI_OPS:                # slow NetworkManager work: own thread, not under the pedal lock
            return self.wifi.request(op, msg)
        try:
            with p.lock:
                if op == "hello":
                    client.send({"ev": "hello", "proto": PROTO, "name": self.name, "version": VERSION,
                                 "features": ["chain"]})
                    for m in (self.msg_plugins(), self.msg_presets(), self.msg_plugin(), self.msg_state()):
                        client.send(m)
                elif op == "get":
                    what = msg.get("what", "all")
                    makers = {"plugins": self.msg_plugins, "presets": self.msg_presets,
                              "plugin": self.msg_plugin, "state": self.msg_state}
                    for k, make in makers.items():
                        if what in ("all", k):
                            client.send(make())
                elif op == "set":
                    self._set(msg)
                elif op == "bypass":
                    on = msg.get("on")
                    p.set_bypass((not p.bypassed) if on is None else bool(on))
                elif op == "page":
                    n = int(msg.get("n", 0))
                    if 0 <= n < p.pages and p.mode == "play":
                        p.page = n
                        p.release_knobs()
                        p.show_page()
                elif op == "load_plugin":
                    i = int(msg["i"])
                    if not 0 <= i < len(p.plugins):
                        raise ValueError("no such plugin")
                    p.mode = "play"
                    p.load(i)
                elif op == "add_block":
                    i = int(msg["i"])
                    if not 0 <= i < len(p.plugins):
                        raise ValueError("no such plugin")
                    p.mode = "play"
                    p.add_block(i, msg.get("pos"))
                elif op == "remove_block":
                    p.mode = "play"
                    p.remove_block(msg["b"])
                elif op == "move_block":
                    p.move_block(msg["b"], msg["to"])
                elif op == "block_on":
                    p.block_on(msg["b"], msg.get("on"))
                elif op == "select_block":
                    p.mode = "play"
                    p.select_block(msg["b"])
                elif op == "load_preset":
                    slot = int(msg["slot"])
                    p.mode = "play"
                    if not p.load_preset(slot):
                        client.send({"ev": "error", "msg": "empty slot or plugin missing"})
                elif op == "save_preset":
                    self._save(msg)
                elif op == "lib_list":
                    client.send(self._lib_list(msg))
                elif op == "set_file":
                    self._set_file(msg)
                else:
                    client.send({"ev": "error", "msg": f"unknown op {op!r}"})
        except Exception as e:      # a bad message must never take the pedal down
            print(f"! remote {op}: {e}")
            client.send({"ev": "error", "msg": f"{op}: {e}"})

    def _set(self, msg):
        p = self.pedal
        if msg.get("gen", self.gen) != self.gen:
            return                    # meant for a plugin that is no longer loaded
        i = int(msg["i"])
        controls = p.plugin.controls
        if not 0 <= i < len(controls):
            return
        c = controls[i]
        v = _clamp(c, msg["v"])
        if abs(v - p.values.get(c.key, c.default)) < 1e-9:
            return
        was_edited = p.edited
        lib = p.lib_of(c)
        if lib is not None:           # Melon NAM / Melon Cab: the number is a position in the library
            p.set_file(c, lib.path_at(int(v)) if v >= 0 else None)
            v = p.values[c.key]
        else:
            p.values[c.key] = v
            p.send(c, v)
        page = p.page_controls()
        if p.mode == "play" and c in page:
            k = page.index(c)
            p.picked[k] = False       # the physical knob must pick the new value up again
            p.display.value(k, c, v)  # LCD pop-up; the wrapper tells the apps
        else:
            self.param_changed(c, v)
        if p.edited != was_edited and p.mode == "play":
            p.display.page(p, popup=False)

    def _lib_control(self, msg):
        p = self.pedal
        if msg.get("gen", self.gen) != self.gen:
            raise ValueError("another plugin is loaded now")
        i = int(msg["i"])
        controls = p.plugin.controls
        if not 0 <= i < len(controls) or p.lib_of(controls[i]) is None:
            raise ValueError("not a library control")
        return i, controls[i], p.lib_of(controls[i])

    def _lib_list(self, msg):
        i, c, lib = self._lib_control(msg)
        folder = str(msg.get("folder") or "").strip("/")
        if not folder:
            lib.refresh()                 # top level: pick up files from a USB import
        dirs, files = lib.list_folder(folder)
        prefix = folder + "/" if folder else ""
        counts = [[d, sum(1 for f in lib.files if f.startswith(f"{prefix}{d}/"))] for d in dirs]
        return {"ev": "lib_list", "gen": self.gen, "i": i, "folder": folder, "dirs": counts, "files": files,
                "current": self.pedal.files.get(c.key), "total": len(lib.files)}

    def _set_file(self, msg):
        p = self.pedal
        i, c, lib = self._lib_control(msg)
        path = msg.get("path") or None
        if path is not None and lib.index_of(str(path)) < 0:
            lib.refresh()
        code = p.set_file(c, str(path) if path else None)
        print(f"  {c.label}: {p.files.get(c.key) or 'none'} (app)" + ("" if code >= 0 else f"   ! mod-host error {code}"))
        if p.mode == "play":
            p.show_page()                 # LCD + full state to the apps (file name, EDITED)
        else:
            self._sync()

    def _save(self, msg):
        p = self.pedal
        slot = int(msg["slot"])
        if not 0 <= slot < SLOTS:
            raise ValueError("slot out of range")
        name = "".join(ch for ch in str(msg.get("name", "")) if ch in CHARSET)    # LCD charset only
        name = " ".join(name.split())[:NAME_LEN].strip()
        name = name or p.plugin.name
        p.save_preset(slot, name)
        print(f"  saved {slot // BANK_SIZE + 1}-{slot % BANK_SIZE + 1:02d} {name} (app)")
        if p.mode == "play":
            p.show_page()
        else:
            self._sync()


class _HubDisplay:
    """Looks like Display; forwards to the LCD and keeps the apps in step."""

    def __init__(self, display, hub):
        self._d = display
        self._hub = hub

    def __getattr__(self, name):
        return getattr(self._d, name)

    def page(self, pedal, popup=False):
        self._d.page(pedal, popup=popup)
        self._hub._sync()

    def value(self, k, control, value):
        self._d.value(k, control, value)
        self._hub.param_changed(control, value)

    def bypass(self, on):
        self._d.bypass(on)
        self._hub.broadcast({"ev": "bypass", "on": bool(on)})

    def browser(self, pedal):
        self._d.browser(pedal)
        self._hub.mode_changed()

    def save(self, pedal, where):
        self._d.save(pedal, where)
        self._hub.mode_changed()

    def files(self, pedal):
        self._d.files(pedal)
        self._hub.mode_changed()

    def notice(self, text):
        self._d.notice(text)
        self._hub.broadcast({"ev": "error", "msg": str(text)})
