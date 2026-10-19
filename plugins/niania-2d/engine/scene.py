"""Backgrounds, screen-space graphics, captions, colour grade and transitions (Pillow + numpy)."""
import math, os, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from geo import hexrgb, shade, font, ease_out, smooth, rot, lerp

# ------------------------------------------------------------------ backgrounds


def _grad(w, h, top, bottom):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    a, b = np.array(hexrgb(top), np.float32), np.array(hexrgb(bottom), np.float32)
    return np.broadcast_to(a * (1 - t) + b * t, (h, w, 3)).copy()


def _radial(w, h, inner, outer, center=(0.5, 0.5), radius=0.75):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - center[0] * w) / w) ** 2 + ((yy - center[1] * h) / h) ** 2)
    f = np.clip(r / radius, 0, 1)[..., None]
    a, b = np.array(hexrgb(inner), np.float32), np.array(hexrgb(outer), np.float32)
    return a * (1 - f) + b * f


def background(spec, w, h, project, seed=1):
    """spec: {"type": solid|gradient|radial|bokeh|room|sky|image, ...}. Returns RGB PIL image (w x h)."""
    t = spec.get('type', 'radial')
    rr = random.Random(spec.get('seed', seed))
    if t == 'solid':
        return Image.new('RGB', (w, h), hexrgb(spec.get('color', '#101418')))
    if t == 'gradient':
        arr = _grad(w, h, spec.get('top', '#1b2a33'), spec.get('bottom', '#05080a'))
    elif t in ('radial', 'bokeh'):
        arr = _radial(w, h, spec.get('inner', '#1c343c'), spec.get('outer', '#05090c'),
                      tuple(spec.get('center', (0.5, 0.5))), spec.get('radius', 0.75))
    elif t == 'sky':
        arr = _grad(w, h, spec.get('top', '#3d6fa8'), spec.get('horizon', '#cfe2f0'))
    elif t == 'room':
        arr = _grad(w, h, spec.get('wall', '#3a4a52'), spec.get('wall2', '#2a363c'))
    elif t == 'image':
        p = spec['file'] if os.path.isabs(spec['file']) else os.path.join(project, spec['file'])
        im = Image.open(p).convert('RGB')
        s = max(w / im.width, h / im.height)
        im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
        x0, y0 = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((x0, y0, x0 + w, y0 + h))
        if spec.get('blur'):
            im = im.filter(ImageFilter.GaussianBlur(spec['blur'] * w / 1000))
        if spec.get('dim'):
            im = Image.blend(im, Image.new('RGB', im.size, (0, 0, 0)), spec['dim'])
        return im
    else:
        arr = _grad(w, h, '#1b2a33', '#05080a')
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGB')
    d = ImageDraw.Draw(img, 'RGBA')
    if t == 'room':
        fy = int(h * spec.get('floor_y', 0.78))
        d.rectangle([0, fy, w, h], fill=hexrgb(spec.get('floor', '#24201e')))
        d.line([(0, fy), (w, fy)], fill=(0, 0, 0, 90), width=max(2, w // 300))
        if spec.get('window', True):
            wx, wy, ww, wh = int(w * 0.62), int(h * 0.16), int(w * 0.28), int(h * 0.32)
            d.rectangle([wx, wy, wx + ww, wy + wh], fill=hexrgb(spec.get('window_color', '#9cc4dc')))
            d.rectangle([wx, wy, wx + ww, wy + wh], outline=(30, 30, 36), width=max(3, w // 200))
            d.line([(wx + ww // 2, wy), (wx + ww // 2, wy + wh)], fill=(30, 30, 36), width=max(3, w // 260))
        if spec.get('shelf', True):
            sx, sy = int(w * 0.08), int(h * 0.3)
            d.rectangle([sx, sy, sx + int(w * 0.26), sy + max(6, h // 120)], fill=(70, 52, 40))
            for k in range(6):
                bw = int(w * rr.uniform(0.018, 0.03))
                bh = int(h * rr.uniform(0.04, 0.07))
                bx = sx + int(w * 0.02) + k * int(w * 0.038)
                d.rectangle([bx, sy - bh, bx + bw, sy], fill=rr.choice([(160, 70, 60), (60, 100, 140), (200, 170, 90), (90, 130, 90)]))
    if t == 'sky':
        for k in range(spec.get('clouds', 6)):
            cx, cy = rr.uniform(0, w), rr.uniform(0.1 * h, 0.55 * h)
            for j in range(5):
                r = rr.uniform(0.04, 0.09) * w
                d.ellipse([cx + j * r * 0.8 - r, cy - r * rr.uniform(0.5, 0.9), cx + j * r * 0.8 + r, cy + r * 0.5],
                          fill=(255, 255, 255, 200))
    if t == 'bokeh' or spec.get('lights'):
        dots = Image.new('RGB', (w, h), (0, 0, 0))
        dd = ImageDraw.Draw(dots)
        cols = [hexrgb(c) for c in spec.get('lights', ['#ff9646', '#ffc88c', '#6ec8e6'])]
        band = spec.get('band', (0.6, 0.95))
        for k in range(spec.get('count', 70)):
            x = rr.uniform(0, w)
            y = rr.uniform(h * band[0], h * band[1])
            s = rr.uniform(0.006, 0.02) * w
            col = rr.choice(cols)
            dd.ellipse([x - s, y - s, x + s, y + s], fill=tuple(int(v * rr.uniform(0.25, 0.6)) for v in col))
        dots = dots.filter(ImageFilter.GaussianBlur(w / 200))
        img = Image.fromarray(np.clip(np.asarray(img, np.int16) + np.asarray(dots, np.int16), 0, 255).astype(np.uint8))
    if spec.get('grid'):
        d = ImageDraw.Draw(img, 'RGBA')
        col = hexrgb(spec.get('grid_color', '#5fe3c8'), 18)
        step = int(w / 12)
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=col, width=max(1, w // 1000))
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=col, width=max(1, w // 1000))
    return img


# ------------------------------------------------------------------ graphics (screen space, normalised coords)
def _alpha(g, t):
    t0, t1 = g['t']
    fi, fo = g.get('fade', 0.25), g.get('fade_out', 0.2)
    return min(ease_out((t - t0) / fi) if fi > 0 else 1.0, smooth((t1 - t) / fo) if fo > 0 else 1.0)


def _text(d, xy, s, f, fill, anchor='la'):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def icon(d, kind, cx, cy, s, col, ang=0.0, outline=None, width=2):
    if kind == 'plane':
        pts = [(-60, -6), (-40, -12), (40, -12), (62, -4), (66, 2), (40, 10), (-40, 10), (-56, 6), (-66, -26), (-58, -26), (-44, -12)]
        wing = [(-6, 0), (14, 0), (-2, 22), (-14, 22)]
        for p in (pts, wing):
            q = rot([(cx + x * s, cy + y * s) for x, y in p], ang, cx, cy)
            d.polygon(q, fill=col)
            if outline:
                d.line(q + [q[0]], fill=outline, width=width)
    elif kind == 'heart':
        q = [(cx + s * 16 * math.sin(a) ** 3 * 4, cy - s * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) * 4)
             for a in np.linspace(0, 2 * math.pi, 60)]
        d.polygon(q, fill=col)
    elif kind == 'check':
        d.line([(cx - 40 * s, cy), (cx - 10 * s, cy + 30 * s), (cx + 45 * s, cy - 35 * s)], fill=col, width=int(14 * s), joint='curve')
    elif kind == 'cross':
        d.line([(cx - 35 * s, cy - 35 * s), (cx + 35 * s, cy + 35 * s)], fill=col, width=int(14 * s))
        d.line([(cx + 35 * s, cy - 35 * s), (cx - 35 * s, cy + 35 * s)], fill=col, width=int(14 * s))
    elif kind == 'warning':
        q = [(cx, cy - 50 * s), (cx + 55 * s, cy + 45 * s), (cx - 55 * s, cy + 45 * s)]
        d.polygon(q, fill=col)
        d.line([(cx, cy - 15 * s), (cx, cy + 15 * s)], fill=(20, 20, 20), width=int(10 * s))
        d.ellipse([cx - 6 * s, cy + 24 * s, cx + 6 * s, cy + 36 * s], fill=(20, 20, 20))
    elif kind == 'clock':
        d.ellipse([cx - 50 * s, cy - 50 * s, cx + 50 * s, cy + 50 * s], outline=col, width=int(8 * s))
        d.line([(cx, cy), (cx, cy - 32 * s)], fill=col, width=int(7 * s))
        d.line([(cx, cy), (cx + 24 * s, cy + 6 * s)], fill=col, width=int(7 * s))


def draw_graphic(layer, g, t, W, H, SS, project):
    """layer: RGBA supersampled image. Coordinates in g are normalised to the frame (0..1)."""
    if not (g['t'][0] <= t < g['t'][1]):
        return
    a = _alpha(g, t)
    if a <= 0.003:
        return
    d = ImageDraw.Draw(layer, 'RGBA')
    w, h = W * SS, H * SS
    A = int(255 * a)
    col = hexrgb(g.get('color', '#ffffff'))
    acc = hexrgb(g.get('accent', '#ff3b2f'))
    typ = g['type']
    x, y = g.get('pos', (0.5, 0.5))
    X, Y = x * w, y * h
    size = g.get('size', 0.04) * h
    fk = g.get('font', 'sans')
    rise = (1 - ease_out((t - g['t'][0]) / 0.3)) * 0.01 * h if g.get('anim', 'rise') == 'rise' else 0
    if typ in ('title', 'text'):
        s = g['text']
        if g.get('anim') == 'type':
            n = int(min(1.0, (t - g['t'][0]) / max(0.2, len(s) * g.get('cps', 0.05))) * len(s))
            s = s[:n]
        f = font(fk, size, project)
        anc = {'left': 'lm', 'center': 'mm', 'right': 'rm'}[g.get('align', 'center')]
        if g.get('shadow', True):
            _text(d, (X + size * 0.04, Y + rise + size * 0.06), s, f, (0, 0, 0, int(A * 0.5)), anc)
        _text(d, (X, Y + rise), s, f, col + (A,), anc)
        if typ == 'title' and g.get('underline', True):
            bw = d.textlength(g['text'], font=f)
            x0 = X - bw / 2 if anc == 'mm' else (X if anc == 'lm' else X - bw)
            d.line([(x0, Y + size * 0.72 + rise), (x0 + bw * ease_out((t - g['t'][0]) / 0.5), Y + size * 0.72 + rise)],
                   fill=acc + (A,), width=max(2, int(size * 0.08)))
    elif typ == 'lower_third':
        f1 = font('sans', size, project)
        f2 = font('mono', size * 0.55, project)
        tw = max(d.textlength(g['title'], font=f1), d.textlength(g.get('sub', ''), font=f2)) + size * 1.2
        slide = ease_out((t - g['t'][0]) / 0.35)
        x0 = X - (1 - slide) * size * 2
        d.rectangle([x0, Y - size * 0.75, x0 + tw, Y + size * 1.25], fill=(8, 12, 18, int(A * 0.82)))
        d.rectangle([x0, Y - size * 0.75, x0 + size * 0.18, Y + size * 1.25], fill=acc + (A,))
        _text(d, (x0 + size * 0.5, Y), g['title'], f1, col + (A,), 'lm')
        _text(d, (x0 + size * 0.5, Y + size * 0.85), g.get('sub', ''), f2, (190, 200, 206, A), 'lm')
    elif typ == 'badge':
        f = font('mono', size, project)
        blink = 1.0 if (t % 1.2) < 0.8 else 0.35
        d.rectangle([X, Y - size * 0.28, X + size * 0.56, Y + size * 0.28], fill=acc + (int(A * blink),))
        _text(d, (X + size * 1.0, Y), g['text'], f, col + (int(A * 0.85),), 'lm')
    elif typ == 'panel':
        bw, bh = g.get('w', 0.8) * w, g.get('h', 0.3) * h
        x0, y0 = X - bw / 2, Y - bh / 2
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(size * 0.5), fill=(6, 12, 16, int(A * 0.75)),
                            outline=acc + (int(A * 0.6),), width=max(2, int(size * 0.05)))
        f1 = font(g.get('title_font', 'mono'), size, project)
        if g.get('title'):
            _text(d, (x0 + size, y0 + size * 1.1), g['title'], f1, col + (A,), 'lm')
            d.line([(x0 + size, y0 + size * 1.9), (x0 + size + d.textlength(g['title'], font=f1), y0 + size * 1.9)],
                   fill=acc + (A,), width=max(2, int(size * 0.08)))
        f2 = font(g.get('item_font', 'sans_regular'), size * 0.8, project)
        for k, it in enumerate(g.get('items', [])):
            tk = g['t'][0] + g.get('stagger', 0.35) * (k + 1)
            ak = ease_out((t - tk) / 0.25)
            if ak <= 0:
                continue
            yy = y0 + size * (3.0 + 1.5 * k)
            d.ellipse([x0 + size, yy - size * 0.15, x0 + size * 1.3, yy + size * 0.15], fill=acc + (int(A * ak),))
            _text(d, (x0 + size * 1.8 + (1 - ak) * size, yy), it, f2, col + (int(A * ak),), 'lm')
    elif typ == 'counter':
        u = smooth((t - g['t'][0]) / g.get('count_dur', 1.2))
        v = g.get('from', 0) + (g.get('to', 100) - g.get('from', 0)) * u
        s = g.get('format', '{:,.0f}').format(v)
        f = font(g.get('font', 'condensed'), size, project)
        _text(d, (X, Y), s, f, col + (A,), 'mm')
        if g.get('label'):
            _text(d, (X, Y - size * 0.8), g['label'], font('mono', size * 0.3, project), (190, 200, 206, A), 'mm')
    elif typ == 'arrow':
        (x0, y0), (x1, y1) = g['from'], g['to']
        u = ease_out((t - g['t'][0]) / g.get('grow', 0.5))
        xa, ya = x0 * w, y0 * h
        xb, yb = lerp(xa, x1 * w, u), lerp(ya, y1 * h, u)
        wd = max(3, int(size * 0.25))
        d.line([(xa, ya), (xb, yb)], fill=acc + (A,), width=wd)
        ang = math.atan2(yb - ya, xb - xa)
        hs = size * 0.6
        d.polygon([(xb + math.cos(ang) * hs, yb + math.sin(ang) * hs),
                   (xb + math.cos(ang + 2.4) * hs, yb + math.sin(ang + 2.4) * hs),
                   (xb + math.cos(ang - 2.4) * hs, yb + math.sin(ang - 2.4) * hs)], fill=acc + (A,))
        if g.get('label'):
            _text(d, ((xa + xb) / 2, (ya + yb) / 2 + size * 0.9), g['label'], font('mono', size * 0.55, project), acc + (A,), 'mm')
    elif typ == 'icon':
        ang = math.radians(g.get('angle', 0.0)) * (ease_out((t - g['t'][0]) / g.get('turn_dur', 0.8)) if g.get('animate_angle') else 1)
        icon(d, g['icon'], X, Y, size / 50, col + (A,), -ang, outline=acc + (A,) if g.get('outline') else None)
    elif typ == 'image':
        p = g['file'] if os.path.isabs(g['file']) else os.path.join(project, g['file'])
        im = Image.open(p).convert('RGBA')
        bw = g.get('w', 0.4) * w
        im = im.resize((int(bw), int(bw * im.height / im.width)), Image.LANCZOS)
        if a < 1:
            al = im.split()[3].point(lambda v: int(v * a))
            im.putalpha(al)
        layer.alpha_composite(im, (int(X - im.width / 2), int(Y - im.height / 2)))


# ------------------------------------------------------------------ captions
def build_captions(lines, cfg):
    words = []
    for ln in lines.get('narration', []) + lines.get('dialogue', []):
        for wd in ln.get('words', []):
            words.append(dict(w=wd['w'], s=wd['s'], e=wd['e'], line=ln['id']))
    words.sort(key=lambda x: x['s'])
    chunks, cur = [], []
    maxw = cfg.get('max_words', 4)
    for i, wd in enumerate(words):
        cur.append(wd)
        nxt = words[i + 1] if i + 1 < len(words) else None
        txt = ' '.join(x['w'] for x in cur)
        if (wd['w'][-1] in '.,?!:;' or len(cur) >= maxw or len(txt) > 22 or nxt is None or nxt['line'] != wd['line']
                or len(txt) + 1 + len(nxt['w']) > 26):
            chunks.append(cur)
            cur = []
    for k, ch in enumerate(chunks):
        nx = chunks[k + 1][0]['s'] if k + 1 < len(chunks) else 1e9
        end = min(ch[-1]['e'] + 0.45, nx - 0.06)
        for wd in ch:
            wd['ch_end'] = end
            wd['style'] = ['rise', 'fade', 'rise_soft'][k % 3]
            wd['chunk'] = k
    return words, chunks


def draw_captions(img, words, t, cfg, W, H, project):
    if not cfg.get('on', True):
        return
    act = [w for w in words if w['s'] - 0.05 <= t < w['ch_end']]
    if not act:
        return
    chunk = [w for w in words if w['chunk'] == act[0]['chunk']]
    d = ImageDraw.Draw(img, 'RGBA')
    size = cfg.get('size', 0.036) * H
    f = font(cfg.get('font', 'sans'), size, project)
    hl = set(cfg.get('highlight', []))
    hlc = hexrgb(cfg.get('highlight_color', '#ff3b2f'))
    col = hexrgb(cfg.get('color', '#ffffff'))
    sp = size * 0.27
    widths = [d.textlength(w['w'], font=f) for w in chunk]
    tot = sum(widths) + sp * (len(chunk) - 1)
    x = (W - tot) / 2
    Y = cfg.get('y', 0.74) * H
    if cfg.get('box'):
        d.rounded_rectangle([x - size * 0.45, Y - size * 0.75, x + tot + size * 0.45, Y + size * 0.75], radius=int(size * 0.25),
                            fill=(0, 0, 0, int(255 * cfg.get('box_alpha', 0.6))))
    for w, wd in zip(chunk, widths):
        if t >= w['s'] - 0.05:
            dt = t - (w['s'] - 0.05)
            out = max(0.0, min(1.0, (w['ch_end'] - t) / 0.14))
            body = w['w']
            dy = 0
            if any(ch.isdigit() for ch in body):
                n = max(1, min(len(body), int(len(body) * min(1.0, dt / max(0.22, 0.8 * (w['e'] - w['s'])))) + 1))
                body = body[:n]
                a = 1.0
            elif w['style'] == 'rise':
                a, dy = ease_out(dt / 0.16), 10 * (1 - ease_out(dt / 0.2))
            elif w['style'] == 'rise_soft':
                a, dy = ease_out(dt / 0.22), 5 * (1 - ease_out(dt / 0.25))
            else:
                a = ease_out(dt / 0.12)
            a *= out
            c = hlc if w['w'].strip('.,?!:;').lower() in {h.strip('.,?!:;').lower() for h in hl} else col
            for ox, oy in ((0, 3), (2, 4), (-2, 4)):
                d.text((x + ox, Y + dy + oy), body, font=f, fill=(0, 0, 0, int(70 * a)), anchor='lm')
            d.text((x, Y + dy), body, font=f, fill=c + (int(255 * a),), anchor='lm')
        x += wd + sp


# ------------------------------------------------------------------ grade + transitions
GRADES = {
    # (saturation, (r,g,b) shadow tint, (r,g,b) highlight tint, contrast, gamma)
    'none': (1.0, (0, 0, 0), (0, 0, 0), 1.0, 1.0),
    'night': (0.82, (-6, 4, 12), (6, 2, -6), 1.06, 0.97),
    'warm': (1.05, (6, 0, -8), (12, 6, -6), 1.04, 0.98),
    'cool': (0.92, (-6, 2, 10), (-2, 4, 10), 1.03, 1.0),
    'noir': (0.0, (0, 0, 0), (0, 0, 0), 1.18, 0.95),
    'vintage': (0.78, (10, 4, -6), (14, 10, -4), 0.94, 1.02),
    'vivid': (1.22, (0, 0, 0), (0, 0, 0), 1.06, 1.0),
}


class Post:
    def __init__(self, W, H, style):
        self.W, self.H = W, H
        g = GRADES.get(style.get('grade', 'none'), GRADES['none'])
        self.sat, self.sh, self.hi, self.con, self.gam = g
        self.grain = style.get('grain', 0.0)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        v = style.get('vignette', 0.25)
        self.vig = (1 - v * np.clip(r - 0.35, 0, 1) ** 1.5)[..., None]
        self.bloom = style.get('bloom', 0.0)

    def apply(self, img, seed):
        a = np.asarray(img, np.float32)
        if self.bloom > 0:
            hi = Image.fromarray(np.clip((a - 170) * 3, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(self.W / 90))
            b = np.asarray(hi, np.float32)
            a = 255 - (255 - a) * (255 - b * self.bloom) / 255
        lum = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114)[..., None]
        a = lum + (a - lum) * self.sat
        l = np.clip(lum / 255, 0, 1)
        a = a + np.array(self.sh, np.float32) * (1 - l) + np.array(self.hi, np.float32) * l
        a = (a - 128) * self.con + 128
        a = 255 * np.clip(a / 255, 0, 1) ** (1 / self.gam)
        a = a * self.vig
        if self.grain > 0:
            rng = np.random.default_rng(seed)
            a = a + rng.normal(0, 255 * self.grain, a.shape[:2])[..., None]
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def transition(img, shot, prev_in_next, t):
    """apply the shot's 'in' transition and a dip-out if the next shot dips in."""
    tau = t - shot['start']
    rem = shot['end'] - t
    kind = shot.get('in', 'cut')
    a = np.asarray(img, np.float32)
    k = 1.0
    add = 0.0
    if kind == 'dip':
        k *= smooth(tau / 0.25)
    elif kind == 'slowfade':
        k *= smooth(tau / 2.0)
    elif kind == 'flash':
        add = 110 * max(0.0, 1 - tau / 0.18)
    elif kind == 'flicker':
        add = 80 if tau < 0.034 else (-60 if tau < 0.1 else (55 if tau < 0.134 else (-30 if tau < 0.2 else 0)))
    if prev_in_next == 'dip':
        k *= smooth(rem / 0.2)
    if k == 1.0 and add == 0.0 and kind != 'whip':
        return img
    a = a * k + add
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    if kind == 'whip' and tau < 0.2:
        r = int((1 - tau / 0.2) * img.width * 0.04)
        out = out.filter(ImageFilter.BoxBlur(max(1, r)))
    return out
