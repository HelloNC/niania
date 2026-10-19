"""Frame renderer: timeline.json -> frames/f%05d.png (parallel, Pillow only).

  python render.py <project> [--frames 10,40] [--shot NAME] [--out DIR] [--pct 100] [--jobs N] [--ss 2]
"""
import json, math, os, sys, time
from multiprocessing import Pool
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geo import Canvas, smooth, lerp            # noqa: E402
from puppet import Look, draw_character         # noqa: E402
from perform import Performer                   # noqa: E402
import scene                                     # noqa: E402

G = {}


def init(project, pct, ss):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    W, H = tl.get('resolution', [1080, 1920])
    W, H = int(W * pct / 100), int(H * pct / 100)
    lp = os.path.join(project, 'audio', 'lines.json')
    lines = json.load(open(lp)) if os.path.exists(lp) else {'narration': [], 'dialogue': []}
    fps = tl.get('fps', 30)
    G.update(tl=tl, W=W, H=H, SS=ss, project=project, fps=fps, lines=lines,
             looks={k: Look(v) for k, v in tl.get('cast', {}).items()},
             perf={k: Performer(k, tl, lines, fps) for k in tl.get('cast', {})},
             post=scene.Post(W, H, tl.get('style', {})), bgs={},
             caps=scene.build_captions(lines, tl.get('captions', {}))[0])


def shot_at(t):
    shots = G['tl']['shots']
    for i, s in enumerate(shots):
        if s['start'] <= t < s['end']:
            return i, s
    return len(shots) - 1, shots[-1]


def anim(v0, v1, u):
    return v0 if v1 is None else lerp(v0, v1, u)


def render_frame(f):
    tl, W, H, SS = G['tl'], G['W'], G['H'], G['SS']
    t = f / G['fps']
    i, shot = shot_at(t)
    u = (t - shot['start']) / max(1e-6, shot['end'] - shot['start'])
    ue = smooth(u)
    w, h = W * SS, H * SS
    # camera: zoom about the frame centre + pan (fractions of the frame)
    cam = shot.get('cam', {})
    z0, z1 = (cam.get('zoom', [1.0, 1.0]) + [None])[:2]
    zoom = anim(z0, z1, ue)
    pans = cam.get('pan', [[0, 0], [0, 0]])
    px = anim(pans[0][0], pans[-1][0], ue) * w
    py = anim(pans[0][1], pans[-1][1], ue) * h
    sh = cam.get('shake', 0.0)
    if sh:
        px += sh * w * 0.004 * math.sin(t * 13.1) * math.sin(t * 3.7)
        py += sh * h * 0.004 * math.sin(t * 11.3 + 1) * math.sin(t * 2.9)
    key = shot['name']
    if key not in G['bgs']:
        G['bgs'][key] = scene.background(shot.get('bg', tl.get('bg', {'type': 'radial'})), int(w * 1.0), int(h * 1.0),
                                         G['project'], seed=i + 1)
    bg = G['bgs'][key]
    if abs(zoom - 1) > 1e-4 or px or py:
        bz = max(zoom, 1.0) * (1 + 2 * (abs(px) / w + abs(py) / h))
        big = bg.resize((int(w * bz), int(h * bz)), Image.BILINEAR)
        x0 = (big.width - w) / 2 - px * bz / max(zoom, 1e-6) * 0.6
        y0 = (big.height - h) / 2 - py * bz / max(zoom, 1e-6) * 0.6
        img = big.crop((int(x0), int(y0), int(x0) + w, int(y0) + h))
    else:
        img = bg.copy()
    # characters
    unit = min(W, H) / 864 * SS
    placed = []
    for c in shot.get('chars', []):
        to = c.get('to', {})
        cx = anim(c.get('x', 0.5), to.get('x'), ue)
        cy = anim(c.get('y', 0.72), to.get('y'), ue)
        sc = anim(c.get('scale', 1.0), to.get('scale'), ue)
        ent = c.get('enter')
        if ent:
            k = 1 - smooth((t - shot['start']) / c.get('enter_dur', 0.5))
            cx += {'left': -0.7, 'right': 0.7}.get(ent, 0) * k
            cy += {'bottom': 0.6}.get(ent, 0) * k
        X = (cx * w - w / 2) * zoom + w / 2 + px
        Y = (cy * h - h / 2) * zoom + h / 2 + py
        placed.append((c.get('z', sc), c, X, Y, sc * unit * zoom))
    for _, c, X, Y, s in sorted(placed, key=lambda p: p[0]):
        cv = Canvas(img, s, X, Y, flip=c.get('flip', False))
        draw_character(cv, G['looks'][c['id']], G['perf'][c['id']].state(t))
    out = img.resize((W, H), Image.LANCZOS)
    out = G['post'].apply(out, f)
    shots = tl['shots']
    nxt = shots[i + 1].get('in') if i + 1 < len(shots) else None
    out = scene.transition(out, shot, nxt, t)
    # screen-space graphics (supersampled layer)
    gs = [g for g in tl.get('graphics', []) + shot.get('graphics', []) if g['t'][0] <= t < g['t'][1]]
    if gs:
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        for g in gs:
            scene.draw_graphic(layer, g, t, W, H, SS, G['project'])
        layer = layer.resize((W, H), Image.LANCZOS)
        out = out.convert('RGBA')
        out.alpha_composite(layer)
        out = out.convert('RGB')
    capcfg = dict(tl.get('captions', {}), **shot.get('captions', {}))
    scene.draw_captions(out, G['caps'], t, capcfg, W, H, G['project'])
    # final fade-out
    fo = tl.get('fade_out', 0.5)
    if fo and t > tl['duration'] - fo:
        k = max(0.0, (tl['duration'] - t) / fo)
        out = Image.eval(out, lambda v: int(v * k))
    out.save(os.path.join(G['out'], 'f%05d.png' % f))
    return f


def _w_init(project, pct, ss, out):
    init(project, pct, ss)
    G['out'] = out


def main():
    a = sys.argv[1:]
    project = os.path.abspath(a[0])
    opt = {a[i]: a[i + 1] for i in range(1, len(a) - 1) if a[i].startswith('--')}
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    fps = tl.get('fps', 30)
    n = int(round(tl['duration'] * fps))
    if '--frames' in opt:
        frames = [int(x) for x in opt['--frames'].split(',')]
    elif '--shot' in opt:
        names = opt['--shot'].split(',')
        frames = []
        for s in tl['shots']:
            if s['name'] in names:
                frames += list(range(int(round(s['start'] * fps)), int(round(s['end'] * fps))))
    else:
        frames = list(range(n))
    out = opt.get('--out', os.path.join(project, 'frames'))
    os.makedirs(out, exist_ok=True)
    pct, ss = int(opt.get('--pct', 100)), int(opt.get('--ss', 2))
    jobs = int(opt.get('--jobs', max(1, (os.cpu_count() or 2) - 1)))
    t0 = time.time()
    if jobs == 1 or len(frames) < 4:
        _w_init(project, pct, ss, out)
        for f in frames:
            render_frame(f)
    else:
        with Pool(jobs, initializer=_w_init, initargs=(project, pct, ss, out)) as pool:
            for k, _ in enumerate(pool.imap_unordered(render_frame, frames, chunksize=4)):
                if k % 60 == 0:
                    print('rendered %d/%d' % (k, len(frames)), flush=True)
    print('RENDER DONE %d frames in %.1fs -> %s' % (len(frames), time.time() - t0, out))


if __name__ == '__main__':
    main()
