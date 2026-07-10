"""Draw a Lucide-style stroke icon set with Pillow.

Icons are designed on a 24x24 grid with 2px strokes, round caps/joins
(emulated by stamping discs along strokes), rendered supersampled at
16x and downscaled to 64px PNGs.
"""

import math
import os

from PIL import Image, ImageDraw

GRID = 24
SS = 16                      # supersample factor
CANVAS = GRID * SS           # 384
OUT_SIZE = 64
STROKE = 2.0 * SS


def P(x, y):
    return (x * SS, y * SS)


class Icon:
    def __init__(self):
        self.img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    # stroke primitives with round caps -------------------------------
    def _dot(self, p, r):
        x, y = p
        self.d.ellipse([x - r, y - r, x + r, y + r], fill="white")

    def line(self, p1, p2, w=STROKE):
        a, b = P(*p1), P(*p2)
        self.d.line([a, b], fill="white", width=int(w))
        self._dot(a, w / 2)
        self._dot(b, w / 2)

    def poly(self, pts, close=False, w=STROKE):
        pts = list(pts)
        if close:
            pts = pts + [pts[0]]
        for i in range(len(pts) - 1):
            self.line(pts[i], pts[i + 1], w)

    def arc(self, cx, cy, r, a0, a1, w=STROKE, steps=64):
        """Angles in degrees, standard math orientation (CCW positive)."""
        pts = []
        for i in range(steps + 1):
            t = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((cx + r * math.cos(t), cy - r * math.sin(t)))
        self.poly(pts, w=w)

    def circle(self, cx, cy, r, w=STROKE):
        self.arc(cx, cy, r, 0, 360, w=w)

    def rrect(self, x0, y0, x1, y1, r, w=STROKE):
        self.line((x0 + r, y0), (x1 - r, y0), w)
        self.line((x0 + r, y1), (x1 - r, y1), w)
        self.line((x0, y0 + r), (x0, y1 - r), w)
        self.line((x1, y0 + r), (x1, y1 - r), w)
        self.arc(x0 + r, y0 + r, r, 90, 180, w=w)
        self.arc(x1 - r, y0 + r, r, 0, 90, w=w)
        self.arc(x0 + r, y1 - r, r, 180, 270, w=w)
        self.arc(x1 - r, y1 - r, r, 270, 360, w=w)

    def render(self, path, color):
        # use the white drawing as an alpha mask, fill with color
        mask = self.img.split()[3].resize((OUT_SIZE, OUT_SIZE),
                                          Image.LANCZOS)
        out = Image.new("RGBA", (OUT_SIZE, OUT_SIZE), color)
        out.putalpha(mask)
        out.save(path)


# ── icon definitions (24x24 grid, Lucide geometry) ───────────────────

def i_plus(ic):
    ic.line((5, 12), (19, 12))
    ic.line((12, 5), (12, 19))


def i_save(ic):
    ic.rrect(3, 3, 21, 21, 2)
    ic.poly([(7, 3), (7, 8), (15, 8), (15, 3)])       # top tab
    ic.poly([(7, 21), (7, 13), (17, 13), (17, 21)])   # bottom card


def i_trash(ic):
    ic.line((3, 6), (21, 6))
    ic.poly([(8, 6), (8, 4), (10, 2.5), (14, 2.5), (16, 4), (16, 6)], w=STROKE * 0.9)
    ic.poly([(5, 6), (6, 21.5), (18, 21.5), (19, 6)])
    ic.line((10, 10), (10, 17))
    ic.line((14, 10), (14, 17))


def i_copy(ic):
    ic.rrect(9, 9, 21, 21, 2)
    ic.poly([(5.5, 15), (3.5, 15), (3.5, 3.5), (15, 3.5), (15, 5.5)])


def i_refresh(ic):
    ic.arc(12, 12, 8.5, -40, 170)
    ic.poly([(3.6, 16.5), (3.6, 11.2)])
    ic.line((3.6, 16.6), (8.9, 16.6))
    ic.arc(12, 12, 8.5, 140, 350)
    ic.line((20.4, 7.4), (20.4, 12.7))
    ic.line((20.4, 7.4), (15.1, 7.4))


def i_history(ic):
    ic.arc(12, 12, 9, -55, 265)                 # open circle
    ic.poly([(3.2, 3.5), (3.2, 8.8), (8.5, 8.8)])
    ic.poly([(12, 7), (12, 12), (16, 14)])       # clock hands


def i_download(ic):
    ic.line((12, 3), (12, 15))
    ic.poly([(7, 10.5), (12, 15.5), (17, 10.5)])
    ic.poly([(3, 16), (3, 20), (21, 20), (21, 16)], w=STROKE * 0.95)


def i_upload(ic):
    ic.line((12, 15.5), (12, 3.5))
    ic.poly([(7, 8), (12, 3), (17, 8)])
    ic.poly([(3, 16), (3, 20), (21, 20), (21, 16)], w=STROKE * 0.95)


def i_moon(ic):
    # crescent: outer circle arc from top to right + inner bite arc
    ic.arc(12, 12, 9, 90, 360)
    ic.arc(18, 6, 6.7, -63.4, -206.6)


def i_sun(ic):
    ic.circle(12, 12, 4)
    for k in range(8):
        t = math.radians(k * 45)
        x1 = 12 + 7.2 * math.cos(t)
        y1 = 12 + 7.2 * math.sin(t)
        x2 = 12 + 9.5 * math.cos(t)
        y2 = 12 + 9.5 * math.sin(t)
        ic.line((x1, y1), (x2, y2))


def i_shield_alert(ic):
    ic.poly([(12, 2.5), (4, 5.5), (4, 11)])
    ic.arc(13.2, 11, 9.2, 180, 262, steps=40)
    ic.poly([(12, 2.5), (20, 5.5), (20, 11)])
    ic.arc(10.8, 11, 9.2, 278, 360, steps=40)
    ic.line((12, 8), (12, 13))
    ic.line((12, 16.6), (12, 16.7), w=STROKE * 1.2)


def i_heart_pulse(ic):
    ic.arc(7.75, 8.5, 4.6, 25, 215)
    ic.arc(16.25, 8.5, 4.6, -35, 155)
    ic.poly([(3.6, 11.5), (7.2, 15.1)])
    ic.poly([(20.4, 11.5), (12, 19.9)])
    ic.line((12, 19.9), (7.2, 15.1))
    ic.poly([(3.4, 12), (8, 12), (10, 9), (13, 15), (15, 12), (20.6, 12)],
            w=STROKE * 0.9)


def i_lock(ic):
    ic.rrect(4.5, 11, 19.5, 21.5, 2)
    ic.line((8, 11), (8, 7.5))
    ic.line((16, 11), (16, 7.5))
    ic.arc(12, 7.5, 4, 0, 180)
    ic.line((12, 15.2), (12, 17.2))


def i_lock_open(ic):
    ic.rrect(4.5, 11, 19.5, 21.5, 2)
    ic.line((8, 11), (8, 6.5))
    ic.arc(12.5, 6.5, 4.5, 25, 180)
    ic.line((12, 15.2), (12, 17.2))


def i_undo(ic):
    ic.poly([(9, 14), (4, 9), (9, 4)])
    ic.line((4, 9), (14.5, 9))
    ic.arc(14.5, 14.5, 5.5, 90, -90)
    ic.line((14.5, 20), (11, 20))


def i_redo(ic):
    ic.poly([(15, 14), (20, 9), (15, 4)])
    ic.line((20, 9), (9.5, 9))
    ic.arc(9.5, 14.5, 5.5, 90, 270)
    ic.line((9.5, 20), (13, 20))


def i_key_round(ic):
    ic.circle(7.5, 15.5, 4.5)
    ic.line((11, 12), (20.5, 2.5))
    ic.line((15.5, 7.5), (18.5, 10.5))


def i_info(ic):
    ic.circle(12, 12, 9.5)
    ic.line((12, 11), (12, 16.5))
    ic.line((12, 7.6), (12, 7.7), w=STROKE * 1.15)


ICONS = {
    "plus": i_plus, "save": i_save, "trash-2": i_trash,
    "copy": i_copy, "lock": i_lock, "lock-open": i_lock_open,
    "refresh-cw": i_refresh, "history": i_history,
    "download": i_download, "upload": i_upload,
    "moon": i_moon, "sun": i_sun,
    "undo-2": i_undo, "redo-2": i_redo, "key-round": i_key_round,
    "info": i_info,
    "shield-alert": i_shield_alert, "heart-pulse": i_heart_pulse,
}

# color variants: name -> (light-mode color, dark-mode color)
GHOST = ("#53535F", "#D3D3D9")
WHITE = ("#FFFFFF", "#FFFFFF")
DANGER = ("#B3261E", "#F87171")
VARIANTS = {name: GHOST for name in ICONS}
VARIANTS["plus"] = WHITE
VARIANTS["save"] = WHITE
VARIANTS["trash-2"] = DANGER

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
os.makedirs(OUT, exist_ok=True)

for name, fn in ICONS.items():
    light, dark = VARIANTS[name]
    for variant, color in (("light", light), ("dark", dark)):
        ic = Icon()
        fn(ic)
        ic.render(os.path.join(OUT, f"{name}_{variant}.png"), color)

print("wrote", len(os.listdir(OUT)), "icons to", OUT)
