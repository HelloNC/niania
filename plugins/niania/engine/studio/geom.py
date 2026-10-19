"""Procedural mesh building: lathes, capsules, boxes, extrusions, with rigid vertex groups."""
import math
import bpy
from mathutils import Vector, Matrix


class MeshBuilder:
    """Accumulates verts / faces / material slots / vertex-group weights, then builds one object."""

    def __init__(self, name):
        self.name = name
        self.v, self.f, self.mi, self.w, self.sharp = [], [], [], [], []

    def add(self, verts, faces, mat=0, group=None, weights=None, smooth=True):
        base = len(self.v)
        self.v.extend([tuple(map(float, p)) for p in verts])
        for i in range(len(verts)):
            if weights is not None:
                self.w.append(dict(weights[i]))
            else:
                self.w.append({group: 1.0} if group else {})
        for f in faces:
            self.f.append(tuple(base + i for i in f))
            self.mi.append(mat)
            self.sharp.append(not smooth)
        return base

    def add_part(self, part, mat=0, group=None, matrix=None, smooth=True):
        verts, faces = part
        if matrix is not None:
            verts = [tuple(matrix @ Vector(p)) for p in verts]
        return self.add(verts, faces, mat, group, smooth=smooth)

    def build(self, mats, collection=None):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.v, [], self.f)
        me.update(calc_edges=True)
        for m in mats:
            me.materials.append(m)
        if self.f:
            me.polygons.foreach_set('material_index', self.mi)
            me.polygons.foreach_set('use_smooth', [not s for s in self.sharp])
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        groups = {}
        for i, wd in enumerate(self.w):
            for g, val in wd.items():
                if val > 1e-4:
                    groups.setdefault(g, {}).setdefault(round(val, 4), []).append(i)
        for g, byw in groups.items():
            vg = ob.vertex_groups.get(g) or ob.vertex_groups.new(name=g)
            for val, idx in byw.items():
                vg.add(idx, val, 'REPLACE')
        return ob


# ---------------------------------------------------------------- primitives (return (verts, faces))
def lathe(profile, segs=24, close_bottom=True, close_top=True, phase=0.0, sx=1.0, sy=1.0):
    """Revolve [(r, z), ...] around Z. Rings with r=0 are poles."""
    verts, faces, rings = [], [], []
    for r, z in profile:
        if r <= 1e-6:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for i in range(segs):
                a = phase + 2 * math.pi * i / segs
                ring.append(len(verts))
                verts.append((r * math.cos(a) * sx, r * math.sin(a) * sy, z))
            rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(segs):
                faces.append((a[0], b[(i + 1) % segs], b[i]))
        elif len(b) == 1:
            for i in range(segs):
                faces.append((a[i], a[(i + 1) % segs], b[0]))
        else:
            for i in range(segs):
                j = (i + 1) % segs
                faces.append((a[i], a[j], b[j], b[i]))
    if close_bottom and len(rings[0]) > 1:
        faces.append(tuple(reversed(rings[0])))
    if close_top and len(rings[-1]) > 1:
        faces.append(tuple(rings[-1]))
    return verts, faces


def sphere_profile(r, z0=0.0, rings=10, sz=1.0):
    return [(r * math.sin(math.pi * i / rings), z0 - r * sz * math.cos(math.pi * i / rings)) for i in range(rings + 1)]


def ellipsoid(rx, ry, rz, center=(0, 0, 0), segs=20, rings=12):
    v, f = lathe(sphere_profile(1.0, 0.0, rings), segs)
    c = Vector(center)
    return [(p[0] * rx + c.x, p[1] * ry + c.y, p[2] * rz + c.z) for p in v], f


def capsule(p0, p1, r0, r1=None, segs=16, rings=6):
    """Rounded tube from p0 to p1 with end radii r0, r1 (hemispherical caps)."""
    r1 = r0 if r1 is None else r1
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    prof = []
    for i in range(rings + 1):                 # bottom cap
        a = -math.pi / 2 + (math.pi / 2) * i / rings
        prof.append((r0 * math.cos(a), r0 * math.sin(a)))
    for i in range(rings + 1):                 # top cap
        a = (math.pi / 2) * i / rings
        prof.append((r1 * math.cos(a), L + r1 * math.sin(a)))
    v, f = lathe(prof, segs)
    m = align_z(d) ; m.translation = p0
    return [tuple(m @ Vector(p)) for p in v], f


def align_z(direction):
    """Rotation matrix (4x4) taking +Z to `direction`."""
    d = Vector(direction).normalized()
    q = Vector((0, 0, 1)).rotation_difference(d)
    return q.to_matrix().to_4x4()


def box(sx, sy, sz, center=(0, 0, 0), bevel=0.0):
    cx, cy, cz = center
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    if bevel <= 0:
        v = [(cx + x * hx, cy + y * hy, cz + z * hz) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
        f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        return v, f
    # rounded box: superellipsoid-ish via a squashed sphere grid
    v, f = [], []
    nu, nv = 16, 8
    for j in range(nv + 1):
        th = -math.pi / 2 + math.pi * j / nv
        for i in range(nu):
            ph = 2 * math.pi * i / nu
            ex = 0.25
            c, s = math.cos(th), math.sin(th)
            x = math.copysign(abs(c) ** ex, c) * math.copysign(abs(math.cos(ph)) ** ex, math.cos(ph))
            y = math.copysign(abs(c) ** ex, c) * math.copysign(abs(math.sin(ph)) ** ex, math.sin(ph))
            z = math.copysign(abs(s) ** ex, s)
            v.append((cx + x * hx, cy + y * hy, cz + z * hz))
    for j in range(nv):
        for i in range(nu):
            a, b = j * nu + i, j * nu + (i + 1) % nu
            f.append((a, b, b + nu, a + nu))
    return v, f


def extrude_polygon(pts2d, z0, z1):
    """Prism from a 2D polygon (CCW) between heights z0 and z1."""
    n = len(pts2d)
    v = [(x, y, z0) for x, y in pts2d] + [(x, y, z1) for x, y in pts2d]
    f = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return v, f


def plane(sx, sy, center=(0, 0, 0), normal='Z'):
    cx, cy, cz = center
    hx, hy = sx / 2, sy / 2
    if normal == 'Z':
        v = [(cx - hx, cy - hy, cz), (cx + hx, cy - hy, cz), (cx + hx, cy + hy, cz), (cx - hx, cy + hy, cz)]
    elif normal == 'Y':     # vertical plane facing -Y (towards a camera looking +Y)
        v = [(cx - hx, cy, cz - hy), (cx + hx, cy, cz - hy), (cx + hx, cy, cz + hy), (cx - hx, cy, cz + hy)]
    else:                   # 'X': vertical plane facing +X
        v = [(cx, cy - hx, cz - hy), (cx, cy + hx, cz - hy), (cx, cy + hx, cz + hy), (cx, cy - hx, cz + hy)]
    return v, [(0, 1, 2, 3)]


def torus_arc(R, r, a0, a1, segs=16, rsegs=8, center=(0, 0, 0), plane_axes='XZ'):
    """Partial torus (e.g. a mug handle) in the given plane."""
    v, f = [], []
    cx, cy, cz = center
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        for j in range(rsegs):
            b = 2 * math.pi * j / rsegs
            rr = R + r * math.cos(b)
            p, q, w = rr * math.cos(a), rr * math.sin(a), r * math.sin(b)
            if plane_axes == 'XZ':
                v.append((cx + p, cy + w, cz + q))
            else:
                v.append((cx + p, cy + q, cz + w))
    for i in range(segs):
        for j in range(rsegs):
            a, b = i * rsegs + j, i * rsegs + (j + 1) % rsegs
            f.append((a, b, b + rsegs, a + rsegs))
    return v, f


def transform(part, m):
    v, f = part
    return [tuple(m @ Vector(p)) for p in v], f


def merge(*parts):
    V, F = [], []
    for v, f in parts:
        b = len(V)
        V.extend(v)
        F.extend(tuple(b + i for i in face) for face in f)
    return V, F


def make_object(name, part, mat, collection=None, smooth=True, location=None):
    mb = MeshBuilder(name)
    mb.add(*part, mat=0, smooth=smooth)
    ob = mb.build([mat] if not isinstance(mat, (list, tuple)) else list(mat), collection)
    if location is not None:
        ob.location = location
    return ob


def add_quad_uv(ob):
    """UVs for a single-quad plane made by plane(): corners map to (0,0) (1,0) (1,1) (0,1)."""
    me = ob.data
    ul = me.uv_layers.new(name='UVMap')
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for poly in me.polygons:
        for k, li in enumerate(poly.loop_indices):
            ul.data[li].uv = corners[k % 4]
    return ob
