"""Tuner support: turns the frequency sent by Melon Tuner into note, cents and string.

Melon Tuner publishes the detected frequency as the read-only LV2 parameter "readout"
(Hz, 0 = no note). mod-host passes it to its feedback port as a patch_set message.
The tables and maths copy the plugin (melon_plugins: plugins/Tuner/Source/TunerDsp.h).
"""
import math

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Same order as the plugin's "Tuning" choice: (name, MIDI notes low -> high, use flats)
TUNINGS = [
    ("Chromatic", [], False),
    ("Guitar Standard", [40, 45, 50, 55, 59, 64], False),
    ("Guitar Eb Standard", [39, 44, 49, 54, 58, 63], True),
    ("Guitar D Standard", [38, 43, 48, 53, 57, 62], False),
    ("Guitar Drop D", [38, 45, 50, 55, 59, 64], False),
    ("Guitar Drop C", [36, 43, 48, 53, 57, 62], False),
    ("Guitar DADGAD", [38, 45, 50, 55, 57, 62], False),
    ("Guitar Open G", [38, 43, 50, 55, 59, 62], False),
    ("Guitar Open D", [38, 45, 50, 54, 57, 62], False),
    ("Guitar 7-String", [35, 40, 45, 50, 55, 59, 64], False),
    ("Bass Standard", [28, 33, 38, 43], False),
    ("Bass 5-String", [23, 28, 33, 38, 43], False),
    ("Bass 6-String", [23, 28, 33, 38, 43, 48], False),
    ("Bass Drop D", [26, 33, 38, 43], False),
    ("Bass Eb Standard", [27, 32, 37, 42], True),
]

IN_TUNE_CENTS = 2.0      # the plugin's lights turn "in tune" within +-2 cents


def _tuning(index):
    return TUNINGS[min(max(int(index), 0), len(TUNINGS) - 1)]


def note_name(midi, flats=False):
    return (FLATS if flats else SHARPS)[midi % 12]


def tuning_name(index):
    return _tuning(index)[0]


def string_names(index):
    _, notes, flats = _tuning(index)
    return [note_name(m, flats) for m in notes]


def reading(hz, reference=440.0, tuning=0):
    """Frequency -> dict for the display, or None when there is no note."""
    if not hz or hz <= 0 or reference <= 0:
        return None
    _, notes, flats = _tuning(tuning)
    m = 69 + 12 * math.log2(hz / reference)
    if notes:
        string = min(range(len(notes)), key=lambda i: abs(m - notes[i]))
        target = notes[string]
    else:
        string, target = None, int(round(m))
    cents = (m - target) * 100
    name = note_name(target, flats)
    return {
        "note": name[0], "acc": name[1:], "octave": target // 12 - 1,
        "cents": round(cents, 1), "hz": round(hz, 1), "string": string,
        "hint": "Tune up" if cents < -50 else "Tune down" if cents > 50 else "",
        "in_tune": abs(cents) <= IN_TUNE_CENTS,
    }
