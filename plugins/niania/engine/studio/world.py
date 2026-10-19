"""Objects, physics, attachments, time remapping and secondary FX.

Clocks: authored performance runs on *video time* t. Physics runs on *story time* tau(t),
the integral of the `time_remap` speed curve, so slow motion keeps gravity consistent.

Object motion segments (timeline props[name].motion), sorted by t:
  {"t":0, "do":"held", "char":"mia", "side":"R"}           attached to a hand from t
  {"t":1.6, "do":"place", "dur":0.6, "pos":[x,y,z], "yaw":deg, "release":0.15}
        the holder's hand carries the object to a resting pose, fingers open, object rests
  {"t":2.4, "do":"topple", "dir":[dx,dy], "nudge":0.6, "support":"table"}
        tip over the support's edge (rigid pivot dynamics) then free fall
  {"t":3.0, "do":"fall"}                                   ballistic from the current state
  {"t":4.4, "do":"catch", "char":"mia", "side":"R", "approach":0.5, "give":0.06}
        the hand converges on the moving object, fingers close, object becomes held
  {"t":5.0, "do":"static", "pos":[..], "rot":[..]}
"""
import math
from mathutils import Vector, Matrix, Quaternion
from .util import clamp, ease, DEG, rng
from .perform import grip_center

G = 9.81


class Clock:
    def __init__(self, remap, fps, duration):
        self.fps = fps
        keys = remap or [[0.0, 1.0]]
        keys = sorted(keys)
        self.keys = keys
        self.dt = 1.0 / 480
        n = int(duration / self.dt) + 960
        self.tau = [0.0]
        for i in range(1, n):
            t = (i - 0.5) * self.dt
            self.tau.append(self.tau[-1] + self.speed(t) * self.dt)

    def speed(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, s0), (t1, s1) in zip(ks[:-1], ks[1:]):
            if t0 <= t <= t1:
                return s0 + (s1 - s0) * ease('inout', (t - t0) / max(1e-6, t1 - t0))
        return ks[-1][1]

    def inverse(self, tau):
        lo, hi = 0, len(self.tau) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if self.tau[m] <= tau:
                lo = m
            else:
                hi = m
        a, b = self.tau[lo], self.tau[hi]
        u = (tau - a) / max(1e-12, b - a)
        return (lo + u) * self.dt

    def __call__(self, t):
        x = t / self.dt
        i = int(max(0, min(len(self.tau) - 2, math.floor(x))))
        u = x - i
        return self.tau[i] * (1 - u) + self.tau[i + 1] * u


class Obj:
    def __init__(self, name, ob, spec):
        self.name, self.ob, self.spec = name, ob, spec
        p = spec.get('pos', (0, 0, 0))
        self.rest = Matrix.Translation(p) @ Matrix.Rotation(math.radians(spec.get('rot', 0.0)), 4, 'Z')
        if spec.get('type') in ('existing', 'image', 'model', 'airliner', 'drone', 'lever'):
            self.rest = ob.matrix_basis.copy()
        self.segs = sorted(spec.get('motion', []), key=lambda s: s.get('t', 1e9))
        self.radius = float(ob.get('radius', 0.05))
        self.height = float(ob.get('height', 0.1))
        g = ob.get('grip_body')
        self.grip = (float(g[0]), float(g[1])) if g else (self.radius, self.height / 2)
        self.mats = {}        # frame -> Matrix
        self.phys = {}        # seg index -> sampled trajectory
        self.held_offsets = {}   # seg index -> Matrix (object in hand coords)


class World:
    def __init__(self, timeline, objects, performers, fps):
        self.tl = timeline
        self.fps = fps
        self.clock = Clock(timeline.get('time_remap'), fps, timeline['duration'])
        self.objs = {n: Obj(n, ob, timeline['props'][n]) for n, ob in objects.items()}
        self.perfs = performers
        self.frame = 0
        self.cache = {}
        self.grip_cache = {}
        self.cameras = {}
        self.notes = []
        self.events = {}
        self.anchors = {}
        self._resolve_catch_times()

    def _resolve_catch_times(self):
        """'catch' segments may give at_height instead of t: catch when the object's base
        falls through that height. Also records named event times (video seconds)."""
        for o in self.objs.values():
            for i, s in enumerate(o.segs):
                if s['do'] == 'place':
                    self.events['place:' + o.name] = s['t'] + s.get('dur', 0.5)
                if s['do'] in ('topple', 'fall'):
                    self.events[s['do'] + ':' + o.name] = s['t']
                if s['do'] == 'catch' and 't' not in s:
                    prev = i - 1
                    t0 = o.segs[prev]['t']
                    t = t0
                    while t < t0 + 20:
                        M = self.physics(o, prev, t)
                        if M.translation.z <= s['at_height']:
                            break
                        t += 1.0 / 480
                    s['t'] = round(t, 4)
                if s['do'] == 'topple' and 't' in s:
                    traj = self.physics(o, i, s['t'] + 1e-4) and o.phys[i]
                    self.events['leave_edge:' + o.name] = self.clock.inverse(traj['tau0'] + traj.get('teeter', 0.0))
                if s['do'] == 'catch':
                    self.events['catch:' + o.name] = s['t']
            o.segs.sort(key=lambda s: s['t'])
            o.phys.clear()

    def time(self, v):
        """Resolve '<event>+<offset>' strings to video seconds."""
        if isinstance(v, (int, float)):
            return float(v)
        v = v.replace(' ', '')
        for op in ('+', '-'):
            if op in v[1:]:
                k = v.rfind(op)
                base, off = v[:k], float(v[k:])
                break
        else:
            base, off = v, 0.0
        return self.events[base] + off

    # ---------------------------------------------------------------- queries used by performers
    def seg_at(self, o, t):
        cur, idx = None, -1
        for i, s in enumerate(o.segs):
            if s['t'] <= t + 1e-9:
                cur, idx = s, i
        return cur, idx

    def held_by(self, char, side, t):
        for o in self.objs.values():
            s, i = self.seg_at(o, t)
            if s and s['do'] in ('held', 'catch', 'place') and s.get('char', self._holder(o, i)) == char and \
                    s.get('side', self._holder_side(o, i)) == side:
                if s['do'] == 'place' and t > s['t'] + s.get('dur', 0.5):
                    continue
                return o.name
        return None

    def _holder(self, o, i):
        for s in reversed(o.segs[:i + 1]):
            if 'char' in s:
                return s['char']
        return None

    def _holder_side(self, o, i):
        for s in reversed(o.segs[:i + 1]):
            if 'side' in s:
                return s['side']
        return 'R'

    def grasp_target(self, char, side, t):
        p = self.perfs[char]
        sa, sb, u = p.hands[side].state(t)
        if isinstance(sb, dict) and 'object' in sb and u > 0.6:
            return sb['object']
        return None

    def grip_radius(self, name):
        return self.objs[name].grip[0]

    def is_attached(self, o, t):
        s, i = self.seg_at(o, t)
        if not s:
            return None
        if s['do'] in ('held', 'catch'):
            return (self._holder(o, i), self._holder_side(o, i), i)
        if s['do'] == 'place' and t <= s['t'] + s.get('dur', 0.5):
            return (self._holder(o, i), self._holder_side(o, i), self._attach_idx(o, i))
        return None

    def _attach_idx(self, o, i):
        for j in range(i, -1, -1):
            if o.segs[j]['do'] in ('held', 'catch'):
                return j
        return i

    def object_matrix(self, name, t):
        o = self.objs[name]
        att = self.is_attached(o, t)
        if att:
            char, side, idx = att
            f = self.frame
            W = self.perfs[char].world.get(f) or self.perfs[char].world.get(f - 1)
            if W:
                return W['hand_target.' + side] @ self.held_offset(name, idx)
        return self.free_matrix(o, t)

    def held_offset(self, name, idx=None):
        o = self.objs[name]
        if idx is None:
            att = self.is_attached(o, self.frame / self.fps)
            idx = att[2] if att else max(o.held_offsets) if o.held_offsets else None
        if idx in o.held_offsets:
            return o.held_offsets[idx]
        seg = o.segs[idx]
        side = seg.get('side', 'R')
        char = seg.get('char')
        if seg.get('keep_grip'):     # take the object exactly where the hand already is (no snap to a side grip)
            f = int(round(seg['t'] * self.fps)) + 1
            W = self.perfs[char].world.get(f - 1)
            if W and (f - 1) in o.mats:
                o.held_offsets[idx] = W['hand_target.' + side].inverted() @ o.mats[f - 1]
                return o.held_offsets[idx]
        gs = {'grip': 'body', 'char': char}
        for k in ('angle', 'flip'):
            if k in seg:
                gs[k] = seg[k]
        Gm = self.grip_frame(name, side, gs, at=seg['t'])
        o.held_offsets[idx] = Gm.inverted()
        return o.held_offsets[idx]

    def grip_frame(self, name, side, spec, at=None):
        """Hand pose in object coordinates for a cylindrical grasp. The angle around the axis
        and the thumb direction are chosen to keep the wrist natural relative to the shoulder."""
        key = (name, side, spec.get('angle'), spec.get('flip'), spec.get('char'), round(at or -1, 3))
        if key in self.grip_cache:
            return self.grip_cache[key]
        o = self.objs[name]
        r, hc = o.grip
        char = spec.get('char') or next(iter(self.perfs))
        perf = self.perfs[char]
        S = perf.S
        C = grip_center(S, r)           # cylinder centre in hand coords
        t = at if at is not None else self.frame / self.fps
        Mo = self.free_matrix(o, t - 1e-4) if not self.is_attached(o, t - 1e-4) else o.rest
        best = None
        W = perf.world.get(int(round(t * self.fps)) + 1) or perf.world.get(max(perf.world) if perf.world else 0)
        if W:
            sh = W['upper_arm.' + side].translation
        else:     # before any frame exists: rest shoulder placed at the stance
            from .util import yaw_quat
            fl, fr = perf.feet['L'](t), perf.feet['R'](t)
            base = Vector(((fl[0] + fr[0]) / 2, (fl[1] + fr[1]) / 2, 0))
            sh = base + yaw_quat((fl[3] + fr[3]) / 2) @ perf.rest['upper_arm.' + side].translation
        if spec.get('hold_at') is not None:
            Mo = Matrix.Translation(spec['hold_at']) @ Mo.to_3x3().to_4x4()
        angles = [spec['angle']] if 'angle' in spec else [i * 10 for i in range(36)]
        flips = [spec['flip']] if 'flip' in spec else [1, -1]
        for flip in flips:
            for ang in angles:
                a = math.radians(ang)
                Zh = -Vector((math.cos(a), math.sin(a), 0))          # palm normal points at the axis
                Xh = Vector((0, 0, flip))
                Yh = Zh.cross(Xh)
                org = Vector((0, 0, hc)) - Yh * C.y - Zh * C.z
                M = Matrix.Identity(4)
                for i in range(3):
                    M[i][0], M[i][1], M[i][2], M[i][3] = Xh[i], Yh[i], Zh[i], org[i]
                Mw = Mo @ M
                wrist = Mw.translation
                fing = Mw.col[1].to_3d()
                fore = (wrist - sh)
                reach = fore.length
                cost = 0.0
                cost += 3.0 * max(0, reach - perf.arm_len * 0.92) + 1.0 * max(0, 0.25 - reach)
                cost += 1.0 - fing.normalized().dot(fore.normalized())        # hand continues forearm
                # thumb up-ish: right hand X axis should point up for a natural grip
                # handle (object +X) opposite the palm, clear of fingertips and wrist
                axis_p = Mo @ Vector((0, 0, hc))
                if o.ob.get('prop_type') == 'mug':
                    hdir = (Mo.to_3x3() @ Vector((1, 0, 0))).normalized()
                    cost += 1.2 * (1.0 - hdir.dot(Mw.col[2].to_3d().normalized()))
                # forearm (towards the shoulder) must not pass through the object
                fdir = (sh - wrist).normalized()
                axw = (Mo.to_3x3() @ Vector((0, 0, 1))).normalized()
                for k in (0.05, 0.1, 0.16):
                    q = wrist + fdir * k
                    dv = q - axis_p
                    rr = (dv - axw * dv.dot(axw)).length
                    hz = dv.dot(axw)
                    if -o.height * 0.6 < hz < o.height * 0.6:
                        cost += 40.0 * max(0.0, r + 0.042 - rr)
                xw = Mw.col[0].to_3d()
                cost += 0.35 * (1 - (xw.z * (1 if side == 'R' else -1)))
                if W:
                    cost += self.arm_cost(perf, W, side, Mw, Mo, o)
                if best is None or cost < best[0]:
                    best = (cost, M)
        self.grip_cache[key] = best[1]
        return best[1]


    def arm_cost(self, perf, W, side, Mhand, obj_M=None, o=None):
        """How unnatural / colliding a hand pose is: estimated elbow from 2-bone IK with the
        elbow pole, wrist bend, and forearm clearance from a held cylinder."""
        S_ = W['upper_arm.' + side].translation
        Wr = Mhand.translation
        l1 = perf.length['upper_arm.' + side]
        l2 = perf.length['forearm.' + side]
        d = max(1e-4, (Wr - S_).length)
        cost = 3.0 * max(0.0, d - (l1 + l2) * 0.97)
        dd = min(d, (l1 + l2) * 0.999)
        a = (l1 * l1 - l2 * l2 + dd * dd) / (2 * dd)
        h = math.sqrt(max(0.0, l1 * l1 - a * a))
        ax = (Wr - S_).normalized()
        base = S_ + ax * a
        pole = W['elbow_pole.' + side].translation
        pv = pole - base
        pv = (pv - ax * pv.dot(ax))
        pv = pv.normalized() if pv.length > 1e-6 else Vector((0, 0, -1))
        elbow = base + pv * h
        fdir = (Wr - elbow).normalized()            # forearm direction towards the hand
        fing = Mhand.col[1].to_3d().normalized()
        palm = Mhand.col[2].to_3d().normalized()
        cost += 1.0 * (1.0 - fing.dot(fdir))        # wrist bend
        cost += 2.0 * max(0.0, -fdir.dot(palm) - 0.25) # forearm rising from the palm side
        if obj_M is not None and o is not None:
            r, hc = o.grip
            axis_p = obj_M @ Vector((0, 0, hc))
            axw = (obj_M.to_3x3() @ Vector((0, 0, 1))).normalized()
            for k in (0.03, 0.07, 0.12, 0.18):
                q = Wr - fdir * k
                dv = q - axis_p
                rr = (dv - axw * dv.dot(axw)).length
                hz = dv.dot(axw)
                if -o.height * 0.7 < hz < o.height * 0.7:
                    cost += 60.0 * max(0.0, r + 0.042 - rr)
        return cost

    def hold_orientation(self, name, spec, t, perf, W, side, P=None):
        key = id(spec)
        if key not in self.cache:
            o = self.objs[name]
            cur = o.mats.get(self.frame - 1) or self.object_matrix(name, t)
            q0 = cur.to_quaternion()
            mode = spec.get('orient', 'upright')
            if mode == 'keep':
                q = q0
            else:
                up = Vector(spec.get('up', (0, 0, 1))).normalized()
                z0 = q0 @ Vector((0, 0, 1))
                qb = z0.rotation_difference(up) @ q0
                if spec.get('tilt'):
                    ax = Vector(spec.get('tilt_axis', (1, 0, 0)))
                    qb = Quaternion(ax, math.radians(spec['tilt'])) @ qb
                q = qb
                if P is not None and W is not None and spec.get('auto_twist', True):
                    # choose the twist about `up` that keeps the wrist natural and the forearm clear
                    Hinv = self.held_offset(name).inverted()
                    best = None
                    for k in range(-12, 13):
                        qq = Quaternion(up, math.radians(k * 15)) @ qb
                        Mo = Matrix.Translation(P) @ qq.to_matrix().to_4x4()
                        c = self.arm_cost(perf, W, side, Mo @ Hinv, Mo, o) + 0.002 * abs(k)
                        if best is None or c < best[0]:
                            best = (c, qq)
                    q = best[1]
            self.cache[key] = q
        return self.cache[key]

    def resolve_point(self, spec, t):
        if spec is None:
            return None
        if isinstance(spec, (list, tuple)):
            return Vector(spec)
        if 'blend' in spec:
            a, b, u = spec['blend']
            pa, pb = self.resolve_point(a, t), self.resolve_point(b, t)
            if pa is None:
                return pb
            return pa.lerp(pb, u)
        if 'object' in spec:
            o = self.objs[spec['object']]
            M = o.mats.get(self.frame) or o.mats.get(self.frame - 1) or self.object_matrix(spec['object'], t)
            return M @ Vector((0, 0, o.height * 0.5)) + Vector(spec.get('offset', (0, 0, 0)))
        if 'char' in spec:
            p = self.perfs[spec['char']]
            W = p.world.get(self.frame) or p.world.get(self.frame - 1)
            if not W:
                return None
            bone = spec.get('bone', 'head_center')
            return W[bone].translation + Vector(spec.get('offset', (0, 0, 0)))
        if 'camera' in spec:
            cam = self.cameras.get('active')
            return cam.copy() if cam is not None else None
        if 'anchor' in spec:
            a = self.anchors.get(spec['anchor'])
            return (Vector(a) + Vector(spec.get('offset', (0, 0, 0)))) if a is not None else None
        return None

    # ---------------------------------------------------------------- free motion
    def free_matrix(self, o, t):
        s, i = self.seg_at(o, t)
        if s is None:
            return o.rest
        if s['do'] == 'static':
            return Matrix.Translation(s['pos']) @ Matrix.Rotation(math.radians(s.get('rot', 0.0)), 4, 'Z')
        if s['do'] in ('swing', 'rattle', 'spin'):
            base = o.rest if i == 0 else self.free_matrix(o, s['t'] - 1e-4)
            if s['do'] == 'spin':
                ang = 2 * math.pi * s.get('rps', 10.0) * (self.clock(t) - self.clock(s['t']))
                return base @ Matrix.Rotation(ang, 4, s.get('axis', 'Y'))
            u = (t - s['t']) / max(1e-6, s.get('dur', 0.5))
            if s['do'] == 'swing':
                ang = math.radians(s.get('angle', 90.0)) * ease(s.get('ease', 'inout'), u)
            else:                           # rattle: a locked door/handle shaking, decaying
                uu = clamp(u)
                ang = math.radians(s.get('amp', 2.0)) * math.sin(2 * math.pi * s.get('freq', 9.0) * (t - s['t'])) * \
                    (1 - uu) * (1.0 if u <= 1 else 0.0)
            return base @ Matrix.Rotation(ang, 4, s.get('axis', 'Z'))
        if s['do'] == 'path':
            return self.path_matrix(o, s, t)
        if s['do'] == 'attach':         # rides on another object (cap on a bottle), twisting angle0 -> angle over dur
            par = self.objs[s['to']]
            Mp = self.object_matrix(s['to'], t)
            loc = s.get('local', (0, 0, par.height))
            ang = self.attach_angle(s, t)
            return Mp @ Matrix.Translation(loc) @ Matrix.Rotation(math.radians(ang), 4, 'Z')
        if s['do'] == 'place':
            return self.place_pose(s, o)
        if s['do'] in ('topple', 'fall'):
            return self.physics(o, i, t)
        if s['do'] in ('held', 'catch'):
            # free_matrix of a held object (used before frame data exists): best effort
            return o.mats.get(self.frame - 1, o.rest)
        return o.rest

    def attach_angle(self, s, t):
        d = s.get('dur', 0.0)
        u = ease(s.get('ease', 'inout'), clamp((t - s['t']) / d)) if d else 1.0
        a0 = s.get('angle0', s.get('angle', 0.0))
        return a0 + (s.get('angle', a0) - a0) * u

    def twist_angle(self, name, t):
        """Current twist (deg) of an `attach`ed object about its parent's axis (last value once released)."""
        o = self.objs[name]
        last = 0.0
        for s in o.segs:
            if s['do'] == 'attach':
                if s['t'] <= t + 1e-9:
                    last = self.attach_angle(s, t)
        return last

    def path_matrix(self, o, s, t):
        """Catmull-Rom flight path; local +Y faces along the path, banking into turns."""
        pts = [Vector(p) for p in s['points']]
        u = ease(s.get('ease', 'linear'), (t - s['t']) / max(1e-6, s.get('dur', 2.0)))
        n = len(pts) - 1

        def at(uu):
            uu = clamp(uu) * n
            i = min(int(uu), n - 1)
            f = uu - i
            p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(n, i + 2)]
            return 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f +
                          (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3)
        p = at(u)
        d = (at(min(1, u + 0.01)) - at(max(0, u - 0.01)))
        d = d.normalized() if d.length > 1e-6 else Vector((0, 1, 0))
        q = d.to_track_quat('Y', 'Z')
        d2 = (at(min(1, u + 0.03)) - 2 * p + at(max(0, u - 0.03)))
        bank = clamp(-d2.dot(q @ Vector((1, 0, 0))) * s.get('bank', 30.0) * 40, -s.get('bank', 30.0), s.get('bank', 30.0))
        q = q @ Quaternion((0, 1, 0), math.radians(bank))
        return Matrix.Translation(p) @ q.to_matrix().to_4x4()

    def place_pose(self, s, o=None):
        if o is not None:
            fr = int(round((s['t'] + s.get('dur', 0.5)) * self.fps)) + 1
            if fr in o.mats:
                return o.mats[fr]
        return Matrix.Translation(s['pos']) @ Matrix.Rotation(math.radians(s.get('yaw', 0.0)), 4, 'Z')

    def physics(self, o, i, t):
        if i not in o.phys:
            o.phys[i] = self.simulate(o, i)
        traj = o.phys[i]
        tau = self.clock(t) - traj['tau0']
        k = tau / traj['dt']
        j = int(max(0, min(len(traj['m']) - 2, math.floor(k))))
        u = clamp(k - j)
        a, b = traj['m'][j], traj['m'][j + 1]
        la, ra, _ = a.decompose()
        lb, rb, _ = b.decompose()
        return Matrix.LocRotScale(la.lerp(lb, u), ra.slerp(rb, u), None)

    def start_state(self, o, i):
        """Pose and velocities at the start of segment i."""
        s = o.segs[i]
        t0 = s['t']
        prev = o.segs[i - 1] if i > 0 else None
        if prev and prev['do'] == 'place':
            return self.place_pose(prev, o), Vector(), Vector()
        if prev and prev['do'] == 'static':
            return self.free_matrix(o, t0 - 1e-4), Vector(), Vector()
        if prev and prev['do'] in ('topple', 'fall'):
            M0 = self.physics(o, i - 1, t0)
            M1 = self.physics(o, i - 1, t0 - 0.02)
            dtau = self.clock(t0) - self.clock(t0 - 0.02)
            v = (M0.translation - M1.translation) / max(dtau, 1e-6)
            q = (M1.to_quaternion().inverted() @ M0.to_quaternion())
            ax, an = q.to_axis_angle()
            w = M1.to_quaternion() @ (ax * (an / max(dtau, 1e-6)))
            return M0, v, w
        # released from a hand: use the recorded hand motion
        f = int(round(t0 * self.fps)) + 1
        M0 = o.mats.get(f - 1, o.rest)
        M1 = o.mats.get(f - 2, M0)
        dtau = self.clock(t0) - self.clock(t0 - 1 / self.fps)
        return M0, (M0.translation - M1.translation) / max(dtau, 1e-6), Vector()

    def simulate(self, o, i):
        s = o.segs[i]
        dt = 1.0 / 960
        tau0 = self.clock(s['t'])
        M0, v0, w0 = self.start_state(o, i)
        com_l = Vector((0, 0, o.height * 0.5))
        R = M0.to_quaternion()
        com = M0 @ com_l
        out = []
        n_end = int(4.0 / dt)
        if s['do'] == 'topple':
            d = Vector((*s['dir'], 0)).normalized()
            sup = self.objs.get(s.get('support', 'table'))
            c = M0.translation
            if sup:
                T = sup.rest.translation
                Rr = sup.radius
                # distance along d from object centre to the table edge
                cx, cy = c.x - T.x, c.y - T.y
                b = cx * d.x + cy * d.y
                cc = cx * cx + cy * cy - Rr * Rr
                sd = -b + math.sqrt(max(0.0, b * b - cc))
            else:
                sd = o.radius
            sd = max(-o.radius * 0.95, min(o.radius, sd))
            E = Vector((c.x + d.x * sd, c.y + d.y * sd, c.z))
            axis = Vector((0, 0, 1)).cross(d).normalized()
            r0 = com - E
            ell = r0.length
            k2 = o.radius ** 2 / 4 + o.height ** 2 / 12
            th, om = 0.0, s.get('nudge', 0.5)
            phi0 = math.atan2(-sd, o.height / 2)
            n = 0
            while True:
                q = Quaternion(axis, th)
                Rn = q @ R
                comn = E + q @ r0
                out.append(Matrix.Translation(comn) @ Rn.to_matrix().to_4x4() @ Matrix.Translation(-com_l))
                if phi0 + th > math.radians(s.get('release_deg', 40)) or n > n_end:
                    break
                acc = G * ell * math.sin(phi0 + th) / (ell * ell + k2)
                om += acc * dt
                th += om * dt
                n += 1
            v = axis.cross(q @ r0) * om
            w = axis * om
            teeter = len(out) * dt
            com, R = comn, Rn
        else:
            v, w = v0, w0
            teeter = 0.0
        # ballistic phase
        floor = s.get('floor', 0.0)
        for _ in range(n_end):
            v = v + Vector((0, 0, -G * dt))
            com = com + v * dt
            if w.length > 1e-9:
                R = Quaternion(w.normalized(), w.length * dt) @ R
            M = Matrix.Translation(com) @ R.to_matrix().to_4x4() @ Matrix.Translation(-com_l)
            low = min((M @ Vector((x * o.radius, y * o.radius, z))).z for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1)) for z in (0, o.height))
            if low < floor:
                M.translation.z += floor - low
                out.append(M)
                break
            out.append(M)
        return {'tau0': tau0, 'dt': dt, 'm': out, 'teeter': teeter}

    # ---------------------------------------------------------------- per-frame update
    def update_objects(self, f, t):
        for o in self.objs.values():
            o.mats[f] = self.object_matrix(o.name, t)
