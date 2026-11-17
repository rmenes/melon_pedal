# Decision log

Short record of project decisions and why they were made. Newest first. Details live in the linked documents.

| # | Date | Decision | Why | Details |
|---|---|---|---|---|
| D16 | 2026-11-17 | Melon Plugins stay on **JUCE**; pedal builds are 64-bit ARM LV2, built natively on arm64 (Pi or GitHub Actions) | One codebase for VST3 (Windows) and LV2 (pedal). JUCE's LV2 build runs a helper at build time, so cross-compiling from x86 is awkward | [Software §7](software-architecture.md#7-plugins-juce-on-arm) |
| D15 | 2026-11-17 | The controller supports both LV2 **control ports** and LV2 **parameters** (`patch_set`) | JUCE exposes its parameters as `lv2:Parameter`, not control ports; mod-host supports `patch_set` | [Software §4, §7.1](software-architecture.md) |
| D14 | 2026-11-17 | Controller `melon-pedald` written in **Python 3** (asyncio) | Fast to develop; audio runs in mod-host, not in Python | [Software §4](software-architecture.md#4-melon-pedald-the-pedal-controller) |
| D13 | 2026-11-17 | **One LV2 plugin at a time** (mod-host instance 0); swaps go through relay bypass | Keeps CPU load low on the Pi 4; the player hears the dry signal during a swap | [Software §3.2–3.3](software-architecture.md#3-audio-engine) |
| D12 | 2026-11-17 | Audio stack: **Raspberry Pi OS Lite 64-bit + JACK2 + mod-host** | Smallest official OS; deterministic latency; proven headless LV2 host | [Software §1](software-architecture.md#1-key-decisions) |
| D11 | 2026-11-17 | LCD GUI generated from LV2 metadata; 4 tiles laid out like the knobs; pages of 4 | Works with any plugin without per-plugin GUI code. Branding comes later | [Software §5](software-architecture.md#5-pedal-user-interface) |
| D10 | 2026-11-17 | Boot and file system on a **64 GB low-profile USB 3 drive**, reachable through a side-wall cut-out | The Pi's micro-SD slot is broken | [Hardware v0.4](hardware-architecture.md) |
| D9 | 2026-11-17 | Build the full-size design first (~100 × 135 × 65 mm); optimize height later | Learn the real problems from a first build | [Backlog](optimization-backlog.md) |
| D8 | 2026-11-17 | All jacks **top-mounted** on one I/O board; Pi rotated 90° | Better on pedalboards; short signal paths | [Hardware §8](hardware-architecture.md#8-mechanical-layout) |
| D7 | 2026-11-17 | Parts mainly from AliExpress; HiFiBerry, USB drive and aluminium plate bought elsewhere | Availability in Brazil; avoid fakes for critical parts | [Shopping list](../hardware/bom/shopping-list.csv) |
| D6 | 2026-11-17 | Power: 9 V centre-negative, **1.5 A** adapter is enough (worst case ≈ 1.1 A) | Measured Pi 4 load + peripherals + converter losses | [Hardware §7](hardware-architecture.md#7-power) |
| D5 | 2026-11-17 | **Stereo** in/out on 6.35 mm TRS; mono TS cables supported | Stereo effects; TRS saves space vs. four jacks | [Hardware §3.6](hardware-architecture.md) |
| D4 | 2026-11-17 | **MIDI IN + OUT/THRU** on 3.5 mm TRS **Type A** (Boss standard) | Same cables as newer Boss pedals | [Hardware §4](hardware-architecture.md#4-midi-35-mm-trs-type-a) |
| D3 | 2026-11-17 | 4 **rotary encoders** with push switches (not pots) | Parameters change per plugin/preset; no value jumps | [Hardware §6](hardware-architecture.md#6-controls--display) |
| D2 | 2026-11-17 | HiFiBerry DAC2 ADC Pro + custom Hi-Z/low-Z buffers + relay true bypass | No Pi HAT offers a true 1 MΩ guitar input | [Hardware §3](hardware-architecture.md#3-analog-circuits-on-the-io-board) |
| D1 | 2026-11-17 | Raspberry Pi 4 (8 GB) running Raspberry Pi OS, hosting Melon Plugins (LV2) | Hardware already owned; simple development | [README](../README.md) |
