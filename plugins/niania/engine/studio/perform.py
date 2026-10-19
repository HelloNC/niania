"""Character performance: verbs -> tracks -> per-frame pose (world-space IK targets + FK).

Design rules that make motion believable by construction:
  * Feet are keyed in world space and only move inside explicit steps -> no sliding.
  * Hips are placed over the support polygon (weight track between the feet) and are
    auto-lowered so legs never over-extend -> balance, no knee pops.
  * Spine/neck/head authored rotations are lagged progressively up the chain -> overlap.
  * Look-at: eyes lead, head follows, chest follows last (critically damped filters).
  * Hands resolve per frame from specs (body-relative, world, object grasp, hold) and blend
    between them along arcs; held objects follow the hand, so contact is exact.
  * Finger curl on a held object is solved against the grip cylinder -> no clipping.
"""
import math
import os
from mathutils import Vector, Matrix, Quaternion
from .tracks import Track, SpecTrack
from .util import (DEG, ease, fwd, right_of, yaw_quat, hand_matrix, blend_matrix, mat_from_axes,
                   noise1, rng, wrap180, clamp)
from .character import FACE_KEYS, SK, HEAD_C, HEAD_R, side_sign, PALM

FK_CHAIN = ['spine', 'chest', 'neck', 'head']
LAG = {'spine': 0.035, 'chest': 0.06, 'neck': 0.08, 'head': 0.10}

HAND_PRESETS = {   # wrist pos in 'chest' frame (out, fwd, up from chest head), finger dir, palm dir (out,fwd,up)
    'relaxed': dict(rel='shoulder', pos=(0.035, 0.03, -0.445), fingers=(0.02, 0.08, -1), palm=(-1, 0.15, 0)),
    'hip': dict(rel='hips', pos=(0.20, 0.0, 0.03), fingers=(-0.3, 0.1, -1), palm=(-1, 0, 0.1)),
    'chest': dict(rel='chest', pos=(0.06, 0.25, 0.02), fingers=(-1, 0.3, 0.3), palm=(0, -1, 0)),
    'ready': dict(rel='shoulder', pos=(0.06, 0.22, -0.33), fingers=(0.0, 1, -0.4), palm=(-0.7, 0, -0.5)),
    'pocket': dict(rel='hips', pos=(0.06, 0.12, 0.08), fingers=(-0.6, 0, -1), palm=(0, -1, 0)),
    'lap': dict(rel='hips', pos=(0.1, 0.30, 0.05), fingers=(-0.15, 1, -0.25), palm=(0, 0, -1)),
    'armrest': dict(rel='hips', pos=(0.24, 0.22, 0.17), fingers=(0, 1, -0.2), palm=(0, 0, -1)),
}

ARM_LEN = None


def _q_local(pitch, roll, yaw):
    """Rotation in the rest-armature frame: + pitch bends forward (-Y), + roll leans to the
    character's right (-X), + yaw turns to the character's left."""
    return (Quaternion((0, 0, 1), yaw * DEG) @ Quaternion((1, 0, 0), pitch * DEG) @
            Quaternion((0, 1, 0), -roll * DEG))


class Lag:
    """Critically damped second-order follower (per component)."""

    def __init__(self, tau, n):
        self.tau, self.x, self.v = tau, None, [0.0] * n

    def __call__(self, target, dt, tau=None):
        tau = tau or self.tau
        if self.x is None or tau <= 1e-4:
            self.x = list(target)
            return tuple(self.x)
        w = 2.0 / tau
        ex = math.exp(-w * dt)
        for i, g in enumerate(target):      # exact critically damped step (unconditionally stable)
            e0, v0 = self.x[i] - g, self.v[i]
            c = v0 + w * e0
            self.x[i] = g + (e0 + c * dt) * ex
            self.v[i] = (v0 - w * c * dt) * ex
        return tuple(self.x)


class Spring:
    """Point mass on a spring hanging off an anchor (pompom, drawstrings)."""

    def __init__(self, k=180.0, c=9.0, g=-4.0):
        self.k, self.c, self.g = k, c, g
        self.p = None
        self.v = Vector()

    def __call__(self, rest_tip, dt):
        if self.p is None:
            self.p = rest_tip.copy()
            return self.p
        sub = 6
        h = dt / sub
        for _ in range(sub):
            a = (rest_tip - self.p) * self.k - self.v * self.c + Vector((0, 0, self.g))
            self.v += a * h
            self.p += self.v * h
        return self.p


class Performer:
    def __init__(self, name, rig, scene):
        self.name, self.rig, self.scene = name, rig, scene
        self.S = float(rig.get('spec_scale', 1.0))
        S = self.S
        self.rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in rig.data.bones}
        self.length = {b.name: b.length for b in rig.data.bones}
        self.leg_len = (Vector(SK['thigh'][0]) - Vector(SK['thigh'][1])).length * S + \
                       (Vector(SK['shin'][0]) - Vector(SK['shin'][1])).length * S
        self.arm_len = (Vector(SK['upper_arm'][0]) - Vector(SK['upper_arm'][1])).length * S + \
                       (Vector(SK['forearm'][0]) - Vector(SK['forearm'][1])).length * S
        self.hip_h = SK['hips'][0][2] * S - 0.012 * S
        self.ankle_h = SK['foot'][0][2] * S
        # ---- tracks
        self.feet = {s: Track((0, 0, self.ankle_h, -90.0, 0.0)) for s in 'LR'}
        self.weight = Track(0.5)
        self.crouch = Track(0.0)
        self.hips_off = Track((0.0, 0.0, 0.0))     # (right, fwd, up) in body frame
        self.hips_rot = Track((0.0, 0.0, 0.0))     # pitch, roll, yaw (deg)
        self.rot = {b: Track((0.0, 0.0, 0.0)) for b in FK_CHAIN}
        self.shrug = {s: Track(0.0) for s in 'LR'}
        self.hands = {s: SpecTrack({'preset': 'relaxed'}) for s in 'LR'}
        self.grip = {s: Track(0.12) for s in 'LR'}
        self.spread = {s: Track(0.0) for s in 'LR'}
        self.face = {k: Track(0.0) for k in FACE_KEYS}
        self.look = SpecTrack(None)
        self.look_w = Track(0.0)
        self.look_speed = Track(1.0)
        self.auto_blink = True
        self.blink_times = []
        self.held = {'L': None, 'R': None}           # filled by world attachments (for finger fit)
        self.grip_fit = {}                           # (side, radius) -> curl angles
        self.lags = {b: Lag(LAG[b], 3) for b in FK_CHAIN}
        self.aim = {'eyes': Lag(0.02, 2), 'head': Lag(0.14, 2), 'chest': Lag(0.32, 2)}
        self.springs = {'pompom': Spring(160, 7.5, -3.0), 'string.L': Spring(120, 6.0, -9.0),
                        'string.R': Spring(120, 6.0, -9.0)}
        self.prev_hips = []
        self.out = {}         # frame -> dict(bone -> basis Matrix, props)
        self.world = {}       # frame -> dict(name -> world Matrix) (analytic, for objects/QC/cameras)
        self.notes = []
        self.events = []

    # ================================================================ verbs
    def stance(self, t=0.0, pos=(0, 0), facing=-90.0, width=0.2, **_):
        f, r = fwd(facing), right_of(facing)
        c = Vector((pos[0], pos[1], 0))
        for s in 'LR':
            p = c + r * (-side_sign(s) * width / 2)
            self.feet[s].set(t, (p.x, p.y, self.ankle_h, facing, 0.0))
        self.weight.set(t, 0.5)

    def sit(self, t=0.0, dur=0.01, seat=(0, 0, 0.47), facing=-90.0, feet_fwd=0.44, width=0.24, lean=-6.0, **_):
        """Seated pose: hips over the seat cushion, feet planted in front, slight recline.
        seat = cushion-top centre [x, y, z] (or an anchor name resolved by the build)."""
        S = self.S
        f, r = fwd(facing), right_of(facing)
        c = Vector(seat)
        for s in 'LR':
            p = c + f * feet_fwd + r * (-side_sign(s) * width / 2)
            self.feet[s].move(t, dur, (p.x, p.y, self.ankle_h, facing, 0.0), 'inout')
        self.weight.move(t, dur, 0.5, 'inout')
        self.hips_off.move(t, dur, (0.0, -feet_fwd + 0.02, 0.0), 'inout')
        self.crouch.move(t, dur, self.hip_h - (c.z + 0.085 * S), 'inout')
        self.hips_rot.move(t, dur, (lean, 0.0, 0.0), 'inout')

    def step(self, t, dur=0.45, foot='R', to=None, by=None, facing=None, lift=0.07, weight_after=0.5,
             shift_first=0.12, toe_off=20.0, **_):
        """Lift one foot along an arc to a new world spot. The body first shifts weight onto
        the other foot (balance), then rolls onto the new foot after contact."""
        tr = self.feet[foot]
        x, y, z, yaw, pitch = tr(t)
        if to is None:
            d = Vector(by or (0.0, 0.25))           # (right, fwd) relative to current facing
            p = Vector((x, y, 0)) + right_of(yaw) * d[0] + fwd(yaw) * d[1]
            to = (p.x, p.y)
        nyaw = yaw if facing is None else facing
        # weight onto the support foot before lift-off
        support = 0.0 if foot == 'R' else 1.0
        if shift_first:
            self.weight.move(t - shift_first, shift_first, support * 0.85 + 0.5 * 0.15, 'inout')
        tr.move(t, dur * 0.25, (x, y, z + lift * 0.25, yaw, -toe_off), 'in')          # heel peels, toe pushes off
        mid = ((x + to[0]) / 2, (y + to[1]) / 2, z + lift, (yaw + nyaw) / 2, 0.0)
        tr.set(t + dur * 0.55, mid, 'auto')
        tr.set(t + dur * 0.85, (to[0], to[1], z + 0.012, nyaw, 8.0), 'auto')          # heel leads
        tr.set(t + dur, (to[0], to[1], z, nyaw, 0.0), 'out')                         # plant
        self.weight.move(t + dur * 0.8, dur * 0.5, weight_after, 'inout')
        self.events.append(('step', foot, t + dur))

    def shift(self, t, dur=0.4, to=0.5, ease_='inout', **_):
        val = {'L': 0.0, 'R': 1.0, 'center': 0.5}.get(to, to)
        self.weight.move(t, dur, float(val), ease_)

    def hips(self, t, dur=0.4, crouch=None, offset=None, rot=None, ease_='auto', **_):
        if crouch is not None:
            self.crouch.move(t, dur, crouch, ease_)
        if offset is not None:
            self.hips_off.move(t, dur, tuple(offset), ease_)
        if rot is not None:
            self.hips_rot.move(t, dur, tuple(rot), ease_)

    def bend(self, t, dur=0.4, bone='chest', rot=(0, 0, 0), ease_='auto', **_):
        """Rotate an FK bone: rot = (pitch fwd, roll right, yaw left) in degrees."""
        bones = bone if isinstance(bone, list) else [bone]
        for b in bones:
            self.rot[b].move(t, dur, tuple(rot), ease_)

    def anticipate(self, t, dur=0.25, crouch=0.03, lean=(0, 0, 0), **_):
        """Small counter-move before a big action (dip + lean away), returns to current."""
        self.crouch.pulse(t, dur, self.crouch(t) + crouch, 'inout', 'inout', 0.6)
        if any(lean):
            base = self.hips_off(t)
            self.hips_off.pulse(t, dur, tuple(b + l for b, l in zip(base, lean)), 'inout', 'inout', 0.6)

    def shrug_(self, t, dur=0.5, amount=1.0, side='both', **_):
        for s in ('LR' if side == 'both' else side):
            self.shrug[s].pulse(t, dur, amount, 'out', 'inout', 0.35)

    def hand(self, t, dur=0.5, side='R', spec=None, ease_='inout', **kw):
        spec = dict(spec or {})
        for k in ('arc',):
            if k in kw:
                spec[k] = kw[k]
        self.hands[side].move(t, dur, spec, ease_)

    def grip_(self, t, dur=0.15, side='R', amount=1.0, ease_='inout', **_):
        self.grip[side].move(t, dur, amount, ease_)

    def spread_(self, t, dur=0.15, side='R', amount=1.0, **_):
        self.spread[side].move(t, dur, amount, 'inout')

    def expr(self, t, dur=0.3, set=None, ease_='auto', **_):
        presets = {
            'neutral': {}, 'content': {'smile': 0.45},
            'happy': {'smile': 0.9, 'happy': 1.0, 'brow_up': 0.3},
            'surprised': {'wide': 1.0, 'brow_up': 1.0, 'o_shape': 0.9},
            'alarm': {'wide': 1.0, 'brow_up': 0.8, 'open': 0.45, 'brow_worried': 0.4},
            'focused': {'squint': 0.6, 'brow_down': 0.7, 'frown': 0.25},
            'relieved': {'smile': 0.55, 'brow_worried': 0.6, 'squint': 0.3},
            'proud': {'smile': 1.0, 'brow_up': 0.5},
            'laugh': {'happy': 1.0, 'open': 0.85, 'smile': 0.4, 'brow_up': 0.4},
            'wince': {'blink_L': 1.0, 'blink_R': 1.0, 'frown': 0.4, 'brow_down': 0.6},
            'sheepish': {'smile': 0.6, 'brow_worried': 0.7, 'squint': 0.3},
        }
        values = {}
        if isinstance(set, str):
            values = presets[set]
        else:
            for k, v in (set or {}).items():
                if k in presets and isinstance(v, (int, float)):
                    for kk, vv in presets[k].items():
                        values[kk] = values.get(kk, 0) + vv * v
                else:
                    values[k] = v
        keys = [k for k in FACE_KEYS if k not in ('look_x', 'look_y', 'blink_L', 'blink_R')]
        for k in keys:
            self.face[k].move(t, dur, float(values.get(k, 0.0)), ease_)
        for k in ('blink_L', 'blink_R'):
            if k in values:
                self.face[k].move(t, dur, float(values[k]), ease_)
            elif self.face[k](t) > 0:
                self.face[k].move(t, dur, 0.0, ease_)

    def blink(self, t, dur=0.16, **_):
        for k in ('blink_L', 'blink_R'):
            self.face[k].move(t, dur * 0.35, 1.0, 'in')
            self.face[k].move(t + dur * 0.55, dur * 0.45, 0.0, 'out')

    def look_at(self, t, dur=0.3, target=None, weight=1.0, speed=1.0, **_):
        """target: [x,y,z] | {'object': name} | {'camera': true} | {'char': name, 'bone': 'head'}"""
        if target is None:
            self.look_w.move(t, dur, 0.0, 'inout')
            return
        self.look.move(t, 0.001, target, 'linear')
        self.look_w.move(t, dur, weight, 'inout')
        self.look_speed.move(t, 0.05, speed, 'linear')

    def apply(self, ev):
        do = ev['do']
        fn = {'stance': self.stance, 'step': self.step, 'sit': self.sit, 'shift': self.shift, 'hips': self.hips,
              'bend': self.bend, 'anticipate': self.anticipate, 'shrug': self.shrug_, 'hand': self.hand,
              'grip': self.grip_, 'spread': self.spread_, 'expr': self.expr, 'blink': self.blink,
              'look': self.look_at}.get(do)
        if fn is None:
            raise ValueError('%s: unknown verb %r' % (self.name, do))
        kw = {k: v for k, v in ev.items() if k not in ('do', 'char')}
        if 'ease' in kw:
            kw['ease_'] = kw.pop('ease')
        fn(**kw)

    # ================================================================ per-frame evaluation
    def fk(self, basis):
        """World (armature) matrices for every bone in `basis`, following parents."""
        out = {}

        def get(b):
            if b in out:
                return out[b]
            p = self.parent[b]
            bm = basis.get(b, Matrix.Identity(4))
            if p is None:
                m = self.rest[b] @ bm
            else:
                m = get(p) @ (self.rest[p].inverted() @ self.rest[b]) @ bm
            out[b] = m
            return m
        for b in self.rest:
            get(b)
        return out

    def _conj(self, bone, q):
        r = self.rest[bone].to_quaternion()
        return r.inverted() @ q @ r

    def frame_frames(self, W):
        """Character-oriented frames from FK world matrices of spine bones: (left, up, fwd)."""
        return W

    def evaluate(self, f, t, dt, world):
        """Compute this character's pose at time t. `world` resolves objects/other chars."""
        S = self.S
        basis = {}
        props = {}
        feet = {s: self.feet[s](t) for s in 'LR'}
        # ---------------- hips placement (balance)
        yawL, yawR = feet['L'][3], feet['R'][3]
        facing = yawL + wrap180(yawR - yawL) / 2
        hr = self.hips_rot(t)
        facing_h = facing + hr[2]
        w = clamp(self.weight(t))
        pl, pr = Vector(feet['L'][:2]), Vector(feet['R'][:2])
        sup = pl.lerp(pr, w)
        ho = self.hips_off(t)
        breathe = math.sin(2 * math.pi * t / 3.8)
        sway = Vector((noise1(hash(self.name) % 97, t * 0.25), noise1(hash(self.name) % 89 + 3, t * 0.21))) * 0.004 * S
        pos = Vector((sup.x, sup.y, 0)) + right_of(facing) * (ho[0] + sway.x) + fwd(facing) * (ho[1] + sway.y)
        z = self.hip_h - self.crouch(t) + ho[2] + 0.0025 * S * breathe
        Rh = yaw_quat(facing_h) @ _q_local(hr[0], hr[1], 0.0)
        # auto-lower so neither leg exceeds 97% extension
        for s in 'LR':
            hj_rel = Rh @ Vector((side_sign(s) * SK['thigh'][0][0] * S, 0, 0))
            a = Vector(feet[s][:3])
            dxy = Vector((pos.x + hj_rel.x - a.x, pos.y + hj_rel.y - a.y)).length
            L = self.leg_len * 0.97
            if dxy < L:
                zmax = a.z + math.sqrt(L * L - dxy * dxy) - hj_rel.z
                if z > zmax:
                    z = zmax
            else:
                self.notes.append((f, 'leg overreach %s' % s))
        pos.z = z
        M_hips = Matrix.Translation(pos) @ Rh.to_matrix().to_4x4() @ self.rest['hips'].to_3x3().to_4x4()
        basis['hips'] = self.rest['hips'].inverted() @ M_hips
        self.prev_hips.append(pos.copy())
        # inertia: chest leans against hips acceleration (in body frame)
        acc_f = 0.0
        if len(self.prev_hips) >= 3:
            p0, p1, p2 = self.prev_hips[-3:]
            acc = (p2 - 2 * p1 + p0) / (dt * dt)
            acc_f = acc.dot(fwd(facing))
        # ---------------- spine chain (lagged authored rotations + look)
        loc = {}
        for b in FK_CHAIN:
            loc[b] = list(self.lags[b](self.rot[b](t), dt))
        loc['chest'][0] += 0.55 * breathe - clamp(acc_f * 0.35, -6, 6)
        loc['head'][0] += clamp(acc_f * 0.25, -4, 4)
        # look-at
        lw = self.look_w(t)
        eyes = (0.0, 0.0)
        sa, sb, u = self.look.state(t)
        tgt = world.resolve_point(sb if sb is not None else sa, t) if lw > 1e-3 else None
        if True:
            if tgt is None:
                hd = self.aim['head']((0.0, 0.0), dt)
                self.aim['eyes']((0.0, 0.0), dt)
                self.aim['chest']((0.0, 0.0), dt)
            else:
                # provisional FK to get the head position
                for b in FK_CHAIN:
                    basis[b] = self._conj(b, _q_local(*loc[b])).to_matrix().to_4x4()
                W0 = self.fk(dict(basis))
                head_p = W0['head'].translation + W0['head'].col[1].to_3d() * (HEAD_C.z - SK['head'][0][2]) * S
                d = tgt - head_p
                fl = fwd(facing_h)
                yaw_t = wrap180(math.degrees(math.atan2(d.y, d.x)) - facing_h)
                pitch_t = -math.degrees(math.atan2(d.z, max(1e-4, Vector((d.x, d.y)).length)))
                # target nearly straight below/above the head: yaw is ill-defined -> hold it
                kh = clamp((Vector((d.x, d.y)).length - 0.06) / 0.22)
                prev_y = self.aim['head'].x[0] if self.aim['head'].x else yaw_t
                yaw_t = wrap180(prev_y + wrap180(yaw_t - prev_y) * kh)
                yaw_t = clamp(yaw_t, -110.0, 110.0)          # humans don't look through their own back
                # steep down/up looks: yaw matters less, keep the chest from twisting
                steep = clamp((abs(pitch_t) - 55.0) / 25.0)
                yaw_t *= (1.0 - 0.6 * steep)
                sp = max(0.2, self.look_speed(t))
                def follow(name, tau):
                    lg = self.aim[name]
                    if lg.x is not None:          # keep filter state in (-180, 180] and chase the short way round
                        if lg.x[0] > 180:
                            lg.x[0] -= 360
                        elif lg.x[0] < -180:
                            lg.x[0] += 360
                        tgt_y = lg.x[0] + wrap180(yaw_t - lg.x[0])
                    else:
                        tgt_y = yaw_t
                    return lg((tgt_y, pitch_t), dt, tau)
                ey = follow('eyes', 0.02 / sp)
                hd = follow('head', 0.14 / sp)
                ch = follow('chest', 0.32 / sp)
                ey = (wrap180(ey[0]), ey[1])
                hd = (wrap180(hd[0]), hd[1])
                ch = (wrap180(ch[0]), ch[1])
                ch_y = clamp(ch[0] * 0.3, -30, 30)
                hd_y = clamp(hd[0] - ch_y, -75, 75)
                loc['chest'][2] += lw * ch_y * 0.6
                loc['spine'][2] += lw * ch_y * 0.4
                loc['neck'][2] += lw * hd_y * 0.35
                loc['head'][2] += lw * hd_y * 0.65
                loc['neck'][0] += lw * clamp(hd[1], -40, 50) * 0.4
                loc['head'][0] += lw * clamp(hd[1], -40, 50) * 0.6
                eyes = (lw * clamp(wrap180(ey[0] - hd[0] * 0.95) / 28.0, -1, 1),
                        lw * clamp(-(ey[1] - hd[1] * 0.95) / 22.0, -1, 1))
        for b in FK_CHAIN:
            basis[b] = self._conj(b, _q_local(*loc[b])).to_matrix().to_4x4()
        for s in 'LR':
            sh = self.shrug[s](t)
            basis['shoulder.' + s] = self._conj('shoulder.' + s, Quaternion((0, -1, 0), side_sign(s) * sh * 9 * DEG)).to_matrix().to_4x4()
        W = self.fk(dict(basis))
        # ---------------- feet controls
        for s in 'LR':
            x, y, zz, yaw, pitch = feet[s]
            R = yaw_quat(yaw) @ Quaternion((1, 0, 0), -pitch * DEG)
            # pitch rotates about the ball of the foot when the heel lifts (toe stays planted)
            M = Matrix.Translation((x, y, zz)) @ R.to_matrix().to_4x4() @ self.rest['foot_ik.' + s].to_3x3().to_4x4()
            if pitch != 0:
                # rotate about the ball when the heel lifts, about the heel at heel-strike
                ball = Vector((0, -0.09 * S, -0.06 * S)) if pitch < 0 else Vector((0, 0.05 * S, -0.07 * S))
                pv = R @ ball
                M = Matrix.Translation(Vector((x, y, zz)) + (Vector(yaw_quat(yaw) @ ball) - pv)) @ R.to_matrix().to_4x4() @ \
                    self.rest['foot_ik.' + s].to_3x3().to_4x4()
            basis['foot_ik.' + s] = self.rest['foot_ik.' + s].inverted() @ M
        # ---------------- hands
        hand_world = {}
        for s in 'LR':
            sa, sb, u = self.hands[s].state(t)
            Ma = self.resolve_hand(s, sa, t, W, world)
            Mb = self.resolve_hand(s, sb, t, W, world)
            M = blend_matrix(Ma, Mb, u)
            arc = (sb or {}).get('arc', 0.0) if isinstance(sb, dict) else 0.0
            if arc and 0 < u < 1:
                d = (Mb.translation - Ma.translation).length
                M.translation += Vector((0, 0, 1)) * arc * d * math.sin(math.pi * u)
            # reach clamp
            shp = W['upper_arm.' + s].translation
            v = M.translation - shp
            if v.length > self.arm_len * 0.995:
                self.notes.append((f, 'hand %s beyond reach by %.3f m' % (s, v.length - self.arm_len)))
                M.translation = shp + v.normalized() * self.arm_len * 0.995
            hand_world[s] = M
            basis['hand_ik.' + s] = self.rest['hand_ik.' + s].inverted() @ self._to_bone(M, 'hand_ik.' + s)
            # fingers
            g = clamp(self.grip[s](t), 0, 1.2)
            sp = self.spread[s](t)
            fit = self.held_fit(s, t, world)
            for fn in ('index', 'middle', 'ring', 'pinky'):
                for i in (1, 2):
                    bn = 'f_%s.%02d.%s' % (fn, i, s)
                    if fit:
                        a = fit[(fn, i)] * min(g, 1.0)
                    else:
                        a = g * (68 if i == 1 else 78) * DEG
                    spread_a = 0.0
                    if i == 1:
                        k = {'index': -1.0, 'middle': -0.3, 'ring': 0.3, 'pinky': 1.0}[fn]
                        spread_a = k * sp * 9 * DEG * side_sign(s)
                    q = Quaternion((1, 0, 0), a) @ Quaternion((0, 0, 1), spread_a)
                    basis[bn] = q.to_matrix().to_4x4()
            for i in (1, 2):
                bn = 'thumb.%02d.%s' % (i, s)
                if fit:
                    a = fit[('thumb', i)] * min(g, 1.0)
                else:
                    a = g * (35 if i == 1 else 45) * DEG
                basis[bn] = Quaternion((1, 0, 0), a).to_matrix().to_4x4()
        # ---------------- secondary springs
        W = self.fk(dict(basis))
        for b, sp in self.springs.items():
            M = W[b]
            head = M.translation
            rest_dir = M.col[1].to_3d().normalized()
            L = self.length[b]
            tip = sp(head + rest_dir * L, dt)
            d = (tip - head).normalized()
            q = rest_dir.rotation_difference(d)
            # convert world-delta into the bone's local frame
            Mrot = M.to_quaternion()
            ql = Mrot.inverted() @ q @ Mrot
            basis[b] = ql.to_matrix().to_4x4()
        W = self.fk(dict(basis))
        # ---------------- face
        for k in FACE_KEYS:
            props[k] = self.face[k](t)
        if any(v != v for v in eyes):
            eyes = (0.0, 0.0)
        props['look_x'] = clamp(props['look_x'] + eyes[0], -1, 1)
        props['look_y'] = clamp(props['look_y'] + eyes[1], -1, 1)
        if self.auto_blink:
            bl = self._auto_blink(t)
            for k in ('blink_L', 'blink_R'):
                props[k] = max(props[k], bl)
        # ---------------- store
        self.out[f] = (basis, props)
        Wd = dict(W)
        for s in 'LR':
            Wd['hand_target.' + s] = hand_world[s]
            Wd['ankle.' + s] = Matrix.Translation(feet[s][:3])
        Wd['head_center'] = Matrix.Translation(W['head'] @ Vector((0, (HEAD_C.z - SK['head'][0][2]) * S, 0)))
        Wd['facing'] = facing
        self.world[f] = Wd
        return Wd

    def _to_bone(self, M_hand, bone):
        """M_hand is in 'hand convention' (Y fingers, Z palm). The hand_ik bone rest has the same
        convention by construction (Y along the bone, Z = palm normal via align_roll)."""
        return M_hand

    def _auto_blink(self, t):
        if not self.blink_times:
            r = rng(sum(map(ord, self.name)))
            x = r.uniform(0.6, 1.8)
            while x < 600:
                self.blink_times.append(x)
                x += r.uniform(2.2, 4.6)
        v = 0.0
        for bt in self.blink_times:
            if bt - 0.1 < t < bt + 0.2:
                u = (t - bt) / 0.17
                v = max(v, 1 - abs(u * 2 - 0.6) / 0.6 if 0 <= u <= 1 else 0)
        return clamp(v)

    # ================================================================ hand spec resolution
    def body_axes(self, W, rel, s):
        """(origin, out, fwd, up) for a body-relative hand spec."""
        if rel == 'shoulder':
            M = W['upper_arm.' + s]
            o = M.translation
            C = W['chest']
        elif rel == 'hips':
            C = W['hips']
            o = C.translation
        elif rel == 'head':
            C = W['head']
            o = C @ Vector((0, (HEAD_C.z - SK['head'][0][2]) * self.S, 0))
        else:
            C = W['chest']
            o = C.translation
        left, up, fw = C.col[0].to_3d().normalized(), C.col[1].to_3d().normalized(), C.col[2].to_3d().normalized()
        out = left * side_sign(s)
        return o, out, fw, up

    def resolve_hand(self, s, spec, t, W, world):
        if spec is None:
            spec = {'preset': 'relaxed'}
        if 'blend' in spec:
            a, b, u = spec['blend']
            return blend_matrix(self.resolve_hand(s, a, t, W, world), self.resolve_hand(s, b, t, W, world), u)
        if 'preset' in spec:
            base = dict(HAND_PRESETS[spec['preset']])
            base.update({k: v for k, v in spec.items() if k != 'preset'})
            spec = base
        if 'rel' in spec:
            o, out, fw, up = self.body_axes(W, spec['rel'], s)
            S = self.S
            p = o + (out * spec['pos'][0] + fw * spec['pos'][1] + up * spec['pos'][2]) * S
            fi = out * spec['fingers'][0] + fw * spec['fingers'][1] + up * spec['fingers'][2]
            pa = out * spec['palm'][0] + fw * spec['palm'][1] + up * spec['palm'][2]
            return hand_matrix(p, fi, pa)
        if 'world' in spec:
            return hand_matrix(spec['world'], spec['fingers'], spec['palm'])
        if 'object' in spec:          # grasp pose around a (possibly moving) object
            Mo = world.object_matrix(spec['object'], t)
            G = world.grip_frame(spec['object'], s, spec, at=spec.get('at'))
            M = Mo @ G
            ap = spec.get('approach', 0.0)
            if ap:
                M = M @ Matrix.Translation((0, -ap * 0.3, -ap))
            return M
        if 'on' in spec:              # hand pinned to a point of a (moving) object, e.g. a door handle
            Mo = world.object_matrix(spec['on'], t)
            R3 = Mo.to_3x3().normalized()
            return hand_matrix(Mo @ Vector(spec['local']), R3 @ Vector(spec['fingers']), R3 @ Vector(spec['palm']))
        if 'twist' in spec:           # palm over a screw cap: pose given in body axes, turned with the cap's twist
            obj = spec['twist']
            Mo = world.object_matrix(obj, t)
            o, out, fw, up = self.body_axes(W, 'chest', s)
            top = Mo @ Vector((0, 0, world.objs[obj].height))
            axis = Mo.col[2].to_3d().normalized()
            q = Quaternion(axis, math.radians(world.twist_angle(obj, t) - spec.get('angle0', 0.0)))

            def B(v):
                return out * v[0] + fw * v[1] + up * v[2]
            return hand_matrix(top + q @ (B(spec.get('offset', (0.031, -0.05, 0.025))) * self.S),
                               q @ B(spec.get('fingers', (-0.5, 0.8, -0.2))), q @ B(spec.get('palm', (0, 0, -1))))
        if 'release_from' in spec:    # back the hand away from an object it just let go of
            obj = spec['release_from']
            Mo = world.object_matrix(obj, t)
            H = world.held_offset(obj, spec.get('idx'))
            d = spec.get('back', 0.07)
            return Mo @ H.inverted() @ Matrix.Translation((0, -0.35 * d, -d))
        if 'hold' in spec:            # place a held object at a point with a given orientation
            obj = spec['hold']
            Ginv = world.held_offset(obj).inverted()
            p = spec['at']
            if isinstance(p, dict):
                o, out, fw, up = self.body_axes(W, p.get('rel', 'chest'), s)
                pv = p['pos']
                P = o + (out * pv[0] + fw * pv[1] + up * pv[2]) * self.S
            else:
                P = Vector(p)
            R = world.hold_orientation(obj, spec, t, self, W, s, P)
            Mo = Matrix.Translation(P) @ R.to_matrix().to_4x4()
            return Mo @ Ginv
        raise ValueError('bad hand spec %r' % spec)

    def held_fit(self, s, t, world):
        obj = world.held_by(self.name, s, t)
        if not obj:
            obj = world.grasp_target(self.name, s, t)
        if not obj:
            return None
        r = world.grip_radius(obj)
        key = (s, round(r, 4))
        if key not in self.grip_fit:
            self.grip_fit[key] = solve_grip(self, s, r)
        return self.grip_fit[key]


# ==================================================================== grip solver
GRIP_CY = 0.060      # cylinder centre along the hand (from the wrist, metres @ scale 1)
GRIP_PAD = 0.0125    # palm half-thickness


def grip_center(S, r):
    return Vector((0.0, GRIP_CY * S, GRIP_PAD * S + r + 0.001 * S))


def solve_grip(perf, s, r):
    """Curl angles (rad) per finger segment so each finger wraps a cylinder of radius r whose
    axis runs along the hand's X axis, palm touching it. Brute force on rest geometry."""
    S = perf.S
    hand_rest = perf.rest['hand.' + s]
    Hinv = hand_rest.inverted()
    C = grip_center(S, r)
    out = {}
    chains = [(fn, ['f_%s.01.%s' % (fn, s), 'f_%s.02.%s' % (fn, s)]) for fn in ('index', 'middle', 'ring', 'pinky')]
    chains.append(('thumb', ['thumb.01.' + s, 'thumb.02.' + s]))
    from .character import FINGER_R

    def dist(p):
        return math.hypot(p.y - C.y, p.z - C.z)
    for fn, (b1, b2) in chains:
        m1 = Hinv @ perf.rest[b1]
        m2 = Hinv @ perf.rest[b2]
        L1, L2 = perf.length[b1], perf.length[b2]
        best = None
        rad = r + FINGER_R * S * 0.95
        for i in range(0, 61):
            a1 = math.radians(i * 1.8)
            R1 = m1 @ Quaternion((1, 0, 0), a1).to_matrix().to_4x4()
            j = R1 @ Vector((0, L1, 0))
            for k in range(0, 61):
                a2 = math.radians(k * 1.8)
                R2 = R1 @ (m1.inverted() @ m2) @ Quaternion((1, 0, 0), a2).to_matrix().to_4x4()
                tip = R2 @ Vector((0, L2, 0))
                mid1 = R1 @ Vector((0, L1 * 0.5, 0))
                mid2 = R2 @ Vector((0, L2 * 0.5, 0))
                pen = sum(max(0.0, rad - dist(p)) ** 2 for p in (j, tip, mid1, mid2))
                gap = (dist(tip) - rad) ** 2 + 0.3 * (dist(j) - rad) ** 2
                cost = gap + 30 * pen + 1e-6 * (a1 + a2)
                if best is None or cost < best[0]:
                    best = (cost, a1, a2)
        out[(fn, 1)], out[(fn, 2)] = best[1], best[2]
    return out
