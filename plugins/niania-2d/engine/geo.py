"""2-D geometry + drawing helpers (Pillow). Units are character units; Canvas maps them to pixels."""
import math
from PIL import ImageDraw, ImageFont
import os


def hexrgb(h, a=None):
    h = h.lstrip('#')
    c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return c + (a,) if a is not None else c


def shade(c, k):
    """darken (k<1) or lighten (k>1) an RGB tuple."""
    if k <= 1:
        return tuple(int(v * k) for v in c[:3])
    return tuple(int(v + (255 - v) * (k - 1)) for v in c[:3])


def mixc(a, b, u):
    return tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))


def bez(p0, p1, p2, p3, n=14):
    out = []
    for k in range(n + 1):
        u = k / n
        a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def mirror(pts):
    return [(-x, y) for x, y in pts]


def ellipse_pts(cx, cy, rx, ry, n=36, a0=0.0, a1=2 * math.pi):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * k / n), cy + ry * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def rot(pts, ang, cx=0.0, cy=0.0):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def off(pts, dx, dy):
    return [(x + dx, y + dy) for x, y in pts]


def strip(path, w0, w1=None):
    """tapered ribbon polygon along a polyline (w0 at the start, w1 at the end)."""
    w1 = w0 if w1 is None else w1
    L, R = [], []
    n = len(path)
    for i, (x, y) in enumerate(path):
        a = path[max(0, i - 1)]
        b = path[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy) or 1
        nx, ny = -dy / l, dx / l
        w = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2
        L.append((x + nx * w, y + ny * w))
        R.append((x - nx * w, y - ny * w))
    return L + R[::-1]


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, u):
    return a + (b - a) * u


class Canvas:
    """Draws unit-space polygons onto a supersampled image.
    M = (scale, ox, oy); flip mirrors the character (facing left); xf(pts) is an extra unit-space transform."""

    def __init__(self, img, scale, ox, oy, flip=False):
        self.img = img
        self.d = ImageDraw.Draw(img, 'RGBA')
        self.s, self.ox, self.oy = scale, ox, oy
        self.flip = flip
        self.xf = None

    def tp(self, pts):
        if self.xf:
            pts = self.xf(pts)
        f = -1 if self.flip else 1
        return [(self.ox + f * x * self.s, self.oy + y * self.s) for x, y in pts]

    def shape(self, pts, fill, line=None, lw=2.6):
        q = self.tp(pts)
        if len(q) < 3:
            return
        if fill is not None:
            self.d.polygon(q, fill=fill)
        if line is not None and lw > 0:
            self.d.line(q + [q[0]], fill=line, width=max(1, int(round(lw * self.s))), joint='curve')

    def poly(self, pts, color, lw):
        q = self.tp(pts)
        self.d.line(q, fill=color, width=max(1, int(round(lw * self.s))), joint='curve')

    def dot(self, x, y, r, fill):
        (px, py), = self.tp([(x, y)])
        rr = r * self.s
        self.d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=fill)


FONT_DIRS = ['/System/Library/Fonts/Supplemental', '/System/Library/Fonts', '/Library/Fonts',
             os.path.expanduser('~/Library/Fonts'), '/usr/share/fonts/truetype/dejavu', '/usr/share/fonts']
FONT_NAMES = {
    'sans': ['Arial Bold.ttf', 'DejaVuSans-Bold.ttf', 'Helvetica.ttc'],
    'sans_regular': ['Arial.ttf', 'DejaVuSans.ttf', 'Helvetica.ttc'],
    'mono': ['Andale Mono.ttf', 'DejaVuSansMono.ttf', 'Menlo.ttc'],
    'condensed': ['DIN Condensed Bold.ttf', 'Arial Narrow Bold.ttf', 'DejaVuSansCondensed-Bold.ttf'],
    'type': ['Courier New Bold.ttf', 'DejaVuSansMono-Bold.ttf', 'Courier.ttc'],
    'serif': ['Georgia Bold.ttf', 'DejaVuSerif-Bold.ttf', 'Times New Roman Bold.ttf'],
}
_FCACHE = {}


def font(kind, px, project=None):
    """kind: sans | sans_regular | mono | condensed | type | serif | a path (absolute or relative to the project)."""
    key = (kind, int(px))
    if key in _FCACHE:
        return _FCACHE[key]
    path = None
    if kind in FONT_NAMES:
        for n in FONT_NAMES[kind]:
            for d in FONT_DIRS:
                p = os.path.join(d, n)
                if os.path.exists(p):
                    path = p
                    break
            if path:
                break
    else:
        p = kind if os.path.isabs(kind) else os.path.join(project or '.', kind)
        path = p if os.path.exists(p) else None
    f = ImageFont.truetype(path, int(px)) if path else ImageFont.load_default()
    _FCACHE[key] = f
    return f
