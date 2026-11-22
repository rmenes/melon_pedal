#!/usr/bin/env python3
"""
dsp_bench.py — measure the DSP cost of LV2 plugins on the Melon Pedal.

Runs on the Pi, next to jackd + mod-host. Two modes:

  single  (default)  load each plugin alone, measure JACK DSP load, save a
                     cost table to /data/plugin_costs.json
  chain              add plugins in series one by one and print the load after
                     each step, to check that costs add up (and where it breaks)

Examples   (use python3 -u ... | tee file.txt to see lines live)
  python3 dsp_bench.py                                  # all Melon plugins, defaults
  python3 dsp_bench.py --variants variants.json         # + specific parameter sets
  python3 dsp_bench.py --chain melon-gatesofdoom,melon-comp,melon-dirt,melon-nam,melon-cab,melon-delay2290,melon-reverberare
  python3 dsp_bench.py --signal input --listen          # use the guitar input and hear it
  python3 dsp_bench.py --chain "melon-nam@model_index=NAM:Amps+Cabs/Jcm800.nam,melon-cab@ir_index=IR:OLA CON -3 B.wav"
      (NAM:/IR: values are paths, or a unique part of one, under /data/media/NAM or /data/media/IR)

Needs: sudo apt install python3-jack-client python3-numpy python3-lilv
Stop the pedal controller first so only the bench uses mod-host:
  sudo systemctl stop melon-pedald
"""
import argparse
import json
import os
import socket
import statistics
import sys
import time

# --------------------------------------------------------------------------- mod-host

class ModHost:
    """Tiny mod-host client: text commands, NUL-terminated, 'resp <n> ...' replies.

    mod-host only starts answering commands once a client is also connected to
    its feedback port (command port + 1), so we open both and drain feedback in
    a background thread (otherwise its buffer fills up and mod-host blocks).
    """

    def __init__(self, host, port, fb_port=None, timeout=30.0):
        import threading
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.fb = None
        fb_port = port + 1 if fb_port is None else fb_port
        if fb_port > 0:
            try:
                self.fb = socket.create_connection((host, fb_port), timeout=5.0)
                self.fb.settimeout(None)
                threading.Thread(target=self._drain, daemon=True).start()
            except OSError as e:
                print(f"  ! feedback port {fb_port} not reachable ({e}); continuing without it")

    def _drain(self):
        try:
            while self.fb.recv(65536):
                pass
        except OSError:
            pass

    def check(self):
        """Fail fast with a clear message if mod-host doesn't answer."""
        old = self.sock.gettimeout()
        self.sock.settimeout(5.0)
        try:
            self.cmd("remove 9999")  # harmless: instance doesn't exist, just wants a reply
        except (TimeoutError, socket.timeout):
            sys.exit("mod-host accepted the connection but doesn't answer commands.\n"
                     "Probably another program is still connected to it. Check with:\n"
                     "  ss -tnp | grep -E ':555[56]'\n"
                     "and stop that program (or: sudo systemctl restart mod-host), then try again.")
        finally:
            self.sock.settimeout(old)

    def cmd(self, text):
        self.sock.sendall(text.encode() + b"\0")
        buf = b""
        while not buf.endswith(b"\0"):
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("mod-host closed the connection")
            buf += chunk
        reply = buf.rstrip(b"\0").decode(errors="replace").strip()
        parts = reply.split()
        status = int(parts[1]) if len(parts) > 1 and parts[0] == "resp" else -999
        return status, reply


# --------------------------------------------------------------------------- helpers

def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read()) / 1000, 1)
    except OSError:
        return None


def summarize(samples):
    s = sorted(samples)
    if not s:
        return {"avg": None, "p95": None, "max": None}
    p95 = s[min(len(s) - 1, int(0.95 * len(s)))]
    return {"avg": round(statistics.fmean(s), 2), "p95": round(p95, 2), "max": round(s[-1], 2)}


def list_plugins(filter_text):
    import lilv
    world = lilv.World()
    world.load_all()
    out = []
    for p in world.get_all_plugins():
        uri = str(p.get_uri())
        if filter_text.lower() in uri.lower():
            out.append((uri, str(p.get_name())))
    return sorted(out)


MEDIA_ROOT = os.environ.get("MELON_MEDIA_DIR", "/data/media")
LIB_EXTS = {"NAM": {"nam", "aidax", "json"}, "IR": {"wav", "aif", "aiff", "flac"}}
_lib_cache = {}


def lib_scan(lib):
    """Same order as melon-pedald library.py / the plugins' MelonLibraryScan.h."""
    if lib in _lib_cache:
        return _lib_cache[lib]
    root_b = os.fsencode(os.path.join(MEDIA_ROOT, lib))
    out = []
    for dirpath, dirnames, filenames in os.walk(root_b, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(b".")]
        for name in filenames:
            if name.startswith(b"."):
                continue
            ext = os.path.splitext(name)[1][1:].lower().decode("utf-8", "replace")
            full = os.path.join(dirpath, name)
            if ext in LIB_EXTS[lib] and os.path.isfile(full):
                out.append(os.path.relpath(full, root_b).replace(os.sep.encode(), b"/"))
    out.sort()
    _lib_cache[lib] = [os.fsdecode(p) for p in out]
    return _lib_cache[lib]


def resolve_value(val):
    """'NAM:Amps+Cabs/Jcm800.nam' / 'IR:Folder/file.wav' -> library index; anything else as is."""
    if isinstance(val, str) and val.split(":", 1)[0] in LIB_EXTS and ":" in val:
        lib, rel = val.split(":", 1)
        files = lib_scan(lib)
        rel = rel.replace("\\", "/").strip("/")
        if rel in files:
            return files.index(rel)
        hits = [i for i, p in enumerate(files) if rel.lower() in p.lower()]
        if len(hits) == 1:
            return hits[0]
        raise SystemExit(f"{lib} file '{rel}' matches {len(hits)} files in {MEDIA_ROOT}/{lib}"
                         + (": " + ", ".join(files[i] for i in hits[:5]) if hits else ""))
    return val


def parse_block(text):
    """'melon-nam@model_index=NAM:Amps+Cabs/Jcm800.nam@input=0' -> ('melon-nam', {...})."""
    name, *pairs = text.split("@")
    params = {}
    for p in pairs:
        k, _, v = p.partition("=")
        params[k.strip()] = v.strip()
    return name.strip(), params


def resolve_uri(short, known):
    """Accept a full URI or any unique substring of one (e.g. 'melon-nam')."""
    if "://" in short:
        return short
    hits = [u for u, _ in known if short.lower() in u.lower()]
    exact = [u for u in hits if u.lower().rstrip("/").endswith(short.lower())]
    if len(exact) == 1:
        return exact[0]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"'{short}' matches {len(hits)} plugins: {hits or 'none'}")


# --------------------------------------------------------------------------- bench

class Bench:
    def __init__(self, args):
        import jack
        import numpy as np

        self.args = args
        self.np = np
        self.client = jack.Client("dsp-bench", no_start_server=True)
        self.xruns = 0
        self.client.set_xrun_callback(self._on_xrun)

        self.sig_port = None
        if args.signal == "generator":
            self.sig_port = self.client.outports.register("sig")
            self._loop = self._make_test_signal(self.client.samplerate)
            self._pos = 0
            self.client.set_process_callback(self._process)

        self.client.activate()
        self.sr = self.client.samplerate
        self.bs = self.client.blocksize
        self.host = ModHost(args.host, args.port, args.fb_port)
        self.host.check()

    # -- JACK callbacks -------------------------------------------------------
    def _on_xrun(self, delay_usecs):
        self.xruns += 1

    def _make_test_signal(self, sr):
        """2 s loop of guitar-like plucks: decaying harmonics + a little noise, ~-12 dBFS."""
        np = self.np
        n = int(sr * 2)
        t = np.arange(n) / sr
        out = np.zeros(n, dtype=np.float32)
        rng = np.random.default_rng(1)
        for start, f0 in ((0.0, 82.41), (0.5, 110.0), (1.0, 146.8), (1.5, 196.0)):
            tt = t - start
            m = tt >= 0
            env = np.exp(-tt[m] * 3.0)
            note = sum(np.sin(2 * np.pi * f0 * k * tt[m]) / k for k in range(1, 7))
            out[m] += (0.25 * env * note).astype(np.float32)
        out += 0.003 * rng.standard_normal(n).astype(np.float32)
        return out

    def _process(self, frames):
        buf = self.sig_port.get_array()
        end = self._pos + frames
        if end <= len(self._loop):
            buf[:] = self._loop[self._pos:end]
        else:
            k = len(self._loop) - self._pos
            buf[:k] = self._loop[self._pos:]
            buf[k:] = self._loop[:frames - k]
        self._pos = end % len(self._loop)

    # -- sources / ports -------------------------------------------------------
    def source_ports(self):
        if self.args.signal == "generator":
            return [self.sig_port.name]
        if self.args.signal == "input":
            caps = self.client.get_ports("system:capture", is_audio=True, is_output=True)
            return [caps[0].name] if caps else []
        return []

    def effect_ports(self, inst, timeout=10.0):
        name = f"effect_{inst}:"
        t0 = time.time()
        while time.time() - t0 < timeout:
            ins = [p.name for p in self.client.get_ports(name, is_audio=True, is_input=True)]
            outs = [p.name for p in self.client.get_ports(name, is_audio=True, is_output=True)]
            if ins or outs:
                return ins, outs
            time.sleep(0.05)
        raise RuntimeError(f"no JACK ports for effect_{inst}")

    def connect_many(self, srcs, dsts):
        """1->N fan out, N->N pairwise, N->1 first channel only."""
        if not srcs or not dsts:
            return
        for i, d in enumerate(dsts):
            s = srcs[i] if i < len(srcs) else srcs[0]
            try:
                self.client.connect(s, d)
            except Exception as e:  # already connected etc.
                print(f"  ! connect {s} -> {d}: {e}")

    def listen(self, outs):
        if self.args.listen:
            play = [p.name for p in self.client.get_ports("system:playback", is_audio=True, is_input=True)]
            self.connect_many(outs, play)

    # -- mod-host ops ----------------------------------------------------------
    def add(self, uri, inst):
        self.remove(inst)  # leftover from an aborted run; error is fine
        t0 = time.time()
        status, reply = self.host.cmd(f"add {uri} {inst}")
        add_ms = round((time.time() - t0) * 1000)
        if status < 0:
            raise RuntimeError(f"add failed ({reply})")
        return add_ms

    def set_params(self, uri, inst, params):
        for key, val in (params or {}).items():
            prop = key if "://" in key else f"{uri}:{key}"
            v = resolve_value(val)
            if v != val:
                print(f"  {key} = {v}  ({val})")
            status, reply = self.host.cmd(f"patch_set {inst} {prop} {v}")
            if status < 0:
                print(f"  ! patch_set {key}={val}: {reply}")

    def remove(self, inst):
        try:
            self.host.cmd(f"remove {inst}")
        except OSError as e:
            print(f"  ! remove {inst}: {e}")

    # -- measuring --------------------------------------------------------------
    def measure(self, seconds, settle):
        time.sleep(settle)
        self.xruns = 0
        samples = []
        t_end = time.time() + seconds
        while time.time() < t_end:
            samples.append(self.client.cpu_load())
            time.sleep(0.02)
        res = summarize(samples)
        res["xruns"] = self.xruns
        return res

    def close(self):
        try:
            self.client.deactivate()
            self.client.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- modes

def run_single(bench, args, known):
    jobs = []
    if args.variants:
        with open(args.variants) as f:
            for v in json.load(f):
                jobs.append((resolve_uri(v["uri"], known), v.get("label", "default"),
                             v.get("params", {}), v.get("settle", args.settle)))
    if not args.variants or args.with_defaults:
        uris = [resolve_uri(u, known) for u in args.only.split(",")] if args.only else [u for u, _ in known]
        jobs = [(u, "default", {}, args.settle) for u in uris] + jobs

    names = dict(known)
    print(f"\nBaseline ({args.seconds}s, signal={args.signal}) ...")
    base = bench.measure(args.seconds, 1.0)
    print(f"  baseline  avg {base['avg']:5.1f}%  p95 {base['p95']:5.1f}%  max {base['max']:5.1f}%  xruns {base['xruns']}")

    results = {}
    inst = args.instance
    for uri, label, params, settle in jobs:
        print(f"\n{names.get(uri, uri)} [{label}]")
        try:
            add_ms = bench.add(uri, inst)
            ins, outs = bench.effect_ports(inst)
            bench.connect_many(bench.source_ports(), ins)
            bench.listen(outs)
            bench.set_params(uri, inst, params)
            m = bench.measure(args.seconds, settle)
        except Exception as e:
            print(f"  FAILED: {e}")
            bench.remove(inst)
            continue
        bench.remove(inst)
        m.update({
            "add_ms": add_ms,
            "audio_in": len(ins), "audio_out": len(outs),
            "params": params,
            "cost_avg": round(max(0.0, m["avg"] - base["avg"]), 2),
            "cost_peak": round(max(0.0, m["p95"] - base["avg"]), 2),
        })
        print(f"  load avg {m['avg']:5.1f}%  p95 {m['p95']:5.1f}%  max {m['max']:5.1f}%  "
              f"xruns {m['xruns']}  -> cost avg {m['cost_avg']:.1f}% / peak {m['cost_peak']:.1f}%  "
              f"(add {add_ms} ms, {len(ins)} in / {len(outs)} out)")
        entry = results.setdefault(uri, {"name": names.get(uri, uri), "variants": {}})
        entry["variants"][label] = m
        time.sleep(0.3)

    save(args.out, bench, base, results, args)
    print_table(results)


def run_chain(bench, args, known):
    blocks = [parse_block(b) for b in args.chain.split(",") if b.strip()]
    uris = [resolve_uri(name, known) for name, _ in blocks]
    params_list = [p for _, p in blocks]
    for p in params_list:            # check file names before starting
        for v in p.values():
            resolve_value(v)
    names = dict(known)
    print(f"\nBaseline ({args.seconds}s) ...")
    base = bench.measure(args.seconds, 1.0)
    print(f"  baseline avg {base['avg']:.1f}%  p95 {base['p95']:.1f}%")

    prev_outs = bench.source_ports()
    added = []
    try:
        for i, uri in enumerate(uris):
            inst = args.instance + i
            add_ms = bench.add(uri, inst)
            added.append(inst)
            ins, outs = bench.effect_ports(inst)
            bench.connect_many(prev_outs, ins)
            prev_outs = outs
            bench.set_params(uri, inst, params_list[i])
            m = bench.measure(args.seconds, args.settle)
            flag = "  <-- over limit" if m["p95"] > args.peak_limit or m["xruns"] else ""
            print(f"  +{names.get(uri, uri):<28} blocks {i + 1}  avg {m['avg']:5.1f}%  "
                  f"p95 {m['p95']:5.1f}%  max {m['max']:5.1f}%  xruns {m['xruns']}  (add {add_ms} ms){flag}")
            if m["p95"] > 95 or m["xruns"] > 5:
                print("  stopping: chain is past the limit")
                break
        bench.listen(prev_outs)
        if args.listen:
            input("\nChain is live on the outputs. Press Enter to tear it down ...")
    finally:
        for inst in reversed(added):
            bench.remove(inst)


# --------------------------------------------------------------------------- output

def save(path, bench, base, results, args):
    data = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    data.update({
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sample_rate": bench.sr, "buffer": bench.bs,
        "period_ms": round(1000 * bench.bs / bench.sr, 3),
        "signal": args.signal, "seconds": args.seconds,
        "cpu_temp_c": cpu_temp(),
        "baseline": base,
    })
    plugins = data.setdefault("plugins", {})
    for uri, entry in results.items():   # merge: keep variants measured in earlier runs
        old = plugins.setdefault(uri, {"name": entry["name"], "variants": {}})
        old["name"] = entry["name"]
        old["variants"].update(entry["variants"])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved {path}")


def print_table(results):
    rows = [(e["name"], label, v) for e in results.values() for label, v in e["variants"].items()]
    if not rows:
        return
    rows.sort(key=lambda r: -r[2]["cost_peak"])
    print(f"\n{'Plugin':<26}{'Variant':<14}{'cost avg':>9}{'cost peak':>10}{'xruns':>7}{'add ms':>8}")
    for name, label, v in rows:
        print(f"{name[:25]:<26}{label[:13]:<14}{v['cost_avg']:>8.1f}%{v['cost_peak']:>9.1f}%"
              f"{v['xruns']:>7}{v['add_ms']:>8}")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Measure LV2 plugin DSP cost on the Melon Pedal")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555, help="mod-host command port")
    ap.add_argument("--fb-port", type=int, default=None,
                    help="mod-host feedback port (default: --port + 1; 0 = don't connect)")
    ap.add_argument("--filter", default="melon", help="only plugins whose URI contains this")
    ap.add_argument("--only", help="comma list of plugins (URI or part of it) instead of all")
    ap.add_argument("--variants", help="JSON list of {uri, label, params, settle}")
    ap.add_argument("--with-defaults", action="store_true", help="with --variants, also run every plugin at defaults")
    ap.add_argument("--chain", help="comma list of plugins to stack in series (chain mode)")
    ap.add_argument("--seconds", type=float, default=10.0, help="measuring time per step")
    ap.add_argument("--settle", type=float, default=2.0, help="wait after loading before measuring")
    ap.add_argument("--signal", choices=["generator", "input", "none"], default="generator")
    ap.add_argument("--listen", action="store_true", help="connect plugin output to the speakers")
    ap.add_argument("--instance", type=int, default=90, help="first mod-host instance number to use")
    ap.add_argument("--peak-limit", type=float, default=85.0, help="chain mode: flag steps above this p95")
    ap.add_argument("--out", default="/data/plugin_costs.json")
    args = ap.parse_args()

    known = list_plugins(args.filter)
    if not known:
        sys.exit(f"No LV2 plugins match '{args.filter}' (check LV2_PATH includes /data/lv2)")

    bench = Bench(args)
    print(f"JACK {bench.sr} Hz, {bench.bs} frames ({1000 * bench.bs / bench.sr:.2f} ms period), "
          f"CPU {cpu_temp()} °C, {len(known)} plugins found")
    try:
        if args.chain:
            run_chain(bench, args, known)
        else:
            run_single(bench, args, known)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        bench.close()
    print(f"CPU {cpu_temp()} °C at end")


if __name__ == "__main__":
    main()
