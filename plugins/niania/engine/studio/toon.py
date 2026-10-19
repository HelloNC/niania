"""Big-head toon figure ("The Observer" model sheet): a huge smooth sphere head with dot eyes, bar brows
and a small mouth, a boxy tunic with a tall funnel collar and short sleeves, slim noodle arms with big
four-finger hands, skinny legs and chunky faceted boots. Skinned to the standard rig, so every
performance verb works unchanged, and the face reacts to the same face props (expr / blink / look / lip-sync).

spec: {"body": "toon", "skin": "#eadfcc", "top": "#8e1f2a", "legs": "#3d3b39", "shoes": "#4a4744",
       "features": "#1d1a1a", "brow_color": "#3b3734", "head_r": 0.185, "scale": 1.0}
Rest pose faces -Y, character-left is +X (same frame as character.SK).
"""
import math
import bpy
from mathutils import Vector, Matrix, Quaternion
from . import geom
from .character import SK, FINGERS, FINGER_R, PALM, mirror, side_sign
from .sculpt import _skin, _bone


def _mat(name, color, rough):
    from . import materials as M
    return M.plastic(name, color, rough=rough, coat=0.05, spec=0.35)


def build_toon(name, rig, sp, col):
    S = sp.get('scale', 1.0)
    HR = sp.get('head_r', 0.185)
    HC = Vector((0, -0.004, sp.get('head_z', 1.585)))
    HK = sp.get('hand_k', 1.0)                       # chunkier cartoon hands (radius scale)
    mats = [_mat(name + '_skin', sp.get('skin', '#eadfcc'), 0.55),
            _mat(name + '_top', sp.get('top', '#8e1f2a'), 0.8),
            _mat(name + '_legs', sp.get('legs', '#3d3b39'), 0.75),
            _mat(name + '_shoes', sp.get('shoes', '#4a4744'), 0.7),
            _mat(name + '_under', sp.get('under', '#2a2626'), 0.8)]
    SKIN, TOP, LEGS, SHOES, UNDER = range(5)
    mb = geom.MeshBuilder(name + '_body')

    def add(part, mat, group=None, bones=None, sigma=0.03):
        v, f = part
        w = _skin(v, bones, sigma) if bones else None
        mb.add([tuple(Vector(p) * S) for p in v], f, mat, group=group, weights=w)

    # ------------------------------------------------------------ head (rigid on the head bone)
    hv, hf = geom.ellipsoid(HR, HR * 0.97, HR * 1.04, HC, 48, 32)
    add((hv, hf), SKIN, 'head')
    # ------------------------------------------------------------ tunic (boxy, slight A-line flare)
    prof = [(0.0, 0.80), (0.168, 0.80), (0.176, 0.815), (0.168, 0.90), (0.156, 0.99), (0.16, 1.10),
            (0.166, 1.19), (0.158, 1.245), (0.13, 1.285), (0.09, 1.30), (0.0, 1.30)]
    BK = sp.get('body_k', 1.0)
    v, f = geom.lathe(prof, 40, sx=BK, sy=0.74 * (1 + (BK - 1) * 0.5))
    add((v, f), TOP, bones=[_bone('hips'), _bone('spine'), _bone('chest'), _bone('shoulder', 'L'), _bone('shoulder', 'R')], sigma=0.05)
    # funnel collar (open tube, flares upward around the base of the head) + dark V notch at the front
    cp = [(0.074, 1.255), (0.086, 1.33), (0.104, 1.415), (0.112, 1.42), (0.096, 1.415), (0.078, 1.33), (0.066, 1.26)]
    v, f = geom.lathe(cp, 40, False, False, sx=1.08 * sp.get('collar_k', 1.0), sy=0.98 * sp.get('collar_k', 1.0))
    add((v, f), TOP, bones=[_bone('chest'), _bone('neck')], sigma=0.04)
    nv = [(-0.022, -0.115, 1.42), (0.022, -0.115, 1.42), (0.0, -0.096, 1.33),
          (-0.02, -0.105, 1.42), (0.02, -0.105, 1.42), (0.0, -0.088, 1.335)]
    add((nv, [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1)]), UNDER, bones=[_bone('chest'), _bone('neck')], sigma=0.04)
    # shorts / pelvis under the tunic
    add(geom.ellipsoid(0.125, 0.09, 0.08, (0, 0.005, 0.86), 24, 12), LEGS, 'hips')
    # ------------------------------------------------------------ arms: short sleeve + noodle arms + big hands
    for s in 'LR':
        sg = side_sign(s)
        sh, el = Vector(mirror(SK['upper_arm'][0], s)), Vector(mirror(SK['upper_arm'][1], s))
        wr = Vector(mirror(SK['forearm'][1], s))
        add(geom.capsule(sh + Vector((-sg * 0.01, 0, 0.0)), sh.lerp(el, 0.42), 0.062 * (1 + (BK - 1) * 0.6), 0.056 * (1 + (BK - 1) * 0.6), 20, 5), TOP,
            bones=[_bone('shoulder', s), _bone('upper_arm', s)], sigma=0.03)
        add(geom.capsule(sh + Vector((0, 0, -0.02)), el, 0.033, 0.031, 16, 4), SKIN, 'upper_arm.' + s)
        add(geom.capsule(el, wr, 0.031, 0.027, 16, 4), SKIN, 'forearm.' + s)
        hb = 'hand.' + s
        c = wr + Vector((0, 0, -PALM[2] / 2))
        add(geom.ellipsoid((PALM[1] / 2 + 0.008) * (1 + (HK - 1) * 0.6), (PALM[0] / 2 + 0.008) * HK, (PALM[2] / 2 + 0.008) * (1 + (HK - 1) * 0.5), c, 20, 12), SKIN, hb)
        add(geom.ellipsoid(0.018, 0.022, 0.026, wr + Vector((-sg * 0.008, -0.022, -0.03)), 14, 8), SKIN, hb)
        fr = FINGER_R * 1.3 * HK
        for fn, (off, segs) in FINGERS.items():
            if fn == 'pinky':
                continue                                   # cartoon four-finger hand: three fingers + thumb
            p = wr + Vector((0, off * 1.25 + (0.004 if fn == 'ring' else 0.0), -PALM[2] + 0.004))
            for i, L in enumerate(segs):
                q = p + Vector((0, 0, -L))
                add(geom.capsule(p, q, fr * (1.0 if i == 0 else 0.95), fr * (0.95 if i == 0 else 0.9), 14, 4), SKIN,
                    'f_%s.%02d.%s' % (fn, i + 1, s))
                p = q
        t0 = wr + Vector((-sg * 0.012, -0.03, -0.022))
        t1 = t0 + Vector((-sg * 0.01, -0.022, -0.022))
        t2 = t1 + Vector((-sg * 0.006, -0.012, -0.02))
        add(geom.capsule(t0, t1, 0.0145 * HK, 0.013 * HK, 14, 4), SKIN, 'thumb.01.' + s)
        add(geom.capsule(t1, t2, 0.013 * HK, 0.0115 * HK, 14, 4), SKIN, 'thumb.02.' + s)
    # ------------------------------------------------------------ legs + chunky boots
    for s in 'LR':
        hip, knee = Vector(mirror(SK['thigh'][0], s)), Vector(mirror(SK['thigh'][1], s))
        ank = Vector(mirror(SK['shin'][1], s))
        add(geom.capsule(hip + Vector((0, 0, 0.02)), knee, 0.046, 0.04, 16, 4), LEGS, 'thigh.' + s)
        add(geom.capsule(knee, ank + Vector((0, 0, 0.03)), 0.04, 0.035, 16, 4), LEGS, 'shin.' + s)
        # boot: faceted block (shoe) on the foot bone + ankle cuff on the shin
        bx, by = ank.x, ank.y
        OK = sp.get('boot_k', 1.0)
        bv, bf = geom.box(0.112 * OK, 0.215 * OK, 0.085 * OK, (bx, by - 0.045 * OK, 0.0425 * OK), bevel=0.012)
        bv = [(x, y, z - 0.032 * OK * min(1.0, max(0.0, (by - 0.03 - y) / (0.11 * OK))) if z > 0.05 * OK else z) for x, y, z in bv]   # toe slopes down
        add((bv, bf), SHOES, 'foot.' + s)
        cv, cf = geom.lathe([(0.0, 0.05), (0.056, 0.05), (0.058, 0.12), (0.05, 0.165), (0.0, 0.165)], 8, phase=math.pi / 8, sx=1.0, sy=1.1)
        cv = [(x + bx, y + by + 0.012, z) for x, y, z in cv]
        add((cv, cf), SHOES, bones=[_bone('foot', s), _bone('shin', s)], sigma=0.03)
    ob = mb.build(mats, col)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.parent = rig
    mod = ob.modifiers.new('rig', 'ARMATURE')
    mod.object = rig
    face = build_toon_face(name, rig, sp, col, HC, HR) if sp.get('face', True) else None
    return ob, face


def build_toon_face(name, rig, sp, col, HC, HR):
    """Dot eyes (blink / squint / happy / wide by squash, look by sliding on the head), rounded bar brows
    (up / down / worried) and a small dark mouth (smile / open / o / frown), rigid on the head bone and driven
    by the rig's face props through shape keys."""
    S = sp.get('scale', 1.0)
    HCn, KF = Vector(HC), HR / 0.185                   # features are designed on the reference head, then scaled on
    HC, HR = Vector((0, -0.004, 1.585)), 0.185

    def fmap(p):
        return (HCn + (Vector(p) - HC) * KF) * S
    A, B, C = HR, HR * 0.97, HR * 1.04

    def surf(u, z, out=0.0):
        k = 1.0 - (u / A) ** 2 - ((z - HC.z) / C) ** 2
        k = max(k, 0.02)
        p = Vector((u, HC.y - B * math.sqrt(k), z))
        n = Vector(((p.x - HC.x) / A ** 2, (p.y - HC.y) / B ** 2, (p.z - HC.z) / C ** 2)).normalized()
        return p + n * out, n

    FEAT = _mat(name + '_feat', sp.get('features', '#1d1a1a'), 0.35)
    BROW = _mat(name + '_brow', sp.get('brow_color', '#3b3734'), 0.6)
    MOUTH = _mat(name + '_mouth', sp.get('mouth_color', '#2a1514'), 0.5)
    V, F, MI = [], [], []
    keys = {}

    def add(verts, faces, mi):
        b = len(V)
        V.extend(verts)
        F.extend(tuple(b + i for i in f) for f in faces)
        MI.extend([mi] * len(faces))
        return b

    EK = sp.get('eye_k', 1.0)
    EX, EZ, EW, EH = 0.058, 1.575, 0.0142 * EK, 0.0215 * EK       # eye centre (x, z) and half width / height

    def eye(sg, sx=1.0, sz=1.0, dx=0.0, dz=0.0, arc=0.0):
        """Flattened dome on the head surface. arc bends it into an upturned crescent (happy)."""
        cu, cz = sg * EX + dx, EZ + dz
        pts = []
        n_r, n_a = 6, 24
        verts = []
        for i in range(n_r + 1):
            r = i / n_r
            for j in range(n_a):
                a = 2 * math.pi * j / n_a
                x, y = math.cos(a) * r, math.sin(a) * r
                u = cu + x * EW * sx
                z = cz + y * EH * sz + arc * EH * (x * x) * 0.9
                h = 0.0045 * math.sqrt(max(0.0, 1 - r * r)) + 0.0006
                p, _ = surf(u, z, h)
                verts.append(p)
        faces = []
        for i in range(n_r):
            for j in range(n_a):
                a0, a1 = i * n_a + j, i * n_a + (j + 1) % n_a
                faces.append((a0, (i + 1) * n_a + j, (i + 1) * n_a + (j + 1) % n_a, a1))
        return verts, faces

    for s in 'LR':
        sg = side_sign(s)
        v, f = eye(sg)
        b = add(v, f, 0)
        for kn, kw in (('blink', dict(sx=1.25, sz=0.1)), ('happy', dict(sx=1.15, sz=0.32, dz=0.004, arc=-1.3)),
                       ('wide', dict(sx=1.3, sz=1.3)), ('squint', dict(sx=1.08, sz=0.5))):
            keys.setdefault('eye_%s:%s' % (s, kn), {}).update({b + i: p for i, p in enumerate(eye(sg, **kw)[0])})
        for kn, d in (('look_l', dict(dx=0.012)), ('look_r', dict(dx=-0.012)), ('look_u', dict(dz=0.009)), ('look_d', dict(dz=-0.008))):
            keys.setdefault('look:' + kn, {}).update({b + i: p for i, p in enumerate(eye(sg, **d)[0])})

        def brow(lift, inner, outer):
            n, m = 12, 10
            verts = []
            for i in range(n + 1):
                x = i / n                                   # 0 inner .. 1 outer
                u = sg * (0.03 + 0.05 * x)
                z = EZ + 0.047 + lift + inner * (1 - x) + outer * x + 0.006 * math.sin(math.pi * x)
                c, nrm = surf(u, z, 0.0055)
                tang = (surf(sg * (0.03 + 0.05 * min(1, x + 0.01)), z)[0] - surf(sg * (0.03 + 0.05 * max(0, x - 0.01)), z)[0]).normalized()
                side = nrm.cross(tang).normalized()
                taper = math.sin(math.pi * (0.08 + 0.84 * x)) ** 0.35
                rw, rh = 0.0092 * taper * sp.get('brow_k', 1.0), 0.0064 * taper * sp.get('brow_k', 1.0)
                for j in range(m):
                    a = 2 * math.pi * j / m
                    verts.append(c + side * (math.cos(a) * rw) + nrm * (math.sin(a) * rh))
            faces = [(i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j) for i in range(n) for j in range(m)]
            faces.append(tuple(range(m)))
            faces.append(tuple(n * m + j for j in reversed(range(m))))
            return verts, faces
        v, f = brow(0, 0, 0)
        b = add(v, f, 1)
        for kn, (l, i_, o) in (('brow_up', (0.012, 0.003, 0.0)), ('brow_down', (-0.006, -0.008, 0.004)),
                               ('brow_worried', (0.004, 0.012, -0.006))):
            keys.setdefault('brow_%s:%s' % (s, kn), {}).update({b + i: p for i, p in enumerate(brow(l, i_, o)[0])})

    N = 15
    xs = [-1 + 2 * i / (N - 1) for i in range(N)]
    shapes = {
        'Basis': [(x * 0.8, 0.006 * x * x + 0.0016, 0.006 * x * x - 0.0016) for x in xs],
        'smile': [(x * 1.15, -0.004 + 0.016 * x * x + 0.002, -0.004 + 0.016 * x * x - 0.0045 * (1 - x * x) - 0.002) for x in xs],
        'open': [(x * 0.9, 0.004 + 0.005 * x * x, 0.004 + 0.005 * x * x - 0.03 * (1 - x * x) ** 0.8 - 0.003) for x in xs],
        'o_shape': [(x * 0.42, 0.011 * math.sqrt(max(0, 1 - x * x)) + 0.0015, -0.014 * math.sqrt(max(0, 1 - x * x)) - 0.0015) for x in xs],
        'frown': [(x * 0.9, 0.005 - 0.012 * x * x + 0.0018, 0.005 - 0.012 * x * x - 0.0018) for x in xs],
    }
    mz, hw = 1.522, 0.02 * sp.get('mouth_k', 1.0)

    def mouth(pts):
        up = [surf(x * hw, mz + a, 0.0012)[0] for x, a, _ in pts]
        lo = [surf(x * hw, mz + b, 0.0012)[0] for x, _, b in pts]
        return up + lo
    b = add(mouth(shapes['Basis']), [(i, i + 1, N + i + 1, N + i) for i in range(N - 1)], 2)
    for kn in ('smile', 'open', 'o_shape', 'frown'):
        keys['mouth:' + kn] = {b + i: p for i, p in enumerate(mouth(shapes[kn]))}

    me = bpy.data.meshes.new(name + '_face')
    me.from_pydata([tuple(fmap(p)) for p in V], [], F)
    me.update()
    for m in (FEAT, BROW, MOUTH):
        me.materials.append(m)
    me.polygons.foreach_set('material_index', MI)
    me.polygons.foreach_set('use_smooth', [True] * len(F))
    ob = bpy.data.objects.new(name + '_face', me)
    col.objects.link(ob)
    ob.shape_key_add(name='Basis')
    for kn, d in keys.items():
        sk = ob.shape_key_add(name=kn, from_mix=False)
        for i, p in d.items():
            sk.data[i].co = fmap(p)
        sk.slider_min, sk.slider_max = 0.0, 1.0

    def drive(kb_name, expr, props):
        kb = ob.data.shape_keys.key_blocks.get(kb_name)
        if not kb:
            return
        d = kb.driver_add('value').driver
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
