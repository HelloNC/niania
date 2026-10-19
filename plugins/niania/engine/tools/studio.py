#!/usr/bin/env python3
"""Animation Studio command line (stdlib only). Orchestrates Blender, TTS and ffmpeg.

  studio.py doctor [--install-tts]        detect / verify Blender, TTS, ffmpeg; write ~/.animation-studio/config.json
  studio.py new <project_dir> [--duration 30] [--size 1920x1080] [--title T]
  studio.py validate <project>            static checks of timeline.json
  studio.py lines <project>               narration + dialogue TTS (lip-sync envelopes)
  studio.py build <project>               timeline.json -> build/scene.blend (+ build_report.json)
  studio.py qc <project> [every]          animation QC -> build/qc.json
  studio.py mix <project>                 SFX/ambience/music + voice -> audio/mix.wav
  studio.py preview <project> [frames|auto] [--pct 30]   low-res frames + contact sheet in preview/
  studio.py render <project> [--shot NAME[,NAME]] [--samples 32] [--pct 100]
  studio.py assemble <project>            shot PNGs -> per-shot MP4s -> final/<name>.mp4 with audio
  studio.py check <project>               media QC of the final MP4 (durations, sync, black frames) + sheet
  studio.py all <project>                 validate, lines, build, qc, mix, render, assemble, check
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
PLUGIN = os.path.dirname(ENGINE)
CFG_DIR = os.path.expanduser('~/.animation-studio')
CFG = os.path.join(CFG_DIR, 'config.json')


# ------------------------------------------------------------------ config
def load_cfg():
    if os.path.exists(CFG):
        return json.load(open(CFG))
    return doctor(quiet=True)


def run(cmd, log=None, check=True):
    print('$', ' '.join(cmd[:4]) + (' ...' if len(cmd) > 4 else ''), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if log:
        open(log, 'a').write(p.stdout)
    if check and (p.returncode != 0 or 'Traceback' in p.stdout):
        print(p.stdout[-4000:])
        sys.exit('step failed: %s' % cmd[0])
    return p.stdout


def doctor(quiet=False, install_tts=False):
    cfg = {}
    cands = [os.environ.get('BLENDER'), '/Applications/Blender.app/Contents/MacOS/Blender', shutil.which('blender')]
    for c in cands:
        if c and os.path.exists(c):
            cfg['blender'] = c
            break
    pys = [os.path.join(CFG_DIR, 'venv/bin/python'), os.path.expanduser('~/blender-tools/tts-venv/bin/python')]
    for py in pys:
        if os.path.exists(py):
            r = subprocess.run([py, '-c', 'import kokoro, soundfile, numpy; print("ok")'], capture_output=True, text=True)
            if 'ok' in r.stdout:
                cfg['tts_python'] = py
                break
    if 'tts_python' not in cfg and install_tts:
        os.makedirs(CFG_DIR, exist_ok=True)
        venv = os.path.join(CFG_DIR, 'venv')
        py = shutil.which('python3.11') or shutil.which('python3.12') or sys.executable
        run([py, '-m', 'venv', venv])
        run([os.path.join(venv, 'bin/pip'), 'install', '-q', 'kokoro>=0.9', 'soundfile', 'numpy', 'imageio-ffmpeg', 'pip'])
        cfg['tts_python'] = os.path.join(venv, 'bin/python')
    ff = shutil.which('ffmpeg')
    if not ff:
        for py in [cfg.get('tts_python')] + glob.glob(os.path.expanduser('~/*/venv/bin/python')) + \
                  glob.glob(os.path.expanduser('~/*/*-venv/bin/python')):
            if py and os.path.exists(py):
                r = subprocess.run([py, '-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'],
                                   capture_output=True, text=True)
                if r.returncode == 0 and os.path.exists(r.stdout.strip()):
                    ff = r.stdout.strip()
                    break
    if ff:
        cfg['ffmpeg'] = ff
    # numpy/soundfile python for mixing (TTS python works; else any python with numpy+soundfile)
    cfg['audio_python'] = cfg.get('tts_python')
    if cfg.get('blender'):
        v = subprocess.run([cfg['blender'], '-b', '--factory-startup', '--version'], capture_output=True, text=True).stdout
        m = re.search(r'Blender (\d+)\.(\d+)', v)
        cfg['blender_version'] = m.group(0) if m else '?'
    os.makedirs(CFG_DIR, exist_ok=True)
    json.dump(cfg, open(CFG, 'w'), indent=1)
    if not quiet:
        print(json.dumps(cfg, indent=1))
        ok = True
        if not cfg.get('blender'):
            print('MISSING Blender 4.2+ (free): https://www.blender.org/download/ -> /Applications'); ok = False
        elif not cfg['blender_version'].startswith(('Blender 4.', 'Blender 5.')):
            print('WARNING Blender version may be too old:', cfg['blender_version'])
        if not cfg.get('tts_python'):
            print('MISSING local TTS. Run: studio.py doctor --install-tts  (free, ~1 GB download, no API key).'
                  ' Without it, supply narration as audio/narration_supplied.wav.')
        if not cfg.get('ffmpeg'):
            print('MISSING ffmpeg: brew install ffmpeg  (or pip install imageio-ffmpeg in the TTS venv)'); ok = False
        print('READY' if ok else 'NOT READY')
    return cfg


# ------------------------------------------------------------------ steps
def blender(cfg, script, project, *args, blend=None, log='build/blender.log'):
    os.makedirs(os.path.join(project, 'build'), exist_ok=True)
    cmd = [cfg['blender'], '-b']
    cmd += [blend] if blend else ['--factory-startup']
    cmd += ['--python', os.path.join(HERE, script), '--', project] + list(args)
    return run(cmd, os.path.join(project, log))


def new(project, duration=30.0, size='1920x1080', title=None):
    os.makedirs(project, exist_ok=True)
    tpl = json.load(open(os.path.join(PLUGIN, 'templates', 'starter_timeline.json')))
    w, h = map(int, size.lower().split('x'))
    tpl['duration'], tpl['resolution'] = float(duration), [w, h]
    tpl['title'] = title or os.path.basename(os.path.abspath(project))
    p = os.path.join(project, 'timeline.json')
    if os.path.exists(p):
        sys.exit('timeline.json already exists in ' + project)
    json.dump(tpl, open(p, 'w'), indent=1)
    shutil.copy(os.path.join(PLUGIN, 'templates', 'story_template.md'), os.path.join(project, 'story.md'))
    for d in ('audio', 'build', 'render', 'preview', 'final'):
        os.makedirs(os.path.join(project, d), exist_ok=True)
    print('created', project)


VERBS = {'stance', 'sit', 'step', 'shift', 'hips', 'bend', 'anticipate', 'shrug', 'hand', 'grip', 'spread', 'point', 'expr', 'blink', 'look'}
OBJ_DO = {'held', 'place', 'topple', 'fall', 'catch', 'static', 'swing', 'rattle', 'path', 'spin', 'attach'}


def validate(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    errs, warns = [], []
    for k in ('duration', 'cast', 'shots', 'set'):
        if k not in tl:
            errs.append('missing key ' + k)
    cast = tl.get('cast', {})
    props = tl.get('props', {})
    for e in tl.get('performance', []):
        if e.get('char') not in cast:
            errs.append('performance event for unknown char: %r' % e)
        if e.get('do') not in VERBS:
            errs.append('unknown verb %r' % e.get('do'))
        if e.get('do') in ('hand',) and 'spec' not in e:
            errs.append('hand event without spec at t=%s' % e.get('t'))
    for n, p in props.items():
        for m in p.get('motion', []):
            if m.get('do') not in OBJ_DO:
                errs.append('prop %s: unknown motion %r' % (n, m.get('do')))
            if 'char' in m and m['char'] not in cast:
                errs.append('prop %s: unknown char %s' % (n, m['char']))
    shots = tl.get('shots', [])
    num = [s for s in shots if isinstance(s['start'], (int, float)) and isinstance(s['end'], (int, float))]
    num.sort(key=lambda s: s['start'])
    if num and abs(num[0]['start']) > 1e-6:
        errs.append('first shot must start at 0')
    for a, b in zip(num[:-1], num[1:]):
        if abs(a['end'] - b['start']) > 1e-6:
            errs.append('shots %s/%s are not contiguous' % (a['name'], b['name']))
    if num and abs(num[-1]['end'] - tl.get('duration', 0)) > 1e-6:
        errs.append('last shot must end at duration')
    for s in shots:
        if s['end'] - s['start'] < 1.0 if isinstance(s['end'], (int, float)) else False:
            warns.append('shot %s shorter than 1 s' % s['name'])
    print(json.dumps({'errors': errs, 'warnings': warns}, indent=1))
    if errs:
        sys.exit(1)


def preview(cfg, project, frames='auto', pct='30'):
    rep = json.load(open(os.path.join(project, 'build', 'build_report.json')))
    if frames == 'auto':
        fs = []
        for s in rep['shots']:
            n = s['f1'] - s['f0']
            fs += [s['f0'] + int(n * k / 5) for k in range(6)]
        frames = ','.join(str(f) for f in fs)
    out = os.path.join(project, 'preview')
    for p in glob.glob(os.path.join(out, 'p*.png')):
        os.remove(p)
    blender(cfg, 'bl_render.py', project, 'frames', frames, '--samples', '8', '--pct', pct,
            blend=os.path.join(project, 'build', 'scene.blend'))
    for pth in sorted(glob.glob(os.path.join(out, 'p*.png'))):
        o = os.path.join(os.path.dirname(pth), 'o' + os.path.basename(pth)[1:])
        if os.path.exists(o):
            tmp = pth + '.tmp.png'
            subprocess.run([cfg['ffmpeg'], '-y', '-loglevel', 'error', '-i', pth, '-i', o, '-filter_complex',
                            '[1:v]scale=iw:ih[o];[0:v][o]overlay=0:0', tmp])
            os.replace(tmp, pth)
            os.remove(o)
    n = len(glob.glob(os.path.join(out, 'p*.png')))
    cols = 6 if n > 12 else 4
    rows = (n + cols - 1) // cols
    run([cfg['ffmpeg'], '-y', '-loglevel', 'error', '-pattern_type', 'glob', '-i', os.path.join(out, 'p*.png'),
         '-vf', 'tile=%dx%d:padding=4' % (cols, rows), '-frames:v', '1', os.path.join(out, 'sheet.png')])
    print('preview sheet:', os.path.join(out, 'sheet.png'))


def render(cfg, project, shot='all', samples='32', pct='100'):
    blender(cfg, 'bl_render.py', project, 'shot', shot, '--samples', samples, '--pct', pct,
            blend=os.path.join(project, 'build', 'scene.blend'), log='build/render.log')


def assemble(cfg, project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    rep = json.load(open(os.path.join(project, 'build', 'build_report.json')))
    fps = str(tl.get('fps', 24))
    ff = cfg['ffmpeg']
    lst = []
    for s in rep['shots']:
        d = os.path.join(project, 'render', s['name'])
        pngs = sorted(glob.glob(os.path.join(d, 'f*.png')))
        need = s['f1'] - s['f0'] + 1
        if len(pngs) != need:
            sys.exit('shot %s has %d/%d frames - render it again: studio.py render %s --shot %s' %
                     (s['name'], len(pngs), need, project, s['name']))
        clip = os.path.join(project, 'render', s['name'] + '.mp4')
        od = os.path.join(project, 'render', s['name'] + '_ovl')
        inp = [ff, '-y', '-loglevel', 'error', '-framerate', fps, '-start_number', str(s['f0']),
               '-i', os.path.join(d, 'f%04d.png')]
        if rep.get('overlay') and len(glob.glob(os.path.join(od, 'f*.png'))) == need:
            inp += ['-framerate', fps, '-start_number', str(s['f0']), '-i', os.path.join(od, 'f%04d.png'),
                    '-filter_complex', '[0:v][1:v]overlay=0:0:format=auto']
        run(inp + ['-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', fps, clip])
        lst.append("file '%s'" % clip.replace("'", "'\\''"))
    cl = os.path.join(project, 'render', 'concat.txt')
    open(cl, 'w').write('\n'.join(lst) + '\n')
    vid = os.path.join(project, 'render', 'video_only.mp4')
    run([ff, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', cl, '-c', 'copy', vid])
    os.makedirs(os.path.join(project, 'final'), exist_ok=True)
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', tl.get('title', 'video')).strip('_') or 'video'
    out = os.path.join(project, 'final', name + '.mp4')
    mix = os.path.join(project, 'audio', 'mix.wav')
    if os.path.exists(mix):
        run([ff, '-y', '-loglevel', 'error', '-i', vid, '-i', mix, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
             '-ar', '48000', '-shortest', '-movflags', '+faststart', out])
    else:
        shutil.copy(vid, out)
    print('FINAL', out)
    return out


def probe(ff, path):
    t = subprocess.run([ff, '-hide_banner', '-i', path], capture_output=True, text=True).stderr
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', t)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    v = re.search(r'Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) fps', t)
    a = re.search(r'Audio: (\w+).*?, (\d+) Hz', t)
    return {'duration': dur, 'video': v.groups() if v else None, 'audio': a.groups() if a else None}


def check(cfg, project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    ff = cfg['ffmpeg']
    finals = sorted(glob.glob(os.path.join(project, 'final', '*.mp4')), key=os.path.getmtime)
    if not finals:
        sys.exit('no final mp4')
    out = finals[-1]
    info = probe(ff, out)
    res = {'file': out, 'probe': info, 'problems': []}
    if not info['video']:
        res['problems'].append('no video stream')
    else:
        w, h = int(info['video'][1]), int(info['video'][2])
        if [w, h] != list(tl.get('resolution', [1920, 1080])):
            res['problems'].append('resolution %dx%d' % (w, h))
    if abs((info['duration'] or 0) - tl['duration']) > 0.1:
        res['problems'].append('duration %.2f vs planned %.2f' % (info['duration'] or 0, tl['duration']))
    if os.path.exists(os.path.join(project, 'audio', 'mix.wav')) and not info['audio']:
        res['problems'].append('audio missing in final')
    # exact stream durations / frame count
    t = subprocess.run([ff, '-hide_banner', '-i', out, '-map', '0:v', '-f', 'null', '-'], capture_output=True, text=True).stderr
    fr = re.findall(r'frame=\s*(\d+)', t)
    res['video_frames'] = int(fr[-1]) if fr else None
    want = int(round(tl['duration'] * tl.get('fps', 24)))
    if res['video_frames'] != want:
        res['problems'].append('frames %s vs %d' % (res['video_frames'], want))
    t = subprocess.run([ff, '-hide_banner', '-i', out, '-map', '0:a', '-f', 'null', '-'], capture_output=True, text=True).stderr
    m = re.findall(r'time=(\d+):(\d+):([\d.]+)', t)
    if m:
        hh, mm, ss = m[-1]
        res['audio_duration'] = int(hh) * 3600 + int(mm) * 60 + float(ss)
        if abs(res['audio_duration'] - tl['duration']) > 0.08:
            res['problems'].append('audio duration %.3f' % res['audio_duration'])
    # black frames
    t = subprocess.run([ff, '-hide_banner', '-i', out, '-vf', 'blackdetect=d=0.1:pix_th=0.05', '-an', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    res['black_segments'] = re.findall(r'black_start:([\d.]+) black_end:([\d.]+)', t)
    if res['black_segments']:
        res['problems'].append('black frames %s' % res['black_segments'])
    # narration sync: measured onsets in the final audio vs plan
    ar = os.path.join(project, 'audio', 'audio_report.json')
    if os.path.exists(ar):
        a = json.load(open(ar))
        res['voice_sync'] = a['voice_onsets']
        for v in a['voice_onsets']:
            if abs(v['measured'] - v['planned']) > 0.12:
                res['problems'].append('voice line "%s" offset %.2fs' % (v['text'], v['measured'] - v['planned']))
    # A/V sync measured on the final file: cross-correlate its audio with the voice stem
    if cfg.get('audio_python') and os.path.exists(os.path.join(project, 'audio', 'stem_voice.wav')):
        r = subprocess.run([cfg['audio_python'], '-I', os.path.join(HERE, 'audio.py'), 'sync', project, out, ff],
                           capture_output=True, text=True)
        m = re.search(r'SYNC offset_ms=([-\d.]+) corr=([\d.]+)', r.stdout)
        if m:
            res['final_audio_offset_ms'] = float(m.group(1))
            res['final_audio_corr'] = float(m.group(2))
            if abs(float(m.group(1))) > 42:
                res['problems'].append('final audio offset %s ms (> 1 frame)' % m.group(1))
    # contact sheet of the final file (1 frame per second)
    sheet = os.path.join(project, 'final', 'contact_sheet.jpg')
    n = int(tl['duration'])
    cols = 6
    rows = (n + cols - 1) // cols
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', out, '-vf', 'fps=1,scale=480:-1,tile=%dx%d:padding=4' % (cols, rows),
                    '-frames:v', '1', sheet])
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
        doctor(install_tts='--install-tts' in a)
        return
    project = os.path.abspath(pos[0])
    if cmd == 'new':
        new(project, opts.get('--duration', 30), opts.get('--size', '1920x1080'), opts.get('--title'))
        return
    if cmd == 'validate':
        validate(project)
        return
    cfg = load_cfg()
    aud = [cfg.get('audio_python') or sys.executable, '-I', os.path.join(HERE, 'audio.py')]
    if cmd == 'lines':
        if not cfg.get('tts_python'):
            print('No local TTS available: narration must be supplied (audio/narration_supplied.wav).')
            os.makedirs(os.path.join(project, 'audio'), exist_ok=True)
            json.dump({'narration': [], 'dialogue': [], 'warnings': ['tts unavailable']},
                      open(os.path.join(project, 'audio', 'lines.json'), 'w'))
            return
        print(run(aud + ['lines', project]))
    elif cmd == 'build':
        print(blender(cfg, 'bl_build.py', project)[-600:])
    elif cmd == 'qc':
        blender(cfg, 'bl_qc.py', project, pos[1] if len(pos) > 1 else '1', blend=os.path.join(project, 'build', 'scene.blend'),
                log='build/qc.log')
        q = json.load(open(os.path.join(project, 'build', 'qc.json')))
        print(json.dumps({'stats': q['stats'], 'summary': q['summary'], 'framing': q['framing']}, indent=1))
        notes = json.load(open(os.path.join(project, 'build', 'build_report.json')))['notes']
        print('build notes:', json.dumps(notes)[:1500])
    elif cmd == 'mix':
        print(run(aud + ['mix', project]))
    elif cmd == 'preview':
        preview(cfg, project, pos[1] if len(pos) > 1 else 'auto', opts.get('--pct', '30'))
    elif cmd == 'render':
        render(cfg, project, opts.get('--shot', 'all'), opts.get('--samples', '32'), opts.get('--pct', '100'))
    elif cmd == 'assemble':
        assemble(cfg, project)
    elif cmd == 'check':
        check(cfg, project)
    elif cmd == 'all':
        validate(project)
        if cfg.get('tts_python'):
            print(run(aud + ['lines', project]))
        print(blender(cfg, 'bl_build.py', project)[-300:])
        blender(cfg, 'bl_qc.py', project, '2', blend=os.path.join(project, 'build', 'scene.blend'), log='build/qc.log')
        print(run(aud + ['mix', project]))
        render(cfg, project)
        assemble(cfg, project)
        check(cfg, project)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
