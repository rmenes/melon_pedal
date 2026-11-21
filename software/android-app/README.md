# Melon Pedal — Android app

Edits the pedal over Bluetooth LE through `software/melon-ble`. Kotlin + Jetpack Compose, Android 8.0+ (API 26).

**Screens**
- **Connect:** finds pedals nearby (filters on the Melon service UUID), remembers the last one, reconnect button.
- **Sound:** every parameter of the loaded plugin, grouped in pages of four like the pedal. The page that is
  on the physical knobs is outlined and shows knob numbers 1–4; "put on knobs" moves the pedal to another page.
  Sliders (log scale where the plugin says so), switches for toggles, chips or a menu for lists.
  Double-tap a parameter's name to reset it to the default. GraphicEQ-style plugins also get a band graph.
- **Presets:** 4 banks × 6 slots, tap to load, *Save current sound…* (name up to 16 characters, pick the slot).
- **Plugins:** tap to load another plugin.
- Big **BYPASS / EFFECT ON** button, preset band with **EDITED** chip, same colours as the LCD.

Knob turns, MIDI and footswitch changes on the pedal show up in the app live; app changes show up on the LCD.

## Build

1. Install Android Studio (Ladybug or newer).
2. *File → Open* → this `android-app` folder. Let it sync; if it offers to update the Android Gradle
   Plugin, Kotlin or the Compose BOM, accept. (The Gradle wrapper jar isn't checked in; Android Studio
   uses `gradle/wrapper/gradle-wrapper.properties`. To build from a terminal, run `gradle wrapper` once.)
3. Enable *Developer options → USB debugging* on the phone, plug it in, press **Run**.

## Code map

| File | What it does |
|---|---|
| `ble/PedalBle.kt` | Scan, connect, MTU 517, subscribe to TX, line reassembly, one-at-a-time GATT write queue |
| `data/Protocol.kt` | JSON messages of the remote API, parameter formatting (same text as the LCD) |
| `PedalViewModel.kt` | State, sends slider moves at most ~30×/s (newest value only), ignores echoes while dragging |
| `ui/PedalScreen.kt`, `ui/Controls.kt`, `MainActivity.kt` | Compose screens |
| `ui/Theme.kt` | Melon colour tokens from `docs/lcd-gui-design.md` |

Fonts: the app uses the system font. To match the LCD, add Fredoka / Barlow Semi Condensed TTFs to
`app/src/main/res/font/` and set them in `Theme.kt`.
