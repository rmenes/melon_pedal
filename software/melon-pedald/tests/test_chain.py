"""Multi-FX chain tests: fake plugins + a fake mod-host, no Pi, JACK or LV2 needed.

Run from software/melon-pedald:   python3 -m unittest tests/test_chain.py -v
"""
import json
import os
import socket
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from melon_pedald import chain as chainmod                       # noqa: E402
from melon_pedald.__main__ import ChainError, Pedal               # noqa: E402
from melon_pedald.catalog import Control, Plugin                  # noqa: E402
from melon_pedald.display import Display                          # noqa: E402
from melon_pedald.engine import ModHost                           # noqa: E402
from melon_pedald.presets import PresetStore                      # noqa: E402
from melon_pedald.remote import RemoteHub                         # noqa: E402

BASE = "https://github.com/melon-audio/melon-"


def plugin(slug, name, n_in=2, n_out=2, extra=()):
    uri = BASE + slug
    controls = [Control("param", f"{uri}:gain", "Gain", 0.0, 10.0, 5.0),
                Control("param", f"{uri}:mix", "Mix", 0.0, 100.0, 50.0, unit="%")] + list(extra)
    return Plugin(uri, name, "/fake", [f"in_{i + 1}" for i in range(n_in)],
                  [f"out_{i + 1}" for i in range(n_out)], controls)


NAM_EXTRA = [Control("param", BASE + "nam:size", "Model Size", 0, 1, 0, choices=[(0, "Full"), (1, "Light")]),
             Control("param", BASE + "nam:model_index", "Library Model", -1, 65535, -1, integer=True)]
PLUGINS = [plugin("gatesofdoom", "Melon Gates of Doom"), plugin("dirt", "Melon Dirt"),
           plugin("nam", "Melon NAM", extra=NAM_EXTRA), plugin("cab", "Melon Cab"),
           plugin("chorus", "Melon Chorus"), plugin("delay2290", "Melon Delay 2290"),
           plugin("reverberare", "Melon Reverberare"), plugin("shifter", "Melon Shifter"),
           plugin("graphiceq", "Melon GraphicEQ"), plugin("weird", "Melon Weird FX")]
IDX = {p.name.replace("Melon ", ""): i for i, p in enumerate(PLUGINS)}


class Recorder(ModHost):
    """Fake mod-host: records the commands, answers 0."""

    def __init__(self):
        super().__init__()
        self.log = []

    def connect(self, retries=0):
        pass

    def cmd(self, text):
        self.log.append(text)
        return 0


def costs(table):
    c = chainmod.CostTable(path="/nonexistent")
    c.costs = {BASE + k: v for k, v in table.items()}
    return c


COSTS = {"gatesofdoom": 1.9, "dirt": 5.5, "cab": 3.2, "chorus": 2.1, "delay2290": 2.2,
         "reverberare": 15.8, "shifter": 5.2, "graphiceq": 3.6}


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.engine = Recorder()
        self.store = PresetStore(os.path.join(self.tmp, "presets.json"))
        # enabled display towards a port nobody listens on: exercises the JSON of every LCD message
        self.pedal = Pedal(self.engine, PLUGINS, ["system:capture_1"],
                           ["system:playback_1", "system:playback_2"],
                           Display(enabled=True, port=59999), self.store, costs(COSTS))
        self.pedal.load(IDX["Dirt"])

    def names(self):
        return [b.short_name for b in self.pedal.chain]

    def test_first_block_routing(self):
        self.assertEqual(self.names(), ["Dirt"])
        b = self.pedal.chain[0]
        fx = f"effect_{b.inst}"
        self.assertEqual(self.engine.links, {("system:capture_1", f"{fx}:in_1"), ("system:capture_1", f"{fx}:in_2"),
                                             (f"{fx}:out_1", "system:playback_1"),
                                             (f"{fx}:out_2", "system:playback_2")})

    def test_category_placement(self):
        p = self.pedal
        for name in ("Reverberare", "Chorus", "NAM", "Gates of Doom", "Shifter", "Delay 2290",
                     "Cab", "GraphicEQ", "Weird FX"):
            p.add_block(IDX[name])
        self.assertEqual(self.names(), ["Gates of Doom", "Shifter", "Dirt", "NAM", "Cab", "Chorus",
                                        "Weird FX", "Delay 2290", "Reverberare", "GraphicEQ"])
        self.assertEqual(p.block.short_name, "Weird FX")        # the block added last is selected
        with self.assertRaises(ChainError):                      # 10 blocks = full
            p.add_block(IDX["Chorus"])

    def test_series_routing_and_move(self):
        p = self.pedal
        p.add_block(IDX["Chorus"])
        p.add_block(IDX["Gates of Doom"])
        insts = [b.inst for b in p.chain]
        a, b, c = (f"effect_{i}" for i in insts)
        self.assertIn((f"{a}:out_1", f"{b}:in_1"), self.engine.links)
        self.assertIn((f"{b}:out_2", f"{c}:in_2"), self.engine.links)
        self.assertIn((f"{c}:out_1", "system:playback_1"), self.engine.links)
        self.engine.log.clear()
        p.move_block(2, 0)                                        # Chorus first
        self.assertEqual(self.names(), ["Chorus", "Gates of Doom", "Dirt"])
        self.assertFalse(any(x.startswith("add ") for x in self.engine.log))   # moving = rewiring only
        self.assertIn(("system:capture_1", f"{c}:in_1"), self.engine.links)
        self.assertEqual(len(self.engine.links), 2 + 2 + 2 + 2)

    def test_block_on_off_and_global_bypass(self):
        p = self.pedal
        p.add_block(IDX["Chorus"])
        chorus = p.chain[1]
        p.block_on(1, False)
        self.assertIn(f"bypass {chorus.inst} 1", self.engine.log)
        p.set_bypass(True)
        p.set_bypass(False)
        self.assertEqual(self.engine.log[-2:], [f"bypass {p.chain[0].inst} 0", f"bypass {chorus.inst} 1"])

    def test_remove_and_last_block(self):
        p = self.pedal
        p.add_block(IDX["Chorus"])
        inst = p.chain[1].inst
        p.remove_block(1)
        self.assertIn(f"remove {inst}", self.engine.log)
        self.assertEqual(self.names(), ["Dirt"])
        self.assertFalse(any(f"effect_{inst}" in a + b for a, b in self.engine.links))
        with self.assertRaises(ChainError):
            p.remove_block(0)

    def test_dsp_limit_and_nam_hint(self):
        p = self.pedal
        for name in ("Gates of Doom", "Reverberare", "Chorus", "Delay 2290", "Cab", "Shifter"):
            p.add_block(IDX[name])
        p.add_block(IDX["NAM"])                                   # no model loaded: almost free
        nam = next(b for b in p.chain if b.short_name == "NAM")
        nam.files[BASE + "nam:model_index"] = "Amps+Cabs/Jcm800.nam"   # a model, Full size
        self.assertGreater(p.costs.predicted(p.chain), 80)    # 1.1 + 1.1 x 77 % of blocks
        with self.assertRaises(ChainError) as e:
            p.add_block(IDX["GraphicEQ"])
        self.assertIn("Light", str(e.exception))
        nam.values[BASE + "nam:size"] = 1                         # Light
        p.add_block(IDX["GraphicEQ"])                             # fits now

    def test_preset_roundtrip_and_same_chain_reload(self):
        p = self.pedal
        p.add_block(IDX["Chorus"])
        p.block_on(1, False)
        p.values[BASE + "chorus:mix"] = 30.0
        p.save_preset(0, "Wet")
        self.assertFalse(p.edited)
        p.values[BASE + "chorus:mix"] = 80.0
        self.assertTrue(p.edited)
        self.engine.log.clear()
        p.load_preset(0)                                          # same chain: values only, no gap
        self.assertFalse(any(x.startswith(("add ", "remove ")) for x in self.engine.log))
        self.assertEqual(p.chain[1].values[BASE + "chorus:mix"], 30.0)
        self.assertFalse(p.chain[1].on)
        self.assertFalse(p.edited)
        with open(self.store.path) as fh:
            data = json.load(fh)
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["presets"]["1"]["plugin_name"], "Dirt + Chorus")
        p.remove_block(1)
        self.assertTrue(p.edited)
        p.load_preset(0)                                          # other chain: rebuilt
        self.assertEqual(self.names(), ["Dirt", "Chorus"])
        self.assertEqual(p.cur, 1)

    def test_version1_preset(self):
        self.store.slots[3] = {"name": "Old", "plugin": BASE + "chorus", "plugin_name": "Melon Chorus",
                               "values": {BASE + "chorus:gain": 7.0}}
        self.pedal.add_block(IDX["Delay 2290"])
        self.assertTrue(self.pedal.load_preset(3))
        self.assertEqual(self.names(), ["Chorus"])
        self.assertEqual(self.pedal.values[BASE + "chorus:gain"], 7.0)
        self.assertFalse(self.pedal.edited)

    def test_replace_selected_block(self):
        p = self.pedal
        p.add_block(IDX["Chorus"])
        inst = p.block.inst
        p.load(IDX["Delay 2290"])                                  # replaces Chorus, same instance
        self.assertEqual(self.names(), ["Dirt", "Delay 2290"])
        self.assertEqual(p.block.inst, inst)

    def test_feedback_only_from_selected_block(self):
        p = self.pedal
        got = []
        p.display.tuner = got.append
        p.on_patch(99, "x", 1.0)                                  # unknown instance: ignored
        self.assertEqual(got, [])


class RemoteTest(unittest.TestCase):
    def test_chain_ops_over_tcp(self):
        engine = Recorder()
        store = PresetStore(os.path.join(tempfile.mkdtemp(), "p.json"))
        hub = RemoteHub(port=0)
        display = hub.wrap(Display(enabled=False))
        pedal = Pedal(engine, PLUGINS, ["system:capture_1"], ["system:playback_1"], display, store, costs(COSTS))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        hub.addr = ("127.0.0.1", port)
        hub.start(pedal)
        pedal.load(IDX["Dirt"])
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        f = s.makefile("r")

        def send(m):
            s.sendall((json.dumps(m) + "\n").encode())

        def until(pred, what):
            t = time.time() + 5
            while time.time() < t:
                m = json.loads(f.readline())
                if pred(m):
                    return m
            self.fail(f"no {what}")

        send({"op": "hello"})
        until(lambda m: m.get("ev") == "hello" and "chain" in m.get("features", []), "hello")
        pl = until(lambda m: m.get("ev") == "plugins", "plugins")["list"]
        nam = pl[IDX["NAM"]]
        self.assertEqual((nam["cat"], nam["tag"], nam["cost"], nam["cost_light"]), ("amp", "AMP", 41.2, 9.1))
        self.assertEqual((pl[IDX["Chorus"]]["cost"], pl[IDX["Weird FX"]]["cost"]), (2.1, 10.0))
        st = until(lambda m: m.get("ev") == "state", "state")
        self.assertEqual([c["name"] for c in st["chain"]], ["Melon Dirt"])
        send({"op": "add_block", "i": IDX["Chorus"]})
        st = until(lambda m: m.get("ev") == "state" and len(m["chain"]) == 2, "state with 2 blocks")
        self.assertEqual(st["cur"], 1)
        self.assertEqual(st["chain"][1]["cat"], "mod")
        self.assertIn("predicted", st["dsp"])
        send({"op": "block_on", "b": 1, "on": False})
        until(lambda m: m.get("ev") == "state" and m["chain"][1]["on"] is False, "block off")
        send({"op": "select_block", "b": 0})
        st = until(lambda m: m.get("ev") == "state" and m["cur"] == 0, "select")
        send({"op": "set", "gen": st["gen"], "i": 0, "v": 9})
        until(lambda m: m.get("ev") == "param" and m["v"] == 9, "param echo")
        self.assertEqual(pedal.chain[0].values[BASE + "dirt:gain"], 9)
        send({"op": "remove_block", "b": 0})
        until(lambda m: m.get("ev") == "state" and len(m["chain"]) == 1, "remove")
        send({"op": "remove_block", "b": 0})
        until(lambda m: m.get("ev") == "error" and "last block" in m["msg"], "refused remove")
        send({"op": "save_preset", "slot": 2, "name": "Only chorus"})
        until(lambda m: m.get("ev") == "presets" and m["slots"][2], "presets")
        s.close()


if __name__ == "__main__":
    unittest.main()


class RestoreTest(unittest.TestCase):
    """The live sound survives a controller restart (new audio interface, crash, reboot)."""

    def make(self, tmp):
        store = PresetStore(os.path.join(tmp, "presets.json"))
        return Pedal(Recorder(), PLUGINS, ["system:capture_1"], ["system:playback_1", "system:playback_2"],
                     Display(enabled=False), store, costs(COSTS))

    def test_restart_keeps_chain_values_preset_and_edits(self):
        from melon_pedald.state import StateKeeper
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "state.json")
        a = self.make(tmp)
        a.load(IDX["Dirt"])
        a.add_block(IDX["Chorus"])
        a.add_block(IDX["Delay 2290"])
        a.save_preset(4, "Big Test")
        mix = a.chain[1].plugin.controls[1]
        a.chain[1].values[mix.key] = 77.0                         # edited after saving
        a.chain[2].on = False
        a.select_block(1)
        a.set_bypass(True)
        keeper = StateKeeper(path, a)
        self.assertTrue(keeper.save_now())
        self.assertFalse(keeper.save_now())                       # unchanged: no second write

        b = self.make(tmp)                                        # "restarted" controller
        self.assertTrue(b.restore(StateKeeper(path, b).read()))
        self.assertEqual([x.short_name for x in b.chain], ["Dirt", "Chorus", "Delay 2290"])
        self.assertEqual(b.chain[1].values[mix.key], 77.0)
        self.assertFalse(b.chain[2].on)
        self.assertEqual(b.slot, 4)
        self.assertTrue(b.edited)
        self.assertEqual(b.cur, 1)
        self.assertTrue(b.bypassed)

    def test_no_state_file(self):
        from melon_pedald.state import StateKeeper
        tmp = tempfile.mkdtemp()
        p = self.make(tmp)
        self.assertFalse(p.restore(StateKeeper(os.path.join(tmp, "none.json"), p).read()))


class AudioIoTest(unittest.TestCase):
    """Choosing inputs / outputs of a multi-channel interface (pedal menu and app)."""

    def setUp(self):
        from melon_pedald import audio_io
        self.audio_io = audio_io
        self._counts = audio_io.jack_counts
        audio_io.jack_counts = lambda a=2, b=2: (12, 4)          # Audient Sono: 12 in / 4 out
        os.environ["MELON_CARD"] = "Sono"
        self.tmp = tempfile.mkdtemp()
        self.engine = Recorder()
        self.pedal = Pedal(self.engine, PLUGINS, ["system:capture_1"], ["system:playback_1", "system:playback_2"],
                           Display(enabled=False), PresetStore(os.path.join(self.tmp, "p.json")), costs(COSTS))
        self.pedal.ports = audio_io.PortStore(os.path.join(self.tmp, "ports.json"))
        self.pedal.load(IDX["Chorus"])

    def tearDown(self):
        self.audio_io.jack_counts = self._counts
        os.environ.pop("MELON_CARD", None)

    def test_options(self):
        ins, outs = self.pedal.io_options()
        self.assertEqual([o["id"] for o in ins][:3], ["1", "2", "3"])
        self.assertIn("11+12", [o["id"] for o in ins])
        self.assertEqual(len(ins), 12 + 6)
        self.assertEqual([o["id"] for o in outs], ["1+2", "3+4", "1", "2", "3", "4"])
        self.assertEqual(self.pedal.io_current(), ("1", "1+2"))

    def test_set_io_relinks_and_remembers_per_interface(self):
        p = self.pedal
        fx = f"effect_{p.chain[0].inst}"
        p.set_io("3+4", "3+4")
        self.assertIn(("system:capture_3", f"{fx}:in_1"), self.engine.links)
        self.assertIn(("system:capture_4", f"{fx}:in_2"), self.engine.links)
        self.assertIn((f"{fx}:out_2", "system:playback_4"), self.engine.links)
        self.assertNotIn(("system:capture_1", f"{fx}:in_1"), self.engine.links)
        cap, pb = p.ports.get("Sono")
        self.assertEqual(cap, ["system:capture_3", "system:capture_4"])
        self.assertEqual(pb, ["system:playback_3", "system:playback_4"])
        self.assertEqual(p.ports.get("AMS22"), (None, None))   # other interfaces keep their own
        with self.assertRaises(ChainError):
            p.set_io("13")

    def test_pedal_menu_audio_tab(self):
        p = self.pedal
        p.open_browser()
        p.menu_press(1)                 # presets -> plugins
        p.menu_press(1)                 # plugins -> audio
        self.assertEqual(p.tab, "audio")
        self.assertEqual(p.io_rows[p.sel][1]["id"], "1")          # starts on the current input
        out_row = next(n for n, (k, o) in enumerate(p.io_rows) if k == "out" and o["id"] == "3")
        p.sel = out_row
        p.menu_press(3)                 # use Out 3 (mono)
        self.assertEqual(p.playback, ["system:playback_3"])
        self.assertEqual(p.mode, "browse")                        # stays in the list to pick more
        p.menu_press(1)                 # audio -> presets
        self.assertEqual(p.tab, "presets")

    def test_remote_audio(self):
        hub = RemoteHub(port=0)
        hub.pedal = self.pedal
        m = hub.msg_audio()
        self.assertEqual((m["card"], m["in"], m["out"]), ("Sono", "1", "1+2"))
        self.assertEqual(len(m["inputs"]), 18)
