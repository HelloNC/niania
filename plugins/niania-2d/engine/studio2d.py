#!/usr/bin/env python3
"""niania-2d command line (stdlib only). Code-only video: Pillow/numpy frames, Kokoro voices, ffmpeg encode.
No Blender, no 3D app, no API keys.

  studio2d.py doctor [--install] [--install-tts]   find/prepare Python deps + ffmpeg (config in ~/.niania2d/config.json)
  studio2d.py new <project> [--duration 30] [--size 1080x1920] [--title T]
  studio2d.py validate <project>
  studio2d.py palette <image> [x,y ...]            dominant colours + sampled colours of a reference sheet
  studio2d.py sheet <project> <char_id>            draw the coded character's turnaround/expression sheet
  studio2d.py lines <project>                      TTS narration + dialogue (word timings, lip-sync envelopes)
  studio2d.py preview <project> [--every 1.0] [--pct 40]   low-res frames + contact sheet (preview/sheet.png)
  studio2d.py render <project> [--shot NAME] [--frames 1,2] [--jobs N]
  studio2d.py mix <project>                        sound design + ducking -> audio/mix_premaster.wav
  studio2d.py assemble <project>                   -14 LUFS master, encode final/<title>.mp4, captions.srt
  studio2d.py check <project>                      media QC + final/contact_sheet.jpg
  studio2d.py all <project>
"""
import glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
CFG_DIR = os.path.expanduser('~/.niania2d')
CFG = os.path.join(CFG_DIR, 'config.json')


def sh(cmd, check=True, quiet=False):
    if not quiet:
        print('$', ' '.join(str(c) for c in cmd[:5]) + (' ...' if len(cmd) > 5 else ''), flush=True)
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and p.returncode != 0:
        print(p.stdout[-3000:], p.stderr[-3000:])
        sys.exit('step failed: %s' % cmd[0])
    return p


def has(py, mods):
    if not py or not os.path.exists(py):
        return False
    r = subprocess.run([py, '-c', 'import ' + ','.join(mods)], capture_output=True)
    return r.returncode == 0


def doctor(install=False, install_tts=False, quiet=False):
    cfg = {}
    cands = [os.path.join(CFG_DIR, 'venv/bin/python'), sys.executable, shutil.which('python3')]
    for py in cands:
        if has(py, ['PIL', 'numpy']):
            cfg['py2d'] = py
            break
    if 'py2d' not in cfg and install:
        venv = os.path.join(CFG_DIR, 'venv')
        os.makedirs(CFG_DIR, exist_ok=True)
        sh([sys.executable, '-m', 'venv', venv])
        sh([os.path.join(venv, 'bin/pip'), 'install', '-q', 'pillow', 'numpy', 'soundfile'])
        cfg['py2d'] = os.path.join(venv, 'bin/python')
    tts_c = [os.path.join(CFG_DIR, 'tts-venv/bin/python'), os.path.expanduser('~/blender-tools/tts-venv/bin/python'),
             os.path.expanduser('~/.animation-studio/venv/bin/python')]
    for py in tts_c:
        if has(py, ['kokoro', 'soundfile', 'numpy']):
            cfg['tts_python'] = py
            break
    if 'tts_python' not in cfg and install_tts:
        venv = os.path.join(CFG_DIR, 'tts-venv')
        py = shutil.which('python3.11') or shutil.which('python3.12') or sys.executable
        sh([py, '-m', 'venv', venv])
        sh([os.path.join(venv, 'bin/pip'), 'install', '-q', 'kokoro>=0.9', 'soundfile', 'numpy'])
        cfg['tts_python'] = os.path.join(venv, 'bin/python')
    for py in [cfg.get('tts_python'), cfg.get('py2d')]:
        if has(py, ['soundfile', 'numpy']):
            cfg['audio_python'] = py
            break
    ff = shutil.which('ffmpeg')
    if not ff:
        for py in [cfg.get('tts_python'), cfg.get('py2d')]:
            if py and has(py, ['imageio_ffmpeg']):
                ff = subprocess.run([py, '-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'],
                                    capture_output=True, text=True).stdout.strip()
                break
    if ff:
        cfg['ffmpeg'] = ff
        fp = shutil.which('ffprobe')
        if fp:
            cfg['ffprobe'] = fp
    os.makedirs(CFG_DIR, exist_ok=True)
    json.dump(cfg, open(CFG, 'w'), indent=1)
    if not quiet:
        print(json.dumps(cfg, indent=1))
        ok = True
        if 'py2d' not in cfg:
            print('MISSING Python with Pillow + numpy. Run: studio2d.py doctor --install  (pip, ~20 MB, free)')
            ok = False
        if 'tts_python' not in cfg:
            print('MISSING local TTS (Kokoro). Run: studio2d.py doctor --install-tts  (~1 GB, free, no API key). '
                  'Without it, supply audio/narration_supplied.wav or make a silent/music-only video.')
        if 'audio_python' not in cfg:
            print('MISSING soundfile for mixing (installed by --install).')
            ok = False
        if 'ffmpeg' not in cfg:
            print('MISSING ffmpeg: brew install ffmpeg')
            ok = False
        print('READY' if ok else 'NOT READY')
    return cfg


def load_cfg():
    return json.load(open(CFG)) if os.path.exists(CFG) else doctor(quiet=True)


def new(project, duration, size, title):
    os.makedirs(project, exist_ok=True)
    p = os.path.join(project, 'timeline.json')
    if os.path.exists(p):
        sys.exit('timeline.json already exists in ' + project)
    tl = json.load(open(os.path.join(PLUGIN, 'templates', 'starter_timeline.json')))
    w, h = map(int, size.lower().split('x'))
    tl.update(duration=float(duration), resolution=[w, h], title=title or os.path.basename(project))
    json.dump(tl, open(p, 'w'), indent=1)
    shutil.copy(os.path.join(PLUGIN, 'templates', 'story_template.md'), os.path.join(project, 'story.md'))
    for d in ('assets', 'audio', 'frames', 'preview', 'final'):
        os.makedirs(os.path.join(project, d), exist_ok=True)
    print('created', project)


DOS = {'expr', 'look', 'turn', 'tilt', 'gesture', 'blink', 'nod', 'shake'}
INS = {'cut', 'dip', 'flash', 'flicker', 'slowfade', 'whip'}


def validate(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    errs, warns = [], []
    for k in ('duration', 'shots', 'cast'):
        if k not in tl:
            errs.append('missing ' + k)
    shots = tl.get('shots', [])
    if shots and abs(shots[0]['start']) > 1e-6:
        errs.append('first shot must start at 0')
    for a, b in zip(shots[:-1], shots[1:]):
        if abs(a['end'] - b['start']) > 1e-6:
            errs.append('shots %s/%s not contiguous' % (a['name'], b['name']))
        if a.get('in') == b.get('in') and b.get('in') not in (None, 'cut'):
            warns.append('same transition twice in a row (%s, %s)' % (a['name'], b['name']))
    if shots and abs(shots[-1]['end'] - tl.get('duration', 0)) > 1e-6:
        errs.append('last shot must end at duration')
    for s in shots:
        if s.get('in', 'cut') not in INS:
            errs.append('shot %s: unknown transition %s' % (s['name'], s.get('in')))
        for c in s.get('chars', []):
            if c['id'] not in tl.get('cast', {}):
                errs.append('shot %s: unknown character %s' % (s['name'], c['id']))
    for e in tl.get('performance', []):
        if e.get('char') not in tl.get('cast', {}):
            errs.append('performance for unknown char %r' % e)
        if e.get('do') not in DOS:
            errs.append('unknown performance verb %r' % e.get('do'))
    for ln in tl.get('audio', {}).get('dialogue', []):
        if ln.get('char') not in tl.get('cast', {}):
            errs.append('dialogue for unknown char %r' % ln)
    wh = sum(1 for e in tl.get('audio', {}).get('sfx', []) if e['type'] in ('whoosh', 'swoosh'))
    if wh > max(2, tl.get('duration', 30) / 20):
        warns.append('%d whooshes - keep them rare' % wh)
    print(json.dumps({'errors': errs, 'warnings': warns}, indent=1))
    if errs:
        sys.exit(1)


def py2d(cfg):
    if 'py2d' not in cfg:
        sys.exit('no Python with Pillow+numpy: run studio2d.py doctor --install')
    return cfg['py2d']


def preview(cfg, project, every=1.0, pct=40):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    fps = tl.get('fps', 30)
    frames = sorted(set([int(round((s['start'] + 0.05) * fps)) for s in tl['shots']] +
                        [int(round(t * fps)) for t in [k * every for k in range(int(tl['duration'] / every))]]))
    out = os.path.join(project, 'preview', 'frames')
    os.makedirs(out, exist_ok=True)
    for p in glob.glob(os.path.join(out, 'f*.png')):
        os.remove(p)
    sh([py2d(cfg), os.path.join(HERE, 'render.py'), project, '--frames', ','.join(map(str, frames)), '--out', out,
        '--pct', str(pct)])
    n = len(frames)
    W, H = tl['resolution']
    cols = 8 if H > W else 5
    rows = (n + cols - 1) // cols
    sc = 'scale=%d:-1' % (180 if H > W else 320)
    sh([cfg['ffmpeg'], '-y', '-loglevel', 'error', '-pattern_type', 'glob', '-i', os.path.join(out, 'f*.png'),
        '-vf', '%s,tile=%dx%d:padding=4' % (sc, cols, rows), '-frames:v', '1', os.path.join(project, 'preview', 'sheet.png')])
    print('preview sheet:', os.path.join(project, 'preview', 'sheet.png'))


def master(cfg, project, target=-14.0):
    ff = cfg['ffmpeg']
    src = os.path.join(project, 'audio', 'mix_premaster.wav')
    out = os.path.join(project, 'audio', 'mix_master.wav')
    e = sh([ff, '-hide_banner', '-i', src, '-af', 'loudnorm=I=%s:TP=-1.5:LRA=11:print_format=json' % target, '-f', 'null', '-'],
           quiet=True).stderr
    js = json.loads(e[e.rindex('{'):e.rindex('}') + 1])
    gain = target - float(js['input_i'])
    tp = float(js['input_tp'])
    for _ in range(3):      # the limiter lowers integrated loudness, so iterate the make-up gain
        lim = '' if tp + gain <= -1.5 else ',alimiter=limit=%.4f:attack=2:release=60:level=disabled' % (10 ** (-1.5 / 20))
        sh([ff, '-y', '-hide_banner', '-i', src, '-af', 'volume=%.3fdB%s' % (gain, lim), '-ar', '48000', '-c:a', 'pcm_s24le',
            out], quiet=True)
        e = sh([ff, '-hide_banner', '-i', out, '-af', 'ebur128', '-f', 'null', '-'], quiet=True).stderr
        m = re.findall(r'I:\s+(-?[\d.]+) LUFS', e)
        got = float(m[-1]) if m else target
        if abs(got - target) < 0.3:
            break
        gain += target - got
    print('master %.1f LUFS' % got)
    return out


def assemble(cfg, project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    fps = tl.get('fps', 30)
    n = int(round(tl['duration'] * fps))
    have = len(glob.glob(os.path.join(project, 'frames', 'f*.png')))
    if have < n:
        sys.exit('only %d/%d frames rendered: run studio2d.py render %s' % (have, n, project))
    audio = master(cfg, project, tl.get('audio', {}).get('lufs', -14.0)) if os.path.exists(
        os.path.join(project, 'audio', 'mix_premaster.wav')) else None
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', tl.get('title', 'video')).strip('_') or 'video'
    out = os.path.join(project, 'final', name + '.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [cfg['ffmpeg'], '-y', '-hide_banner', '-loglevel', 'error', '-framerate', str(fps), '-i',
           os.path.join(project, 'frames', 'f%05d.png')]
    if audio:
        cmd += ['-i', audio]
    cmd += ['-c:v', 'libx264', '-preset', 'slow', '-crf', str(tl.get('crf', 18)), '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-frames:v', str(n)]
    if audio:
        cmd += ['-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-t', str(tl['duration'])]
    cmd += ['-movflags', '+faststart', out]
    sh(cmd)
    if os.path.exists(os.path.join(project, 'audio', 'lines.json')):
        sh([py2d(cfg), os.path.join(HERE, 'tools2d.py'), 'srt', project])
    print('FINAL', out)
    return out


def check(cfg, project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    finals = sorted(glob.glob(os.path.join(project, 'final', '*.mp4')), key=os.path.getmtime)
    if not finals:
        sys.exit('no final mp4')
    f = finals[-1]
    ff = cfg['ffmpeg']
    res = {'file': f, 'problems': []}
    t = sh([ff, '-hide_banner', '-i', f, '-map', '0:v', '-f', 'null', '-'], quiet=True, check=False).stderr
    fr = re.findall(r'frame=\s*(\d+)', t)
    res['frames'] = int(fr[-1]) if fr else None
    v = re.search(r'Video: .*?, (\d+)x(\d+)', t)
    res['size'] = [int(v.group(1)), int(v.group(2))] if v else None
    want = int(round(tl['duration'] * tl.get('fps', 30)))
    if res['frames'] != want:
        res['problems'].append('frames %s vs %d' % (res['frames'], want))
    if res['size'] != list(tl['resolution']):
        res['problems'].append('size %s' % res['size'])
    t = sh([ff, '-hide_banner', '-i', f, '-map', '0:a?', '-af', 'ebur128=peak=true', '-f', 'null', '-'], quiet=True, check=False).stderr
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', t)
    res['lufs'] = float(m[-1]) if m else None
    if res['lufs'] is not None and abs(res['lufs'] - tl.get('audio', {}).get('lufs', -14.0)) > 0.6:
        res['problems'].append('loudness %.1f LUFS' % res['lufs'])
    t = sh([ff, '-hide_banner', '-i', f, '-vf', 'blackdetect=d=0.4:pix_th=0.05', '-an', '-f', 'null', '-'], quiet=True,
           check=False).stderr
    res['black'] = re.findall(r'black_start:([\d.]+) black_end:([\d.]+)', t)
    sheet = os.path.join(project, 'final', 'contact_sheet.jpg')
    W, H = tl['resolution']
    sh([ff, '-y', '-loglevel', 'error', '-i', f, '-vf', 'fps=1,scale=%s,tile=%dx%d:padding=4' %
        ('240:-1' if H > W else '360:-1', 10 if H > W else 6, (int(tl['duration']) + (9 if H > W else 5)) // (10 if H > W else 6)),
        '-frames:v', '1', sheet], quiet=True)
    res['contact_sheet'] = sheet
    json.dump(res, open(os.path.join(project, 'final', 'media_check.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1))
    print('MEDIA OK' if not res['problems'] else 'MEDIA PROBLEMS')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    cmd = a[0]
    opts = {a[i]: a[i + 1] for i in range(len(a) - 1) if a[i].startswith('--')}
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith('--') and not a[i - 1].startswith('--')]
    if cmd == 'doctor':
        doctor('--install' in a, '--install-tts' in a)
        return
    cfg = load_cfg()
    if cmd == 'palette':
        print(sh([py2d(cfg), os.path.join(HERE, 'tools2d.py'), 'palette'] + pos, quiet=True).stdout)
        return
    project = os.path.abspath(pos[0])
    if cmd == 'new':
        new(project, opts.get('--duration', 30), opts.get('--size', '1080x1920'), opts.get('--title'))
    elif cmd == 'validate':
        validate(project)
    elif cmd == 'sheet':
        print(sh([py2d(cfg), os.path.join(HERE, 'tools2d.py'), 'sheet', project, pos[1]]).stdout)
    elif cmd == 'lines':
        if not cfg.get('tts_python'):
            sys.exit('no local TTS: run studio2d.py doctor --install-tts (ask the user first)')
        print(sh([cfg['tts_python'], '-I', os.path.join(HERE, 'audio2d.py'), 'lines', project]).stdout)
    elif cmd == 'preview':
        preview(cfg, project, float(opts.get('--every', 1.0)), int(opts.get('--pct', 40)))
    elif cmd == 'render':
        args = [py2d(cfg), os.path.join(HERE, 'render.py'), project]
        for k in ('--shot', '--frames', '--jobs', '--pct'):
            if k in opts:
                args += [k, opts[k]]
        p = subprocess.run(args)
        if p.returncode:
            sys.exit('render failed')
    elif cmd == 'mix':
        print(sh([cfg['audio_python'], '-I', os.path.join(HERE, 'audio2d.py'), 'mix', project]).stdout)
    elif cmd == 'assemble':
        assemble(cfg, project)
    elif cmd == 'check':
        check(cfg, project)
    elif cmd == 'all':
        validate(project)
        if cfg.get('tts_python'):
            print(sh([cfg['tts_python'], '-I', os.path.join(HERE, 'audio2d.py'), 'lines', project]).stdout)
        print(sh([cfg['audio_python'], '-I', os.path.join(HERE, 'audio2d.py'), 'mix', project]).stdout)
        subprocess.run([py2d(cfg), os.path.join(HERE, 'render.py'), project], check=True)
        assemble(cfg, project)
        check(cfg, project)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
