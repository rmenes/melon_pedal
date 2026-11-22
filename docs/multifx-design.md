# Melon Pedal — Multi-FX design (v0.1, 2026-11-22)

**Status 2026-11-22: step 1 working on the Pi.** `melon-pedald` 0.4: chain engine (one mod-host instance per block, series routing), category placement, preset format v2 (v1 presets load as one block), DSP limit from the cost table + live JACK meter, remote API chain ops (`add_block`, `remove_block`, `move_block`, `block_on`, `select_block`; CLI shortcuts in `melon_remote_cli.py`). LCD: **chain strip** on the Play screen (lit = on, dim = off, cream frame = selected) and live **DSP nn%** in the header. NexFoot: press C = block on/off, hold B = next block, browser plugins tab C = add block. Startup note: mod-host only answers once its feedback port (5556) is connected, so the controller connects that first.


From one LV2 plugin at a time (v1) to a **chain of blocks** per preset. Builds on `melon-pedald`, the remote API (phone app) and the LCD design. DSP numbers: [dsp-budget.md](dsp-budget.md).

## 1. Decisions

| Topic | Decision |
|---|---|
| Preset | An ordered **chain of up to 10 blocks**. Block = plugin + parameter values + on/off (+ NAM/IR file by path) |
| Routing | **Serial only** (parallel paths maybe later). Mono until the first stereo block |
| Default order | **Gate → Pitch/Synth → Comp → Drive → Amp (NAM) → Cab → Mod → Delay → Reverb → EQ** |
| Placement | Every plugin has a **category**; "Add block" inserts it at its category's position; blocks can still be moved by hand |
| Quick knobs | 4 per preset, each pointing at any parameter of any block (the Play screen tiles) |
| Footswitch | **Only one** on the pedal: **tap = bypass the whole pedal** (relays), **hold = tuner** (output muted, tap leaves). Same on every screen |
| Other switching | Blocks on/off and preset changes from the LCD knobs, the phone app and **MIDI** (CC/PC on the existing MIDI IN) |
| Where chains are built | Mainly in the **phone app**; the pedal for choosing presets and tweaking (full chain editing also possible on the LCD) |
| Tuner | Not a chain block: its own screen, never costs chain DSP |
| Old presets | A v1 single-plugin preset loads as a chain of 1 |

## 2. Categories and default positions

| Position | Category | Melon Plugins |
|---|---|---|
| 1 | Gate | Gates of Doom, Simple Gate |
| 2 | Pitch / Synth | Shifter, Guitar Synth (right after the gate: they track best on a clean signal) |
| 3 | Dynamics | Comp |
| 4 | Drive | Dirt, Muffs |
| 5 | Amp | NAM |
| 6 | Cab | Cab |
| 7 | Modulation | Chorus, Flanger (later: a Melon Multimod) |
| 8 | Delay | Delay 2290, Multi Delay |
| 9 | Reverb | Reverberare |
| 10 | EQ (post) | GraphicEQ, Pro EQ (EQ can go anywhere; default is a post-EQ at the end) |

The table lives in `melon-pedald` (plugin URI → category); a new plugin needs one line. Unknown plugins go before Delay.

## 3. Engine (`melon-pedald`)

- **One mod-host instance per block** (0–9), connected in series in JACK. Only `melon-pedald` talks to mod-host (it accepts one command client).
- **Block on/off:** mod-host's per-instance `bypass` (instant). The relays stay the global true bypass.
- **Preset change:** compare old and new chain. Same plugins in the same order → only send parameter values (no gap). Otherwise → relays to dry, add/remove/reconnect the blocks that changed, back to effect.
- **Mono/stereo:** a stereo block followed by a mono one (e.g. Chorus before NAM) is folded to mono; the chain editor shows a "mono from here" mark.
- **DSP guard** (numbers and rules in [dsp-budget.md](dsp-budget.md) §6):
  - A block counts against the budget **even when it is off**, so switching it on mid-song can never overload the Pi.
  - Before adding: predicted = current peak + 1.1 × block cost (cost table, NAM per model size). Refuse if over the limit, or offer "switch NAM to Light".
  - After adding: watch the load ~1.5 s; remove the block again on overload or xruns.
  - Expected: the full 10-block default chain with NAM Light ≈ 60 % at 256 frames.
- **Tempo (later):** one pedal tempo (tap from the app/MIDI, or MIDI clock) for delay times and modulation rates.

## 4. LCD

Builds on [lcd-gui-design.md](lcd-gui-design.md) (tokens, list pattern, corner = knob).

- **Play (stage view):** header with DSP meter; preset band; **chain strip** (one chip per block, lit = on, dim = off; colour by category); 4 tiles = the preset's **quick knobs** (label shows the block, e.g. "3 · DLY Mix").
- **Chain edit** (K1 push from Play): list of blocks with on/off and DSP cost, "+ Add block" at the end. K1 turn = select, K1 push = back, K2 push = block on/off, K3 turn = move block, K4 push = edit block.
- **Block edit:** today's plugin screen (tiles, pages of 4, value pop-up), with the block name in the preset band.
- **Add block:** the plugin list with category, cost and a "won't fit" mark; the block lands at its category's position.
- **Footswitch:** tap = BYPASS bar (whole pedal), hold = Tuner screen. Resolves the "footswitch hold" open point in [lcd-gui-design.md](lcd-gui-design.md) §5.

## 5. Phone app and remote API

- New ops: `add_block {uri, pos?}`, `remove_block {b}`, `move_block {b, to}`, `block_on {b, on}`, `select_block {b}`, `set_quick {k, b, i}`; `set`, `lib_list` and `set_file` get a block index `b`.
- `state` gets `chain [{uri, name, cat, on, cost}]`, `dsp {load, peak, xruns, predicted}`.
- Old single-plugin messages keep working on a chain of 1 (block 0).
- App: **Chain** screen with drag to reorder, tap to switch on/off, add from a list with cost bars, live DSP meter; the Sound screen edits the selected block.

## 6. Build order

1. **Engine + preset format** (chain of 1 = today's behaviour), category table, DSP guard with the cost table.
2. **Phone app chain editor** + remote API ops.
3. **LCD** Play / Chain edit / Add block screens; footswitch hold = tuner.
4. **Quick knobs**, MIDI CC → block on/off.
5. Later: pedal tempo, scenes/snapshots, parallel paths, Melon Multimod, web UI.

## 7. Open points

- Max chain length 10 is a starting point; check DSP with real presets.
- Exact chip colours per category on the LCD (within the existing tokens).
- Whether a preset change keeps spill-over (delay/reverb tails) — needs crossfading between chains, later.
