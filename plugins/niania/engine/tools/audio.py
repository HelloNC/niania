"""Audio for a project: narration/dialogue (Kokoro TTS, local, no API key), procedural SFX,
ambience, music bed, slow-motion filtering and the final mix.

  python audio.py lines <project>   # TTS -> audio/lines/*.wav + audio/lines.json (+ lip-sync envelopes)
  python audio.py mix   <project>   # needs build/build_report.json (event times) -> audio/mix.wav + stems
  python audio.py voices            # list a few good Kokoro voices

Supplied narration fallback: put a WAV at audio/narration_supplied.wav (placed at t=0) and set
"narration_mode": "supplied" in timeline.audio. TTS is then skipped for narration.
Runs with a Python that has numpy + soundfile (+ kokoro for TTS).
"""
import json
import math
import os
import sys
import numpy as np
import soundfile as sf

SR = 48000
VOICES = {'am_michael': 'warm US male', 'af_heart': 'bright US female', 'bm_george': 'UK male',
          'bf_emma': 'UK female', 'af_bella': 'soft US female', 'am_fenrir': 'deep US male'}


# ------------------------------------------------------------------ helpers
def resample(x, sr_in, sr_out=SR):
    if sr_in == sr_out:
        return x
    n = int(len(x) * sr_out / sr_in)
    t_in = np.arange(len(x)) / sr_in
    t_out = np.arange(n) / sr_out
    return np.interp(t_out, t_in, x)


def fft_filter(x, lo=None, hi=None, sr=SR, tilt=0.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    g = np.ones_like(f)
    if lo:
        g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi:
        g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if tilt:
        g *= (np.maximum(f, 20) / 1000.0) ** tilt
    return np.fft.irfft(X * g, len(x))


def env_ad(n, a, d, sr=SR):
    t = np.arange(n) / sr
    e = np.where(t < a, t / max(a, 1e-4), np.exp(-(t - a) / max(d, 1e-4)))
    return e


def rng(seed):
    return np.random.default_rng(seed)


def place(buf, x, t, gain=1.0):
    i = int(round(t * SR))
    if i < 0:
        x = x[-i:]
        i = 0
    j = min(len(buf), i + len(x))
    if j > i:
        buf[i:j] += x[:j - i] * gain


# ------------------------------------------------------------------ SFX library
def sfx(kind, seed=0):
    r = rng(seed)
    if kind in ('clink', 'tick'):
        dur = 0.6 if kind == 'clink' else 0.25
        n = int(dur * SR)
        t = np.arange(n) / SR
        parts = [(2150, 0.22, 1.0), (3390, 0.12, 0.6), (5180, 0.07, 0.4), (7020, 0.05, 0.25)]
        x = sum(a * np.sin(2 * np.pi * f * (1 + r.uniform(-0.01, 0.01)) * t) * np.exp(-t / d) for f, d, a in parts)
        click = fft_filter(r.normal(0, 1, n) * np.exp(-t / 0.004), 2000, 9000)
        x = x * 0.5 + click * 0.6
        return x * (0.35 if kind == 'tick' else 0.6)
    if kind == 'whoosh_soft':
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        e = np.sin(np.pi * np.clip(t / 0.7, 0, 1)) ** 2
        return fft_filter(r.normal(0, 1, n), 300, 2500) * e * 0.25
    if kind == 'heartbeat':
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        def thump(t0, a):
            tt = np.clip(t - t0, 0, None)
            f = 48 + 30 * np.exp(-tt / 0.03)
            ph = 2 * np.pi * np.cumsum(f) / SR
            return a * np.sin(ph) * np.exp(-tt / 0.09) * (t >= t0)
        x = thump(0.0, 1.0) + thump(0.27, 0.7)
        return fft_filter(x, None, 200) * 0.9
    if kind == 'step':
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 85 * t) * np.exp(-t / 0.04) * 0.7
        x += fft_filter(r.normal(0, 1, n), 400, 3500) * np.exp(-t / 0.05) * 0.35
        return x * 0.7
    if kind == 'catch':
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 120 * t) * np.exp(-t / 0.05) * 0.8
        x += fft_filter(r.normal(0, 1, n), 200, 2000) * np.exp(-t / 0.03) * 0.5
        k = sfx('tick', seed + 1)
        x[int(0.03 * SR):int(0.03 * SR) + len(k)] += k[:n - int(0.03 * SR)] * 0.8
        return x
    if kind in ('plip', 'drip'):
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        f = (500 if kind == 'plip' else 800) + 1400 * np.clip(t / 0.03, 0, 1)
        ph = 2 * np.pi * np.cumsum(f) / SR
        return np.sin(ph) * np.exp(-t / 0.035) * (0.6 if kind == 'plip' else 0.3)
    if kind == 'cloth':
        n = int(0.4 * SR)
        t = np.arange(n) / SR
        return fft_filter(r.normal(0, 1, n), 1500, 7000) * np.sin(np.pi * t / 0.4) ** 2 * 0.15
    if kind == 'knock':                       # fist on a door panel
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 150 * t) * np.exp(-t / 0.05) + 0.5 * np.sin(2 * np.pi * 310 * t) * np.exp(-t / 0.03)
        x += fft_filter(r.normal(0, 1, n), 200, 2500) * np.exp(-t / 0.015) * 0.6
        return x * 0.8
    if kind == 'rattle':                      # locked latch being forced
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        x = np.zeros(n)
        for k in range(9):
            t0 = k * 0.09 + r.uniform(0, 0.02)
            i0 = int(t0 * SR)
            m = n - i0
            tt = np.arange(m) / SR
            x[i0:] += (np.sin(2 * np.pi * 1900 * tt) * 0.4 + np.sin(2 * np.pi * 3100 * tt) * 0.25) * np.exp(-tt / 0.02) * r.uniform(0.5, 1)
            x[i0:] += fft_filter(r.normal(0, 1, m), 800, 6000) * np.exp(-tt / 0.01) * 0.3
        return x * 0.6
    if kind == 'beep':                        # cockpit alert chime
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        return (np.sin(2 * np.pi * 880 * t) * (t < 0.2) + np.sin(2 * np.pi * 660 * t) * (t >= 0.25)) * np.exp(-t / 0.4) * 0.3
    if kind == 'hiss':                        # carbonation escaping from a cracked cap
        n = int(1.4 * SR)
        t = np.arange(n) / SR
        e = np.clip(t / 0.03, 0, 1) * np.exp(-t / 0.45)
        x = fft_filter(r.normal(0, 1, n), 3000, 11000) * e * 0.35
        for k in range(40):                   # fizz crackle
            i0 = int(r.uniform(0.05, 1.3) * SR)
            m = min(n - i0, int(0.01 * SR))
            tt = np.arange(m) / SR
            x[i0:i0 + m] += np.sin(2 * np.pi * r.uniform(2500, 6000) * tt) * np.exp(-tt / 0.002) * 0.08 * np.exp(-i0 / SR / 0.8)
        return x
    if kind == 'twist':                       # plastic cap ratchet clicks
        n = int(0.6 * SR)
        x = np.zeros(n)
        for k in range(6):
            i0 = int((k * 0.09 + r.uniform(0, 0.015)) * SR)
            m = n - i0
            tt = np.arange(m) / SR
            x[i0:] += fft_filter(r.normal(0, 1, m), 1500, 7000) * np.exp(-tt / 0.004) * r.uniform(0.4, 0.8)
        return x * 0.5
    if kind == 'pop':
        n = int(0.15 * SR)
        t = np.arange(n) / SR
        return np.sin(2 * np.pi * (300 + 900 * np.exp(-t / 0.01)) * t) * np.exp(-t / 0.03) * 0.5
    raise ValueError('unknown sfx ' + kind)


def ambience(kind, dur, seed=5):
    r = rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    brown = np.cumsum(r.normal(0, 1, n))
    brown -= np.convolve(brown, np.ones(4801) / 4801, mode='same')
    base = fft_filter(brown, 40, 700) * 0.02
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * t / 9.0 + 1.0) ** 2
    x = base * swell
    x += np.sin(2 * np.pi * 60 * t) * 0.0015
    if kind == 'aircraft_cabin':              # engine drone + air-conditioning hiss
        hum = fft_filter(r.normal(0, 1, n), 40, 260) * 0.05 + np.sin(2 * np.pi * 92 * t) * 0.004
        hiss = fft_filter(r.normal(0, 1, n), 2500, 9000) * 0.006
        x = hum + hiss
    if kind in ('evening_street', 'park'):
        for k in range(int(dur / 3.5)):
            t0 = r.uniform(0, dur - 0.5)
            m = int(0.12 * SR)
            tt = np.arange(m) / SR
            f = 3200 + 1600 * np.sin(2 * np.pi * 18 * tt) + r.uniform(-300, 300)
            ch = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / 0.12) ** 2 * 0.012
            place(x, ch, t0)
    return x / max(1e-6, np.abs(x).max()) * 0.12


def music(kind, dur, seed=9):
    """'warm_pad': gentle Fmaj7-Am7-Dm9-Bbmaj7 pad. 'tension': low pulsing drone for news/explainers."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == 'tension':
        x = np.zeros(n)
        for f, a in ((55.0, 0.5), (82.4, 0.3), (110.0, 0.2), (116.5, 0.12)):
            x += a * np.sin(2 * np.pi * f * t + f)
        pulse = 0.55 + 0.45 * np.clip(np.sin(2 * np.pi * t / 0.92) , 0, 1) ** 3
        x *= pulse * np.clip(t / 2.0, 0, 1)
        x += 0.05 * np.sin(2 * np.pi * 440 * t) * np.exp(-((t % 3.68) / 0.4)) * (t > 3)
        x = fft_filter(x, 35, 900)
        return x / max(1e-6, np.abs(x).max()) * 0.22
    chords = [[53, 57, 60, 64], [57, 60, 64, 67], [50, 57, 60, 64, 69], [46, 53, 57, 62]]
    bar = 3.75
    x = np.zeros(n)
    for i in range(int(dur / bar) + 2):
        ch = chords[i % len(chords)]
        t0 = i * bar
        for k, m in enumerate(ch):
            f = 440 * 2 ** ((m - 69) / 12)
            seg = (t >= t0 - 0.5) & (t < t0 + bar + 1.5)
            tt = t[seg] - t0
            e = np.clip((tt + 0.5) / 1.4, 0, 1) * np.clip((bar + 1.5 - tt) / 1.6, 0, 1)
            v = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt + 0.3) +
                 0.12 * np.sin(2 * np.pi * 3.01 * f * tt)) * e
            x[seg] += v * (0.5 if k == 0 else 0.3)
    x = fft_filter(x, 60, 1800)
    return x / max(1e-6, np.abs(x).max()) * 0.2


def time_varying_lowpass(x, cutoff_fn, block=2048):
    """Overlap-add STFT lowpass with cutoff(t) in Hz."""
    hop = block // 2
    win = np.hanning(block)
    out = np.zeros(len(x) + block)
    norm = np.zeros(len(x) + block)
    f = np.fft.rfftfreq(block, 1 / SR)
    xp = np.concatenate([x, np.zeros(block)])
    for i in range(0, len(x), hop):
        seg = xp[i:i + block] * win
        c = cutoff_fn((i + hop) / SR)
        g = 1 / np.sqrt(1 + (f / c) ** 6)
        y = np.fft.irfft(np.fft.rfft(seg) * g, block)
        out[i:i + block] += y * win
        norm[i:i + block] += win ** 2
    return (out / np.maximum(norm, 1e-6))[:len(x)]


# ------------------------------------------------------------------ TTS
def tts(text, voice, speed=1.0):
    from kokoro import KPipeline
    lang = 'b' if voice.startswith('b') else 'a'
    key = (lang,)
    if key not in tts.cache:
        tts.cache[key] = KPipeline(lang_code=lang, repo_id='hexgrad/Kokoro-82M')
    pipe = tts.cache[key]
    chunks = [np.asarray(a, dtype=np.float64) for _, _, a in pipe(text, voice=voice, speed=speed)]
    y = np.concatenate(chunks) if chunks else np.zeros(100)
    y = resample(y, 24000)
    # trim leading/trailing silence
    a = np.abs(y)
    idx = np.where(a > 0.01 * a.max())[0]
    if len(idx):
        y = y[max(0, idx[0] - 480):idx[-1] + 2400]
    return y


tts.cache = {}


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
    fps = tl.get('fps', 24)
    d = os.path.join(project, 'audio', 'lines')
    os.makedirs(d, exist_ok=True)
    out = {'narration': [], 'dialogue': [], 'warnings': []}
    mode = au.get('narration_mode', 'tts')
    nv = au.get('narrator_voice', 'am_michael')
    if mode == 'tts':
        for i, ln in enumerate(au.get('narration', [])):
            y = tts(ln['text'], ln.get('voice', nv), ln.get('speed', au.get('narrator_speed', 1.0)))
            fn = os.path.join(d, 'narr_%02d.wav' % i)
            sf.write(fn, y, SR)
            out['narration'].append({'t': ln['t'], 'start': ln['t'], 'dur': len(y) / SR, 'file': fn, 'text': ln['text']})
    for i, ln in enumerate(au.get('dialogue', [])):
        y = tts(ln['text'], ln.get('voice', 'af_heart'), ln.get('speed', 1.0))
        fn = os.path.join(d, 'dlg_%02d.wav' % i)
        sf.write(fn, y, SR)
        out['dialogue'].append({'t': ln['t'], 'start': ln['t'], 'dur': len(y) / SR, 'file': fn, 'char': ln.get('char'),
                                'text': ln['text'], 'env': envelope(y, fps)})
    # overlap / length checks
    allx = sorted(out['narration'], key=lambda x: x['start'])
    for a, b in zip(allx[:-1], allx[1:]):
        if a['start'] + a['dur'] > b['start'] - 0.15:
            out['warnings'].append('narration "%s" (%.2fs) runs into the next line by %.2fs' %
                                   (a['text'][:30], a['dur'], a['start'] + a['dur'] - b['start'] + 0.15))
    if allx and allx[-1]['start'] + allx[-1]['dur'] > tl['duration']:
        out['warnings'].append('last narration line ends after the video')
    json.dump(out, open(os.path.join(project, 'audio', 'lines.json'), 'w'), indent=1)
    for n in out['narration'] + out['dialogue']:
        print('%-50s start %.2f dur %.2f' % (n['text'][:50], n['start'], n['dur']))
    for w in out['warnings']:
        print('WARNING', w)


def resolve_time(item, events):
    if 't' in item:
        return float(item['t'])
    v = item['at'].replace(' ', '')
    for op in ('+', '-'):
        k = v.rfind(op)
        if k > 0:
            return events[v[:k]] + float(v[k:])
    return events[v]


def cmd_mix(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    rep = json.load(open(os.path.join(project, 'build', 'build_report.json')))
    events = rep.get('events', {})
    au = tl.get('audio', {})
    dur = tl['duration']
    n = int(dur * SR)
    lines = json.load(open(os.path.join(project, 'audio', 'lines.json'))) if os.path.exists(
        os.path.join(project, 'audio', 'lines.json')) else {'narration': [], 'dialogue': []}
    voice = np.zeros(n)
    for ln in lines['narration'] + lines['dialogue']:
        y, sr = sf.read(ln['file'])
        place(voice, y, ln['start'], 0.9 if ln in lines['narration'] else 1.0)
    sup = os.path.join(project, 'audio', 'narration_supplied.wav')
    if au.get('narration_mode') == 'supplied' and os.path.exists(sup):
        y, sr = sf.read(sup)
        if y.ndim > 1:
            y = y.mean(axis=1)
        place(voice, resample(y, sr), 0.0)
    fxb = np.zeros(n)
    for i, it in enumerate(au.get('sfx', [])):
        if it.get('auto') == 'steps':
            for k, tt in events.items():
                if k.startswith('step:%s:' % it.get('char', '')):
                    place(fxb, sfx(it['type'], i * 13 + len(k)), tt, it.get('gain', 0.4))
            continue
        if it.get('auto') == 'splats':
            for k, tt in events.items():
                if k.startswith('splat:') and 'face' not in k:
                    place(fxb, sfx(it['type'], i * 31 + len(k)), tt, it.get('gain', 0.3))
            continue
        try:
            tt = resolve_time(it, events)
        except KeyError as e:
            print('WARNING sfx event missing', e)
            continue
        place(fxb, sfx(it['type'], i * 7 + 1), tt, it.get('gain', 0.5))
    amb = ambience(au.get('ambience', 'evening_street'), dur) if au.get('ambience') else np.zeros(n)
    mus = music(au.get('music', 'warm_pad'), dur) if au.get('music') else np.zeros(n)
    # slow-motion: muffle the world (ambience + music) while time is slowed
    remap = tl.get('time_remap')
    if remap and au.get('slowmo_filter', True):
        ks = sorted(remap)

        def speed(t):
            if t <= ks[0][0]:
                return ks[0][1]
            for (t0, s0), (t1, s1) in zip(ks[:-1], ks[1:]):
                if t0 <= t <= t1:
                    u = (t - t0) / max(1e-6, t1 - t0)
                    u = u * u * (3 - 2 * u)
                    return s0 + (s1 - s0) * u
            return ks[-1][1]
        cut = lambda t: 300 + 15000 * min(1.0, speed(t)) ** 1.5
        amb = time_varying_lowpass(amb, cut)
        mus = time_varying_lowpass(mus, lambda t: 500 + 15000 * min(1.0, speed(t)) ** 1.5)
    # duck music under voice
    venv = np.convolve(np.abs(voice), np.ones(4800) / 4800, mode='same')
    duck = 1 - 0.55 * np.clip(venv / (venv.max() * 0.3 + 1e-9), 0, 1)
    mix = voice * 1.0 + fxb * 0.9 + amb * 0.8 + mus * 0.55 * duck
    peak = np.abs(mix).max()
    mix = mix / max(peak, 1e-6) * 0.89
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    out = os.path.join(project, 'audio')
    st = np.stack([mix, mix], axis=1)
    sf.write(os.path.join(out, 'mix.wav'), st, SR)
    for name, x in (('stem_voice', voice), ('stem_sfx', fxb), ('stem_ambience', amb), ('stem_music', mus)):
        sf.write(os.path.join(out, name + '.wav'), x.astype(np.float32), SR)
    # timing report for QC
    rep_a = {'duration': dur, 'voice_onsets': [], 'sfx': []}
    for ln in lines['narration'] + lines['dialogue']:
        i0 = int(ln['start'] * SR)
        seg = np.abs(voice[i0:i0 + int(0.6 * SR)])
        on = np.argmax(seg > 0.05 * (seg.max() + 1e-9)) / SR if seg.max() > 0 else None
        rep_a['voice_onsets'].append({'text': ln['text'][:40], 'planned': ln['start'], 'measured': ln['start'] + (on or 0)})
    json.dump(rep_a, open(os.path.join(out, 'audio_report.json'), 'w'), indent=1)
    print('MIX OK', os.path.join(out, 'mix.wav'), '%.2fs' % dur)


def cmd_sync(project, mp4, ff):
    """Offset of the voice stem inside the final MP4's audio (positive = audio late)."""
    import subprocess
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), 'a.wav')
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', mp4, '-vn', '-ac', '1', '-ar', str(SR), tmp], check=True)
    a, _ = sf.read(tmp)
    v, _ = sf.read(os.path.join(project, 'audio', 'stem_voice.wav'))
    hop = 48                                      # 1 ms envelopes
    def env(x):
        n = len(x) // hop
        return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    ea, ev = env(a), env(v)
    n = min(len(ea), len(ev))
    ea, ev = ea[:n] - ea[:n].mean(), ev[:n] - ev[:n].mean()
    best, lag_best = -1, 0
    for lag in range(-200, 201):
        x = ea[max(0, lag):n + min(0, lag)]
        y = ev[max(0, -lag):n - max(0, lag)]
        c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-12))
        if c > best:
            best, lag_best = c, lag
    print('SYNC offset_ms=%d corr=%.3f' % (lag_best, best))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'lines':
        cmd_lines(sys.argv[2])
    elif cmd == 'mix':
        cmd_mix(sys.argv[2])
    elif cmd == 'sync':
        cmd_sync(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'voices':
        for k, v in VOICES.items():
            print(k, '-', v)
