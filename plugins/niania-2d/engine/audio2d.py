"""Audio for niania-2d: Kokoro TTS lines (word timings + lip-sync envelopes), procedural SFX /
ambience / music, ducking and the pre-master mix. Runs with a Python that has numpy + soundfile
(+ kokoro for `lines`).

  python audio2d.py lines <project>
  python audio2d.py mix <project>
"""
import json, math, os, re, sys
import numpy as np
import soundfile as sf

SR = 48000


def fft_filter(x, lo=None, hi=None, tilt=0.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo:
        g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi:
        g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if tilt:
        g *= (np.maximum(f, 20) / 1000.0) ** tilt
    return np.fft.irfft(X * g, len(x))


def norm(x, peak=1.0):
    m = np.abs(x).max() if len(x) else 0
    return x * (peak / m) if m > 0 else x


def place(buf, x, t, g=1.0):
    i = int(round(t * SR))
    if i >= len(buf):
        return
    if i < 0:
        x, i = x[-i:], 0
    n = min(len(x), len(buf) - i)
    buf[i:i + n] += g * x[:n]


# ------------------------------------------------------------------ TTS
PIPES = {}


def tts(text, voice, speed):
    from kokoro import KPipeline
    lc = 'b' if voice.startswith('b') else 'a'
    if lc not in PIPES:
        PIPES[lc] = KPipeline(lang_code=lc, repo_id='hexgrad/Kokoro-82M')
    audio, toks, off = [], [], 0.0
    for r in PIPES[lc](text, voice=voice, speed=speed):
        a = np.asarray(r.audio, dtype=np.float32)
        for t in (r.tokens or []):
            if t.start_ts is not None and re.search(r'\w', t.text):
                toks.append((t.text, off + t.start_ts, off + (t.end_ts or t.start_ts + 0.2)))
        audio.append(a)
        off += len(a) / 24000
    y = np.concatenate(audio) if audio else np.zeros(2400, np.float32)
    thr = 0.02 * (np.abs(y).max() or 1)
    i0 = max(0, int(np.argmax(np.abs(y) > thr)) - 720)
    y = y[i0:]
    sh = i0 / 24000
    toks = [(w, s - sh, e - sh) for w, s, e in toks]
    y48 = np.interp(np.arange(len(y) * 2) / 48000, np.arange(len(y)) / 24000, y).astype(np.float32)
    return y48, toks


def map_words(text, show, toks, t0):
    """spoken tokens -> caption words ('show' may replace e.g. 'twenty sixteen' by '2016' with a map)."""
    say = text.split()
    sw, k = [], 0
    for w in say:
        core = re.sub(r'\W', '', w).lower()
        acc, st, en = '', None, None
        while k < len(toks) and len(acc) < len(core):
            acc += re.sub(r'\W', '', toks[k][0]).lower()
            st = toks[k][1] if st is None else st
            en = toks[k][2]
            k += 1
        sw.append((w, st if st is not None else (sw[-1][2] if sw else 0.0), en if en is not None else (sw[-1][2] + 0.2 if sw else 0.2)))
    shown = (show or text).split()
    if len(shown) == len(say):
        groups = [[i] for i in range(len(say))]
    else:   # proportional fallback
        groups = []
        for j in range(len(shown)):
            a = int(j * len(say) / len(shown))
            b = max(a, int((j + 1) * len(say) / len(shown)) - 1)
            groups.append(list(range(a, b + 1)))
    return [{'w': s, 's': round(t0 + sw[g[0]][1], 3), 'e': round(t0 + sw[g[-1]][2], 3)} for s, g in zip(shown, groups)]


def envelope(y, fps):
    hop = SR // fps
    n = int(math.ceil(len(y) / hop))
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) if len(y[i * hop:(i + 1) * hop]) else 0 for i in range(n)])
    if e.max() > 0:
        e = np.clip(e / (e.max() * 0.7), 0, 1)
    return [round(float(v), 3) for v in e]


def cmd_lines(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    au = tl.get('audio', {})
    fps = tl.get('fps', 30)
    d = os.path.join(project, 'audio', 'lines')
    os.makedirs(d, exist_ok=True)
    out = {'narration': [], 'dialogue': [], 'warnings': []}
    nv = au.get('narrator_voice', 'bm_george')
    for kind, items in (('narration', au.get('narration', [])), ('dialogue', au.get('dialogue', []))):
        for i, ln in enumerate(items):
            voice = ln.get('voice', nv if kind == 'narration' else tl['cast'].get(ln.get('char'), {}).get('voice', 'am_michael'))
            speed = ln.get('speed', au.get('narrator_speed', 1.0) if kind == 'narration' else 1.0)
            y, toks = tts(ln['text'], voice, speed)
            fn = os.path.join(d, '%s_%02d.wav' % (kind[:3], i))
            sf.write(fn, y, SR)
            rec = {'id': '%s_%02d' % (kind[:3], i), 'start': ln['t'], 'dur': round(len(y) / SR, 3), 'file': fn,
                   'text': ln['text'], 'voice': voice, 'words': map_words(ln['text'], ln.get('show'), toks, ln['t'])}
            if kind == 'dialogue':
                rec['char'] = ln.get('char')
                rec['env'] = envelope(y, fps)
            out[kind].append(rec)
    allx = sorted(out['narration'] + out['dialogue'], key=lambda x: x['start'])
    for a, b in zip(allx[:-1], allx[1:]):
        if a['start'] + a['dur'] > b['start'] - 0.1:
            out['warnings'].append('"%s..." (ends %.2f) overlaps the next line (starts %.2f)' %
                                   (a['text'][:30], a['start'] + a['dur'], b['start']))
    if allx and allx[-1]['start'] + allx[-1]['dur'] > tl['duration']:
        out['warnings'].append('last line ends after the video (%.2f s)' % (allx[-1]['start'] + allx[-1]['dur']))
    json.dump(out, open(os.path.join(project, 'audio', 'lines.json'), 'w'), indent=1)
    for n in allx:
        print('%-8s %6.2f-%6.2f  %s' % (n['id'], n['start'], n['start'] + n['dur'], n['text'][:60]))
    for w in out['warnings']:
        print('WARNING', w)


# ------------------------------------------------------------------ procedural sound library
def sfx(kind, seed=0):
    r = np.random.default_rng(seed)

    def tt(d):
        return np.arange(int(d * SR)) / SR
    if kind == 'pop':
        t = tt(0.15)
        return np.sin(2 * np.pi * (300 + 900 * np.exp(-t / 0.01)) * t) * np.exp(-t / 0.03)
    if kind == 'click':
        x = np.zeros(int(0.03 * SR)); x[0] = 1
        return norm(fft_filter(x, 1800, 6000) * np.exp(-tt(0.03) * 220))
    if kind in ('chime', 'ding'):
        t = tt(1.2)
        f0 = 880 if kind == 'ding' else 660
        return sum(np.sin(2 * np.pi * f0 * m * t) * g for m, g in ((1, 1), (2.01, 0.4), (3.02, 0.2))) * np.exp(-t * 3) * 0.5
    if kind in ('beep', 'alert'):
        t = tt(0.25 if kind == 'beep' else 0.3)
        f = (1000, 1000) if kind == 'beep' else (622, 830)
        e = np.minimum(1, t / 0.01) * np.minimum(1, (t[-1] - t) / 0.03)
        return (0.6 * np.sin(2 * np.pi * f[0] * t) + 0.4 * np.sin(2 * np.pi * f[1] * t)) * e
    if kind in ('whoosh', 'swoosh'):
        n = int(0.7 * SR)
        x = r.standard_normal(n)
        out = np.zeros(n)
        for i in range(0, n, 1024):
            u = i / n
            fc = 300 + 3500 * math.sin(math.pi * u) ** 2
            out[i:i + 1024] = fft_filter(x[i:i + 1024], fc * 0.5, fc * 1.8)
        return norm(out * np.sin(np.pi * tt(0.7)[:n] / 0.7) ** 2)
    if kind == 'thunder':
        t = tt(3.0)
        x = fft_filter(r.standard_normal(len(t)), 25, 500)
        return norm(x * (1 - np.exp(-t * 25)) * np.exp(-t * 1.1))
    if kind == 'heartbeat':
        t = tt(0.5)
        th = lambda d: np.sin(2 * np.pi * (52 - 20 * (t - d)) * (t - d)) * np.exp(-np.maximum(t - d, 0) * 26) * (t >= d)
        return norm(th(0) + 0.65 * th(0.24))
    if kind == 'boom':
        t = tt(3.0)
        f = 52 * np.exp(-t * 0.9) + 26
        return norm(np.tanh(2.2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.4)))
    if kind == 'typing':
        x = np.zeros(int(1.5 * SR))
        for k in range(18):
            c = sfx('click', seed + k)
            place(x, c, k * 0.08 + r.uniform(0, 0.03), r.uniform(0.4, 1))
        return norm(x)
    if kind == 'paper':
        return norm(fft_filter(r.standard_normal(int(0.4 * SR)), 1500, 8000) * np.exp(-tt(0.4) * 8))
    raise ValueError('unknown sfx ' + kind)


def ambience(kind, n, seed=5):
    r = np.random.default_rng(seed)
    t = np.arange(n) / SR
    if kind == 'rain':
        x = norm(fft_filter(r.standard_normal(n), 900, 9000, -0.3), 0.35)
        drops = np.zeros(n)
        idx = r.integers(0, n, max(1, n // 300))
        drops[idx] = r.uniform(0.3, 1, len(idx))
        return x + norm(fft_filter(drops, 1500, 7000), 0.25)
    if kind == 'wind':
        return norm(fft_filter(r.standard_normal(n), 60, 700), 0.45) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.11 * t))
    if kind == 'city':
        return norm(fft_filter(r.standard_normal(n), 80, 1200), 0.3) + 0.02 * np.sin(2 * np.pi * 60 * t)
    if kind == 'cabin':
        return norm(fft_filter(r.standard_normal(n), 40, 260), 0.4) + norm(fft_filter(r.standard_normal(n), 2500, 9000), 0.05)
    if kind == 'office':
        x = norm(fft_filter(r.standard_normal(n), 100, 3000, -0.5), 0.12)
        for k in range(int(n / SR / 4)):
            place(x, sfx('click', k) * 0.2, r.uniform(0, n / SR))
        return x
    # room tone
    return norm(fft_filter(r.standard_normal(n), 40, 700), 0.15)


def music(kind, n, seed=9):
    t = np.arange(n) / SR
    if kind in ('tension', 'drone'):
        x = sum(g * sum(np.sin(h * 2 * np.pi * 55 * m * t) / h for h in range(1, 6)) for m, g in ((1, .5), (1.5, .22), (2, .18), (1.189, .12)))
        x = fft_filter(x, None, 420) * (0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t))
        if kind == 'tension':
            x *= 0.6 + 0.4 * np.clip(np.sin(2 * np.pi * t / 0.92), 0, 1) ** 3
        return norm(x, 0.6)
    if kind in ('warm_pad', 'gentle'):
        chords = [[53, 57, 60, 64], [57, 60, 64, 67], [50, 57, 60, 64, 69], [46, 53, 57, 62]]
        bar = 3.75
        x = np.zeros(n)
        for i in range(int(n / SR / bar) + 2):
            for k, m in enumerate(chords[i % 4]):
                f = 440 * 2 ** ((m - 69) / 12)
                t0 = i * bar
                seg = (t >= t0 - 0.5) & (t < t0 + bar + 1.5)
                tt = t[seg] - t0
                e = np.clip((tt + 0.5) / 1.4, 0, 1) * np.clip((bar + 1.5 - tt) / 1.6, 0, 1)
                x[seg] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * e * (0.5 if k == 0 else 0.3)
        return norm(fft_filter(x, 60, 1800), 0.6)
    if kind == 'upbeat':
        bpm = 112
        beat = 60 / bpm
        x = np.zeros(n)
        notes = [60, 64, 67, 72, 67, 64, 62, 65]
        for k in range(int(n / SR / beat)):
            t0 = k * beat
            kick = np.sin(2 * np.pi * (55 + 60 * np.exp(-np.arange(int(0.2 * SR)) / SR * 30)) * np.arange(int(0.2 * SR)) / SR) * \
                np.exp(-np.arange(int(0.2 * SR)) / SR * 14)
            if k % 2 == 0:
                place(x, kick, t0, 0.8)
            m = notes[k % len(notes)]
            tt = np.arange(int(beat * SR)) / SR
            place(x, np.sin(2 * np.pi * 440 * 2 ** ((m - 69) / 12) * tt) * np.exp(-tt * 6) * 0.3, t0)
        return norm(x, 0.6)
    return np.zeros(n)


def cmd_mix(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    au = tl.get('audio', {})
    n = int(tl['duration'] * SR)
    lp = os.path.join(project, 'audio', 'lines.json')
    lines = json.load(open(lp)) if os.path.exists(lp) else {'narration': [], 'dialogue': []}
    voice = np.zeros(n)
    for ln in lines['narration'] + lines['dialogue']:
        y, sr = sf.read(ln['file'])
        y = y.mean(1) if y.ndim > 1 else y
        place(voice, norm(y, 0.9), ln['start'])
    voice = fft_filter(voice, 70)
    fx = np.zeros(n)
    whooshes = 0
    for k, e in enumerate(au.get('sfx', [])):
        if e['type'] in ('whoosh', 'swoosh'):
            whooshes += 1
        place(fx, norm(sfx(e['type'], k)), e['t'], e.get('gain', 0.6))
    amb = np.zeros(n)
    for a in ([au['ambience']] if isinstance(au.get('ambience'), str) else au.get('ambience') or []):
        if a and a != 'none':
            amb += ambience(a, n)
    mus = music(au.get('music', 'none'), n) if au.get('music', 'none') != 'none' else np.zeros(n)
    # silence windows (e.g. a hard cut to black)
    for s0, s1 in au.get('silence', []):
        i0, i1 = int(s0 * SR), int(s1 * SR)
        amb[i0:i1] = 0
        mus[i0:i1] = 0
    venv = np.convolve(np.abs(voice), np.ones(2400) / 2400, mode='same')
    act = np.clip(venv / (0.25 * (venv.max() or 1)), 0, 1)
    act = np.convolve(act, np.ones(9600) / 9600, mode='same')
    duck_db = au.get('duck_db', -12.0)
    duck = 10 ** ((duck_db * np.clip(act * 1.5, 0, 1)) / 20)
    g = au.get('gains', {})
    stems = {'voice': voice * g.get('voice', 1.0), 'sfx': fx * g.get('sfx', 0.55),
             'ambience': amb * g.get('ambience', 0.25) * 10 ** ((-5 * np.clip(act * 1.5, 0, 1)) / 20),
             'music': mus * g.get('music', 0.3) * duck}
    mix = sum(stems.values())
    pk = np.abs(mix).max() or 1
    mix = mix / pk * 0.9
    os.makedirs(os.path.join(project, 'audio'), exist_ok=True)
    sf.write(os.path.join(project, 'audio', 'mix_premaster.wav'), np.stack([mix, mix], 1).astype(np.float32), SR, subtype='FLOAT')
    for k, x in stems.items():
        sf.write(os.path.join(project, 'audio', 'stem_%s.wav' % k), (x / pk * 0.9).astype(np.float32), SR, subtype='FLOAT')
    print('MIX OK whooshes=%d duck=%.0fdB' % (whooshes, duck_db))


if __name__ == '__main__':
    {'lines': cmd_lines, 'mix': cmd_mix}[sys.argv[1]](os.path.abspath(sys.argv[2]))
