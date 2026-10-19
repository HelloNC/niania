"""Parametric 2-D cel character ("bust" rig), drawn with polygons from a JSON spec.

Units: origin = neck base, y down. Head ~ 370 units tall (chin -100, crown -470), shoulders +-235.
Everything is vector + flat cel shading + dark linework, so it reads like an anime/cartoon turnaround.
Spec keys (all optional; see reference/characters.md):
  skin, skin_shade, line, hair{style,color,highlight,seed,part}, brows, eyes{iris,shape},
  glasses{style,color}, facial_hair, top{style,color,shade}, outer{style,color,shade},
  accessories[...], stethoscope_color, mug_color, badge_color, earrings
"""
import math, random
from geo import (bez, mirror, ellipse_pts, rot, off, strip, smooth, lerp, hexrgb, shade, mixc)

DEFAULT = {
    'skin': '#f0ccaa', 'skin_shade': None, 'line': '#151b2e', 'lips': '#a0524a',
    'hair': {'style': 'short', 'color': '#2a2230', 'highlight': None, 'seed': 7, 'part': 'left'},
    'brows': None, 'eyes': {'iris': '#4a6280', 'shape': 'normal', 'lashes': False},
    'glasses': {'style': 'none', 'color': '#181f36'}, 'facial_hair': 'none',
    'top': {'style': 'tshirt', 'color': '#5b7fa6'}, 'outer': {'style': 'none', 'color': '#e4e6e4'},
    'accessories': [], 'stethoscope_color': '#ce4238', 'mug_color': '#d94a3c', 'badge_color': '#2d6fd6',
}

# expression presets -> face parameters
EXPR = {
    'neutral':   dict(brow_in=0.0, brow_out=0.0, brow_up=0.0, lid=0.12, wide=0.0, smile=0.0, open=0.0, oshape=0.0),
    'smile':     dict(brow_in=0.1, brow_out=0.15, brow_up=0.1, lid=0.25, wide=0.0, smile=1.0, open=0.0, oshape=0.0),
    'happy':     dict(brow_in=0.2, brow_out=0.2, brow_up=0.3, lid=0.15, wide=0.1, smile=1.0, open=0.35, oshape=0.0),
    'laugh':     dict(brow_in=0.2, brow_out=0.2, brow_up=0.3, lid=0.85, wide=0.0, smile=1.0, open=0.7, oshape=0.0),
    'worried':   dict(brow_in=0.9, brow_out=-0.2, brow_up=0.1, lid=0.2, wide=0.0, smile=-0.35, open=0.0, oshape=0.0),
    'sad':       dict(brow_in=1.0, brow_out=-0.4, brow_up=0.0, lid=0.4, wide=0.0, smile=-0.7, open=0.0, oshape=0.0),
    'surprised': dict(brow_in=0.3, brow_out=0.4, brow_up=1.0, lid=0.0, wide=1.0, smile=0.0, open=0.55, oshape=1.0),
    'exhausted': dict(brow_in=0.4, brow_out=-0.3, brow_up=-0.1, lid=0.55, wide=0.0, smile=-0.4, open=0.0, oshape=0.0),
    'angry':     dict(brow_in=-1.0, brow_out=0.3, brow_up=-0.3, lid=0.3, wide=0.0, smile=-0.5, open=0.1, oshape=0.0),
    'focused':   dict(brow_in=-0.35, brow_out=0.0, brow_up=-0.15, lid=0.3, wide=0.0, smile=0.0, open=0.0, oshape=0.0),
    'thinking':  dict(brow_in=0.4, brow_out=-0.1, brow_up=0.2, lid=0.3, wide=0.0, smile=-0.1, open=0.0, oshape=0.0),
}

# arm poses: elbow, wrist (units, for the screen-right arm; mirrored for the left), hand shape
POSES = {
    'rest':       ((262, 400), (276, 690), 'none'),
    'open_palm':  ((332, 270), (386, 20), 'open'),
    'point':      ((336, 290), (450, 150), 'point'),
    'wave':       ((340, 230), (400, -40), 'open'),
    'hold_mug':   ((262, 400), (150, 250), 'mug'),
    'chin':       ((230, 330), (70, -70), 'fist'),
    'present':    ((300, 330), (420, 300), 'open_up'),
    'shrug':      ((330, 320), (420, 220), 'open_up'),
    'chest':      ((250, 360), (90, 200), 'open'),
}


def merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = dict(out[k], **v)
        else:
            out[k] = v
    return out


class Look:
    """resolved colours for one character."""

    def __init__(self, spec):
        sp = merge(DEFAULT, spec)
        self.sp = sp
        c = hexrgb
        self.line = c(sp['line'])
        self.skin = c(sp['skin'])
        self.skin_sh = c(sp['skin_shade']) if sp.get('skin_shade') else shade(self.skin, 0.86)
        h = sp['hair']
        self.hair = c(h['color'])
        self.hair_hi = c(h['highlight']) if h.get('highlight') else shade(self.hair, 1.35)
        self.hair_sh = shade(self.hair, 0.6)
        self.brow = c(sp['brows']) if sp.get('brows') else self.hair
        self.iris = c(sp['eyes'].get('iris', '#4a6280'))
        self.lips = c(sp['lips'])
        t = sp['top']
        self.top = c(t['color'])
        self.top_sh = c(t['shade']) if t.get('shade') else shade(self.top, 0.78)
        o = sp['outer']
        self.outer = c(o['color'])
        self.outer_sh = c(o['shade']) if o.get('shade') else mixc(shade(self.outer, 0.8), (110, 140, 170), 0.18)
        self.outer_sh2 = shade(self.outer_sh, 0.85)
        self.glass = c(sp['glasses'].get('color', '#181f36'))
        self.steth = c(sp['stethoscope_color'])
        self.mug = c(sp['mug_color'])
        self.badge = c(sp['badge_color'])
        self.metal, self.metal_sh = (200, 206, 212), (120, 128, 138)
        r = random.Random(h.get('seed', 7))
        self.spikes = [(r.uniform(-0.14, 0.14), r.uniform(0.86, 1.22)) for _ in range(19)]
        self.fringe = []
        part = -40 if h.get('part', 'left') == 'left' else 40
        sgn = 1 if part < 0 else -1
        for k in range(12):
            x0 = -128 + k * 23 + r.uniform(-4, 4)
            y0 = -392 + abs(x0 - part) * 0.12
            tx = x0 + sgn * (22 + r.uniform(0, 26))
            ty = -282 - r.uniform(0, 34) - (12 if abs(tx) < 20 else 0)
            self.fringe.append((x0, y0, tx, ty, sgn * (0.25 + r.uniform(-0.1, 0.25)), r.uniform(46, 64)))
        self.curls = [(r.uniform(0, 2 * math.pi), r.uniform(0.9, 1.1)) for _ in range(16)]

    @property
    def sleeve(self):
        return (self.outer, self.outer_sh) if self.sp['outer']['style'] != 'none' else (self.top, self.top_sh)


# ------------------------------------------------------------------ head
def head_x(st):
    """unit-space transform for head features: yaw squeeze + shift."""
    yaw = st.get('yaw', 0.0)

    def fx(x):
        return x * (1 - 0.14 * abs(yaw)) + yaw * 26
    return fx


def draw_hair_back(c, L, st):
    h = L.sp['hair']
    style = h.get('style', 'short')
    sway = st.get('sway', 0.0)
    yaw = st.get('yaw', 0.0)
    dx = -yaw * 8
    if style in ('bald', 'none'):
        return
    if style == 'long':
        back = [(-150 + dx, -300), (-178 + dx, -120), (-190 + dx, 40), (-150 + dx, 120), (150 + dx, 120), (190 + dx, 40),
                (178 + dx, -120), (150 + dx, -300)]
        c.shape(back, L.hair, L.line, 2.6)
    if style == 'messy':
        pts = []
        n = len(L.spikes)
        for k in range(n + 1):
            a = math.pi * (1.0 + k / n)
            jit, ln = L.spikes[k % n]
            rx, ry = 158, 200
            base = (rx * math.cos(a) + dx, -290 + ry * math.sin(a))
            tip = (1.16 * ln * rx * math.cos(a + jit) + sway * 4 + dx, -290 + 1.12 * ln * ry * math.sin(a + jit))
            if k:
                pts.append(tip)
            pts.append(base)
        pts = [(-150 + dx, -205)] + pts + [(150 + dx, -205), (130 + dx, -175), (-130 + dx, -175)]
        c.shape(pts, L.hair, L.line, 3.0)
    elif style == 'curly':
        for a, k in L.curls:
            x = 150 * math.cos(math.pi * (1 + a / (2 * math.pi))) * k + dx
            y = -300 + 180 * math.sin(math.pi * (1 + a / (2 * math.pi))) * k
            c.shape(ellipse_pts(x, y, 52, 52, 20), L.hair, L.line, 2.4)
        c.shape(ellipse_pts(dx, -330, 150, 140, 36), L.hair, None)
    else:   # short / long / bun: smooth cap
        cap = bez((-150 + dx, -220), (-170 + dx, -470), (170 + dx, -470), (150 + dx, -220), 22)
        c.shape(cap + [(130 + dx, -190), (-130 + dx, -190)], L.hair, L.line, 2.8)
        if style == 'bun':
            c.shape(ellipse_pts(dx * 1.5, -470, 66, 58, 28), L.hair, L.line, 2.6)
            c.poly(bez((-40 + dx, -480), (-10, -500), (20, -500), (40 + dx, -470), 8), L.hair_sh, 2.4)


def draw_hair_front(c, L, st):
    h = L.sp['hair']
    style = h.get('style', 'short')
    sway = st.get('sway', 0.0)
    yaw = st.get('yaw', 0.0)
    dx = yaw * 18
    if style in ('bald', 'none'):
        return
    for sx in (-1, 1):
        if style in ('messy', 'short', 'bun', 'curly'):
            lock = [(sx * 112 + dx, -340), (sx * 152 + dx * 0.5, -300), (sx * 150 + dx * 0.5, -235),
                    (sx * 146 + dx * 0.5, -205 if style == 'messy' else -225), (sx * 132 + dx * 0.5, -240),
                    (sx * 120 + dx * 0.5, -262)]
            c.shape(lock, L.hair, L.line, 2.4)
        if style == 'long':
            curtain = [(sx * 110 + dx, -360), (sx * 158 + dx * 0.5, -300), (sx * 168 + dx * 0.4, -120),
                       (sx * 160 + dx * 0.3, 60 + sway * 3), (sx * 128 + dx * 0.3, 40), (sx * 122 + dx * 0.4, -150),
                       (sx * 112 + dx * 0.5, -270)]
            c.shape(curtain, L.hair, L.line, 2.6)
    if style == 'messy':
        for x0, y0, x1, y1, bend, wd in L.fringe:
            tipx = x1 + sway * 5 + dx
            path = bez((x0 + dx * 0.6, y0), (x0 + bend * 20 + dx * 0.6, y0 + 40), (tipx - bend * 30, y1 - 34), (tipx, y1), 12)
            c.shape(strip(path, wd, 1.5), L.hair, L.line, 2.2)
            c.poly(path[3:-3], L.hair_sh, 2.0)
        cap = bez((-140 + dx * 0.5, -330), (-110, -420), (110, -425), (140 + dx * 0.5, -330), 16) + \
            [(110, -350), (0, -372), (-110, -350)]
        c.shape(cap, L.hair, None)
        band = bez((-96, -428), (-40, -452), (40, -452), (96, -426), 14)
        c.shape(strip(band, 9, 9), L.hair_hi, None)
    elif style == 'curly':
        for k in range(7):
            x = -110 + k * 37 + dx
            c.shape(ellipse_pts(x, -340 + (k % 2) * 12, 34, 30, 18), L.hair, L.line, 2.2)
    else:
        # swept fringe for short / long / bun
        part = -40 if h.get('part', 'left') == 'left' else 40
        sg = 1 if part < 0 else -1
        fr = bez((part + dx, -400), (part + sg * 90 + dx, -395), (sg * 140 + dx, -350), (sg * 132 + dx, -300), 14)
        fr += bez((sg * 132 + dx, -300), (sg * 80 + dx, -330), (part - sg * 60 + dx, -340), (-sg * 140 + dx, -312), 14)
        fr += [(-sg * 150 + dx, -380), (part + dx, -420)]
        c.shape(fr, L.hair, L.line, 2.4)
        band = bez((-90 + dx, -420), (-30, -446), (40, -446), (96 + dx, -420), 14)
        c.shape(strip(band, 8, 8), L.hair_hi, None)


def draw_face(c, L, st):
    fx = head_x(st)
    yaw = st.get('yaw', 0.0)
    e = st['expr']
    sp = L.sp

    def F(pts):
        return [(fx(x), y) for x, y in pts]
    # ears (the far ear hides as the head turns)
    for sx in (-1, 1):
        vis = 1 - max(0.0, sx * yaw) * 1.6
        if vis <= 0.1:
            continue
        ex = sx * (116 + 4 * (1 - vis))
        ear = bez((ex, -272), (ex + sx * 30 * vis, -276), (ex + sx * 34 * vis, -222), (ex - sx * 4, -214), 10)
        c.shape(F(ear), L.skin, L.line, 2.4)
    left = bez((-120, -310), (-128, -250), (-122, -196), (-100, -160), 12) + \
        bez((-100, -160), (-78, -128), (-38, -104), (0, -101), 12)[1:]
    outline = left + mirror(left[::-1])[1:]
    c.shape(F(outline + [(118, -330), (-118, -330)]), L.skin, L.line, 2.8)
    # cel shadow on the far cheek (key light from screen-left)
    sh = bez((122, -300), (126, -245), (118, -196), (98, -162), 10) + [(70, -150), (92, -200), (100, -260)]
    c.shape(F(sh), L.skin_sh, None)
    # facial hair
    fh = sp.get('facial_hair', 'none')
    if fh in ('stubble', 'beard'):
        rr = random.Random(3)
        for k in range(70 if fh == 'stubble' else 0):
            a = rr.uniform(0.15, math.pi - 0.15)
            r_ = rr.uniform(0.75, 0.98)
            x, y = 92 * r_ * math.cos(a), -150 + 48 * r_ * math.sin(a)
            if abs(x) < 26 and -160 < y < -138:
                continue
            c.dot(fx(x), y, 0.9, (90, 80, 90, 70))
        if fh == 'beard':
            beard = bez((-104, -190), (-100, -120), (-50, -86), (0, -84), 12) + mirror(bez((0, -84), (-50, -86), (-100, -120), (-104, -190), 12))[1:]
            beard += [(70, -170), (30, -135), (0, -132), (-30, -135), (-70, -170)]
            c.shape(F(beard), L.hair, L.line, 2.0)
    # nose
    c.poly(F([(-2, -214), (6 + yaw * 6, -190), (-4, -184)]), shade(L.skin, 0.62), 2.2)
    # mouth: expression smile + lip-sync opening
    op = max(st.get('mouth', 0.0), e['open'])
    sm = e['smile']
    mx = yaw * 6
    if op < 0.08:
        cy = -148
        pts = bez((-26 + mx, cy - 7 * sm), (-9 + mx, cy + 4 * sm), (9 + mx, cy + 4 * sm), (26 + mx, cy - 7 * sm), 10)
        c.poly(F(pts), shade(L.lips, 0.7), 2.6)
    else:
        w = 22 - 8 * e['oshape']
        hgt = 4 + 18 * op
        top = bez((-w + mx, -150 - 4 * sm), (-8 + mx, -153), (8 + mx, -153), (w + mx, -150 - 4 * sm), 8)
        bot = bez((w + mx, -150 - 4 * sm), (10 + mx, -150 + hgt), (-10 + mx, -150 + hgt), (-w + mx, -150 - 4 * sm), 8)
        c.shape(F(top + bot[1:]), (70, 28, 30), shade(L.lips, 0.7), 2.0)
        if op > 0.35 and e['oshape'] < 0.5:
            c.shape(F([(-12 + mx, -150), (12 + mx, -150), (10 + mx, -146), (-10 + mx, -146)]), (236, 232, 228), None)
    # eyes
    shape_k = {'tired': 0.25, 'round': -0.2, 'sharp': 0.15}.get(sp['eyes'].get('shape', 'normal'), 0.0)
    lid = min(1.0, e['lid'] + shape_k + st.get('blink', 0.0) * (1 - e['lid']))
    for sx in (-1, 1):
        cx, cy = sx * 58, -236
        sq = 1 - 0.3 * max(0.0, sx * yaw)           # far eye foreshortened
        def E(pts):
            return [(fx(cx + (x - cx) * sq), y) for x, y in pts]
        open_h = 14 + 6 * e['wide']
        up_y = cy - open_h + (open_h + 2) * lid
        if lid > 0.88:
            arc = 6 if e['smile'] > 0.5 else -2
            c.poly(E(bez((cx - 30, cy), (cx - 10, cy - arc), (cx + 10, cy - arc), (cx + 30, cy - 2), 8)), L.line, 4.0)
        else:
            upper = bez((cx - 30, cy), (cx - 14, up_y - 2), (cx + 12, up_y - 2), (cx + 30, cy - 4), 10)
            lower = bez((cx + 28, cy - 2), (cx + 12, cy + 12 + 4 * e['wide']), (cx - 12, cy + 12 + 4 * e['wide']),
                        (cx - 28, cy + 1), 10)
            c.shape(E(upper + lower[1:]), (246, 246, 244), None)
            lx, ly = st.get('look', (0.0, 0.0))
            ix = cx + lx * 9 + yaw * 6
            iy = cy + 1 + ly * 4
            ry = max(4, 13 - 9 * lid)
            c.shape(E(ellipse_pts(ix, iy, 11, ry)), L.iris, None)
            c.shape(E(ellipse_pts(ix, iy + 1, 5.5, min(ry, 7))), (14, 18, 30), None)
            c.dot(fx(cx + (ix - 4 - cx) * sq), iy - 5, 2.6, (255, 255, 255, 230))
            lidp = bez((cx - 34, cy - 2), (cx - 14, up_y - 4), (cx + 12, up_y - 4), (cx + 34, cy - 6), 10) + \
                [(cx + 34, cy - 34), (cx - 34, cy - 34)]
            c.shape(E(lidp), L.skin, None)
            c.poly(E(upper), L.line, 4.6)
            if sp['eyes'].get('lashes'):
                c.poly(E([(cx + 28 * sx * 0 + 28, cy - 6), (cx + 38, cy - 12)]), L.line, 3.0)
            c.poly(E(lower[2:-2]), shade(L.skin, 0.55), 1.6)
        # brows
        bi, bo, bu = e['brow_in'], e['brow_out'], e['brow_up']
        p_in = (cx - sx * 32, -276 - 8 * bi - 10 * bu)
        p_out = (cx + sx * 34, -282 - 6 * bo - 10 * bu)
        brow = strip(bez(p_in, (cx - sx * 10, -286 - 6 * bi - 10 * bu), (cx + sx * 14, -288 - 4 * bo - 10 * bu), p_out, 8), 8, 3)
        c.shape(E(brow), L.brow, None)
    # glasses
    gs = sp['glasses'].get('style', 'none')
    if gs != 'none':
        for sx in (-1, 1):
            sq = 1 - 0.3 * max(0.0, sx * yaw)
            gx, gy = sx * 60, -240
            if gs == 'round':
                r = ellipse_pts(gx, gy, 44, 40, 32)
            else:
                r = [(gx - 50, gy - 27), (gx + 50, gy - 27), (gx + 50, gy + 25), (gx - 50, gy + 25)]
            r = [(fx(gx + (x - gx) * sq), y) for x, y in r]
            c.shape(r, (200, 225, 240, 26), L.glass, 5.2)
            c.poly([(fx(gx - 22 * sq), gy - 18), (fx(gx - 12 * sq), gy + 12)], (255, 255, 255, 60), 3)
            if max(0.0, sx * yaw) < 0.5:
                c.poly(F([(sx * 110, -258), (sx * 124, -256)]), L.glass, 4.5)
        c.poly(F([(-10, -246), (0, -250), (10, -246)]), L.glass, 4.0)


# ------------------------------------------------------------------ ball head ("head": {"shape": "ball"})
BALL_R = 250
BALL_CY = -330


def is_ball(L):
    return (L.sp.get('head') or {}).get('shape') == 'ball'


def draw_ball_face(c, L, st):
    """big sphere head, no ears/nose, dot eyes, bar brows (designer-toy style)."""
    yaw = st.get('yaw', 0.0)
    e = st['expr']
    R = (L.sp.get('head') or {}).get('r', BALL_R)
    cy = -110 - R * 0.88

    def fx(x):
        return x * (1 - 0.18 * abs(yaw)) + yaw * 64
    # sphere: shade disc, lit disc offset to the key light (screen-left/top), soft highlight, outline
    c.shape(ellipse_pts(0, cy, R, R, 72), L.skin_sh, None)
    c.shape(ellipse_pts(-16, cy - 14, R * 0.92, R * 0.93, 72), L.skin, None)
    c.shape(ellipse_pts(-70, cy - 90, R * 0.34, R * 0.26, 36), mixc(L.skin, (255, 255, 255), 0.35) + (110,), None)
    c.shape(ellipse_pts(0, cy, R, R, 72), None, L.line, 3.0)
    # eyes: solid dark ovals that squash with the lid
    base = max(0.0, e['lid'] - 0.12) / 0.88
    lid = min(1.0, base + st.get('blink', 0.0) * (1 - base))
    lx, ly = st.get('look', (0.0, 0.0))
    for sx in (-1, 1):
        ex, ey = sx * 70 + lx * 10, cy + 40 + ly * 6
        sq = 1 - 0.3 * max(0.0, sx * yaw)
        hh = 21 * (1 + 0.3 * e['wide']) * (1 - lid)
        if lid > 0.8:
            arc = 7 if e['smile'] > 0.5 else -3
            path = bez((ex - 16, ey), (ex - 6, ey - arc), (ex + 6, ey - arc), (ex + 16, ey), 8)
            c.poly([(fx(ex + (x - ex) * sq), y) for x, y in path], L.line, 5.0)
        else:
            c.shape([(fx(ex + (x - ex) * sq), y) for x, y in ellipse_pts(ex, ey, 14, max(3.0, hh * 1.1), 24)], L.line, None)
            c.dot(fx(ex - 4 * sq), ey - hh * 0.45, 2.4, (255, 255, 255, 150))
        # thick rounded bar brows
        bi, bo, bu = e['brow_in'], e['brow_out'], e['brow_up']
        p_in = (sx * 34, cy - 34 - 12 * bi - 14 * bu)
        p_out = (sx * 112, cy - 40 - 8 * bo - 14 * bu)
        mid = ((p_in[0] + p_out[0]) / 2, (p_in[1] + p_out[1]) / 2 - 6)
        path = bez(p_in, mid, mid, p_out, 10)
        pts = [(fx(sx * 72 + (x - sx * 72) * sq), y) for x, y in path]
        c.poly(pts, L.brow, 19)
        for q in (pts[0], pts[-1]):
            c.dot(q[0], q[1], 9.5, L.brow)
    # mouth: tiny line / small dark "o"
    op = max(st.get('mouth', 0.0), e['open'])
    sm = e['smile']
    my = cy + 118
    mx = yaw * 6 + lx * 4
    if op < 0.08:
        w = 15
        pts = bez((-w + mx, my - 5 * sm), (-5 + mx, my + 4 * sm), (5 + mx, my + 4 * sm), (w + mx, my - 5 * sm), 10)
        c.poly([(fx(x), y) for x, y in pts], L.line, 3.6)
    else:
        w = 12 - 4 * e['oshape'] + 4 * (1 - e['oshape']) * op
        h = 4 + 15 * op
        c.shape([(fx(x), y) for x, y in ellipse_pts(mx, my + h * 0.3, w, h, 24)], (58, 26, 28), L.line, 2.2)


def draw_funnel_back(c, L):
    """inside of the high stand collar (behind the head)."""
    inner = shade(L.top, 0.45)
    c.shape([(-150, -150), (150, -150), (120, 0), (-120, 0)], inner, L.line, 2.6)


def draw_funnel_front(c, L, st):
    br = st.get('breath', 0.0)
    left = [(-170, 26 + br), (-178, -150), (-150, -146), (-70, -118), (-16, -96), (-8, -30), (-70, 10 + br)]
    for sx in (-1, 1):
        pts = [(-sx * x, y) for x, y in left] if sx > 0 else left
        c.shape(pts, L.top if sx < 0 else L.top_sh, L.line, 2.8)
        c.poly([(sx * 140, -120), (sx * 132, 0)], shade(L.top, 0.72), 4)
    c.shape([(-14, -86), (0, -100), (14, -86), (8, -30), (0, -18), (-8, -30)], shade(L.top, 0.35), L.line, 2.0)


# ------------------------------------------------------------------ body
def draw_body(c, L, st):
    sp = L.sp
    br = st.get('breath', 0.0)
    top_style = sp['top'].get('style', 'tshirt')
    outer = sp['outer'].get('style', 'none')
    acc = set(sp.get('accessories', []))
    # hood / collar behind the neck
    if top_style == 'hoodie':
        c.shape(bez((-150, 30), (-160, -120), (160, -120), (150, 30), 16), L.top_sh, L.line, 2.6)
    if outer in ('labcoat', 'jacket', 'blazer'):
        c.shape([(-78, -20), (-60, -62), (60, -62), (78, -20)], L.outer_sh, L.line, 2.4)
    if top_style == 'funnel':
        draw_funnel_back(c, L)
    if not is_ball(L):
        # neck
        c.shape([(-46, -140), (46, -140), (54, 4), (-54, 4)], L.skin, L.line, 2.4)
        c.shape([(-46, -132), (46, -132), (40, -98), (0, -84), (-40, -98)], L.skin_sh, None)
    # torso
    base, base_sh = (L.outer, L.outer_sh) if outer != 'none' else (L.top, L.top_sh)
    torso = bez((-62, -18 + br), (-150, 8), (-210, 28 + br), (-232, 70 + br), 10) + \
        [(-238, 360), (-246, 760), (246, 760), (238, 360)] + \
        bez((232, 70 + br), (210, 28 + br), (150, 8), (62, -18 + br), 10)
    c.shape(torso, base, L.line, 3.0)
    c.shape([(-232, 70 + br), (-238, 360), (-246, 760), (-200, 760), (-196, 300), (-190, 110)], base_sh, None)
    # top (visible inside an open outer layer, or as the whole torso)
    if outer != 'none':
        c.shape([(-64, -6), (-34, 760), (34, 760), (64, -6), (0, 24)], L.top, L.line, 2.4)
        c.shape([(-64, -6), (-48, 330), (-34, 760), (-4, 760), (-20, 300)], L.top_sh, None)
    if top_style == 'vneck':
        c.shape([(-50, -4), (0, 112), (50, -4)], L.skin, L.line, 2.2)
        c.shape([(-30, -2), (0, 70), (30, -2), (0, 20)], L.skin_sh, None)
        c.poly([(-56, -6), (0, 120), (56, -6)], L.top_sh, 6)
    elif top_style in ('tshirt', 'hoodie'):
        c.shape(bez((-52, -8), (-40, 40), (40, 40), (52, -8), 10), L.skin, L.line, 2.2)
        c.poly(bez((-56, -8), (-42, 46), (42, 46), (56, -8), 10), L.top_sh, 7)
        if top_style == 'hoodie':
            for sx in (-1, 1):
                c.poly([(sx * 30, 40), (sx * 34, 200)], (235, 235, 235), 4)
    elif top_style == 'shirt_tie':
        for sx in (-1, 1):
            c.shape([(sx * 8, -6), (sx * 56, -20), (sx * 64, 26), (sx * 14, 40)], (240, 242, 245), L.line, 2.0)
        c.shape([(-14, 30), (14, 30), (24, 300), (0, 340), (-24, 300)], hexrgb(sp['top'].get('tie', '#7a1f2b')), L.line, 2.0)
        c.shape([(-16, 2), (16, 2), (14, 32), (-14, 32)], hexrgb(sp['top'].get('tie', '#7a1f2b')), L.line, 2.0)
    # open outer layer: lapels
    if outer in ('labcoat', 'jacket', 'blazer'):
        for sx in (-1, 1):
            lap = [(sx * 62, -18 + br), (sx * 104, 46), (sx * 82, 110), (sx * 98, 150), (sx * 46, 420), (sx * 38, 760),
                   (sx * 66, 760), (sx * 76, 420)]
            c.shape(lap, L.outer, L.line, 2.6)
            c.poly([(sx * 98, 150), (sx * 112, 330), (sx * 104, 760)], L.outer_sh, 3)
    if 'pen_pocket' in acc or outer == 'labcoat':
        c.shape([(118, 200), (200, 196), (204, 268), (122, 272)], None, L.line, 2.2)
        if 'pen_pocket' in acc:
            for px, col in ((140, (30, 34, 52)), (156, (190, 60, 52))):
                c.shape([(px, 166), (px + 9, 166), (px + 9, 206), (px, 206)], col, L.line, 1.6)
    if 'badge' in acc:
        c.shape([(-200, 190), (-130, 186), (-128, 280), (-198, 284)], (245, 245, 245), L.line, 2.0)
        c.shape([(-196, 192), (-132, 188), (-132, 212), (-196, 216)], L.badge, None)
        c.poly([(-165, 186), (-160, 120)], L.line, 2)
    if 'stethoscope' in acc:
        lp = bez((-56, -26), (-92, 30), (-104, 140), (-96, 238), 16)
        rp = bez((56, -26), (90, 30), (98, 130), (92, 210), 16)
        for path in (lp, rp):
            c.poly(path, L.line, 17)
            c.poly(path, L.steth, 12)
            c.poly(off(path, 2, 0), shade(L.steth, 0.72), 3)
        c.shape(ellipse_pts(-96, 262, 27, 27), L.metal, L.line, 3)
        c.shape(ellipse_pts(-96, 262, 17, 17), L.metal_sh, L.line, 2)
        c.dot(-102, 254, 4, (255, 255, 255, 200))
        for dx, ex in ((-6, 76), (6, 112)):
            path = bez((92, 210), (92 + dx, 230), (ex - 4, 250), (ex, 272), 8)
            c.poly(path, L.line, 9)
            c.poly(path, L.metal, 6)
            c.dot(ex, 276, 7, (40, 44, 60))


def draw_hand(c, L, wr, ang, shape, arm):
    if shape == 'none':
        return
    sk = L.skin
    if shape in ('open', 'open_up'):
        tilt = -math.radians(25) if shape == 'open' else math.radians(60)
        a = ang + tilt
        palm = off(rot([(0, -26), (54, -30), (62, 22), (0, 26)], a), *wr)
        c.shape(palm, sk, L.line, 2.4)
        for fy, ln in ((-24, 40), (-9, 46), (6, 44), (19, 36)):
            f = rot([(56, fy - 6), (56 + ln, fy - 9), (56 + ln, fy), (56, fy + 6)], a)
            c.shape(off(f, *wr), sk, L.line, 2.0)
        th = rot([(18, -26), (40, -58), (52, -52), (36, -22)], a)
        c.shape(off(th, *wr), sk, L.line, 2.0)
    elif shape == 'point':
        a = ang
        fist = off(rot([(0, -24), (50, -26), (56, 22), (0, 26)], a), *wr)
        c.shape(fist, sk, L.line, 2.4)
        f = off(rot([(50, -24), (110, -22), (110, -10), (50, -8)], a), *wr)
        c.shape(f, sk, L.line, 2.0)
    elif shape in ('fist', 'mug'):
        fist = off(rot([(0, -26), (50, -28), (58, 24), (0, 28)], ang), *wr)
        c.shape(fist, sk, L.line, 2.4)
        for k in range(3):
            c.poly(off(rot([(50, -14 + k * 14), (58, -14 + k * 14)], ang), *wr), shade(sk, 0.6), 2)


def draw_mug(c, L, wr):
    x, y = wr[0] - 70, wr[1] - 60
    body = [(x - 46, y - 52), (x + 46, y - 52), (x + 42, y + 58), (x - 42, y + 58)]
    c.shape(body, L.mug, L.line, 2.6)
    c.shape([(x + 10, y - 52), (x + 46, y - 52), (x + 42, y + 58), (x + 14, y + 58)], shade(L.mug, 0.8), None)
    c.shape(ellipse_pts(x, y - 52, 46, 10), shade(L.mug, 0.6), L.line, 2.2)
    c.poly(bez((x + 44, y - 30), (x + 82, y - 30), (x + 82, y + 30), (x + 42, y + 30), 10), L.line, 16)
    c.poly(bez((x + 44, y - 30), (x + 82, y - 30), (x + 82, y + 30), (x + 42, y + 30), 10), L.mug, 10)


def draw_arm(c, L, sx, el, wr, hand, behind=False):
    col, col_sh = L.sleeve
    short = L.sp['top'].get('sleeves') == 'short' and L.sp['outer']['style'] == 'none'
    if short:
        col, col_sh = L.skin, L.skin_sh
    br = 0
    sh = (sx * 226, 96 + br)
    el = (sx * el[0], el[1])
    wr = (sx * wr[0], wr[1])
    c.shape(ellipse_pts(sh[0] - sx * 6, sh[1] + 6, 48, 44), col, L.line, 3)
    c.shape(strip([sh, el], 112, 98), col, L.line, 3)
    c.shape(strip([el, wr], 98, 86), col, L.line, 3)
    c.shape(ellipse_pts(sh[0] - sx * 6, sh[1] + 6, 45, 41), col, None)
    c.shape(ellipse_pts(el[0], el[1], 47, 47), col, None)
    ox = sx * 30
    c.poly([(sh[0] + ox, sh[1] + 30), (el[0] + ox, el[1]), (wr[0] + ox * 0.8, wr[1])], col_sh, 9)
    ang = math.atan2(wr[1] - el[1], wr[0] - el[0])
    if short:
        mid = (sh[0] + (el[0] - sh[0]) * 0.5, sh[1] + (el[1] - sh[1]) * 0.5)
        c.shape(ellipse_pts(sh[0] - sx * 6, sh[1] + 6, 62, 56), L.top, L.line, 3)
        c.shape(strip([sh, mid], 140, 176), L.top, L.line, 3)
        c.shape(ellipse_pts(sh[0] - sx * 6, sh[1] + 6, 59, 53), L.top, None)
        c.poly([(sh[0] + sx * 40, sh[1] + 20), (mid[0] + sx * 44, mid[1])], L.top_sh, 14)
        draw_hand(c, L, wr, ang, hand, 1.0) if hand != 'mug' else draw_mug(c, L, (wr[0] + (0 if sx > 0 else 140), wr[1]))
        return
    cuff = rot([(wr[0] - 8, wr[1] - 40), (wr[0] + 6, wr[1] - 40), (wr[0] + 6, wr[1] + 40), (wr[0] - 8, wr[1] + 40)],
               ang, wr[0], wr[1])
    c.shape(cuff, col_sh, L.line, 2)
    if hand == 'mug':
        draw_mug(c, L, (wr[0] + (0 if sx > 0 else 140), wr[1]))
    draw_hand(c, L, wr, ang, hand, 1.0)


def draw_character(c, L, st):
    """c: Canvas positioned at the neck base. st: per-frame state from perform.evaluate()."""
    arms = st['arms']
    raised = {s: (arms[s][1][1] < 300) for s in ('L', 'R')}
    # head group rotates about the neck pivot
    tilt = st.get('tilt', 0.0)
    nod = st.get('nod', 0.0)
    base_xf = c.xf

    def hx(pts):
        p = rot(off(pts, 0, nod + 22), tilt, 0, -120)
        return base_xf(p) if base_xf else p
    c.xf = hx
    draw_hair_back(c, L, st)
    c.xf = base_xf
    draw_body(c, L, st)
    for s, sx in (('L', -1), ('R', 1)):
        el, wr, hand = arms[s]
        if not raised[s]:
            draw_arm(c, L, sx, el, wr, hand)
    c.xf = hx
    if is_ball(L):
        draw_ball_face(c, L, st)
    else:
        draw_face(c, L, st)
    draw_hair_front(c, L, st)
    c.xf = base_xf
    if L.sp['top'].get('style') == 'funnel':
        draw_funnel_front(c, L, st)
    for s, sx in (('L', -1), ('R', 1)):
        el, wr, hand = arms[s]
        if raised[s]:
            draw_arm(c, L, sx, el, wr, hand)
