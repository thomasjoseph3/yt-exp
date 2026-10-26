"""Thoma, drawn in code: identical in every video, free, and animatable.

draw(pose, mouth, blink, gesture) returns an RGBA sprite. Shapes are drawn at
2x and downscaled, which gives smooth edges.
"""
import math
from functools import lru_cache

from PIL import Image, ImageDraw

W, H = 600, 900          # sprite size at 1x
SS = 2                    # supersampling factor
INK = (29, 29, 33, 255)
SKIN = (198, 139, 89, 255)
SKIN_DARK = (168, 112, 68, 255)
SHIRT = (244, 241, 232, 255)
VEST = (233, 162, 59, 255)
VEST_DARK = (196, 128, 36, 255)
HAIR = (170, 170, 172, 255)
MOUSTACHE = (58, 56, 58, 255)
MOUTH = (92, 30, 36, 255)
CHALK = (250, 250, 245, 255)
OUT = 5  # outline width at 1x

SHOULDERS = {"left": (185, 440), "right": (415, 440)}
# (elbow, hand) for each arm, per pose. "left" is the viewer's left (towards the board).
POSES = {
    "talk":  {"left": ((150, 640), (185, 800)), "right": ((480, 610), (420, 520))},
    "point": {"left": ((112, 405), (55, 315)), "right": ((450, 640), (415, 800))},
    "think": {"left": ((150, 640), (185, 800)), "right": ((470, 600), (330, 372))},
    "wave":  {"left": ((150, 640), (185, 800)), "right": ((520, 330), (540, 190))},
}


def _p(*xy):
    return [v * SS for v in xy]


def _limbs(d, segments, fill):
    """Draw joined segments [(a, b, width), ...]: all outlines first, then all fills."""
    for pass_ in (0, 1):
        for a, b, width in segments:
            w = width + (0 if pass_ else 2 * OUT)
            colour = fill if pass_ else INK
            d.line(_p(*a, *b), fill=colour, width=w * SS)
            for x, y in (a, b):
                d.ellipse(_p(x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=colour)


def _arm(d, shoulder, elbow, hand, pose, side):
    _limbs(d, [(shoulder, elbow, 58), (elbow, hand, 50)], SHIRT)
    hx, hy = hand
    ex, ey = elbow
    ang = math.atan2(hy - ey, hx - ex)
    fingers = []
    if pose == "point" and side == "left":
        fingers = [(hand, (hx + math.cos(ang) * 50, hy + math.sin(ang) * 50), 17)]
    if pose == "wave" and side == "right":
        fingers = [(hand, (hx + math.cos(ang + k) * 48, hy + math.sin(ang + k) * 48), 14)
                   for k in (-0.55, -0.2, 0.15, 0.5)]
    _limbs(d, fingers + [(hand, hand, 62)], SKIN)
    if side == "right" and pose in ("talk", "point"):  # the chalk
        cx, cy = hx + 14, hy - 30
        d.rounded_rectangle(_p(cx - 8, cy - 26, cx + 8, cy + 8), radius=4 * SS, fill=CHALK, outline=INK, width=3 * SS)


@lru_cache(maxsize=512)
def draw(pose: str = "talk", mouth: int = 0, blink: bool = False, gesture: int = 0) -> Image.Image:
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    arms = {k: list(v) for k, v in POSES.get(pose, POSES["talk"]).items()}
    if pose == "talk":  # small hand movement while talking
        (ex, ey), (hx, hy) = arms["right"]
        dx, dy = math.cos(gesture * 1.1) * 18, math.sin(gesture * 1.3) * 22
        arms["right"] = [(ex + dx / 3, ey + dy / 3), (hx + dx, hy + dy)]

    # torso
    d.rounded_rectangle(_p(150 - OUT, 395 - OUT, 450 + OUT, H + 40), radius=70 * SS, fill=INK)
    d.rounded_rectangle(_p(150, 395, 450, H + 40), radius=70 * SS, fill=SHIRT)
    vest = [(150, 450), (262, 405), (300, 520), (338, 405), (450, 450), (450, H + 40), (150, H + 40)]
    d.polygon([v * SS for xy in vest for v in xy], fill=VEST, outline=INK, width=OUT * SS)
    d.line(_p(300, 520, 300, H), fill=VEST_DARK, width=4 * SS)
    for by in (585, 665, 745):
        d.ellipse(_p(288, by - 10, 312, by + 10), fill=VEST_DARK, outline=INK, width=3 * SS)
    # collar
    d.polygon([v * SS for v in (262, 395, 300, 440, 248, 450)], fill=SHIRT, outline=INK, width=3 * SS)
    d.polygon([v * SS for v in (338, 395, 300, 440, 352, 450)], fill=SHIRT, outline=INK, width=3 * SS)
    # neck
    d.rectangle(_p(272, 345, 328, 405), fill=SKIN, outline=INK, width=OUT * SS)
    d.rectangle(_p(272 + OUT, 345, 328 - OUT, 398), fill=SKIN)

    # arms behind the head only when pointing; otherwise draw after the torso
    for side in ("left", "right"):
        elbow, hand = arms[side]
        if not (pose == "think" and side == "right"):
            _arm(d, SHOULDERS[side], elbow, hand, pose, side)

    # head
    for ex in (178, 422):  # ears
        d.ellipse(_p(ex - 24, 215, ex + 24, 275), fill=SKIN, outline=INK, width=OUT * SS)
    d.ellipse(_p(178, 95, 422, 365), fill=SKIN, outline=INK, width=OUT * SS)
    for x0, x1 in ((168, 216), (384, 432)):  # grey hair on the sides, bald on top
        d.ellipse(_p(x0, 140, x1, 232), fill=HAIR, outline=INK, width=3 * SS)
    d.arc(_p(225, 120, 290, 150), 200, 340, fill=SKIN_DARK, width=3 * SS)  # forehead line

    # eyebrows
    for cx in (252, 348):
        d.arc(_p(cx - 34, 162, cx + 34, 196), 200, 340, fill=MOUSTACHE, width=9 * SS)
    # eyes
    for cx in (252, 348):
        if blink:
            d.line(_p(cx - 11, 228, cx + 11, 228), fill=INK, width=5 * SS)
        else:
            d.ellipse(_p(cx - 13, 214, cx + 13, 242), fill=(255, 255, 255, 255))
            d.ellipse(_p(cx - 8, 220, cx + 8, 238), fill=INK)
            d.ellipse(_p(cx - 1, 222, cx + 4, 227), fill=(255, 255, 255, 255))
    # glasses
    for cx in (252, 348):
        d.ellipse(_p(cx - 40, 188, cx + 40, 268), outline=INK, width=8 * SS)
    d.arc(_p(285, 214, 315, 236), 200, 340, fill=INK, width=7 * SS)
    d.line(_p(212, 222, 190, 214), fill=INK, width=7 * SS)
    d.line(_p(388, 222, 410, 214), fill=INK, width=7 * SS)
    # nose
    d.ellipse(_p(282, 250, 318, 290), fill=SKIN_DARK, outline=INK, width=3 * SS)
    # mouth (behind the moustache)
    mh = (0, 10, 18, 28)[mouth]
    if mh:
        d.ellipse(_p(278, 306, 322, 312 + mh + 6), fill=MOUTH, outline=INK, width=3 * SS)
    else:
        d.arc(_p(282, 300, 318, 322), 20, 160, fill=INK, width=4 * SS)
    # moustache
    d.ellipse(_p(240, 284, 302, 318), fill=MOUSTACHE, outline=INK, width=3 * SS)
    d.ellipse(_p(298, 284, 360, 318), fill=MOUSTACHE, outline=INK, width=3 * SS)
    d.ellipse(_p(278, 286, 322, 310), fill=MOUSTACHE)

    if pose == "think":
        elbow, hand = arms["right"]
        _arm(d, SHOULDERS["right"], elbow, hand, pose, "right")

    return img.resize((W, H), Image.LANCZOS)


@lru_cache(maxsize=1024)
def sprite(pose: str, mouth: int, blink: bool, gesture: int, height: int) -> Image.Image:
    base = draw(pose, mouth, blink, gesture)
    return base.resize((round(W * height / H), height), Image.LANCZOS)
