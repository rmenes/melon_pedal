"""Mock-ups of the pedal's 320x240 LCD screens (drawn 2x for readability).

    python3 tools/render_ui_mockups.py   ->  docs/images/ui-mockups.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

S = 2  # scale
W, H = 320 * S, 240 * S
FONT_DIR = "/usr/share/fonts/opentype/inter/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "images", "ui-mockups.png")

BG = (10, 14, 20)
BAR = (22, 34, 44)
TXT = (230, 236, 242)
DIM = (140, 158, 172)
ACC = (120, 220, 140)
TRACK = (35, 48, 58)
RED = (235, 90, 80)


def f(style, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Inter-{style}.otf"), size * S)


def header(d, left, right, bypass=False):
    d.rectangle((0, 0, W, 24 * S), fill=BAR)
    d.text((8 * S, 12 * S), left, font=f("Bold", 13), fill=ACC, anchor="lm")
    d.text((W - 8 * S, 12 * S), right, font=f("Medium", 10), fill=DIM, anchor="rm")
    if bypass:
        d.rounded_rectangle((W / 2 - 34 * S, 5 * S, W / 2 + 34 * S, 19 * S), radius=4 * S, fill=RED)
        d.text((W / 2, 12 * S), "BYPASS", font=f("Bold", 10), fill=(255, 255, 255), anchor="mm")


def tile(d, x, y, n, name, val, txt, focused=False):
    w, h = 148 * S, 62 * S
    d.rounded_rectangle((x, y, x + w, y + h), radius=6 * S, fill=(18, 26, 34),
                        outline=ACC if focused else (30, 42, 52), width=2 * S if focused else S)
    d.text((x + 8 * S, y + 14 * S), f"{n}", font=f("Bold", 11), fill=DIM, anchor="lm")
    d.text((x + 22 * S, y + 14 * S), name, font=f("SemiBold", 13), fill=TXT, anchor="lm")
    d.text((x + w - 8 * S, y + 36 * S), txt, font=f("Bold", 16), fill=ACC, anchor="rm")
    d.rounded_rectangle((x + 8 * S, y + 48 * S, x + w - 8 * S, y + 54 * S), radius=3 * S, fill=TRACK)
    d.rounded_rectangle((x + 8 * S, y + 48 * S, x + 8 * S + int((w - 16 * S) * val), y + 54 * S), radius=3 * S, fill=ACC)


def screen_play():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    header(d, "P01", "CPU 18%  ·  48k/128")
    d.text((W / 2, 44 * S), "Melon Drive", font=f("Bold", 20), fill=TXT, anchor="mm")
    d.text((W / 2, 63 * S), "Clean Boost", font=f("Medium", 11), fill=DIM, anchor="mm")
    # tiles laid out like the physical knobs: 3 4 on top, 1 2 below
    tile(d, 8 * S, 76 * S, 3, "Mix", 0.30, "30 %")
    tile(d, 164 * S, 76 * S, 4, "Level", 0.75, "-2.0 dB")
    tile(d, 8 * S, 146 * S, 1, "Gain", 0.62, "6.2")
    tile(d, 164 * S, 146 * S, 2, "Tone", 0.45, "2.4 kHz", focused=True)
    for i in range(3):
        d.ellipse((W / 2 - 14 * S + i * 12 * S, 220 * S, W / 2 - 8 * S + i * 12 * S, 226 * S),
                  fill=ACC if i == 0 else TRACK)
    return im


def screen_eq():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    header(d, "P07", "Page 3 / 8", bypass=False)
    d.text((W / 2, 40 * S), "Melon GraphicEQ · 31", font=f("Bold", 16), fill=TXT, anchor="mm")
    import math
    x0, x1, yc = 12 * S, W - 12 * S, 118 * S
    n = 31
    for i in range(n):
        g = 6 * math.sin(i / 4.0) * math.exp(-((i - 15) / 12) ** 2)
        x = x0 + (x1 - x0) * i / (n - 1)
        sel = 8 <= i <= 11
        d.line((x, yc, x, yc - g * 6 * S), fill=ACC if sel else (70, 110, 90), width=4 * S)
    d.line((x0, yc, x1, yc), fill=TRACK, width=S)
    sel_x0 = x0 + (x1 - x0) * 7.6 / 30
    sel_x1 = x0 + (x1 - x0) * 11.4 / 30
    d.rounded_rectangle((sel_x0, 66 * S, sel_x1, 170 * S), radius=4 * S, outline=ACC, width=S)
    labels = [("3", "160 Hz", "+2.5"), ("4", "200 Hz", "+3.8"), ("1", "100 Hz", "+0.9"), ("2", "125 Hz", "+1.7")]
    pos = [(8, 178), (164, 178), (8, 206), (164, 206)]
    for (n_, fr, v), (x, y) in zip(labels, pos):
        d.text((x * S + 6 * S, y * S + 10 * S), f"{n_}  {fr}", font=f("SemiBold", 12), fill=TXT, anchor="lm")
        d.text((x * S + 142 * S, y * S + 10 * S), f"{v} dB", font=f("Bold", 12), fill=ACC, anchor="rm")
    return im


def screen_browser():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    header(d, "PRESETS", "Bank A")
    items = ["01  Clean Boost", "02  Edge of Breakup", "03  Lead Drive", "04  Wide Chorus",
             "05  Ambient Verb", "06  Slapback", "07  Studio EQ"]
    for i, it in enumerate(items):
        y = 32 * S + i * 28 * S
        if i == 2:
            d.rounded_rectangle((6 * S, y - 2 * S, W - 6 * S, y + 24 * S), radius=5 * S, fill=(30, 60, 42))
        d.text((14 * S, y + 11 * S), it, font=f("SemiBold" if i == 2 else "Medium", 14),
               fill=TXT if i == 2 else DIM, anchor="lm")
    return im


def screen_popup():
    im = screen_play()
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, H), fill=(0, 0, 0, 150))
    d.rounded_rectangle((40 * S, 60 * S, W - 40 * S, 180 * S), radius=10 * S, fill=(20, 30, 38), outline=ACC, width=2 * S)
    d.text((W / 2, 84 * S), "2  Tone", font=f("SemiBold", 15), fill=DIM, anchor="mm")
    d.text((W / 2, 122 * S), "2.4 kHz", font=f("Bold", 34), fill=TXT, anchor="mm")
    d.rounded_rectangle((60 * S, 152 * S, W - 60 * S, 160 * S), radius=4 * S, fill=TRACK)
    d.rounded_rectangle((60 * S, 152 * S, 60 * S + int((W - 120 * S) * 0.45), 160 * S), radius=4 * S, fill=ACC)
    return im


def bezel(im, title):
    pad, cap = 24, 46
    out = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad + cap), (245, 245, 243))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((pad - 10, pad - 10, pad + im.width + 10, pad + im.height + 10), radius=14, fill=(15, 15, 16))
    out.paste(im, (pad, pad))
    d.text((out.width / 2, pad + im.height + 10 + cap / 2 + 4), title, font=ImageFont.truetype(os.path.join(FONT_DIR, "Inter-SemiBold.otf"), 26),
           fill=(40, 40, 40), anchor="mm")
    return out


if __name__ == "__main__":
    shots = [bezel(screen_play(), "Play: 4 knobs = 4 tiles"), bezel(screen_popup(), "Turning a knob"),
             bezel(screen_eq(), "Many parameters: pages of 4"), bezel(screen_browser(), "Preset browser")]
    sw, sh = shots[0].size
    sheet = Image.new("RGB", (sw * 2, sh * 2), (245, 245, 243))
    for i, s in enumerate(shots):
        sheet.paste(s, ((i % 2) * sw, (i // 2) * sh))
    sheet.save(OUT)
    print(OUT)
