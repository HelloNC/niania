"""Stylised character: rig + body + clothing + face, built from a small spec.

Rest pose faces -Y, character-left is +X, ground at z=0. All proportions derive from
SKELETON (metres) scaled by spec['scale'], so every shot reuses identical geometry.

Controls (pose bones, all parentless unless noted, authored in world space by perform.py):
  hips                     body root (FK spine chain hangs off it)
  spine, chest, neck, head FK rotations
  foot_ik.L/R              ankle position + foot orientation; knee_pole.L/R are children
  hand_ik.L/R              wrist position + hand orientation; elbow_pole.L/R are children of chest
  f_*.01/.02, thumb.*      finger curl (local X), driven by grip values
  pompom, string.L/R       secondary-motion bones (spring-baked)
Face: custom props on the armature object, mapped to shape keys by drivers:
  blink_L blink_R happy wide squint look_x look_y smile open o_shape frown brow_up brow_down brow_worried
"""
import math
import bpy
from mathutils import Vector, Matrix
from . import geom, materials
from .util import srgb

SK = {   # joint positions for a 1.0-scale character (metres)
    'hips': ((0, 0, 0.86), (0, 0, 0.97)),
    'spine': ((0, 0, 0.97), (0, 0, 1.10)),
    'chest': ((0, 0, 1.10), (0, 0, 1.29)),
    'neck': ((0, 0, 1.29), (0, 0, 1.37)),
    'head': ((0, 0, 1.37), (0, 0, 1.72)),
    'thigh': ((0.085, 0, 0.86), (0.088, -0.025, 0.47)),
    'shin': ((0.088, -0.025, 0.47), (0.09, 0.0, 0.075)),
    'foot': ((0.09, 0.0, 0.075), (0.09, -0.125, 0.03)),
    'shoulder': ((0.03, 0, 1.255), (0.145, 0, 1.255)),
    'upper_arm': ((0.145, 0, 1.255), (0.175, 0.03, 0.995)),
    'forearm': ((0.175, 0.03, 0.995), (0.185, 0.0, 0.76)),
    'hand': ((0.185, 0.0, 0.76), (0.185, 0.0, 0.685)),
}
HEAD_C = Vector((0, -0.005, 1.535))
HEAD_R = 0.165
FINGERS = {   # name: (offset across the palm (-Y front .. +Y back), seg lengths)
    'index': (-0.024, (0.030, 0.026)),
    'middle': (-0.008, (0.033, 0.028)),
    'ring': (0.008, (0.031, 0.026)),
    'pinky': (0.023, (0.025, 0.021)),
}
FINGER_R = 0.0085
PALM = (0.072, 0.022, 0.076)   # width (across), thickness, length
FACE_KEYS = ['blink_L', 'blink_R', 'happy', 'wide', 'squint', 'look_x', 'look_y', 'smile', 'open',
             'o_shape', 'frown', 'brow_up', 'brow_down', 'brow_worried']

DEFAULT_SPEC = {
    'skin': '#0c0a12', 'top': '#d8352c', 'top_style': 'hoodie', 'legs': '#0c0a12',
    'shoes': '#141118', 'hat': 'beanie', 'hat_color': '#f2c12e', 'pompom': True,
    'scale': 1.0, 'face': '#fdf7ee', 'rim': 1.0, 'brows': True,
}


def side_sign(s):
    return 1.0 if s == 'L' else -1.0


def mirror(p, s):
    return Vector((p[0] * side_sign(s), p[1], p[2]))


# ====================================================================== armature
def build_armature(name, col, scale):
    arm = bpy.data.armatures.new(name + '_rig')
    ob = bpy.data.objects.new(name, arm)
    col.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones
    S = scale

    def bone(n, h, t, parent=None, connect=False, roll_to=None, deform=True):
        b = eb.new(n)
        b.head, b.tail = Vector(h) * S, Vector(t) * S
        if roll_to is not None:
            b.align_roll(Vector(roll_to))
        if parent:
            b.parent = eb[parent]
            b.use_connect = connect
        b.use_deform = deform
        return b

    bone('hips', *SK['hips'], roll_to=(0, -1, 0))
    bone('spine', *SK['spine'], 'hips', True, roll_to=(0, -1, 0))
    bone('chest', *SK['chest'], 'spine', True, roll_to=(0, -1, 0))
    bone('neck', *SK['neck'], 'chest', True, roll_to=(0, -1, 0))
    bone('head', *SK['head'], 'neck', True, roll_to=(0, -1, 0))
    top = HEAD_C + Vector((0, 0.0, HEAD_R))
    bone('pompom', top + Vector((0, 0.0, 0.0)), top + Vector((0, 0.03, 0.07)), 'head', roll_to=(0, -1, 0))
    for s in 'LR':
        m = lambda k: (mirror(SK[k][0], s), mirror(SK[k][1], s))
        bone('thigh.' + s, *m('thigh'), 'hips', roll_to=(0, -1, 0))
        bone('shin.' + s, *m('shin'), 'thigh.' + s, True, roll_to=(0, -1, 0))
        bone('foot.' + s, *m('foot'), 'shin.' + s, True, roll_to=(0, 0, 1))
        bone('foot_ik.' + s, *m('foot'), roll_to=(0, 0, 1), deform=False)
        kp = mirror((0.09, -0.6, 0.5), s)
        bone('knee_pole.' + s, kp, kp + Vector((0, 0, 0.06)), 'foot_ik.' + s, deform=False)
        bone('shoulder.' + s, *m('shoulder'), 'chest', roll_to=(0, -1, 0))
        bone('upper_arm.' + s, *m('upper_arm'), 'shoulder.' + s, True, roll_to=(0, -1, 0))
        bone('forearm.' + s, *m('forearm'), 'upper_arm.' + s, True, roll_to=(0, -1, 0))
        palm_n = (-side_sign(s), 0, 0)          # palms face the thighs
        bone('hand.' + s, *m('hand'), 'forearm.' + s, True, roll_to=palm_n)
        bone('hand_ik.' + s, *m('hand'), roll_to=palm_n, deform=False)
        ep = mirror((0.24, 0.32, 0.55), s)
        bone('elbow_pole.' + s, ep, ep + Vector((0, 0, 0.06)), 'chest', deform=False)
        wrist = Vector(mirror(SK['hand'][0], s))
        for fn, (off, segs) in FINGERS.items():
            base = wrist + Vector((0, off, -PALM[2]))
            p = base
            for i, L in enumerate(segs):
                q = p + Vector((0, 0, -L))
                bone('f_%s.%02d.%s' % (fn, i + 1, s), p, q,
                     'hand.' + s if i == 0 else 'f_%s.%02d.%s' % (fn, i, s), i > 0, roll_to=palm_n)
                p = q
        # thumb: from the front edge of the palm, angled forward/down, nail facing out
        t0 = wrist + Vector((-side_sign(s) * 0.012, -0.03, -0.022))
        t1 = t0 + Vector((-side_sign(s) * 0.01, -0.022, -0.022))
        t2 = t1 + Vector((-side_sign(s) * 0.006, -0.012, -0.02))
        bone('thumb.01.' + s, t0, t1, 'hand.' + s, roll_to=palm_n)
        bone('thumb.02.' + s, t1, t2, 'thumb.01.' + s, True, roll_to=palm_n)
        cl = Vector(mirror((0.035, -0.11, 1.2), s))
        bone('string.' + s, cl, cl + Vector((0, -0.005, -0.12)), 'chest', roll_to=(0, -1, 0))
    rest = {b.name: (b.head.copy(), b.tail.copy(), b.x_axis.copy()) for b in eb}
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    # IK constraints with rest-preserving pole angles
    for s in 'LR':
        for upper, lower, tgt, pole in (('thigh', 'shin', 'foot_ik', 'knee_pole'),
                                        ('upper_arm', 'forearm', 'hand_ik', 'elbow_pole')):
            c = ob.pose.bones[lower + '.' + s].constraints.new('IK')
            c.target, c.subtarget = ob, tgt + '.' + s
            c.pole_target, c.pole_subtarget = ob, pole + '.' + s
            c.chain_count = 2
            uh, ut, ux = rest[upper + '.' + s]
            lh, lt, _ = rest[lower + '.' + s]
            ph = rest[pole + '.' + s][0]
            c.pole_angle = _pole_angle(uh, ut, ux, lt, ph)
        for b, tgt in (('foot', 'foot_ik'), ('hand', 'hand_ik')):
            c = ob.pose.bones[b + '.' + s].constraints.new('COPY_ROTATION')
            c.target, c.subtarget = ob, tgt + '.' + s
    bpy.ops.object.mode_set(mode='OBJECT')
    for k in FACE_KEYS:
        ob[k] = 0.0
    ob['studio_character'] = True
    return ob


def _pole_angle(base_head, base_tail, base_x, ik_tail, pole_loc):
    def signed(v1, v2, n):
        a = v1.angle(v2)
        return a if n.dot(v1.cross(v2)) < 0 else -a
    pole_normal = (ik_tail - base_head).cross(pole_loc - base_head)
    proj = pole_normal.cross(base_tail - base_head)
    return signed(base_x, proj, base_tail - base_head)


# ====================================================================== body mesh
def build_body(name, rig, spec, col):
    S = spec['scale']
    M = {k: materials.cel('%s_%s' % (name, k), spec[c], rim=spec['rim'] * r)
         for k, c, r in (('skin', 'skin', 1.0), ('top', 'top', 0.8), ('legs', 'legs', 1.0),
                         ('shoes', 'shoes', 1.0), ('hat', 'hat_color', 0.7))}
    mats = [M['skin'], M['top'], M['legs'], M['shoes'], M['hat']]
    SKIN, TOP, LEGS, SHOES, HAT = range(5)
    mb = geom.MeshBuilder(name + '_body')
    sc = Matrix.Scale(S, 4)

    def put(part, mat, group=None, weights_fn=None):
        v, f = part
        v = [tuple(sc @ Vector(p)) for p in v]
        if weights_fn:
            mb.add(v, f, mat, weights=[weights_fn(Vector(p) / S) for p in v])
        else:
            mb.add(v, f, mat, group)

    # head + neck
    put(geom.ellipsoid(HEAD_R, HEAD_R * 0.96, HEAD_R * 1.0, HEAD_C, 32, 18), SKIN, 'head')
    put(geom.capsule((0, 0, 1.27), (0, 0, 1.40), 0.032), SKIN, 'neck')

    # torso (hoodie): lathe with an oval section, blended weights hips->spine->chest
    def torso_w(p):
        z = p.z
        if z < 0.97:
            return {'hips': 1.0}
        if z < 1.04:
            u = (z - 0.97) / 0.07
            return {'hips': 1 - u, 'spine': u}
        if z < 1.12:
            u = (z - 1.04) / 0.08
            return {'spine': 1 - u, 'chest': u}
        return {'chest': 1.0}
    if spec['top_style'] in ('hoodie', 'jacket', 'shirt'):
        prof = [(0.0, 0.80), (0.115, 0.805), (0.135, 0.84), (0.14, 0.92), (0.13, 1.02), (0.135, 1.12),
                (0.15, 1.20), (0.14, 1.26), (0.10, 1.295), (0.05, 1.31), (0.0, 1.312)]
        put(geom.lathe(prof, 28, False, False, sx=0.92, sy=0.72), TOP, weights_fn=torso_w)
        if spec['top_style'] == 'hoodie':   # hood bunched behind the neck + pocket
            put(geom.ellipsoid(0.11, 0.07, 0.06, (0, 0.085, 1.30), 18, 10), TOP, 'chest')
            put(geom.box(0.16, 0.02, 0.07, (0, -0.098, 0.95), bevel=0.01), TOP, 'hips')
    # strings (secondary motion)
    for s in 'LR':
        base = mirror((0.035, -0.11, 1.2), s)
        put(geom.capsule(base, base + Vector((0, -0.005, -0.12)), 0.0045, 0.0045, 8, 3), HAT, 'string.' + s)

    for s in 'LR':
        g = lambda b: b + '.' + s
        # legs: thin black limbs with joint spheres hiding the seams
        hip, knee, ank = [mirror(p, s) for p in (SK['thigh'][0], SK['thigh'][1], SK['shin'][1])]
        put(geom.capsule(hip + Vector((0, 0, 0.03)), knee, 0.047, 0.036, 16, 5), LEGS, g('thigh'))
        put(geom.capsule(knee, ank, 0.036, 0.03, 16, 5), LEGS, g('shin'))
        # shoe: rounded wedge along the foot bone
        put(_shoe(s), SHOES, g('foot'))
        # arms: sleeve on upper arm + forearm, black wrist
        sh, el, wr = [mirror(p, s) for p in (SK['upper_arm'][0], SK['upper_arm'][1], SK['forearm'][1])]
        put(geom.capsule(mirror((0.06, 0, 1.25), s), sh, 0.05, 0.05, 14, 4), TOP, g('shoulder'))
        put(geom.capsule(sh, el, 0.042, 0.037, 16, 5), TOP, g('upper_arm'))
        cuff = wr + (el - wr).normalized() * 0.03
        put(geom.capsule(el, cuff, 0.037, 0.034, 16, 5), TOP, g('forearm'))
        put(geom.capsule(cuff, wr, 0.024, 0.022, 12, 3), SKIN, g('forearm'))
        # hand: palm + fingers + thumb, each rigid on its bone
        put(_palm(s), SKIN, g('hand'))
        wrist = Vector(mirror(SK['hand'][0], s))
        for fn, (off, segs) in FINGERS.items():
            p = wrist + Vector((0, off, -PALM[2]))
            for i, L in enumerate(segs):
                q = p + Vector((0, 0, -L))
                r1 = FINGER_R * (0.92 if i else 1.0)
                put(geom.capsule(p, q + Vector((0, 0, (r1 * 0.6 if i else 0))), r1, r1 * 0.95, 10, 3), SKIN,
                    'f_%s.%02d.%s' % (fn, i + 1, s))
                p = q
        t0 = wrist + Vector((-side_sign(s) * 0.012, -0.03, -0.022))
        t1 = t0 + Vector((-side_sign(s) * 0.01, -0.022, -0.022))
        t2 = t1 + Vector((-side_sign(s) * 0.006, -0.012, -0.02))
        put(geom.capsule(t0, t1, 0.011, 0.01, 10, 3), SKIN, g('thumb.01'))
        put(geom.capsule(t1, t2, 0.0095, 0.0088, 10, 3), SKIN, g('thumb.02'))

    # hat
    if spec.get('hat') == 'beanie':
        prof = []
        for i in range(13):
            a = (math.pi / 2) * i / 12
            prof.append(((HEAD_R + 0.012) * math.cos(a) * (1.0 if i else 1.0),
                         HEAD_C.z + 0.035 + (HEAD_R + 0.03) * math.sin(a)))
        prof[-1] = (0.0, prof[-1][1])
        v, f = geom.lathe(prof, 32, False, False)
        put((v, f), HAT, 'head')
        band = [(HEAD_R + 0.02, HEAD_C.z + 0.02), (HEAD_R + 0.024, HEAD_C.z + 0.045),
                (HEAD_R + 0.021, HEAD_C.z + 0.075), (HEAD_R + 0.012, HEAD_C.z + 0.08)]
        put(geom.lathe(band, 32, True, True), HAT, 'head')
        if spec.get('pompom'):
            top = HEAD_C + Vector((0, 0.03, HEAD_R + 0.085))
            put(geom.ellipsoid(0.04, 0.04, 0.038, top, 16, 10), HAT, 'pompom')
    elif spec.get('hat') == 'cap':
        prof = [(HEAD_R + 0.008, HEAD_C.z + 0.03)] + [((HEAD_R + 0.01) * math.cos(a), HEAD_C.z + 0.03 + (HEAD_R + 0.01) * math.sin(a))
                                                    for a in [math.pi / 2 * i / 10 for i in range(1, 11)]]
        prof[-1] = (0.0, prof[-1][1])
        put(geom.lathe(prof, 32, True, False), HAT, 'head')
        put(geom.ellipsoid(0.12, 0.09, 0.008, HEAD_C + Vector((0, -0.17, 0.045)), 20, 6), HAT, 'head')

    ob = mb.build(mats, col)
    ob.parent = rig
    mod = ob.modifiers.new('rig', 'ARMATURE')
    mod.object = rig
    return ob


def _shoe(s):
    """Rounded shoe around the foot bone (ankle -> toe), sole at z=0."""
    ank = mirror(SK['foot'][0], s)
    v, f = geom.ellipsoid(0.05, 0.105, 0.045, (0, 0, 0), 18, 10)
    out = []
    for p in v:
        x, y, z = p
        z = max(z, -0.03) + 0.03                      # flat sole
        if y < 0:
            z *= 0.75 + 0.25 * (1 + y / 0.105)          # toe slightly lower
        out.append((ank.x + x, ank.y - 0.045 + y, z))
    return out, f


def _palm(s):
    wrist = Vector(mirror(SK['hand'][0], s))
    v, f = geom.ellipsoid(PALM[1] / 2 + 0.002, PALM[0] / 2 + 0.006, PALM[2] / 2 + 0.008, (0, 0, 0), 14, 8)
    c = wrist + Vector((0, 0, -PALM[2] / 2))
    return [(c.x + p[0], c.y + p[1], c.z + p[2]) for p in v], f


# ====================================================================== face
def _project(u, v, out=0.004):
    """Face-plane coordinates (u right-of-viewer = -X... we use +u = character left) to head surface."""
    R = HEAD_R + out
    d = R * R - u * u - v * v
    y = -math.sqrt(max(d, 1e-6))
    return Vector((u, HEAD_C.y + y, HEAD_C.z + v))


def _shape(cx, cy, n, upper, lower, sx=1.0, dx=0.0, dy=0.0):
    """Filled region between two curves sampled at n points across x in [-1,1]."""
    pts = []
    for i in range(n):
        x = -1 + 2 * i / (n - 1)
        pts.append((x, upper(x), lower(x)))
    return pts


def _region_mesh(curves_by_key, cx, cy, half_w):
    """curves_by_key: key -> list of (x, up, lo) with identical n. Returns basis verts, faces, key verts."""
    keys = {}
    n = None
    for k, pts in curves_by_key.items():
        vs = []
        for x, up, lo in pts:
            vs.append(_project(cx + x * half_w, cy + up))
        for x, up, lo in pts:
            vs.append(_project(cx + x * half_w, cy + lo))
        keys[k] = vs
        n = len(pts)
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    return keys, faces


def build_face(name, rig, spec, col):
    """White face features with shape keys, rigid on the head bone, driven by rig custom props."""
    S = spec['scale']
    white = materials.flat(name + '_face', spec['face'], 1.0)
    N = 15
    parts = []   # (keys dict, faces, key_map(prop->key name))

    def ellipse(h):
        return lambda x: h * math.sqrt(max(0.0, 1 - x * x))

    for s in 'LR':
        cx = side_sign(s) * 0.056
        cy = 0.018
        w = 0.026
        base = [(x, ellipse(0.034)(x), -ellipse(0.034)(x)) for x in [-1 + 2 * i / (N - 1) for i in range(N)]]
        xs = [-1 + 2 * i / (N - 1) for i in range(N)]
        k = {
            'Basis': base,
            'blink': [(x, -0.012 + 0.006 * (1 - x * x) + 0.003, -0.012 + 0.006 * (1 - x * x) - 0.003) for x in xs],
            'happy': [(x, 0.004 + 0.016 * (1 - x * x) + 0.0035, 0.004 + 0.016 * (1 - x * x) - 0.0035) for x in xs],
            'wide': [(x * 1.18, ellipse(0.042)(x), -ellipse(0.042)(x)) for x in xs],
            'squint': [(x, ellipse(0.013)(x) + 0.002, -ellipse(0.022)(x)) for x in xs],
        }
        parts.append(('eye_' + s, cx, cy, w, k))
    # mouth
    xs = [-1 + 2 * i / (N - 1) for i in range(N)]
    mk = {
        'Basis': [(x * 0.8, -0.003 + 0.008 * x * x + 0.0032, -0.003 + 0.008 * x * x - 0.0032) for x in xs],
        'smile': [(x * 1.25, -0.012 + 0.022 * x * x + 0.0036, -0.012 + 0.022 * x * x - 0.0036) for x in xs],
        'open': [(x * 1.0, 0.004 + 0.006 * x * x, 0.004 + 0.006 * x * x - 0.036 * (1 - x * x) ** 0.8 - 0.004) for x in xs],
        'o_shape': [(x * 0.45, 0.012 * math.sqrt(max(0, 1 - x * x)) + 0.002, -0.016 * math.sqrt(max(0, 1 - x * x)) - 0.002) for x in xs],
        'frown': [(x * 0.95, 0.006 - 0.014 * x * x + 0.0032, 0.006 - 0.014 * x * x - 0.0032) for x in xs],
    }
    parts.append(('mouth', 0.0, -0.062, 0.03, mk))
    if spec.get('brows', True):
        for s in 'LR':
            sg = side_sign(s)
            # x runs across the brow; inner end is x=-sg... we write curves in character-left space
            def br(lift, inner, outer, thick=0.0035):
                def f(x):
                    tin = (1 - x * sg) / 2      # 1 at inner end (towards the nose)
                    return lift + inner * tin + outer * (1 - tin) + 0.004 * (1 - x * x)
                return [(x, f(x) + thick, f(x) - thick) for x in xs]
            bk = {'Basis': br(0, 0, 0), 'brow_up': br(0.016, 0.004, 0.0), 'brow_down': br(-0.008, -0.012, 0.004),
                  'brow_worried': br(0.006, 0.014, -0.006)}
            parts.append(('brow_' + s, sg * 0.058, 0.072, 0.024, bk))

    mb_keys = {}
    allv, allf = [], []
    key_lists = {}
    for pname, cx, cy, w, k in parts:
        keys, faces = _region_mesh(k, cx, cy, w)
        b = len(allv)
        allv.extend(keys['Basis'])
        allf.extend(tuple(b + i for i in f) for f in faces)
        for kn, vs in keys.items():
            if kn == 'Basis':
                continue
            key_lists.setdefault((pname, kn), (b, vs))
    me = bpy.data.meshes.new(name + '_face')
    me.from_pydata([tuple(Vector(p) * S) for p in allv], [], allf)
    me.update()
    me.materials.append(white)
    ob = bpy.data.objects.new(name + '_face', me)
    col.objects.link(ob)
    ob.visible_shadow = False
    ob.shape_key_add(name='Basis')
    # one shape key per (part, key): eye keys per side so blinks can be asymmetric
    for (pname, kn), (b, vs) in key_lists.items():
        sk = ob.shape_key_add(name='%s:%s' % (pname, kn), from_mix=False)
        for i, p in enumerate(vs):
            sk.data[b + i].co = Vector(p) * S
    # look shapes: translate eyes (and slightly the brows) on the surface
    for kn, (du, dv) in (('look_r', (-0.024, 0)), ('look_l', (0.024, 0)), ('look_u', (0, 0.016)), ('look_d', (0, -0.016))):
        sk = ob.shape_key_add(name='look:' + kn, from_mix=False)
        off = 0
        for pname, cx, cy, w, k in parts:
            cnt = len(k['Basis']) * 2
            if pname.startswith('eye') or pname.startswith('brow'):
                f = 1.0 if pname.startswith('eye') else 0.5
                for i in range(cnt):
                    p = Vector(allv[off + i])
                    u, v = p.x + du * f, p.z - HEAD_C.z + dv * f
                    sk.data[off + i].co = _project(u, v) * S
            off += cnt
    for kb in ob.data.shape_keys.key_blocks[1:]:
        kb.slider_min = 0.0
        kb.slider_max = 1.0
    # drivers from rig props
    def drive(kb_name, expr, props):
        kb = ob.data.shape_keys.key_blocks.get(kb_name)
        if not kb:
            return
        fc = kb.driver_add('value')
        d = fc.driver
        d.type = 'SCRIPTED'
        for p in props:
            v = d.variables.new()
            v.name = p
            v.targets[0].id_type = 'OBJECT'
            v.targets[0].id = rig
            v.targets[0].data_path = '["%s"]' % p
        d.expression = expr
    for s in 'LR':
        drive('eye_%s:blink' % s, 'min(1,blink_%s)' % s, ['blink_' + s])
        drive('eye_%s:happy' % s, 'happy*(1-min(1,blink_%s))' % s, ['happy', 'blink_' + s])
        drive('eye_%s:wide' % s, 'wide*(1-min(1,blink_%s))*(1-happy)' % s, ['wide', 'blink_' + s, 'happy'])
        drive('eye_%s:squint' % s, 'squint*(1-min(1,blink_%s))*(1-happy)' % s, ['squint', 'blink_' + s, 'happy'])
        for k in ('brow_up', 'brow_down', 'brow_worried'):
            drive('brow_%s:%s' % (s, k), k, [k])
    for k in ('smile', 'open', 'o_shape', 'frown'):
        drive('mouth:' + k, k, [k])
    drive('look:look_l', 'max(0,look_x)', ['look_x'])
    drive('look:look_r', 'max(0,-look_x)', ['look_x'])
    drive('look:look_u', 'max(0,look_y)', ['look_y'])
    drive('look:look_d', 'max(0,-look_y)', ['look_y'])
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = 'head'
    hb = rig.data.bones['head']
    ob.matrix_parent_inverse = (hb.matrix_local @ Matrix.Translation((0, hb.length, 0))).inverted()
    return ob


# ====================================================================== mannequin body
def body_material(name, sp):
    """Material for the mannequin look: 'clay' (white), 'subject' (solid colour), 'ghost' (hologram)."""
    kind = sp.get('material', 'clay')
    color = sp.get('color', '#ececec' if kind == 'clay' else '#e8382f')
    if kind == 'ghost':
        return materials.ghost(name + '_ghost', sp.get('color', '#9fd8ff'), sp.get('glow', 1.6), sp.get('alpha', 0.3))
    if kind == 'subject':
        return materials.subject(name + '_subject', color)
    if kind == 'smooth':
        return materials.plastic(name + '_skin', sp.get('color', '#f4f3f0'), rough=0.28, coat=0.35)
    if kind == 'cel':
        return materials.cel(name + '_skin', sp['skin'], rim=sp['rim'])
    return materials.clay(name + '_clay', color)


def build_mannequin(name, rig, sp, col):
    """Smooth, faceless mannequin with adult proportions on the standard rig (news/explainer look)."""
    S = sp['scale']
    M = body_material(name, sp)
    mb = geom.MeshBuilder(name + '_body')
    sc = Matrix.Scale(S, 4)

    def put(part, group=None, weights_fn=None):
        v, f = part
        v = [tuple(sc @ Vector(p)) for p in v]
        if weights_fn:
            mb.add(v, f, 0, weights=[weights_fn(Vector(p) / S) for p in v])
        else:
            mb.add(v, f, 0, group)

    hs = sp.get('head_scale', 1.18)
    hc = Vector((0, -0.005, 1.49 + 0.08 * hs))
    put(geom.ellipsoid(0.098 * hs, 0.11 * hs, 0.122 * hs, hc, 28, 16), 'head')
    put(geom.capsule((0, 0, 1.27), (0, 0.0, hc.z - 0.06), 0.047), 'neck')

    def torso_w(p):
        z = p.z
        if z < 0.97:
            return {'hips': 1.0}
        if z < 1.04:
            u = (z - 0.97) / 0.07
            return {'hips': 1 - u, 'spine': u}
        if z < 1.12:
            u = (z - 1.04) / 0.08
            return {'spine': 1 - u, 'chest': u}
        return {'chest': 1.0}
    prof = [(0.0, 0.80), (0.12, 0.81), (0.15, 0.86), (0.155, 0.93), (0.14, 1.0), (0.135, 1.06), (0.15, 1.13),
            (0.17, 1.2), (0.17, 1.25), (0.13, 1.295), (0.06, 1.315), (0.0, 1.318)]
    put(geom.lathe(prof, 32, False, False, sx=1.0, sy=0.62), weights_fn=torso_w)
    for s in 'LR':
        g = lambda b: b + '.' + s
        hip, knee, ank = [mirror(p, s) for p in (SK['thigh'][0], SK['thigh'][1], SK['shin'][1])]
        put(geom.capsule(hip + Vector((0, 0, 0.03)), knee, 0.075, 0.052, 18, 6), g('thigh'))
        put(geom.capsule(knee, ank, 0.052, 0.036, 18, 6), g('shin'))
        put(_shoe(s), g('foot'))
        sh, el, wr = [mirror(p, s) for p in (SK['upper_arm'][0], SK['upper_arm'][1], SK['forearm'][1])]
        put(geom.capsule(mirror((0.07, 0, 1.245), s), sh, 0.058, 0.055, 16, 5), g('shoulder'))
        put(geom.capsule(sh, el, 0.047, 0.04, 16, 5), g('upper_arm'))
        put(geom.capsule(el, wr, 0.04, 0.029, 16, 5), g('forearm'))
        put(_palm(s), g('hand'))
        wrist = Vector(mirror(SK['hand'][0], s))
        for fn, (off, segs) in FINGERS.items():
            p = wrist + Vector((0, off, -PALM[2]))
            for i, L in enumerate(segs):
                q = p + Vector((0, 0, -L))
                r1 = FINGER_R * (0.92 if i else 1.0)
                put(geom.capsule(p, q + Vector((0, 0, (r1 * 0.6 if i else 0))), r1, r1 * 0.95, 10, 3),
                    'f_%s.%02d.%s' % (fn, i + 1, s))
                p = q
        t0 = wrist + Vector((-side_sign(s) * 0.012, -0.03, -0.022))
        t1 = t0 + Vector((-side_sign(s) * 0.01, -0.022, -0.022))
        t2 = t1 + Vector((-side_sign(s) * 0.006, -0.012, -0.02))
        put(geom.capsule(t0, t1, 0.011, 0.01, 10, 3), g('thumb.01'))
        put(geom.capsule(t1, t2, 0.0095, 0.0088, 10, 3), g('thumb.02'))
    hat = sp.get('hat')
    if hat == 'pilot_cap':
        top = hc.z + 0.07 * hs
        put(geom.lathe([(0.0, top - 0.02), (0.105, top - 0.02), (0.108, top + 0.035), (0.135, top + 0.06),
                        (0.13, top + 0.075), (0.0, top + 0.08)], 32), 'head')
        put(geom.ellipsoid(0.085, 0.06, 0.008, hc + Vector((0, -0.11, 0.055)), 20, 6), 'head')
    elif hat == 'cap':
        put(geom.lathe([(0.102, hc.z + 0.03)] + [(0.104 * math.cos(a), hc.z + 0.03 + 0.11 * math.sin(a))
                                                 for a in [math.pi / 2 * i / 8 for i in range(1, 9)]], 32, True, False), 'head')
        put(geom.ellipsoid(0.09, 0.07, 0.007, hc + Vector((0, -0.12, 0.04)), 20, 6), 'head')
    if sp.get('hair') == 'bun':
        put(geom.ellipsoid(0.05, 0.05, 0.045, hc + Vector((0, 0.09, 0.08)), 16, 10), 'head')
    elif sp.get('hair') == 'short':
        put(geom.ellipsoid(0.103, 0.116, 0.1, hc + Vector((0, 0.008, 0.035)), 28, 14), 'head')
    ob = mb.build([M], col)
    ob.parent = rig
    mod = ob.modifiers.new('rig', 'ARMATURE')
    mod.object = rig
    if sp.get('material') == 'ghost':
        ob.visible_shadow = False
    return ob


# ====================================================================== entry
def load_preset(spec):
    """{"preset": "timmy", ...overrides} -> the saved character spec from engine/characters/<preset>.json."""
    spec = dict(spec or {})
    if spec.get('preset'):
        import json, os
        fn = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'characters', spec['preset'].lower() + '.json')
        base = {k: v for k, v in json.load(open(fn)).items() if not k.startswith('_')}
        base.update({k: v for k, v in spec.items() if k != 'preset'})
        spec = base
    return spec


def build_character(name, spec, col):
    sp = dict(DEFAULT_SPEC)
    sp.update(load_preset(spec))
    rig = build_armature(name, col, sp['scale'])
    if sp.get('body') == 'toon':
        from .toon import build_toon
        body, face = build_toon(name, rig, sp, col)
        rig['spec_scale'] = sp['scale']
        rig.hide_render = True
        return rig, body, face
    if sp.get('body') == 'sculpt':
        from .sculpt import build_sculpt
        body, face = build_sculpt(name, rig, sp, col, body_material(name, sp))
        rig['spec_scale'] = sp['scale']
        rig.hide_render = True
        return rig, body, face
    if sp.get('body') == 'mannequin':
        body = build_mannequin(name, rig, sp, col)
        face = build_face(name, rig, sp, col) if sp.get('face_marks') else None
        rig['spec_scale'] = sp['scale']
        rig.hide_render = True
        return rig, body, face
    body = build_body(name, rig, sp, col)
    face = build_face(name, rig, sp, col)
    rig['spec_scale'] = sp['scale']
    rig.show_in_front = False
    rig.hide_render = True
    return rig, body, face
