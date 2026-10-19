"""Aircraft kit for reconstruction/explainer scenes (narrow-body airliner, real scale, metres).

Frame: the fuselage runs along +Y (nose at +Y), cabin floor at z = 0, aisle at x = 0.
`front` (y of the forward cabin bulkhead / cockpit door) defaults to 0, so the cockpit is y > 0
and passenger rows are y < 0. Every builder returns anchors (seats, door hinge, pilot seats...)
that timelines can reference.

Builders: cabin_interior, cockpit, airliner_exterior (with optional cutaway), drone, lever.
"""
import math
import bpy
from mathutils import Vector, Matrix
from . import geom, materials

R_IN = 1.86          # interior radius
CZ = 0.72            # fuselage circle centre height above the cabin floor
R_OUT = 1.98
SEAT_X = {'A': -1.40, 'B': -0.95, 'C': -0.50, 'D': 0.50, 'E': 0.95, 'F': 1.40}
PITCH = 0.81


def _m(name, color, kind='clay', **kw):
    if kind == 'clay':
        return materials.clay(name, color, **kw)
    return materials.cel(name, color, rim=0.5)


def _obj(name, parts, col, loc=(0, 0, 0)):
    mb = geom.MeshBuilder(name)
    mats = []
    for part, mat in parts:
        if mat not in mats:
            mats.append(mat)
        mb.add(*part, mat=mats.index(mat))
    ob = mb.build(mats, col)
    ob.location = loc
    return ob


def ring_profile(r, a0, a1, n, cz=CZ):
    return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))), cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))))
            for i in range(n)]


def extrude_y(prof, y0, y1, closed=False):
    """Sweep a 2D (x, z) polyline along Y."""
    n = len(prof)
    v = [(x, y0, z) for x, z in prof] + [(x, y1, z) for x, z in prof]
    f = []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return v, f


# ---------------------------------------------------------------------------- seats
def seat_parts(x, y, facing_pos_y=True, width=0.44, colors=None):
    """One economy seat whose occupant faces +Y. (x, y) = seat cushion centre."""
    s = 1 if facing_pos_y else -1
    parts = []
    parts.append(geom.box(width, 0.46, 0.13, (x, y, 0.41), bevel=0.05))                       # cushion
    back = geom.box(width, 0.11, 0.56, (0, 0, 0.28), bevel=0.05)
    m = Matrix.Translation((x, y - s * 0.25, 0.43)) @ Matrix.Rotation(math.radians(-12 * s), 4, 'X')
    parts.append(geom.transform(back, m))
    hr = geom.box(width * 0.86, 0.12, 0.16, (0, 0.01, 0.62), bevel=0.06)
    parts.append(geom.transform(hr, m))
    parts.append(geom.box(0.05, 0.42, 0.05, (x - width / 2 - 0.01, y - s * 0.04, 0.62), bevel=0.02))  # armrest
    parts.append(geom.box(0.04, 0.04, 0.36, (x, y + s * 0.12, 0.17)))                          # leg
    parts.append(geom.box(0.04, 0.04, 0.36, (x, y - s * 0.18, 0.17)))
    return parts


# ---------------------------------------------------------------------------- cabin
def cabin_shell(col, name, y0, y1, cut=None, tint='#e6e6e8', front=0.0):
    """Walls + windows + overhead bins between y0 < y1. cut='left' leaves the upper-left open."""
    wall = _m('cab_wall', tint)
    bin_m = _m('cab_bin', '#efeff0')
    win_m = _m('cab_window', '#f3eadb', emit=0.6)
    frame_m = _m('cab_winframe', '#9a9ca2')
    parts = []
    a0, a1 = (-28, 208) if cut is None else (-28, 60)
    parts.append((extrude_y(ring_profile(R_IN, a0, a1, 48), y0, y1), wall))
    if cut:                                   # keep the lower-left wall below the window line
        parts.append((extrude_y(ring_profile(R_IN, 178, 208, 8), y0, y1), wall))
    n = int((front - 0.9 - y0) / 0.53) + 1
    for i in range(n):
        y = front - 0.9 - i * 0.53
        if not (y0 + 0.15 < y < y1 - 0.15):
            continue
        for sx in (-1, 1):
            if cut and sx < 0:
                continue
            ang = math.radians(180 - 8) if sx < 0 else math.radians(8)
            wx = R_IN * math.cos(ang) * 0.985
            wz = CZ + R_IN * math.sin(ang)
            frame = geom.box(0.04, 0.30, 0.42, (0, 0, 0), bevel=0.012)
            pane = geom.box(0.045, 0.22, 0.32, (0, 0, 0), bevel=0.01)
            mm = Matrix.Translation((wx, y, wz + 0.25)) @ Matrix.Rotation(-sx * math.radians(8), 4, 'Y')
            parts.append((geom.transform(frame, mm), frame_m))
            parts.append((geom.transform(pane, Matrix.Translation((-sx * 0.006, 0, 0)) @ mm), win_m))
    seg = 1.62
    for sx in (-1, 1):
        if cut and sx < 0:
            continue
        k = 0
        while True:
            yc = front - 0.5 - (k + 0.5) * seg
            k += 1
            if yc < y0 + seg / 2 - 0.01:
                break
            if yc > y1 - seg / 2 + 0.01:
                continue
            b = geom.box(0.62, seg - 0.04, 0.42, (0, 0, 0), bevel=0.05)
            mm = Matrix.Translation((sx * 1.36, yc, 1.86)) @ Matrix.Rotation(sx * math.radians(-14), 4, 'Y')
            parts.append((geom.transform(b, mm), bin_m))
    if y0 - 1e-6 <= front <= y1 + 1e-6:        # left part of the forward bulkhead belongs to the shell
        bw = 3.6
        h = 2.4 if cut is None else 0.95
        parts.append((geom.box((bw - 0.9) / 2, 0.1, h, (-(bw + 0.9) / 4, front, h / 2)), wall))
    return _obj(name, parts, col)


def cabin_furniture(col, rows=24, front=0.0, first_row=1, seat_color='#dadadc', tint='#e6e6e8', door_color='#f2f2f2'):
    """Floor, seat rows (3+3), forward bulkhead and the cockpit door. Returns (obj, anchors)."""
    wall = _m('cab_wall', tint)
    seat_m = _m('cab_seat', seat_color)
    floor_m = _m('cab_floor', '#d6d6d8', rough=0.8)
    frame_m = _m('cab_winframe', '#9a9ca2')
    y_back = front - 1.4 - rows * PITCH
    parts = [(geom.box(3.5, front - y_back, 0.06, (0, (front + y_back) / 2, -0.03)), floor_m)]
    bw = 3.6
    parts.append((geom.box((bw - 0.9) / 2, 0.1, 2.4, ((bw + 0.9) / 4, front, 1.2)), wall))
    parts.append((geom.box(0.9, 0.1, 0.38, (0, front, 2.21)), wall))
    parts.append((geom.box(1.02, 0.14, 0.06, (0, front, 2.02)), frame_m))
    seats = []
    for r in range(rows):
        y = front - 1.4 - r * PITCH
        for L in 'ABCDEF':
            x = SEAT_X[L]
            for pt in seat_parts(x, y):
                parts.append((pt, seat_m))
            seats.append({'id': '%d%s' % (first_row + r, L), 'pos': [x, y + 0.02, 0.47], 'facing': 90.0, 'row': first_row + r})
        parts.append((geom.box(0.05, 0.42, 0.05, (SEAT_X['C'] + 0.24, y - 0.04, 0.62), bevel=0.02), seat_m))
        parts.append((geom.box(0.05, 0.42, 0.05, (SEAT_X['F'] + 0.24, y - 0.04, 0.62), bevel=0.02), seat_m))
    ob = _obj('cabin_furniture', parts, col)
    door = cabin_door(col, front, door_color)
    return ob, {'seats': seats, 'door': door.name, 'front': front, 'back': y_back,
                'aisle': [0.0, (front + y_back) / 2, 0.0],
                'door_handle': [-0.43 + 0.74, front - 0.06, 1.02]}


def cabin_interior(col, rows=24, front=0.0, first_row=1, cut=None, **kw):
    """Convenience: furniture + one shell over the whole cabin (closed, or cut open on the left)."""
    ob, info = cabin_furniture(col, rows, front, first_row)
    cabin_shell(col, 'cabin_shell', info['back'], front, cut, front=front)
    return ob, info


def cabin_door(col, front, color='#f2f2f2', name='cockpit_door'):
    """Cockpit door hinged on its left edge (seen from the cabin). Origin = hinge, so 'swing' rotates it."""
    m = _m(name + '_m', color)
    dk = _m(name + '_dark', '#2c2d31')
    w, h = 0.86, 1.98
    parts = [(geom.box(w, 0.06, h, (w / 2, 0, h / 2), bevel=0.01), m),
             (geom.box(0.035, 0.03, 0.005, (w / 2, -0.035, 1.55)), dk),           # viewer
             (geom.box(0.12, 0.024, 0.024, (w - 0.12, -0.085, 1.02), bevel=0.01), dk),   # lever, 4 cm standoff
             (geom.box(0.03, 0.06, 0.03, (w - 0.07, -0.055, 1.02)), dk)]
    ob = _obj(name, parts, col, (-w / 2, front - 0.005, 0.0))
    ob['hinge'] = True
    return ob


# ---------------------------------------------------------------------------- cockpit
def cockpit(col, front=0.0, depth=2.6, colors=None, cut=None, parts_sel='all', name='cockpit'):
    """Flight deck forward of the bulkhead: two pilot seats with harnesses, centre pedestal with
    throttles, main panel with screens, glareshield, overhead panel and windshield frame."""
    shell = _m('ck_shell', '#cfd0d4')
    panel = _m('ck_panel', '#3a3c42', rough=0.5)
    screen = _m('ck_screen', '#2a4a6e', emit=1.2)
    seat_m = _m('ck_seat', '#8d8f95', rough=0.7)
    strap = _m('ck_strap', '#3b3d43')
    metal = _m('ck_metal', '#e3e3e6', rough=0.3)
    floor_m = _m('ck_floor', '#2f3035', rough=0.8)
    parts = []
    y0, y1 = front, front + depth
    shell_parts = []
    parts.append((geom.box(2.6, depth, 0.06, (0, (y0 + y1) / 2, -0.03)), floor_m))
    # tapering side walls / roof (cockpit is narrower than the cabin)
    for i in range(10):
        ya = y0 + depth * i / 10
        yb = y0 + depth * (i + 1) / 10
        ka = 1.0 - 0.28 * (i / 10) ** 1.6
        kb = 1.0 - 0.28 * ((i + 1) / 10) ** 1.6
        aa, ab = (-20, 60) if cut == 'left' else (-20, 200)
        pa = ring_profile(R_IN * ka, aa, ab, 30, CZ * ka + 0.15 * (1 - ka))
        pb = ring_profile(R_IN * kb, aa, ab, 30, CZ * kb + 0.15 * (1 - kb))
        v = [(x, ya, z) for x, z in pa] + [(x, yb, z) for x, z in pb]
        f = [(j, j + 1, 30 + j + 1, 30 + j) for j in range(29)]
        shell_parts.append(((v, f), shell))
    # pilot seats
    pilot_seats = []
    for sx, label in ((-0.52, 'captain'), (0.52, 'first_officer')):
        y = y0 + 1.05
        parts.append((geom.box(0.5, 0.5, 0.14, (sx, y, 0.50), bevel=0.05), seat_m))
        back = geom.box(0.5, 0.12, 0.78, (0, 0, 0.39), bevel=0.05)
        m = Matrix.Translation((sx, y - 0.27, 0.52)) @ Matrix.Rotation(math.radians(-10), 4, 'X')
        parts.append((geom.transform(back, m), seat_m))
        parts.append((geom.transform(geom.box(0.4, 0.13, 0.2, (0, 0.0, 0.88), bevel=0.06), m), seat_m))
        for k in (-0.12, 0.12):
            parts.append((geom.transform(geom.box(0.05, 0.03, 0.74, (k, 0.07, 0.42)), m), strap))
        parts.append((geom.box(0.06, 0.4, 0.06, (sx + 0.27, y, 0.7), bevel=0.02), seat_m))
        parts.append((geom.box(0.06, 0.4, 0.06, (sx - 0.27, y, 0.7), bevel=0.02), seat_m))
        parts.append((geom.box(0.3, 0.3, 0.42, (sx, y, 0.21)), panel))
        pilot_seats.append({'id': label, 'pos': [sx, y + 0.02, 0.57], 'facing': 90.0})
    # centre pedestal + throttles
    py = y0 + 1.6
    parts.append((geom.box(0.42, 0.9, 0.62, (0, py, 0.31), bevel=0.03), panel))
    parts.append((geom.box(0.42, 0.5, 0.25, (0, py + 0.25, 0.74), bevel=0.03), panel))
    for k in (-0.08, 0.08):
        parts.append((geom.box(0.035, 0.035, 0.18, (k, py - 0.05, 0.72)), metal))
        parts.append((geom.box(0.07, 0.05, 0.05, (k, py - 0.05, 0.82), bevel=0.015), metal))
    # control yokes / sidesticks
    for sx in (-0.52, 0.52):
        parts.append((geom.capsule((sx, y0 + 1.75, 0.35), (sx, y0 + 1.68, 0.8), 0.025), panel))
        parts.append((geom.box(0.28, 0.05, 0.12, (sx, y0 + 1.66, 0.83), bevel=0.03), panel))
    # main panel + screens
    my = y0 + 2.1
    parts.append((geom.box(2.0, 0.35, 0.55, (0, my, 0.9), bevel=0.03), panel))
    for k in range(5):
        x = -0.8 + k * 0.4
        parts.append((geom.box(0.3, 0.02, 0.24, (x, my - 0.18, 0.96), bevel=0.01), screen))
    parts.append((geom.box(2.0, 0.3, 0.08, (0, my - 0.05, 1.22), bevel=0.03), panel))       # glareshield
    # overhead panel
    if cut is None:
        shell_parts.append((geom.box(0.9, 1.0, 0.1, (0, y0 + 1.5, 2.15), bevel=0.02), panel))
    for i in (range(6) if cut is None else []):
        for j in range(4):
            shell_parts.append((geom.box(0.08, 0.06, 0.03, (-0.3 + i * 0.12, y0 + 1.15 + j * 0.2, 2.09)), metal))
    # windshield frame
    for k in ((-0.9, -0.3, 0.3, 0.9) if cut is None else ()):
        shell_parts.append((geom.capsule((k, my - 0.05, 1.25), (k * 0.85, y1 - 0.05, 1.8), 0.035), shell))
    sel = parts + shell_parts if parts_sel == 'all' else (parts if parts_sel == 'furniture' else shell_parts)
    ob = _obj(name, sel, col)
    return ob, {'pilot_seats': pilot_seats, 'pedestal': [0, py, 0.82], 'panel': [0, my, 0.95],
                'throttle': [0.0, py - 0.05, 0.82]}


def lever(name, col, length=0.11, radius=0.011, color='#2c2d31', loc=(0, 0, 0), rot=(0, 0, 0)):
    """Door/handle lever: a grippable cylinder along local Z (so `grip_body` applies)."""
    m = _m(name + '_m', color)
    ob = _obj(name, [(geom.capsule((0, 0, 0), (0, 0, length), radius), m)], col)
    ob.location = loc
    ob.rotation_euler = rot
    ob['grip_body'] = [radius, length * 0.55]
    ob['radius'], ob['height'] = radius, length
    ob['prop_type'] = 'lever'
    return ob


# ---------------------------------------------------------------------------- exterior
def airliner_exterior(col, name='airliner', front=0.0, length=37.0, body='#f4f4f6', tail='#e6e6ea',
                      stripe=None, cut=None, scale=1.0, loc=(0, 0, 0), rot_z=0.0, logo=None, windows=True,
                      gear=True):
    """Generic narrow-body airliner. front = y of the cockpit bulkhead (nose ~4.3 m ahead).
    cut: None | 'nose_left' (removes the upper-left skin over cockpit + first rows for cutaways)."""
    skin = _m(name + '_skin', body, rough=0.45)
    tail_m = _m(name + '_tail', tail, rough=0.45)
    dark = _m(name + '_win', '#2b2e36', rough=0.3)
    eng = _m(name + '_eng', '#d8d9dd', rough=0.4)
    yn = front + 4.3                       # nose tip
    yt = yn - length                       # tail tip
    prof = []
    for i in range(14):                    # nose cone (radius grows from tip)
        u = i / 13
        prof.append((R_OUT * math.sin(u * math.pi / 2) ** 0.7, yn - 4.6 * (1 - math.cos(u * math.pi / 2))))
    y = yn - 4.6 - 0.8
    while y > yt + 9.0:                    # constant section, a ring every 0.8 m (cutaways need them)
        prof.append((R_OUT, y))
        y -= 0.8
    prof.append((R_OUT, yt + 9.0))
    for i in range(1, 10):                 # tail cone, upswept
        u = i / 9
        prof.append((R_OUT * (1 - u) ** 1.1 + 0.15 * u, yt + 9.0 * (1 - u)))
    # lathe around Y: build manually (x, z ring), centre line rises toward the tail
    segs = 40
    verts, faces = [], []
    rings = []
    for r, y in prof:
        ring = []
        cz = CZ + (0.0 if y > yt + 9 else 1.0 * (1 - (y - yt) / 9.0) ** 1.5)
        for k in range(segs):
            a = 2 * math.pi * k / segs
            ring.append(len(verts))
            verts.append((r * math.cos(a), y, cz + r * math.sin(a) * 1.02))
        rings.append(ring)
    def in_cut(k, y):
        if cut != 'nose_left':
            return False
        a = math.degrees(2 * math.pi * (k + 0.5) / segs) % 360
        return (front - 6.2) <= y <= (yn - 1.3) and 62 <= a <= 212
    for ra, rb in zip(rings[:-1], rings[1:]):
        ym = (verts[ra[0]][1] + verts[rb[0]][1]) / 2
        for k in range(segs):
            j = (k + 1) % segs
            if in_cut(k, ym):
                continue
            faces.append((ra[k], rb[k], rb[j], ra[j]))
    faces.append(tuple(reversed(rings[-1])))
    parts = [((verts, faces), skin)]
    # wings (swept, low) + engines
    for sx in (-1, 1):
        root_y, root_c, tip_c, span, sweep = front - 15.0, 6.0, 1.6, 16.5, 7.0
        pts = [(sx * 1.6, root_y), (sx * 1.6, root_y - root_c), (sx * span, root_y - sweep - tip_c), (sx * span, root_y - sweep)]
        if sx < 0:
            pts = list(reversed(pts))
        v, f = geom.extrude_polygon(pts, CZ - 1.2, CZ - 0.95)
        v = [(x, y, z + 0.05 * abs(x)) for x, y, z in v]      # dihedral
        parts.append(((v, f), skin))
        nac = geom.lathe([(0.0, 0.0), (0.9, 0.2), (1.0, 1.2), (0.95, 3.2), (0.6, 4.0), (0.0, 4.1)], 24)
        m = Matrix.Translation((sx * 5.6, root_y + 2.6, CZ - 1.75)) @ Matrix.Rotation(math.radians(90), 4, 'X')
        parts.append((geom.transform(nac, m), eng))
        parts.append((geom.box(0.25, 2.0, 0.7, (sx * 5.6, root_y - 0.3, CZ - 1.2)), skin))
    # tail
    v, f = geom.extrude_polygon([(yt + 0.6, 0), (yt + 6.5, 0), (yt + 3.2, 6.6), (yt + 0.2, 6.6)], -0.12, 0.12)
    v = [(z, x, y + CZ + 1.4) for x, y, z in v]
    parts.append(((v, f), tail_m))
    for sx in (-1, 1):
        pts = [(sx * 0.3, yt + 1.2), (sx * 0.3, yt + 4.6), (sx * 6.0, yt + 1.5), (sx * 6.0, yt + 0.4)]
        if sx < 0:
            pts = list(reversed(pts))
        parts.append((geom.extrude_polygon(pts, CZ + 1.1, CZ + 1.25), skin))
    if windows:
        for i in range(30):
            y = front - 1.3 - i * 0.53
            for sx in (-1, 1):
                if cut == 'nose_left' and sx < 0 and y >= front - 6.4:
                    continue
                parts.append((geom.box(0.03, 0.2, 0.28, (sx * (R_OUT * 0.985), y, CZ + 0.62), bevel=0.01), dark))
        for k in (-0.55, -0.2, 0.2, 0.55):
            if cut == 'nose_left' and k < 0.3:
                continue
            parts.append((geom.box(0.32, 0.12, 0.18, (k, yn - 1.9 + abs(k) * 0.4, CZ + 1.15), bevel=0.02), dark))
    if stripe:
        parts.append((extrude_y(ring_profile(R_OUT + 0.01, 186, 200, 4), yt + 9, front + 1.5), _m(name + '_stripe', stripe)))
        parts.append((extrude_y(ring_profile(R_OUT + 0.01, -20, -6, 4), yt + 9, front + 1.5), _m(name + '_stripe', stripe)))
    if gear:
        for gx, gy in ((0, yn - 3.5), (-2.4, front - 17), (2.4, front - 17)):
            parts.append((geom.box(0.18, 0.18, 1.3, (gx, gy, CZ - R_OUT - 0.2)), dark))
            for k in (-0.22, 0.22):
                w = geom.lathe(geom.sphere_profile(0.45, 0, 8), 16)
                w = geom.transform(w, Matrix.Translation((gx + k, gy, CZ - R_OUT - 0.85)) @ Matrix.Scale(1, 4) @
                                   Matrix.Rotation(math.radians(90), 4, 'Y') @ Matrix.Diagonal((1, 1, 0.45, 1)))
                parts.append((w, dark))
    ob = _obj(name, parts, col)
    if cut == 'nose_left':
        sol = ob.modifiers.new('thick', 'SOLIDIFY')      # gives the cut edge a visible wall thickness
        sol.thickness = 0.09
        sol.offset = -1.0
    if logo:
        lm = materials.image_mat(name + '_logo', logo, emit=1.0, alpha=True, lit=True)
        lp = geom.make_object(name + '_logo', geom.plane(1, 1, normal='X'), lm, col)
        geom.add_quad_uv(lp)
        lp.location = (0.13, yt + 3.2, CZ + 4.6)
        lp.scale = (1, 3.0, 3.0)
        lp2 = geom.make_object(name + '_logo2', geom.plane(1, 1, normal='X'), lm, col)
        geom.add_quad_uv(lp2)
        lp2.location = (-0.13, yt + 3.2, CZ + 4.6)
        lp2.scale = (1, 3.0, 3.0)
        lp2.rotation_euler.z = math.pi
    if scale != 1.0 or any(loc) or rot_z:
        for o in [ob] + ([lp, lp2] if logo else []):
            pass
        root = bpy.data.objects.new(name + '_root', None)
        col.objects.link(root)
        for o in [ob] + ([lp, lp2] if logo else []):
            o.parent = root
        root.location = loc
        root.rotation_euler.z = math.radians(rot_z)
        root.scale = (scale, scale, scale)
        return root
    return ob


def drone(name, col, color='#2f7bf0', loc=(0, 0, 0), span=2.6):
    """Delta-wing drone with a rear pusher prop (prop is a child object named <name>_prop)."""
    m = materials.subject(name + '_m', color)
    s = span / 2
    pts = [(0, 0.9 * s), (-s, -0.55 * s), (-0.15 * s, -0.4 * s), (0, -0.5 * s), (0.15 * s, -0.4 * s), (s, -0.55 * s)]
    wing = geom.extrude_polygon(pts, -0.03, 0.03)
    body = geom.transform(geom.lathe([(0, 0), (0.12, 0.15), (0.14, 0.9), (0.1, 1.6), (0, 1.75)], 16),
                          Matrix.Translation((0, 0.85 * s, 0.05)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    ob = _obj(name, [(wing, m), (body, m)], col, loc)
    prop = _obj(name + '_prop', [(geom.box(0.04, 0.02, 0.7, (0, 0, 0), bevel=0.01), m),
                                 (geom.box(0.7, 0.02, 0.04, (0, 0, 0), bevel=0.01), m)], col)
    prop.parent = ob
    prop.location = (0, -0.55 * s, 0.05)
    ob['radius'], ob['height'] = s, 0.2
    return ob
