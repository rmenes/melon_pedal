"""Talks to mod-host over its TCP command socket.

Start mod-host in socket mode first:   mod-host -n -p 5555
Every command is a text line ending in a NUL byte; mod-host answers
"resp <n>" (n >= 0 is OK, negative is an error code).
"""
import socket
import threading
import time

INSTANCE = 0  # one-plugin rule: always instance 0


class ModHostError(RuntimeError):
    pass


class ModHost:
    def __init__(self, host="127.0.0.1", port=5555, verbose=False):
        self.addr = (host, port)
        self.verbose = verbose
        self.sock = None
        self.loaded = None
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

    # --- plugin ---
    def load(self, plugin, capture, playback):
        # Always clear instance 0 first, even if we didn't load it: a controller killed by a
        # restart leaves its plugin in mod-host, and "add" would then fail with -2 (already exists).
        self.cmd(f"remove {INSTANCE}")      # -3 (no such instance) is fine
        self.loaded = None
        code = self.cmd(f"add {plugin.uri} {INSTANCE}")
        if code < 0:
            raise ModHostError(f"mod-host could not load {plugin.name} (error {code})")
        self.loaded = plugin
        fx = f"effect_{INSTANCE}"
        ins, outs = plugin.audio_in, plugin.audio_out
        # inputs: one capture port feeds every plugin input; two capture ports go L/R
        for i, port in enumerate(ins):
            self.cmd(f"connect {capture[min(i, len(capture) - 1)]} {fx}:{port}")
        # outputs: a mono plugin feeds both speakers
        for i, play in enumerate(playback):
            if outs:
                self.cmd(f"connect {fx}:{outs[min(i, len(outs) - 1)]} {play}")

    def unload(self):
        if self.loaded:
            try:
                self.cmd(f"remove {INSTANCE}")
            finally:
                self.loaded = None

    def set(self, control, value):
        v = f"{value:.6g}"
        if control.kind == "param":
            return self.cmd(f"patch_set {INSTANCE} {control.key} {v}")
        return self.cmd(f"param_set {INSTANCE} {control.key} {v}")

    def bypass(self, on):
        return self.cmd(f"bypass {INSTANCE} {1 if on else 0}")


class Feedback:
    """Reads mod-host's feedback port (one NUL-terminated text message at a time).

    Used for values the plugin sends to the host, e.g. Melon Tuner's reading:
    "patch_set <instance> <parameter URI> <type> <value>" (older mod-host: no type).
    Reconnects by itself when mod-host restarts. `on_patch(uri, value)` runs in this thread.

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
        if len(parts) >= 4 and parts[0] == "patch_set" and parts[1] == str(INSTANCE):
            try:
                value = float(parts[-1])
            except ValueError:
                return
            try:
                self.on_patch(parts[2], value)
            except Exception as e:          # never let the display kill the reader
                print(f"! feedback handler: {e!r}")


class FakeEngine(ModHost):
    """Prints commands instead of sending them (for testing without mod-host)."""

    def connect(self, retries=0):
        pass

    def cmd(self, text):
        print(f"  [mod-host] {text}")
        return 0
