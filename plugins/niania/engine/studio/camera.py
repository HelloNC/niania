"""Shot cameras. One camera object per shot; keys are only meaningful inside the shot.

shot = {"name": "s1", "start": 0.0, "end": 3.0,
        "keys": [{"t": 0.0, "pos": [x,y,z], "aim": [x,y,z] | {"char": "mia", "bone": "head_center"} | {"object": "cup"},
                  "lens": 35, "roll": 0}, ...],
        "focus": <point spec> (default: the first key's aim), "fstop": 2.8,
        "lag": 0.12      # operator follow lag on the aim point (s)
        "shake": 0.15    # handheld amplitude (deg)
        "ease": "auto"}  # interpolation of positions between keys
Times inside a shot are absolute video seconds.
"""
import math
import bpy
from mathutils import Vector, Matrix, Quaternion
from .tracks import Track
from .util import noise1, DEG, ease
from .perform import Lag


class Shot:
    def __init__(self, spec):
        self.spec = spec
        self.name = spec['name']
        self.start, self.end = spec['start'], spec['end']
        ks = sorted(spec['keys'], key=lambda k: k['t'])
        self.keys = ks
        e = spec.get('ease', 'auto')
        self.pos = Track(tuple(ks[0]['pos']))
        self.lens = Track(ks[0].get('lens', 35))
        self.roll = Track(ks[0].get('roll', 0.0))
        for k in ks:
            self.pos.set(k['t'], tuple(k['pos']), k.get('ease', e))
            self.lens.set(k['t'], k.get('lens', self.lens(k['t'])), k.get('ease', e))
            self.roll.set(k['t'], k.get('roll', 0.0), k.get('ease', e))
        self.lag = Lag(spec.get('lag', 0.12), 3)

    def aim_spec(self, t):
        ks = self.keys
        if t <= ks[0]['t']:
            return ks[0]['aim'], ks[0]['aim'], 0.0
        for a, b in zip(ks[:-1], ks[1:]):
            if a['t'] <= t <= b['t']:
                return a['aim'], b['aim'], ease(b.get('ease', 'inout') if b.get('ease', 'auto') != 'auto' else 'inout',
                                                (t - a['t']) / max(1e-6, b['t'] - a['t']))
        return ks[-1]['aim'], ks[-1]['aim'], 1.0

    def active(self, t):
        return self.start - 1e-6 <= t < self.end - 1e-6


def camera_world_pos(shots, t):
    for sh in shots:
        if sh.active(t):
            return Vector(sh.pos(t))
    return None


def compute(shots, world, fps, nframes):
    """Returns {shot_name: {frame: (Matrix, lens, focus_dist)}}"""
    res = {}
    for sh in shots:
        f0 = max(1, int(math.floor(sh.start * fps)) + 1 - 2)
        f1 = min(nframes, int(math.ceil(sh.end * fps)) + 2)
        data = {}
        seed = sum(map(ord, sh.name))
        amp = sh.spec.get('shake', 0.12)
        for f in range(f0, f1 + 1):
            t = (f - 1) / fps
            world.frame = f
            a, b, u = sh.aim_spec(t)
            pa, pb = world.resolve_point(a, t), world.resolve_point(b, t)
            aim = pa.lerp(pb, u) if (pa is not None and pb is not None) else (pa or pb)
            aim = Vector(sh.lag(tuple(aim), 1.0 / fps))
            pos = Vector(sh.pos(t))
            d = (aim - pos).normalized()
            q = d.to_track_quat('-Z', 'Y')
            roll = sh.roll(t) + amp * noise1(seed + 3, t * 0.6)
            q = q @ Quaternion((0, 0, 1), roll * DEG)
            q = q @ Quaternion((1, 0, 0), amp * noise1(seed + 1, t * 0.5) * DEG) @ \
                Quaternion((0, 1, 0), amp * noise1(seed + 2, t * 0.45) * DEG)
            fs = sh.spec.get('focus')
            fp = world.resolve_point(fs, t) if fs is not None else aim
            fd = (fp - pos).length if fp is not None else (aim - pos).length
            data[f] = (Matrix.LocRotScale(pos, q, None), sh.lens(t), fd)
        res[sh.name] = data
    return res


def create_objects(shots, col):
    cams = {}
    for sh in shots:
        cd = bpy.data.cameras.new('cam_' + sh.name)
        cd.sensor_width = 36.0
        cd.clip_start, cd.clip_end = 0.05, 2000.0
        fstop = sh.spec.get('fstop')
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
        ob = bpy.data.objects.new('cam_' + sh.name, cd)
        col.objects.link(ob)
        cams[sh.name] = ob
    return cams
