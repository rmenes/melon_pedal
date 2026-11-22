"""Talks to mod-host over its TCP command socket.

Start mod-host in socket mode first:   mod-host -n -p 5555
Every command is a text line ending in a NUL byte; mod-host answers
"resp <n>" (n >= 0 is OK, negative is an error code).

Multi-FX: every block of the chain is its own mod-host instance (and JACK client
effect_<n>). Instance numbers belong to the block, not to its position, so moving a
block only changes the JACK connections. `route()` connects the chain in series and
only adds / removes the connections that changed.
"""
import socket
import threading
import time

MAX_INSTANCES = 10


class ModHostError(RuntimeError):
    pass


def link_ports(srcs, dsts):
    """Which output feeds which input: 1 -> N fans out, N -> N pairs up, N -> 1 takes the first."""
    if not srcs or not dsts:
        return []
    return [(srcs[i] if i < len(srcs) else srcs[0], d) for i, d in enumerate(dsts)]


class ModHost:
    def __init__(self, host="127.0.0.1", port=5555, verbose=False):
        self.addr = (host, port)
        self.verbose = verbose
        self.sock = None
        self.instances = {}              # instance number -> plugin
        self.links = set()               # (output port, input port) made by route()
        self.lock = threading.Lock()     # the feedback thread also sends commands

    def connect(self, retries=10):
        for i in range(retries):
            try:
                self.sock = socket.create_connection(self.addr, timeout=10)
                return
            except OSError:
                time.sleep(0.5)
        raise ModHostError(
            f"cannot reach mod-host on {self.addr[0]}:{self.addr[1]} - is it running? (mod-host -n -p {self.addr[1]})")

    def cmd(self, text):
        with self.lock:
            return self._cmd(text)

    def _cmd(self, text):
        if self.verbose:
            print(f"  > {text}")
        self.sock.sendall(text.encode() + b"\0")
        buf = b""
        while not buf.endswith(b"\0"):
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ModHostError("mod-host closed the connection")
            buf += chunk
        reply = buf.rstrip(b"\0").decode(errors="replace").strip()
        parts = reply.split()
        try:
            code = int(parts[1]) if parts and parts[0] == "resp" else int(parts[0])
        except (IndexError, ValueError):
            raise ModHostError(f"unexpected reply to {text!r}: {reply!r}")
        if self.verbose:
            print(f"  < {reply}")
        return code

    # --- instances (one per block) ---
    def clear(self):
        """At start: remove whatever a previous controller left in mod-host (-3 = nothing there)."""
        for inst in range(MAX_INSTANCES):
            self.cmd(f"remove {inst}")
        self.instances.clear()
        self.links.clear()

    def add(self, inst, plugin):
        """Load `plugin` as instance `inst` (replacing what was there). Not connected yet: see route()."""
        self.remove(inst)
        code = self.cmd(f"add {plugin.uri} {inst}")
        if code < 0:
            raise ModHostError(f"mod-host could not load {plugin.name} (error {code})")
        self.instances[inst] = plugin

    def remove(self, inst):
        self.cmd(f"remove {inst}")       # -3 (no such instance) is fine; mod-host drops its connections
        self.instances.pop(inst, None)
        fx = f"effect_{inst}:"
        self.links = {l for l in self.links if not (l[0].startswith(fx) or l[1].startswith(fx))}

    def unload(self):
        for inst in list(self.instances):
            self.remove(inst)

    def route(self, insts, capture, playback):
        """Connect capture -> instance 1 -> instance 2 -> ... -> playback (no instances: dry)."""
        want, prev = [], list(capture)
        for inst in insts:
            plugin = self.instances.get(inst)
            if plugin is None:
                continue
            fx = f"effect_{inst}"
            ins = [f"{fx}:{p}" for p in plugin.audio_in]
            outs = [f"{fx}:{p}" for p in plugin.audio_out]
            want += link_ports(prev, ins)
            prev = outs or prev
        want += link_ports(prev, list(playback))
        want = set(want)
        for a, b in sorted(self.links - want):
            self.cmd(f"disconnect {a} {b}")
        for a, b in sorted(want - self.links):
            code = self.cmd(f"connect {a} {b}")
            if code < 0:
                print(f"! connect {a} -> {b}: mod-host error {code}")
        self.links = want

    def set(self, inst, control, value):
        v = f"{value:.6g}"
        if control.kind == "param":
            return self.cmd(f"patch_set {inst} {control.key} {v}")
        return self.cmd(f"param_set {inst} {control.key} {v}")

    def bypass(self, inst, on):
        return self.cmd(f"bypass {inst} {1 if on else 0}")


class Feedback:
    """Reads mod-host's feedback port (one NUL-terminated text message at a time).

    Used for values the plugin sends to the host, e.g. Melon Tuner's reading:
    "patch_set <instance> <parameter URI> <type> <value>" (older mod-host: no type).
    Reconnects by itself when mod-host restarts. `on_patch(inst, uri, value)` runs in this thread.

    Flow control: after each batch mod-host sends "data_finish" and then waits for
    "output_data_ready" on the command port before it sends the next batch (as mod-ui does).
    `ready()` sends that command.
    """

    def __init__(self, on_patch, ready, host="127.0.0.1", port=5556, verbose=False):
        self.addr = (host, port)
        self.on_patch = on_patch
        self.ready = ready
        self.verbose = verbose
        self.connected = False

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="modhost-feedback").start()

    def _run(self):
        warned = False
        while True:
            try:
                with socket.create_connection(self.addr, timeout=5) as sock:
                    sock.settimeout(None)
                    self.connected, warned = True, False
                    print(f"mod-host feedback connected ({self.addr[1]})")
                    self._ready()
                    buf = b""
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                        *msgs, buf = buf.split(b"\0")
                        for m in msgs:
                            self._message(m.decode(errors="replace").strip())
            except OSError as e:
                if not warned:
                    print(f"! mod-host feedback port {self.addr[1]} not reachable ({e}); retrying")
                    warned = True
            self.connected = False
            time.sleep(1)

    def _ready(self):
        try:
            code = self.ready()
        except Exception as e:
            print(f"! output_data_ready: {e!r}")
            return
        if isinstance(code, int) and code < 0 and not getattr(self, "_ready_warned", False):
            self._ready_warned = True
            print(f"! mod-host refused output_data_ready (error {code}): plugin values will stop after the first one")

    def _message(self, text):
        if text == "data_finish":
            return self._ready()
        parts = text.split()
        if self.verbose and parts and parts[0] != "patch_set":
            print(f"  [feedback] {text}")
        if len(parts) >= 4 and parts[0] == "patch_set":
            try:
                inst, value = int(parts[1]), float(parts[-1])
            except ValueError:
                return
            try:
                self.on_patch(inst, parts[2], value)
            except Exception as e:          # never let the display kill the reader
                print(f"! feedback handler: {e!r}")


class FakeEngine(ModHost):
    """Prints commands instead of sending them (for testing without mod-host)."""

    def connect(self, retries=0):
        pass

    def cmd(self, text):
        print(f"  [mod-host] {text}")
        return 0
