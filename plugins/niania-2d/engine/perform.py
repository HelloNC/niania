"""Turns timeline 'performance' events + dialogue lip-sync into per-frame character state."""
import math, random
from geo import smooth, lerp
from puppet import EXPR, POSES


class Chan:
    """scalar or vector channel; events (t, target, dur) blend from the value at event time."""

    def __init__(self, default, events):
        self.default = default
        self.ev = sorted(events, key=lambda e: e[0])

    @staticmethod
    def _mix(a, b, u):
        if isinstance(a, dict):
            return {k: lerp(a[k], b[k], u) for k in a}
        if isinstance(a, (tuple, list)):
            return tuple(lerp(x, y, u) for x, y in zip(a, b))
        return lerp(a, b, u)

    def __call__(self, t):
        cf, ct, cto, cd = self.default, -1e9, self.default, 1e-6
        for et, tv, dur in self.ev:
            if et > t:
                break
            v_at = self._mix(cf, cto, smooth((et - ct) / cd))
            cf, ct, cto, cd = v_at, et, tv, max(dur, 1e-3)
        return self._mix(cf, cto, smooth((t - ct) / cd))


def expr_of(name_or_dict):
    if isinstance(name_or_dict, dict):
        return dict(EXPR['neutral'], **name_or_dict)
    return dict(EXPR.get(name_or_dict, EXPR['neutral']))


def pose_vec(name):
    el, wr, hand = POSES.get(name, POSES['rest'])
    return (el[0], el[1], wr[0], wr[1])


class Performer:
    def __init__(self, cid, tl, lines, fps):
        ev = [e for e in tl.get('performance', []) if e.get('char') == cid]
        self.id = cid
        self.fps = fps
        g = lambda do: [e for e in ev if e.get('do') == do]
        base = tl['cast'][cid].get('expression', 'neutral')
        self.expr = Chan(expr_of(base), [(e['t'], expr_of(e['set']), e.get('dur', 0.3)) for e in g('expr')])
        self.look = Chan((0.0, 0.0), [(e['t'], (e.get('x', 0.0), e.get('y', 0.0)), e.get('dur', 0.12)) for e in g('look')])
        self.yaw = Chan(0.0, [(e['t'], e.get('yaw', 0.0), e.get('dur', 0.4)) for e in g('turn')])
        self.tilt = Chan(0.0, [(e['t'], math.radians(e.get('deg', 0.0)), e.get('dur', 0.4)) for e in g('tilt')])
        self.arms = {}
        self.hands = {}
        self.wave = {'L': [], 'R': []}
        for side in ('L', 'R'):
            gs = [e for e in g('gesture') if e.get('side', 'R') == side]
            self.arms[side] = Chan(pose_vec('rest'), [(e['t'], pose_vec(e.get('pose', 'rest')), e.get('dur', 0.45)) for e in gs])
            self.hands[side] = sorted([(e['t'] + e.get('dur', 0.45) * 0.5, POSES.get(e.get('pose', 'rest'), POSES['rest'])[2])
                                       for e in gs])
            self.wave[side] = [(e['t'], e.get('hold', 2.0)) for e in gs if e.get('pose') == 'wave']
        self.nods = [(e['t'], e.get('n', 1)) for e in g('nod')]
        self.shakes = [(e['t'], e.get('n', 2)) for e in g('shake')]
        r = random.Random(hash(cid) % 9973)
        self.blinks = [e['t'] for e in g('blink')]
        tt = r.uniform(0.6, 1.8)
        while tt < tl['duration']:
            self.blinks.append(tt)
            tt += r.uniform(2.6, 4.6)
        self.lines = [ln for ln in lines.get('dialogue', []) if ln.get('char') == cid]

    def mouth(self, t):
        for ln in self.lines:
            i = int((t - ln['start']) * self.fps)
            env = ln.get('env', [])
            if 0 <= i < len(env):
                a = env[max(0, i - 1):i + 2]
                return max(0.0, min(1.0, (sum(a) / len(a) - 0.08) * 1.5))
        return 0.0

    def state(self, t):
        e = self.expr(t)
        blink = 0.0
        for b in self.blinks:
            d = t - b
            if 0 <= d < 0.16:
                blink = max(blink, 1 - abs(d - 0.08) / 0.08)
        m = self.mouth(t)
        talking = m > 0.02
        nod = 1.6 * math.sin(t * 2.3) * m
        for t0, n in self.nods:
            d = t - t0
            if 0 <= d < 0.35 * n:
                nod += 9 * math.sin(math.pi * d / 0.35)
        yaw = self.yaw(t)
        for t0, n in self.shakes:
            d = t - t0
            if 0 <= d < 0.3 * n:
                yaw += 0.25 * math.sin(2 * math.pi * d / 0.3)
        arms = {}
        for side in ('L', 'R'):
            v = self.arms[side](t)
            for t0, hold in self.wave[side]:
                if t0 + 0.3 < t < t0 + 0.3 + hold:
                    v = (v[0], v[1], v[2] + 28 * math.sin((t - t0) * 11), v[3])
            hand = 'none'
            for th, hs in self.hands[side]:
                if t >= th:
                    hand = hs
            arms[side] = ((v[0], v[1]), (v[2], v[3]), hand if v[3] < 600 or hand == 'mug' else 'none')
        return dict(expr=e, blink=blink, mouth=m, look=self.look(t), yaw=yaw,
                    tilt=self.tilt(t) + math.radians(1.6 * math.sin(t * 0.9) + (1.2 * m if talking else 0)),
                    nod=nod, sway=math.sin(t * 1.3), breath=2.0 * math.sin(2 * math.pi * t / 3.6), arms=arms)
