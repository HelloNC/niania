"""Prop library. Each builder returns an object whose origin is the prop's physical base
(bottom centre) and stores interaction metadata as custom properties:
  grip_<name>   = [radius, height_of_centre]  (cylindrical grip around local Z)
  radius/height = collision proxy (vertical cylinder) used by physics and QC
"""
import math
import bpy
from mathutils import Vector, Matrix
from . import geom, materials


def _obj(name, parts, col, loc=(0, 0, 0), rot_z=0.0):
    """parts: [(part, material)]"""
    mb = geom.MeshBuilder(name)
    mats = []
    for part, mat in parts:
        if mat not in mats:
            mats.append(mat)
        mb.add(*part, mat=mats.index(mat))
    ob = mb.build(mats, col)
    ob.location = loc
    ob.rotation_euler.z = math.radians(rot_z)
    return ob


def mug(name, col, color='#f3ede2', liquid='#4a2a17', loc=(0, 0, 0), rot_z=0.0):
    r, h, t = 0.040, 0.092, 0.005
    body = geom.lathe([(0.0, 0.0), (r - 0.006, 0.0), (r, 0.006), (r, h), (r - t, h), (r - t, 0.012), (0.0, 0.012)],
                      28, False, False)
    handle = geom.torus_arc(0.026, 0.0065, -math.pi / 2 * 1.05, math.pi / 2 * 1.05, 14, 8, (r + 0.004, 0, h * 0.52), 'XZ')
    surf = geom.lathe([(0.0, h - 0.016), (r - t, h - 0.016)], 28, False, False)
    m = materials.cel(name + '_mat', color, rim=0.8, emit=0.35)
    lq = materials.cel(name + '_liquid', liquid, rim=0.2)
    ob = _obj(name, [(body, m), (handle, m), (surf, lq)], col, loc, rot_z)
    ob['grip_body'] = [r, h * 0.5]
    ob['radius'], ob['height'] = r, h
    ob['mouth'] = [r - t, h]
    return ob


def bistro_table(name, col, top_r=0.30, height=0.74, color='#3b2a3f', loc=(0, 0, 0)):
    top = geom.lathe([(0, height - 0.03), (top_r, height - 0.03), (top_r + 0.004, height - 0.015), (top_r, height), (0, height)], 40)
    stem = geom.capsule((0, 0, 0.05), (0, 0, height - 0.03), 0.022)
    base = geom.lathe([(0, 0), (0.2, 0), (0.2, 0.012), (0.06, 0.04), (0, 0.045)], 32)
    m = materials.cel(name + '_mat', color, rim=0.8)
    ob = _obj(name, [(top, m), (stem, m), (base, m)], col, loc)
    ob['top_z'], ob['radius'], ob['height'] = height, top_r, height
    return ob


def chair(name, col, color='#2d2333', loc=(0, 0, 0), rot_z=0.0):
    seat_h = 0.46
    parts = [geom.box(0.40, 0.40, 0.03, (0, 0, seat_h)), geom.box(0.40, 0.025, 0.42, (0, 0.19, seat_h + 0.22))]
    for x in (-0.18, 0.18):
        for y in (-0.18, 0.18):
            parts.append(geom.capsule((x, y, 0), (x, y, seat_h), 0.014))
    m = materials.cel(name + '_mat', color, rim=0.8)
    ob = _obj(name, [(p, m) for p in parts], col, loc, rot_z)
    ob['seat_z'] = seat_h
    return ob


def ball(name, col, r=0.11, color='#f4f1ea', loc=(0, 0, 0)):
    m = materials.cel(name + '_mat', color, rim=0.6)
    ob = _obj(name, [(geom.ellipsoid(r, r, r, (0, 0, r), 24, 14), m)], col, loc)
    ob['grip_body'] = [r, r]
    ob['radius'], ob['height'] = r, 2 * r
    return ob


def book(name, col, color='#3a6fb0', loc=(0, 0, 0), rot_z=0.0):
    cover = materials.cel(name + '_cover', color, rim=0.6)
    pages = materials.cel(name + '_pages', '#efe7d6', rim=0.3)
    ob = _obj(name, [(geom.box(0.16, 0.23, 0.03, (0, 0, 0.015)), cover),
                     (geom.box(0.15, 0.22, 0.032, (0.006, 0, 0.015)), pages)], col, loc, rot_z)
    ob['radius'], ob['height'] = 0.12, 0.03
    return ob


def lamp_post(name, col, height=3.4, color='#1b1622', light='#ffcf8a', loc=(0, 0, 0), power=60.0):
    m = materials.cel(name + '_mat', color, rim=1.0)
    g = materials.flat(name + '_bulb', light, 6.0)
    parts = [(geom.capsule((0, 0, 0), (0, 0, height), 0.045, 0.03), m),
             (geom.lathe([(0.0, height + 0.05), (0.16, height + 0.02), (0.06, height + 0.16), (0.0, height + 0.17)], 20), m),
             (geom.ellipsoid(0.07, 0.07, 0.05, (0, 0, height - 0.01), 16, 8), g),
             (geom.lathe([(0, 0), (0.1, 0), (0.08, 0.2), (0.05, 0.25), (0, 0.25)], 16), m)]
    ob = _obj(name, parts, col, loc)
    L = bpy.data.lights.new(name + '_light', 'POINT')
    L.color = materials.srgb(light)[:3]
    L.energy = power
    L.shadow_soft_size = 0.15
    lo = bpy.data.objects.new(name + '_light', L)
    col.objects.link(lo)
    lo.location = Vector(loc) + Vector((0, 0, height - 0.08))
    glow = geom.make_object(name + '_glow', geom.plane(1, 1, normal='Y'), materials.radial_glow(name + '_glowm', light, 2.0, 2.2, 0.55), col)
    glow.location = Vector(loc) + Vector((0, -0.05, height - 0.02))
    glow.scale = (0.9, 1, 0.9)
    glow.visible_shadow = False
    return ob


def tree(name, col, height=4.0, color='#1d1527', loc=(0, 0, 0), seed=0):
    import random
    rnd = random.Random(seed)
    m = materials.cel(name + '_mat', color, rim=0.5, shade=0.4)
    parts = [(geom.capsule((0, 0, 0), (0, 0, height * 0.55), 0.09, 0.06), m)]
    for i in range(6):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.2, 0.8)
        rr = rnd.uniform(0.6, 1.0) * height * 0.22
        c = (d * math.cos(a) * 0.8, d * math.sin(a) * 0.5, height * rnd.uniform(0.62, 0.85))
        parts.append((geom.ellipsoid(rr, rr * 0.8, rr * 0.85, c, 16, 10), m))
    return _obj(name, parts, col, loc)


def building(name, col, w, d, h, color='#2c2140', window='#ffb15e', loc=(0, 0, 0), floors=3, cols=4,
             lit=0.75, seed=0, awning=None, door=True, face_dir=-1, trim='#1e1630'):
    """Block with a front facade of lit/unlit windows. face_dir=-1: facade faces -Y."""
    import random
    rnd = random.Random(seed)
    wall = materials.cel(name + '_wall', color, rim=0.5, shade=0.8)
    trim_m = materials.cel(name + '_trim', trim, rim=0.3, shade=0.6)
    win_on = materials.flat('win_on_' + window, window, 1.6)
    win_off = materials.cel('win_off', '#1a1430', rim=0.0, shade=0.3)
    parts = [(geom.box(w, d, h, (0, 0, h / 2)), wall), (geom.box(w + 0.15, d + 0.15, 0.18, (0, 0, h + 0.09)), trim_m)]
    fy = face_dir * (d / 2 + 0.005)
    ww, wh = w / cols * 0.48, h / floors * 0.42
    for fl in range(floors):
        for c in range(cols):
            x = -w / 2 + w / cols * (c + 0.5)
            z = h / floors * (fl + 0.55)
            if fl == 0 and door and c == cols // 2:
                parts.append((geom.box(ww * 1.1, 0.04, h / floors * 0.7, (x, fy, h / floors * 0.35)), trim_m))
                continue
            on = rnd.random() < lit
            parts.append((geom.box(ww + 0.08, 0.05, wh + 0.08, (x, fy, z)), trim_m))
            parts.append((geom.box(ww, 0.06, wh, (x, fy + face_dir * 0.006, z)), win_on if on else win_off))
            # mullions
            parts.append((geom.box(0.025, 0.07, wh, (x, fy + face_dir * 0.01, z)), trim_m))
            parts.append((geom.box(ww, 0.07, 0.025, (x, fy + face_dir * 0.01, z + wh * 0.1)), trim_m))
    ob = _obj(name, parts, col, loc)
    if awning:
        _awning(name + '_awning', col, w * 0.9, Vector(loc) + Vector((0, fy, h / floors * 0.95)), face_dir, awning)
    return ob


def _awning(name, col, w, base, face_dir, colors):
    a, b = colors
    ma, mb = materials.cel(name + '_a', a, rim=0.6), materials.cel(name + '_b', b, rim=0.6)
    n = max(6, int(w / 0.35))
    parts = []
    for i in range(n):
        x0 = -w / 2 + w * i / n
        x1 = x0 + w / n
        v = [(x0, 0, 0.45), (x1, 0, 0.45), (x1, face_dir * 0.9, 0.0), (x0, face_dir * 0.9, 0.0),
             (x0, face_dir * 0.9, -0.14), (x1, face_dir * 0.9, -0.14)]
        f = [(0, 3, 2, 1) if face_dir < 0 else (0, 1, 2, 3), (3, 4, 5, 2) if face_dir < 0 else (3, 2, 5, 4)]
        parts.append(((v, f), ma if i % 2 == 0 else mb))
    return _obj(name, parts, col, base)


def window_glow_light(name, col, loc, size=(2.0, 1.2), color='#ffb35e', power=40.0, rot=(math.pi / 2, 0, 0)):
    L = bpy.data.lights.new(name, 'AREA')
    L.shape = 'RECTANGLE'
    L.size, L.size_y = size
    L.energy = power
    L.color = materials.srgb(color)[:3]
    ob = bpy.data.objects.new(name, L)
    col.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def droplet(name, col, r=0.008, color='#4a2a17'):
    m = materials.cel('drop_' + color, color, rim=0.8, gloss=0.0, emit=0.05)
    ob = _obj(name, [(geom.ellipsoid(r, r, r * 1.2, (0, 0, 0), 10, 6), m)], col)
    ob.visible_shadow = False
    return ob


def splat(name, col, r=0.02, color='#3b2213'):
    m = materials.cel('splat_' + color, color, rim=0.0, shade=0.5)
    pts = []
    for i in range(14):
        a = 2 * math.pi * i / 14
        k = r * (1.0 + 0.35 * math.sin(5 * a + 1.3) * (i % 2))
        pts.append((k * math.cos(a), k * math.sin(a)))
    return _obj(name, [(geom.extrude_polygon(pts, 0.0, 0.0015), m)], col)


def _resolve(path, project):
    import os
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.join(project or '', path)


def image_plane(name, col, file, width=1.0, loc=(0, 0, 0), rot=(90, 0, 0), emit=1.0, lit=False, project=None):
    """Any image (attached reference, logo, photo, backdrop) as a textured plane, aspect preserved.
    rot in degrees; default stands the plane upright facing -Y."""
    path = _resolve(file, project)
    m = materials.image_mat(name + '_img', path, emit=emit, alpha=True, lit=lit)
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size[:] if img.size[0] else (1, 1)
    ob = geom.make_object(name, geom.plane(width, width * h / w), m, col)
    geom.add_quad_uv(ob)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    ob.visible_shadow = lit
    return ob


def model(name, col, file, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, project=None, material=None):
    """Import a 3D model (glTF/GLB, OBJ, FBX, STL, PLY, USD) under one root empty named `name`."""
    import os
    path = _resolve(file, project)
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in ('.gltf', '.glb'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.stl':
        bpy.ops.wm.stl_import(filepath=path)
    elif ext == '.ply':
        bpy.ops.wm.ply_import(filepath=path)
    elif ext in ('.usd', '.usda', '.usdc', '.usdz'):
        bpy.ops.wm.usd_import(filepath=path)
    else:
        raise ValueError('unsupported model format ' + ext)
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    col.objects.link(root)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
        if o.parent is None:
            o.parent = root
        if material and o.type == 'MESH':
            o.data.materials.clear()
            o.data.materials.append(material)
    root.location = loc
    root.rotation_euler = [math.radians(a) for a in rot]
    root.scale = (scale, scale, scale)
    return root


def soda_bottle(name, col, color='#2fa35a', label='#f4efe4', stripe='#d8352c', liquid='#cfe9b0', loc=(0, 0, 0), rot_z=0.0):
    """500 ml PET soda bottle. Origin at the base; the cap is a separate `bottle_cap` prop
    that rides on `mouth` (see the `attach` motion segment)."""
    r, h = 0.033, 0.205
    prof = [(0.0, 0.0), (r - 0.010, 0.0), (r - 0.003, 0.004), (r, 0.014), (r, 0.120), (r - 0.002, 0.135),
            (0.022, 0.165), (0.0145, 0.188), (0.0135, 0.192), (0.0150, 0.194), (0.0150, 0.196), (0.0125, 0.197), (0.0125, h), (0.0, h)]
    body = geom.lathe(prof, 32)
    lab = geom.lathe([(0.0, 0.050), (r + 0.0012, 0.050), (r + 0.0012, 0.105), (0.0, 0.105)], 32)
    band = geom.lathe([(0.0, 0.068), (r + 0.0022, 0.068), (r + 0.0022, 0.084), (0.0, 0.084)], 32)
    m = materials.cel(name + '_mat', color, rim=1.0, emit=0.25, gloss=0.6)
    ml = materials.cel(name + '_label', label, rim=0.6, emit=0.2)
    ms = materials.cel(name + '_stripe', stripe, rim=0.6, emit=0.2)
    ob = _obj(name, [(body, m), (lab, ml), (band, ms)], col, loc, rot_z)
    ob['grip_body'] = [r, 0.085]
    ob['radius'], ob['height'] = r, h
    ob['mouth'] = [0.0125, h]
    return ob


def bottle_cap(name, col, color='#d8352c', loc=(0, 0, 0)):
    """Screw cap; origin at its open bottom so `attach` with local [0,0,mouth_z-0.012] seats it."""
    r, h = 0.0158, 0.019
    shell = geom.lathe([(0.0, 0.0), (r, 0.0), (r, h - 0.002), (r - 0.002, h), (0.0, h)], 24)
    ribs = [geom.box(0.0018, 0.0016, h * 0.8, (math.cos(a) * r, math.sin(a) * r, h * 0.45))
            for a in [k * 2 * math.pi / 18 for k in range(18)]]
    m = materials.cel(name + '_mat', color, rim=0.9, emit=0.3)
    parts = [(shell, m)] + [(rb, m) for rb in ribs]
    ob = _obj(name, parts, col, loc)
    ob['grip_body'] = [r + 0.001, h * 0.5]
    ob['radius'], ob['height'] = r, h
    return ob


BUILDERS = {
    'mug': mug, 'bistro_table': bistro_table, 'chair': chair, 'ball': ball, 'book': book,
    'lamp_post': lamp_post, 'tree': tree, 'soda_bottle': soda_bottle, 'bottle_cap': bottle_cap,
}


def build_prop(name, spec, col):
    kind = spec['type']
    proj = spec.get('_project')
    if kind == 'existing':                     # an object created by the set (door, lever, ...)
        ob = bpy.data.objects[spec.get('object', name)]
        ob['prop_type'] = ob.get('prop_type', 'existing')
        return ob
    if kind == 'image':
        ob = image_plane(name, col, spec['file'], spec.get('width', 1.0), tuple(spec.get('pos', (0, 0, 0))),
                         tuple(spec.get('rot3', (90, 0, spec.get('rot', 0)))), spec.get('emit', 1.0), spec.get('lit', False), proj)
        ob['prop_type'] = 'image'
        return ob
    if kind == 'model':
        mat = None
        if spec.get('material'):
            mk = spec['material']
            mat = (materials.ghost(name + '_gm', spec.get('color', '#9fd8ff')) if mk == 'ghost' else
                   materials.subject(name + '_sm', spec.get('color', '#e3322b')) if mk == 'subject' else
                   materials.clay(name + '_cm', spec.get('color', '#ececec')))
        ob = model(name, col, spec['file'], tuple(spec.get('pos', (0, 0, 0))), tuple(spec.get('rot3', (0, 0, spec.get('rot', 0)))),
                   spec.get('scale', 1.0), proj, mat)
        ob['prop_type'] = 'model'
        return ob
    if kind in ('lever', 'drone', 'airliner'):
        from . import aircraft
        kw = {k: v for k, v in spec.items() if k not in ('type', 'pos', 'motion', 'rot', '_project')}
        if kind == 'lever':
            ob = aircraft.lever(name, col, loc=tuple(spec.get('pos', (0, 0, 0))), **kw)
        elif kind == 'drone':
            ob = aircraft.drone(name, col, loc=tuple(spec.get('pos', (0, 0, 0))), **kw)
        else:
            if 'logo' in kw:
                kw['logo'] = _resolve(kw['logo'], proj)
            ob = aircraft.airliner_exterior(col, name=name, loc=tuple(spec.get('pos', (0, 0, 0))), rot_z=spec.get('rot', 0), **kw)
        ob['prop_type'] = kind
        return ob
    kw = {k: v for k, v in spec.items() if k not in ('type', 'pos', 'motion', 'rot', '_project')}
    kw['loc'] = tuple(spec.get('pos', (0, 0, 0)))
    if 'rot' in spec and kind in ('mug', 'chair', 'book', 'soda_bottle'):
        kw['rot_z'] = spec['rot']
    ob = BUILDERS[kind](name, col, **kw)
    ob['prop_type'] = kind
    return ob
