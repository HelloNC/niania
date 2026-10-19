"""Keyframe tracks evaluated by the engine itself (not Blender f-curves).

Every animated quantity is a Track: sorted keys (t, value, ease). Segments with
ease='auto' use monotone cubic Hermite through neighbouring keys, which keeps
velocity continuous across chained moves without overshoot; named eases
('inout', 'snap', 'back', 'anticip', ...) shape a single segment explicitly.
"""
from .util import ease as _ease


def _is_vec(v):
    return isinstance(v, (tuple, list))


class Track:
    def __init__(self, default):
        self.default = tuple(default) if _is_vec(default) else float(default)
        self.keys = []          # [t, value, ease]

    # --------------------------------------------------------------- editing
    def set(self, t, value, ease='auto'):
        value = tuple(value) if _is_vec(value) else float(value)
        for k in self.keys:
            if abs(k[0] - t) < 1e-6:
                k[1], k[2] = value, ease
                return
        self.keys.append([t, value, ease])
        self.keys.sort(key=lambda k: k[0])

    def move(self, t0, dur, value, ease='auto', hold_from=True):
        """Transition from whatever value is current at t0 to `value` at t0+dur.
        Keys strictly inside (t0, t0+dur] are superseded."""
        if t0 <= 1e-6 and dur <= 0.05:          # initial state: no transition from the default
            self.keys = [k for k in self.keys if k[0] > dur + 1e-6]
            self.set(0.0, value, 'auto')
            return
        t1 = t0 + max(dur, 1e-3)
        cur = self(t0)
        self.keys = [k for k in self.keys if not (t0 + 1e-6 < k[0] <= t1 + 1e-6)]
        if hold_from:
            self.set(t0, cur, 'auto')
        self.set(t1, value, ease)

    def add(self, t0, dur, delta, ease='auto'):
        cur = self(t0 + dur)
        if _is_vec(cur):
            self.move(t0, dur, tuple(c + d for c, d in zip(cur, delta)), ease)
        else:
            self.move(t0, dur, cur + delta, ease)

    def pulse(self, t0, dur, peak, ease_in='out', ease_out='inout', peak_at=0.4):
        """Go to `peak` and come back to the current value (for nods, bounces...)."""
        base = self(t0)
        self.move(t0, dur * peak_at, peak, ease_in)
        self.move(t0 + dur * peak_at, dur * (1 - peak_at), base, ease_out)

    # --------------------------------------------------------------- evaluation
    def __call__(self, t):
        ks = self.keys
        if not ks:
            return self.default
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        lo, hi = 0, len(ks) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ks[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        t0, v0, _ = ks[lo]
        t1, v1, e = ks[hi]
        u = (t - t0) / (t1 - t0)
        if e != 'auto':
            w = _ease(e, u)
            if _is_vec(v0):
                return tuple(a + (b - a) * w for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * w
        m0, m1 = self._tan(lo), self._tan(hi)
        h = t1 - t0
        u2, u3 = u * u, u * u * u
        h00, h10, h01, h11 = 2 * u3 - 3 * u2 + 1, u3 - 2 * u2 + u, -2 * u3 + 3 * u2, u3 - u2
        if _is_vec(v0):
            return tuple(h00 * a + h10 * h * ma + h01 * b + h11 * h * mb
                         for a, b, ma, mb in zip(v0, v1, m0, m1))
        return h00 * v0 + h10 * h * m0 + h01 * v1 + h11 * h * m1

    def _tan(self, i):
        ks = self.keys
        vec = _is_vec(ks[i][1])
        n = len(ks[i][1]) if vec else 1
        if i == 0 or i == len(ks) - 1:
            return (0.0,) * n if vec else 0.0
        # a named-ease segment on either side ends at rest
        if ks[i][2] != 'auto' or ks[i + 1][2] != 'auto':
            return (0.0,) * n if vec else 0.0
        ta, tb, tc = ks[i - 1][0], ks[i][0], ks[i + 1][0]
        a, b, c = ks[i - 1][1], ks[i][1], ks[i + 1][1]
        if not vec:
            a, b, c = (a,), (b,), (c,)
        out = []
        for x, y, z in zip(a, b, c):
            d0, d1 = (y - x) / (tb - ta), (z - y) / (tc - tb)
            if d0 * d1 <= 0:
                out.append(0.0)
            else:
                m = 0.5 * (d0 + d1)
                lim = 3 * min(abs(d0), abs(d1))
                out.append(max(-lim, min(lim, m)))
        return tuple(out) if vec else out[0]


class SpecTrack:
    """Keys whose values are *specs* resolved per frame (e.g. a hand target relative
    to a moving object). Returns (spec_a, spec_b, w) for the caller to blend."""

    def __init__(self, default):
        self.keys = [[0.0, default, 'linear']]

    def move(self, t0, dur, spec, ease='inout'):
        if t0 <= 1e-6 and dur <= 0.05:          # initial state
            self.keys = [[0.0, spec, 'linear']] + [k for k in self.keys if k[0] > dur + 1e-6]
            return
        cur = self.state(t0)
        self.keys = [k for k in self.keys if not (t0 + 1e-6 < k[0] <= t0 + dur + 1e-6)]
        # freeze the in-flight blend at t0 as an explicit key
        self.keys = [k for k in self.keys if k[0] <= t0 + 1e-6]
        if cur[2] not in (0.0, 1.0):
            self.keys.append([t0, {'blend': cur}, 'linear'])
        elif self.keys[-1][0] < t0 - 1e-6:
            self.keys.append([t0, cur[1] if cur[2] >= 1.0 else cur[0], 'linear'])
        self.keys.append([t0 + max(dur, 1e-3), spec, ease])
        self.keys.sort(key=lambda k: k[0])

    def state(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1], ks[0][1], 0.0
        for i in range(len(ks) - 1):
            if ks[i][0] <= t < ks[i + 1][0]:
                u = (t - ks[i][0]) / (ks[i + 1][0] - ks[i][0])
                return ks[i][1], ks[i + 1][1], _ease(ks[i + 1][2], u)
        return ks[-1][1], ks[-1][1], 1.0

    def last_time(self):
        return self.keys[-1][0]
