"""Math, easing, color and noise helpers shared by the whole engine (Blender-side)."""
import math
from mathutils import Vector, Matrix, Quaternion, Euler

DEG = math.pi / 180.0


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, u):
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * u for x, y in zip(a, b))
    return a + (b - a) * u


# ---------------------------------------------------------------- easing
def _back_out(u, s=1.4):
    u -= 1.0
    return 1 + (s + 1) * u ** 3 + s * u ** 2


def _back_in(u, s=1.4):
    return (s + 1) * u ** 3 - s * u ** 2


EASES = {
    'linear': lambda u: u,
    'inout': lambda u: u * u * (3 - 2 * u),
    'inout5': lambda u: u ** 3 * (u * (6 * u - 15) + 10),
    'in': lambda u: u * u,
    'in3': lambda u: u ** 3,
    'out': lambda u: 1 - (1 - u) ** 2,
    'out3': lambda u: 1 - (1 - u) ** 3,
    'snap': lambda u: 1 - (1 - u) ** 4,          # explosive start, long settle
    'back': _back_out,                         # overshoot then settle (follow-through)
    'anticip': _back_in,                       # pull back first (anticipation)
}


def ease(name, u):
    u = clamp(u)
    return EASES.get(name or 'inout', EASES['inout'])(u)


# ---------------------------------------------------------------- orientation
def fwd(theta_deg):
    """Forward vector of a character with facing angle theta (deg, CCW from +X)."""
    a = theta_deg * DEG
    return Vector((math.cos(a), math.sin(a), 0.0))


def right_of(theta_deg):
    f = fwd(theta_deg)
    return Vector((f.y, -f.x, 0.0))


def yaw_quat(theta_deg):
    """Rotation taking the rest pose (facing -Y) to facing angle theta."""
    return Quaternion((0, 0, 1), (theta_deg + 90.0) * DEG)


def body_frame(theta_deg, origin):
    """Matrix whose columns are (right, forward, up) of a character frame."""
    r, f = right_of(theta_deg), fwd(theta_deg)
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = r[i], f[i], (0, 0, 1)[i], origin[i]
    return m


def mat_from_axes(x, y, z, pos):
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], pos[i]
    return m


def hand_matrix(pos, fingers, palm):
    """Hand bone matrix: Y along the fingers, Z out of the palm, X = Y x Z."""
    y = Vector(fingers).normalized()
    z = Vector(palm)
    z = (z - y * z.dot(y)).normalized()
    x = y.cross(z)
    return mat_from_axes(x, y, z, Vector(pos))


def blend_matrix(a, b, u):
    la, ra, _ = a.decompose()
    lb, rb, _ = b.decompose()
    # 'back' eases overshoot past 1: position extrapolates, rotation is clamped for slerp
    return Matrix.LocRotScale(la.lerp(lb, u), ra.slerp(rb, min(1.0, max(0.0, u))), None)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------- color
def srgb(h, alpha=1.0):
    """Hex '#rrggbb' (sRGB) -> linear RGBA tuple."""
    if isinstance(h, (tuple, list)):
        return tuple(h) + ((alpha,) if len(h) == 3 else ())
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (alpha,)


def mix_col(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


# ---------------------------------------------------------------- deterministic noise
def noise1(seed, t, octaves=3):
    """Smooth, deterministic noise in [-1, 1] (sum of incommensurate sines)."""
    v, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        s = seed * 12.9898 + o * 78.233
        ph = math.sin(s) * 43758.5453 % (2 * math.pi)
        fr = (1.0 + o * 1.73) * (0.9 + 0.2 * abs(math.sin(s * 1.7)))
        v += amp * math.sin(t * fr * 2 * math.pi + ph)
        tot += amp
        amp *= 0.5
    return v / tot


def rng(seed):
    import random
    return random.Random(seed)
