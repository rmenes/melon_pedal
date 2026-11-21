"""Talks to mod-host over its TCP command socket.

Start mod-host in socket mode first:   mod-host -n -p 5555
Every command is a text line ending in a NUL byte; mod-host answers
"resp <n>" (n >= 0 is OK, negative is an error code).
"""
import socket
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


class FakeEngine(ModHost):
    """Prints commands instead of sending them (for testing without mod-host)."""

    def connect(self, retries=0):
        pass

    def cmd(self, text):
        print(f"  [mod-host] {text}")
        return 0
