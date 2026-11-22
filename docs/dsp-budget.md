# Melon Pedal — Multi-FX DSP budget

**Measured 2026-11-22** on the Pi 4 (4 GB) with `software/tools/dsp_bench.py`. Purpose: find out how many Melon Plugins fit in one chain, and give `melon-pedald` real numbers for a DSP limit when it moves from one plugin to a multi-FX chain.

## 1. Setup

| Item | Value |
|---|---|
| Audio interface | Momix USB (`hw:MomixCab`); the HiFiBerry is not fitted yet |
| JACK | 48 kHz, **256 frames × 3 periods** (5.33 ms period). Note: the architecture doc still says 128 × 2 |
| Host | mod-host (`melon-modhost.service`), each plugin is its own JACK client `effect_<n>` |
| Signal | built-in test signal (guitar-like plucks, about −12 dBFS), mono into each plugin |
| Measurement | JACK DSP load sampled every 20 ms for 10 s per step; xrun callback |
| Baseline | 1.0–1.1 % (JACK + the bench's own client, no plugin) |
| CPU temperature | 63–69 °C on the open bench |

**Cost** = load with the plugin − baseline. "Peak" uses the 95th percentile.

### How to run the bench
mod-host serves **one command client at a time**, so the pedal programs must be stopped first. Restarting `melon-modhost` also restarts `melon-pedald`, so restart first, then stop:

```bash
sudo systemctl restart melon-modhost; sleep 2
sudo systemctl stop melon-pedald melon-display melon-ble; sleep 1
unset DISPLAY
python3 -u dsp_bench.py --out ~/plugin_costs.json | tee bench_single.txt            # every plugin alone
python3 -u dsp_bench.py --variants variants_nam_size.json --out ~/plugin_costs.json  # parameter variants
python3 -u dsp_bench.py --settle 5 --chain "melon-gatesofdoom,melon-nam@size=1@model_index=NAM:Amps+Cabs/Jcm800.nam,..."
sudo systemctl restart melon-modhost
sudo systemctl start melon-pedald melon-display melon-ble
```

- `NAM:` / `IR:` values are file paths under `/data/media/NAM` and `/data/media/IR`; the bench turns them into `model_index` / `ir_index` with the same scan order as `library.py`.
- Results are merged into `~/plugin_costs.json` (`/data` is not writable by the user yet).
- Use `python3 -u` with `| tee`, otherwise the output only appears at the end.

## 2. Cost of each plugin alone (defaults)

| Plugin | Cost avg | Cost peak | Notes |
|---|---:|---:|---|
| **Muffs** | **25.8 %** | 25.9 % | Heaviest non-NAM plugin; optimization target |
| **Reverberare** | **15.7 %** | 15.8 % | Hall, 3 s |
| **Comp** | **8.2 %** | 8.3 % | High for a compressor |
| Dirt | 5.3 % | 5.5 % | |
| Shifter | 5.0 % | 5.2 % | |
| Tuner | 4.3 % | 4.4 % | |
| Guitar Synth | 3.3 % | 3.4 % | |
| Multi Delay | 2.4 % | 2.4 % | |
| Delay 2290 | 2.1 % | 2.2 % | |
| Chorus | 2.0 % | 2.1 % | |
| Flanger | 1.9 % | 2.0 % | |
| Gates of Doom | 1.8 % | 1.9 % | |
| GraphicEQ | 1.5 % | 1.6 % | 10 bands; **31 bands = 3.5 %** |
| Pro EQ | 1.2 % | 1.3 % | |
| Simple Gate | 0.9 % | 0.9 % | |
| Cab | 0.5 % | 0.6 % | No IR loaded; **with an IR (OLA CON −3 B) = 3.1 %** |
| NAM | 0.8 % | 0.9 % | No model loaded; see §3 |

No xruns in any run. Load time per plugin: 40–120 ms.

## 3. Melon NAM by model

| Model | Architecture | Cost |
|---|---|---:|
| Jcm800 (your library), **Full** | SlimmableContainer → WaveNet 8 ch | **41.1 %** |
| Jcm800, **Light** | SlimmableContainer → WaveNet 3 ch | **8.9 %** |
| Fortin TS9 #1, Full | SlimmableContainer → WaveNet 8 ch | 40.8 % |
| Fortin TS9 #1, Light | SlimmableContainer → WaveNet 3 ch | 8.6 % |
| Boss test capture a2 | SlimmableContainer | 41.5 % |
| Boss test capture standard | WaveNet 16/8 | 39.0 % |
| Boss test capture feather | WaveNet 8/4 | 13.7 % |
| Boss test capture nano | WaveNet 4/2 | 5.7 % |

- **Every model in `/data/media/NAM` is a NAM A2 "SlimmableContainer"** holding two networks of the same capture: up to 0.5 → WaveNet 3 channels (light), 0.5–1.0 → WaveNet 8 channels (full).
- Melon NAM used to always run the full one. It now has a **Model Size** parameter (`size`: Full / Light, default Full; [melon_plugins](https://github.com/rmenes/melon_plugins) `plugins/Nam`), which picks the network through NeuralAudio's `SetQualityScaleFactor`. The switch happens off the audio thread; models without sizes ignore it.
- **Light costs 4.6× less.** Sound quality of Light still has to be judged by ear.
- Melon NAM was already mono inside (runs the model once on the left input, copies to both outputs), so there was no stereo saving to make.

## 4. Chains (serial, one block after another)

Load after each block was added (avg):

| Blocks | Without amp/cab files | With Jcm800 **Full** + OLA CON −3 B |
|---|---:|---:|
| + Gates of Doom | 2.7 % | 2.8 % |
| + Comp | 11.1 % | 11.2 % |
| + Dirt | 16.7 % | 16.8 % |
| + NAM | 17.7 % | **59.8 %** |
| + Cab | 18.6 % | 64.7 % |
| + Delay 2290 | 21.2 % | 67.4 % |
| + Reverberare | **38.8 %** | **84.9 %** (p95 85.8 %) |

Two runs of the full chain agreed within 0.3 %. No xruns, even at 86 %.

**Estimated with NAM at Light:** about **50 %** for the same 7-block chain (to be confirmed with the bench).

## 5. Findings

1. **Costs add up, plus about 10 %.** Sum of single costs + baseline: 35.4 % → measured 38.8 %; 78.2 % → measured 84.9 %. Both are ≈ baseline + **1.1 × sum of costs**. The extra is the per-client overhead (each mod-host plugin is its own JACK client).
2. **A serial chain runs on one core.** Each block needs the previous block's output, so the four cores don't multiply the budget; JACK's DSP load (% of the 5.33 ms period) is the number to watch.
3. **Load is very steady**: p95 is within about 1 % of the average for every plugin and chain measured.
4. **NAM decides the budget**: Full NAM is half of it. With Light, a full rig (gate, comp, drive, amp, cab, delay, reverb) fits with plenty of headroom at 256 frames.
5. **Parameters change the cost**, not only adding blocks: GraphicEQ 10 → 31 bands (1.5 → 3.5 %), NAM model and size (9 → 41 %), Cab with or without IR.
6. All Melon Plugins run 2 in / 2 out.

## 6. Rules for the multi-FX engine (proposal)

| Load (p95) | Meaning |
|---|---|
| below 60 % | green |
| 60–75 % | amber warning on the LCD and in the app |
| above 75 % (avg) or 85 % (peak) | refuse to add a block |
| any xrun | meter turns red |

- **Before adding a block:** predicted = current peak + **1.1 × the block's `cost_peak`** from the cost table. Refuse if it's above the limit and say how much is free.
- **After adding:** watch the load for about 1.5 s; if the peak goes over the limit or an xrun happens, remove the block again and tell the player.
- For NAM, look up the cost **per size** (Full ≈ 41 %, Light ≈ 9 %). When a chain doesn't fit, the pedal can offer "switch NAM to Light" instead of only refusing.
- Unknown plugins (not in the table) get a cautious default cost until benched.
- Parameter changes that raise the cost can't be blocked nicely; show the meter and the warning instead.
- The cost table lives in `plugin_costs.json` (now `~/plugin_costs.json`; move it to `/data` when that is writable). Re-bench after plugin updates and once with the final audio interface.
- Only one program may command mod-host: the chain, the DSP check, the LCD and the phone app all go through `melon-pedald`.

## 7. Next steps

- **Listen** to Jcm800 at Full vs Light on the pedal.
- **Bench the full chain with NAM Light** (command in §1) to confirm the ≈ 50 % estimate.
- **Optimize Muffs (26 %), Reverberare (16 %) and Comp (8 %)**: check oversampling and per-sample work first; consider mono processing for blocks that sit before the first stereo effect.
- Measure again at **128 frames** (lower latency) and with the **final interface** (iOne or HiFiBerry).
- Re-check temperature with the Pi **inside the enclosure** under a full chain (69 °C already on the open bench).
