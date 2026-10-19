"""Sculpted clay figure: an organic, anatomical body (skull, brow, nose, ears, jaw, chest, shoulder and
limb muscles) built from metaball 'clay' and skinned to the standard rig, so every performance verb
works unchanged. Reconstruction / explainer look (reference: saturated red/blue news figures).

spec: {"body": "sculpt", "material": "subject"|"clay"|"ghost", "color": "#e8382f",
       "hair": "ponytail"|"short"|"bun"|None, "build": 1.0 (shoulder/muscle width), "scale": 1.0}

Rest pose faces -Y, character-left is +X (same frame as character.SK).
Metaball families are kept separate per region (torso, head, each arm, each leg) so limbs that
rest close to the body do not fuse; the converted meshes are joined into one skinned object.
"""
import math
import bpy
from mathutils import Vector, Quaternion
from . import geom
from .character import SK, FINGERS, FINGER_R, PALM, mirror, side_sign

K = 0.574           # surface radius / element radius for stiffness 2, threshold 0.6 (measured)
EYE_X, EYE_Z, EYE_R = 0.034, 1.544, 0.0142     # eye centres (character frame) and eyeball radius


class Clay:
    """One metaball family."""

    def __init__(self, tag, res):
        self.mb = bpy.data.metaballs.new('sc_' + tag)
        self.mb.resolution = res
        self.mb.render_resolution = res
        self.mb.threshold = 0.6
        self.ob = bpy.data.objects.new('sc_' + tag, self.mb)
        bpy.context.scene.collection.objects.link(self.ob)

    def ball(self, c, R, neg=False, stiff=2.0):
        e = self.mb.elements.new()
        e.type = 'BALL'
        e.co = Vector(c)
        e.radius = R / K
        e.stiffness = stiff
        e.use_negative = neg
        return e

    def ell(self, c, size, rot=None, neg=False):
        """Ellipsoid with surface half-axes `size` (metres)."""
        e = self.mb.elements.new()
        e.type = 'ELLIPSOID'
        e.co = Vector(c)
        m = max(size)
        e.radius = m / K
        e.size_x, e.size_y, e.size_z = size[0] / m, size[1] / m, size[2] / m
        if rot is not None:
            e.rotation = rot
        e.use_negative = neg
        return e

    def chain(self, p0, p1, r0, r1, n=None):
        """Tapered limb: overlapping balls from p0 (radius r0) to p1 (radius r1)."""
        p0, p1 = Vector(p0), Vector(p1)
        L = (p1 - p0).length
        n = n or max(3, int(L / (min(r0, r1) * 0.45)) + 1)
        for i in range(n):
            u = i / (n - 1)
            self.ball(p0.lerp(p1, u), r0 + (r1 - r0) * u)

    def mesh(self):
        dg = bpy.context.evaluated_depsgraph_get()
        me = self.ob.evaluated_get(dg).to_mesh()
        v = [tuple(x.co) for x in me.vertices]
        f = [tuple(p.vertices) for p in me.polygons]
        self.ob.evaluated_get(dg).to_mesh_clear()
        bpy.data.objects.remove(self.ob)
        bpy.data.metaballs.remove(self.mb)
        return v, f


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(1e-9, ab.dot(ab))))
    return (p - (a + ab * t)).length


def _skin(verts, bones, sigma=0.022):
    """Smooth weights from distance to bone segments (nearest bone dominates, neighbours blend)."""
    segs = [(n, Vector(h), Vector(t)) for n, h, t in bones]
    out = []
    for p in verts:
        p = Vector(p)
        d = [(_seg_dist(p, a, b), n) for n, a, b in segs]
        d.sort()
        d0 = d[0][0]
        w = {}
        for di, n in d[:3]:
            x = (di - d0) / sigma
            if x < 2.5:
                w[n] = w.get(n, 0.0) + math.exp(-x * x)
        s = sum(w.values())
        out.append({k: v / s for k, v in w.items()})
    return out


def _bone(name, s=None):
    k = name
    h, t = SK[k]
    if s:
        h, t = mirror(h, s), mirror(t, s)
    return ((name + '.' + s) if s else name, h, t)


def _smooth(v, f, iters=2, fac=0.5):
    """Laplacian smoothing of a converted metaball mesh (removes voxel stepping)."""
    nb = [set() for _ in v]
    for poly in f:
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            nb[a].add(b)
            nb[b].add(a)
    P = [Vector(x) for x in v]
    for _ in range(iters):
        Q = []
        for i, p in enumerate(P):
            if nb[i]:
                c = sum((P[j] for j in nb[i]), Vector()) / len(nb[i])
                Q.append(p.lerp(c, fac))
            else:
                Q.append(p)
        P = Q
    return [tuple(p) for p in P], f


def _shade(hexc, k):
    h = hexc.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % (int(r * k), int(g * k), int(b * k))


def build_sculpt(name, rig, sp, col, material):
    S = sp.get('scale', 1.0)
    bw = sp.get('build', 1.0)
    mb = geom.MeshBuilder(name + '_body')

    extra = 1 if sp.get('material') == 'smooth' else 0      # extra relaxation for the polished look

    def add(part, bones, sigma=0.022, smooth=2, mat=0):
        v, f = _smooth(*part, iters=smooth + extra) if (smooth + extra) else part
        w = _skin(v, bones, sigma)
        mb.add([tuple(Vector(p) * S) for p in v], f, mat, weights=w)

    # ---------------------------------------------------------------- torso + neck
    T = Clay(name + '_torso', 0.0075)
    T.ell((0, 0.008, 0.915), (0.152 * bw, 0.1, 0.095))                  # pelvis
    for s in (-1, 1):
        T.ball((s * 0.064, 0.036, 0.885), 0.074)                        # glutes
    T.ell((0, -0.004, 1.03), (0.128 * bw, 0.088, 0.10))                 # abdomen
    T.ell((0, -0.03, 1.02), (0.085, 0.05, 0.085))                       # belly front
    T.ell((0, 0.004, 1.165), (0.162 * bw, 0.108, 0.14))                 # ribcage
    T.ell((0, 0.035, 1.17), (0.158 * bw, 0.072, 0.125))                # lats / upper back
    for s in (-1, 1):
        T.ell((s * 0.068 * bw, -0.058, 1.19), (0.07, 0.036, 0.055))     # pecs
        T.chain((s * 0.03, 0.018, 1.315), (s * 0.13 * bw, 0.01, 1.272), 0.042, 0.04)   # trapezius
        T.ball((s * 0.155 * bw, 0.0, 1.245), 0.05)                      # shoulder cap (arm deltoid overlaps)
    T.chain((0, 0.008, 1.27), (0, 0.004, 1.43), 0.052, 0.046)           # neck
    T.ball((0, -0.03, 1.3), 0.035)                                      # throat
    nf0 = len(mb.f)
    add(T.mesh(), [_bone('hips'), _bone('spine'), _bone('chest'), _bone('neck'), _bone('head'),
                   _bone('shoulder', 'L'), _bone('shoulder', 'R')], sigma=0.03)
    for i in range(nf0, len(mb.f)):          # below the waistband = trousers
        if sum(mb.v[k][2] for k in mb.f[i]) / len(mb.f[i]) < 0.955 * S:
            mb.mi[i] = 2

    # ---------------------------------------------------------------- head (finer clay)
    H = Clay(name + '_head', 0.0042)
    H.ell((0, 0.012, 1.565), (0.093, 0.106, 0.112))                     # cranium
    H.ell((0, -0.04, 1.5), (0.069, 0.07, 0.072))                        # face / jaw mass
    H.ell((0, -0.02, 1.468), (0.06, 0.06, 0.035))                       # jaw line
    H.ball((0, -0.083, 1.448), 0.026)                                   # chin
    H.ell((0, -0.088, 1.568), (0.05, 0.016, 0.012))                     # brow ridge
    H.chain((0, -0.097, 1.556), (0, -0.112, 1.516), 0.011, 0.015)       # nose bridge -> tip
    H.ell((0, -0.106, 1.512), (0.02, 0.012, 0.01))                      # nostrils
    if not sp.get('face', True):
        H.ell((0, -0.096, 1.478), (0.026, 0.01, 0.01))                  # lips (faceless only)
    for s in (-1, 1):
        H.ell((s * 0.088, 0.006, 1.528), (0.014, 0.027, 0.034))         # ears
        H.ball((s * 0.046, -0.078, 1.518), 0.016)                       # cheekbones
        if sp.get('face', True):
            H.ball((s * EYE_X, -0.096, EYE_Z), 0.0165, neg=True)       # eye sockets for the eyeballs
        else:
            H.ell((s * 0.034, -0.086, 1.546), (0.02, 0.006, 0.01))      # faceless: smooth closed lids
    H.chain((0, 0.008, 1.40), (0, 0.004, 1.47), 0.045, 0.048)          # neck top (blends into the skull)
    head_vf = _smooth(*H.mesh(), iters=1)
    add(head_vf, [_bone('neck'), _bone('head')], sigma=0.02, smooth=0)
    hair = sp.get('hair')
    HR = Clay(name + '_hair', 0.0042) if hair else None
    if hair in ('short', 'ponytail', 'bun', 'curly'):
        HR.ell((0, 0.024, 1.6), (0.099, 0.11, 0.092))                    # hair cap
        HR.ell((0, -0.05, 1.64), (0.078, 0.04, 0.035))                   # fringe volume
        HR.ell((0, 0.06, 1.55), (0.092, 0.07, 0.07))                     # back of hair
        for s in (-1, 1):
            HR.ell((s * 0.082, -0.018, 1.585), (0.022, 0.04, 0.04))      # sideburn volume
    if hair == 'curly':
        import random
        rnd = random.Random(7)
        for _ in range(26):
            a, b = rnd.uniform(-2.6, 2.6), rnd.uniform(0.15, 1.35)
            HR.ball((0.1 * math.sin(a) * math.sin(b), 0.025 + 0.11 * math.cos(a) * math.sin(b) * 0.9, 1.59 + 0.095 * math.cos(b)), 0.03)
    if hair == 'ponytail':
        HR.ball((0, 0.112, 1.56), 0.032)
        HR.chain((0, 0.12, 1.545), (0, 0.13, 1.42), 0.028, 0.016)
    elif hair == 'bun':
        HR.ball((0, 0.112, 1.6), 0.046)
    if HR is not None:
        add(HR.mesh(), [_bone('head')], sigma=0.02, smooth=1, mat=1)

    # ---------------------------------------------------------------- legs
    for s in 'LR':
        sg = side_sign(s)
        hip, knee = Vector(mirror(SK['thigh'][0], s)), Vector(mirror(SK['thigh'][1], s))
        ank = Vector(mirror(SK['shin'][1], s))
        Lg = Clay(name + '_leg' + s, 0.0065)
        Lg.ball(hip + Vector((sg * 0.012, 0.0, 0.0)), 0.082)
        Lg.chain(hip + Vector((0, 0, -0.03)), knee, 0.082, 0.056)
        Lg.ell(hip.lerp(knee, 0.45) + Vector((sg * 0.012, -0.024, 0)), (0.056, 0.05, 0.12))    # quads
        Lg.ell(hip.lerp(knee, 0.4) + Vector((0, 0.03, 0)), (0.05, 0.045, 0.11))               # hamstrings
        Lg.ball(knee + Vector((0, -0.012, 0)), 0.054)
        Lg.chain(knee, ank, 0.054, 0.04)
        Lg.ell(knee.lerp(ank, 0.3) + Vector((0, 0.022, 0)), (0.044, 0.044, 0.085))             # calf
        Lg.ball(ank, 0.03)
        Lg.ball(ank + Vector((0, 0.02, -0.04)), 0.034)                                         # heel
        Lg.ell(ank + Vector((0, -0.065, -0.045)), (0.042, 0.08, 0.03))                         # foot
        Lg.ball(ank + Vector((0, -0.125, -0.052)), 0.026)                                      # toes
        v, f = _smooth(*Lg.mesh())
        v = [(x, y, max(z, 0.0)) for x, y, z in v]                                             # flat sole
        add((v, f), [_bone('hips'), _bone('thigh', s), _bone('shin', s), _bone('foot', s)], smooth=0, mat=2)

    # ---------------------------------------------------------------- arms + palm
    for s in 'LR':
        sg = side_sign(s)
        sh, el = Vector(mirror(SK['upper_arm'][0], s)), Vector(mirror(SK['upper_arm'][1], s))
        wr = Vector(mirror(SK['forearm'][1], s))
        A = Clay(name + '_arm' + s, 0.0055)
        A.ball(sh + Vector((sg * 0.012, 0, -0.012)), 0.062 * bw)                     # deltoid
        A.chain(sh + Vector((0, 0, -0.03)), el, 0.052, 0.04)
        A.ell(sh.lerp(el, 0.5) + Vector((0, -0.016, 0)), (0.036, 0.034, 0.075))      # biceps
        A.ball(el, 0.035)
        A.chain(el, wr, 0.042, 0.027)
        A.ell(el.lerp(wr, 0.25) + Vector((sg * 0.006, 0, 0)), (0.04, 0.038, 0.07))  # forearm muscle
        A.ball(wr, 0.024)
        c = wr + Vector((0, 0, -PALM[2] / 2))
        A.ell(c, (PALM[1] / 2 + 0.003, PALM[0] / 2 + 0.004, PALM[2] / 2 + 0.006))    # palm
        A.ell(wr + Vector((-sg * 0.008, -0.022, -0.03)), (0.014, 0.018, 0.024))       # thumb mound
        add(A.mesh(), [_bone('shoulder', s), _bone('upper_arm', s), _bone('forearm', s), (('hand.' + s), wr, wr + Vector((0, 0, -0.075)))],
            sigma=0.02)
        # fingers: smooth tapered capsules on their own bones (exact radius for the grip solver)
        for fn, (off, segs) in FINGERS.items():
            p = wr + Vector((0, off, -PALM[2] + 0.004))
            for i, L in enumerate(segs):
                q = p + Vector((0, 0, -L))
                r0 = FINGER_R * (1.0 if i == 0 else 0.9)
                r1 = FINGER_R * (0.92 if i == 0 else 0.78)
                v, f = geom.capsule(p, q, r0, r1, 14, 4)
                mb.add([tuple(Vector(x) * S) for x in v], f, 0, 'f_%s.%02d.%s' % (fn, i + 1, s))
                p = q
        t0 = wr + Vector((-sg * 0.012, -0.03, -0.022))
        t1 = t0 + Vector((-sg * 0.01, -0.022, -0.022))
        t2 = t1 + Vector((-sg * 0.006, -0.012, -0.02))
        for a, b, ra, rb, g in ((t0, t1, 0.0115, 0.0102, 'thumb.01.'), (t1, t2, 0.0098, 0.0082, 'thumb.02.')):
            v, f = geom.capsule(a, b, ra, rb, 14, 4)
            mb.add([tuple(Vector(x) * S) for x in v], f, 0, g + s)

    # ---------------------------------------------------------------- clothing hems (sculpted cues)
    if sp.get('clothes', True):
        def ring(c, axis, R, r, group_w, sx=1.0, sy=1.0, segs=36, mat=0):
            c, axis = Vector(c), Vector(axis).normalized()
            q = Vector((0, 0, 1)).rotation_difference(axis)
            v, f = [], []
            for i in range(segs):
                a = 2 * math.pi * i / segs
                for j in range(8):
                    b = 2 * math.pi * j / 8
                    p = Vector(((R + r * math.cos(b)) * math.cos(a) * sx, (R + r * math.cos(b)) * math.sin(a) * sy, r * math.sin(b)))
                    v.append(tuple((c + q @ p) * S))
            for i in range(segs):
                for j in range(8):
                    a0, a1 = i * 8 + j, ((i + 1) % segs) * 8 + j
                    f.append((a0, a1, ((i + 1) % segs) * 8 + (j + 1) % 8, i * 8 + (j + 1) % 8))
            mb.add(v, f, mat, weights=[group_w] * len(v))
        ring((0, -0.004, 1.30), (0, 0.15, 1), 0.06, 0.009, {'chest': 0.6, 'neck': 0.4}, sx=1.05, sy=0.95)    # collar
        ring((0, 0.004, 0.955), (0, 0, 1), 0.128 * bw, 0.01, {'hips': 1.0}, sx=1.0, sy=0.74, mat=2)              # waistband
        for s in 'LR':
            sh, el = Vector(mirror(SK['upper_arm'][0], s)), Vector(mirror(SK['upper_arm'][1], s))
            ring(sh.lerp(el, 0.62), el - sh, 0.05, 0.008, {'upper_arm.' + s: 1.0})                       # sleeve hem
            knee, ank = Vector(mirror(SK['shin'][0], s)), Vector(mirror(SK['shin'][1], s))
            ring(knee.lerp(ank, 0.86), ank - knee, 0.044, 0.008, {'shin.' + s: 1.0}, mat=2)                     # trouser cuff
    mats = [material, material, material]
    if sp.get('material', 'subject') in ('subject', 'clay', 'smooth'):
        from . import materials as M
        kind = sp.get('material', 'subject')
        base = sp.get('color', {'subject': '#e8382f', 'clay': '#ececec', 'smooth': '#f4f3f0'}[kind])
        mk = {'subject': M.subject, 'clay': M.clay, 'smooth': lambda n, c: M.plastic(n, c, rough=0.3, coat=0.3)}[kind]
        mats[1] = mk(name + '_hairmat', sp.get('hair_color', _shade(base, 0.55)))
        mats[2] = mk(name + '_pantsmat', sp.get('pants_color', _shade(base, 0.62)))
    ob = mb.build(mats, col)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.parent = rig
    mod = ob.modifiers.new('rig', 'ARMATURE')
    mod.object = rig
    if sp.get('material') == 'ghost':
        ob.visible_shadow = False
    face = build_sculpt_face(name, rig, sp, col, head_vf, mats) if sp.get('face', True) and sp.get('material') != 'ghost' else None
    return ob, face


# ====================================================================== sculpted face
def build_sculpt_face(name, rig, sp, col, head_vf, mats):
    """Real eyes (eyeballs + irises that rotate to look), eyelids that blink / squint / widen, moving brows and
    a mouth that smiles / opens / frowns, all rigid on the head bone and driven by the rig's face props
    (same names as the cel face, so `expr`, `blink`, `look` and dialogue lip-sync work unchanged)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Matrix
    from . import materials as M
    S = sp.get('scale', 1.0)
    hv, hf = head_vf
    bvh = BVHTree.FromPolygons([Vector(p) for p in hv], hf)

    def surf(u, z, out=0.0012):
        hit = bvh.ray_cast(Vector((u, -0.4, z)), Vector((0, 1, 0)))
        p = hit[0] if hit[0] is not None else Vector((u, -0.09, z))
        n = hit[1] if hit[1] is not None else Vector((0, -1, 0))
        return p + n.normalized() * out

    white = M.clay(name + '_eyewhite', sp.get('eye_white', '#f4f2ee'), rough=0.25, spec=0.6)
    iris = M.clay(name + '_iris', sp.get('iris', '#24170f'), rough=0.2, spec=0.7)
    mouthm = M.clay(name + '_mouth', sp.get('mouth_color', '#3b0c0a'), rough=0.6)
    skin, hair = mats[0], mats[1]
    mlist = [white, iris, skin, hair, mouthm]
    V, F, MI = [], [], []
    keys = {}            # key name -> {vert index: co}

    def add(verts, faces, mi):
        b = len(V)
        V.extend(verts)
        F.extend(tuple(b + i for i in f) for f in faces)
        MI.extend([mi] * len(faces))
        return b

    def sph(c, r, th0, th1, ps0, ps1, n=14, m=18):
        """Spherical patch around centre c. th = elevation from straight ahead (-Y) towards +Z, ps = azimuth to +X."""
        pts = []
        for i in range(n + 1):
            th = th0 + (th1 - th0) * i / n
            for j in range(m + 1):
                ps = ps0 + (ps1 - ps0) * j / m
                d = Vector((math.sin(ps) * math.cos(th), -math.cos(ps) * math.cos(th), math.sin(th)))
                pts.append(c + d * r)
        faces = [(i * (m + 1) + j, i * (m + 1) + j + 1, (i + 1) * (m + 1) + j + 1, (i + 1) * (m + 1) + j)
                 for i in range(n) for j in range(m)]
        return pts, faces
    rad = math.radians
    for s in 'LR':
        sg = side_sign(s)
        front = surf(sg * EYE_X, EYE_Z, 0.0)
        c = Vector((sg * EYE_X, front.y + EYE_R - 0.0075, EYE_Z))        # eyeball pokes ~7.5 mm out of the socket
        v, f = sph(c, EYE_R, rad(-90), rad(90), rad(-100), rad(100), 22, 26)
        add(v, f, 0)
        # iris cap + look keys (rotate about the eyeball centre)
        v, f = sph(c, EYE_R + 0.0003, rad(-28), rad(28), rad(-28), rad(28), 12, 12)
        b = add(v, f, 1)
        for kn, q in (('look_l', Quaternion((0, 0, 1), rad(24))), ('look_r', Quaternion((0, 0, 1), rad(-24))),
                      ('look_u', Quaternion((1, 0, 0), rad(-18))), ('look_d', Quaternion((1, 0, 0), rad(18)))):
            keys.setdefault('look:' + kn, {}).update({b + i: c + q @ (p - c) for i, p in enumerate(v)})
        # lids: spherical shells slightly larger than the eye; keys move the lid edge
        R = EYE_R + 0.0016
        def upper(edge):
            return sph(c, R, rad(edge), rad(100), rad(-95), rad(95), 8, 20)
        def lower(edge):
            return sph(c, R, rad(-100), rad(edge), rad(-95), rad(95), 6, 20)
        v, f = upper(52)
        b = add(v, f, 2)
        for kn, e in (('blink', -52), ('wide', 70), ('happy', 18), ('squint', 16)):
            keys.setdefault('eye_%s:%s' % (s, kn), {}).update({b + i: p for i, p in enumerate(upper(e)[0])})
        v, f = lower(-60)
        b2 = add(v, f, 2)
        for kn, e in (('blink', -40), ('wide', -68), ('happy', -10), ('squint', -22)):
            keys.setdefault('eye_%s:%s' % (s, kn), {}).update({b2 + i: p for i, p in enumerate(lower(e)[0])})
        # brow: a hair-coloured tapered ridge following the brow surface
        def brow(lift, inner, outer):
            pts = []
            n = 10
            for i in range(n + 1):
                x = i / n                                   # 0 inner .. 1 outer
                u = sg * (0.014 + 0.036 * x)
                z = EYE_Z + 0.02 + lift + inner * (1 - x) + outer * x + 0.004 * math.sin(math.pi * x)
                p = surf(u, z, 0.0016)
                th = 0.0032 * (1.15 - 0.5 * x)
                pts += [p + Vector((0, 0, th)), p - Vector((0, 0, th))]
            faces = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(n)]
            return pts, faces
        v, f = brow(0, 0, 0)
        b = add(v, f, 3)
        for kn, (l, i_, o) in (('brow_up', (0.007, 0.002, 0.0)), ('brow_down', (-0.004, -0.005, 0.002)),
                               ('brow_worried', (0.002, 0.007, -0.003))):
            keys.setdefault('brow_%s:%s' % (s, kn), {}).update({b + i: p for i, p in enumerate(brow(l, i_, o)[0])})
    # mouth: dark opening on the face surface (curves as in the cel face, scaled to this head)
    N = 15
    xs = [-1 + 2 * i / (N - 1) for i in range(N)]
    sc = 0.62
    shapes = {
        'Basis': [(x * 0.8, -0.003 + 0.008 * x * x + 0.0026, -0.003 + 0.008 * x * x - 0.0026) for x in xs],
        'smile': [(x * 1.2, -0.01 + 0.02 * x * x + 0.003, -0.01 + 0.02 * x * x - 0.004 * (1 - x * x) - 0.003) for x in xs],
        'open': [(x * 0.95, 0.004 + 0.006 * x * x, 0.004 + 0.006 * x * x - 0.034 * (1 - x * x) ** 0.8 - 0.004) for x in xs],
        'o_shape': [(x * 0.45, 0.012 * math.sqrt(max(0, 1 - x * x)) + 0.002, -0.016 * math.sqrt(max(0, 1 - x * x)) - 0.002) for x in xs],
        'frown': [(x * 0.95, 0.006 - 0.014 * x * x + 0.0028, 0.006 - 0.014 * x * x - 0.0028) for x in xs],
    }
    mz, hw = 1.479, 0.032 * sc

    def mouth(pts):
        up = [surf(x * hw, mz + a * sc, 0.0009) for x, a, _ in pts]
        lo = [surf(x * hw, mz + b * sc, 0.0009) for x, _, b in pts]
        return up + lo
    mv = mouth(shapes['Basis'])
    b = add(mv, [(i, i + 1, N + i + 1, N + i) for i in range(N - 1)], 4)
    for kn in ('smile', 'open', 'o_shape', 'frown'):
        keys['mouth:' + kn] = {b + i: p for i, p in enumerate(mouth(shapes[kn]))}

    me = bpy.data.meshes.new(name + '_face')
    me.from_pydata([tuple(Vector(p) * S) for p in V], [], F)
    me.update()
    for m in mlist:
        me.materials.append(m)
    me.polygons.foreach_set('material_index', MI)
    me.polygons.foreach_set('use_smooth', [True] * len(F))
    ob = bpy.data.objects.new(name + '_face', me)
    col.objects.link(ob)
    ob.shape_key_add(name='Basis')
    for kn, d in keys.items():
        sk = ob.shape_key_add(name=kn, from_mix=False)
        for i, p in d.items():
            sk.data[i].co = Vector(p) * S
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
