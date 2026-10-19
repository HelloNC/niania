"""Secondary effects computed after the main pass: liquid droplets, splats.

fx events (timeline "fx" list):
  {"t": 3.3, "do": "spill", "from": "cup", "count": 6, "dur": 0.5, "speed": 0.5, "seed": 2}
        droplets leave the object's mouth carrying its velocity (story-time physics)
  {"t": 9.6, "do": "fling", "from": "cup", "dur": 0.32, "to": {"char": "mia", "face": [u, v]}}
        one droplet flies on a ballistic arc and sticks to the target (face coords on the head)
"""
import math
from mathutils import Vector, Matrix, Quaternion
from .util import rng, clamp
from .character import HEAD_C, HEAD_R, SK

G = 9.81


def mouth_point(o, M):
    r, h = (o.ob.get('mouth') or (o.radius, o.height))
    return M @ Vector((0, 0, h))


def obj_velocity(world, o, f):
    a = o.mats.get(f - 1, o.mats.get(f))
    b = o.mats.get(f)
    dtau = world.clock((f - 1) / world.fps) - world.clock((f - 2) / world.fps)
    return (b.translation - a.translation) / max(dtau, 1e-5)


def face_point(perf, uv, f):
    """World point + normal on the head surface at face coords (u: +char-left, v: up)."""
    u, v = uv
    S = perf.S
    R = HEAD_R + 0.003
    y = -math.sqrt(max(1e-6, R * R - u * u - v * v))
    p_rest = Vector((u, HEAD_C.y + y, HEAD_C.z + v)) * S
    n_rest = (p_rest - HEAD_C * S).normalized()
    W = perf.world[f]
    Mh = W['head'] @ perf.rest['head'].inverted()
    return Mh @ p_rest, (Mh.to_3x3() @ n_rest).normalized(), Mh, p_rest, n_rest


def simulate(world, events, nframes):
    """Returns list of particles: dict(name, kind, frames: {f: (Matrix, visible)})"""
    fps = world.fps
    parts = []
    for ei, ev in enumerate(events):
        o = world.objs[ev['from']]
        r = rng(ev.get('seed', ei + 1))
        if ev['do'] == 'spill':
            n = ev.get('count', 5)
            for k in range(n):
                ts = ev['t'] + ev.get('dur', 0.4) * k / max(1, n - 1)
                fs = int(round(ts * fps)) + 1
                M = o.mats[fs]
                p0 = mouth_point(o, M) + (M.to_3x3() @ Vector((r.uniform(-1, 1), r.uniform(-1, 1), 0)) * o.radius * 0.5)
                v0 = obj_velocity(world, o, fs) + Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(0, 1))) * ev.get('speed', 0.4)
                parts.append(_ballistic(world, 'drop%d_%d' % (ei, k), fs, p0, v0, nframes, r.uniform(0.6, 1.1)))
        elif ev['do'] == 'fling':
            fs = int(round(ev['t'] * fps)) + 1
            fe = int(round((ev['t'] + ev['dur']) * fps)) + 1
            M = o.mats[fs]
            p0 = mouth_point(o, M)
            tgt = ev['to']
            perf = world.perfs[tgt['char']]
            p1, n1, Mh, prest, nrest = face_point(perf, tgt['face'], fe)
            T = world.clock((fe - 1) / fps) - world.clock((fs - 1) / fps)
            v0 = (p1 - p0 - 0.5 * Vector((0, 0, -G)) * T * T) / T
            tau0 = world.clock((fs - 1) / fps)
            fr = {}
            for f in range(1, nframes + 1):
                if f < fs:
                    fr[f] = (Matrix.Translation(p0), 0.0)
                elif f <= fe:
                    tau = world.clock((f - 1) / fps) - tau0
                    p = p0 + v0 * tau + 0.5 * Vector((0, 0, -G)) * tau * tau
                    v = v0 + Vector((0, 0, -G)) * tau
                    fr[f] = (_stretch(p, v), 1.0 if f < fe else 0.0)
                else:
                    fr[f] = (Matrix.Translation(p1), 0.0)
            parts.append({'name': 'fling%d' % ei, 'kind': 'drop', 'frames': fr, 'size': 1.2})
            # the splat that stays on the face
            sp = {}
            local = Matrix.Translation(prest) @ Vector((0, 0, 1)).rotation_difference(nrest).to_matrix().to_4x4()
            for f in range(1, nframes + 1):
                W = perf.world[f]
                Mh = W['head'] @ perf.rest['head'].inverted()
                grow = clamp((f - fe + 1) / 2.0)
                sp[f] = (Mh @ local, grow)
            parts.append({'name': 'splat_face%d' % ei, 'kind': 'splat', 'frames': sp, 'size': 0.45})
    return parts


def _stretch(p, v):
    sp = v.length
    q = Vector((0, 0, 1)).rotation_difference(v.normalized()) if sp > 1e-4 else Quaternion()
    return Matrix.LocRotScale(p, q, Vector((1, 1, 1 + min(2.5, sp * 0.35))))


def _ballistic(world, name, fs, p0, v0, nframes, size):
    fps = world.fps
    tau0 = world.clock((fs - 1) / fps)
    fr = {}
    hit = None
    for f in range(1, nframes + 1):
        if f < fs:
            fr[f] = (Matrix.Translation(p0), 0.0)
            continue
        tau = world.clock((f - 1) / fps) - tau0
        p = p0 + v0 * tau + 0.5 * Vector((0, 0, -G)) * tau * tau
        if hit is None and p.z <= 0.002:
            # time of impact
            a, b, c = -0.5 * G, v0.z, p0.z
            disc = b * b - 4 * a * c
            ti = (-b - math.sqrt(max(0, disc))) / (2 * a)
            hit = (p0 + v0 * ti + 0.5 * Vector((0, 0, -G)) * ti * ti, f)
            hit[0].z = 0.0
        if hit:
            fr[f] = (Matrix.Translation(hit[0]), 0.0)
        else:
            v = v0 + Vector((0, 0, -G)) * tau
            fr[f] = (_stretch(p, v), 1.0)
    out = {'name': name, 'kind': 'drop', 'frames': fr, 'size': size}
    if hit:
        sp = {f: (Matrix.Translation(hit[0] + Vector((0, 0, 0.001))), clamp((f - hit[1] + 1) / 3.0)) for f in range(1, nframes + 1)}
        return [out, {'name': name + '_splat', 'kind': 'splat', 'frames': sp, 'size': 0.8 * size}]
    return [out]


def flatten(parts):
    out = []
    for p in parts:
        if isinstance(p, list):
            out.extend(p)
        else:
            out.append(p)
    return out
