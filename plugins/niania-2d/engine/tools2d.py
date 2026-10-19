"""Helpers that need Pillow: palette extraction, character turnaround sheets, SRT export.

  python tools2d.py palette <image> [x,y x,y ...]        (x,y normalised 0..1)
  python tools2d.py sheet <project> <char_id> [out.png]   (turnaround + expressions + poses of the coded character)
  python tools2d.py srt <project>
"""
import json, os, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geo import Canvas, font                      # noqa: E402
from puppet import Look, draw_character, EXPR, POSES   # noqa: E402
import scene                                       # noqa: E402


def palette(path, pts):
    im = Image.open(path).convert('RGB')
    small = im.copy()
    small.thumbnail((400, 400))
    q = small.quantize(colors=14, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:14 * 3]
    counts = sorted(q.getcolors(), reverse=True)
    print('dominant colours (share, hex):')
    tot = sum(c for c, _ in counts)
    for c, i in counts:
        r, g, b = pal[3 * i:3 * i + 3]
        print('  %5.1f%%  #%02x%02x%02x' % (100 * c / tot, r, g, b))
    for p in pts:
        x, y = (float(v) for v in p.split(','))
        px = im.getpixel((min(im.width - 1, int(x * im.width)), min(im.height - 1, int(y * im.height))))
        # average a small neighbourhood
        box = im.crop((int(x * im.width) - 3, int(y * im.height) - 3, int(x * im.width) + 4, int(y * im.height) + 4))
        avg = tuple(int(sum(c) / len(c)) for c in zip(*box.getdata()))
        print('  sample %s -> #%02x%02x%02x' % (p, *avg))


def neutral_state(expr='neutral', yaw=0.0, poseR='rest', poseL='rest', look=(0, 0)):
    def arm(p):
        el, wr, hand = POSES[p]
        return (el, wr, hand)
    return dict(expr=dict(EXPR[expr]), blink=0, mouth=0, look=look, yaw=yaw, tilt=0, nod=0, sway=0, breath=0,
                arms={'L': arm(poseL), 'R': arm(poseR)})


def sheet(project, cid, out=None):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    L = Look(tl['cast'][cid])
    cells = [('FRONT', neutral_state()), ('TURN LEFT', neutral_state(yaw=-0.6)), ('TURN RIGHT', neutral_state(yaw=0.6)),
             ('SMILE', neutral_state('smile')), ('WORRIED', neutral_state('worried')), ('SURPRISED', neutral_state('surprised')),
             ('EXHAUSTED', neutral_state('exhausted')), ('ANGRY', neutral_state('angry')),
             ('OPEN PALM', neutral_state(poseR='open_palm')), ('POINT', neutral_state(poseR='point')),
             ('HOLD MUG', neutral_state(poseR='hold_mug')), ('THINKING', neutral_state('thinking', poseR='chin'))]
    cw, ch, SS = 520, 640, 2
    cols = 4
    rows = (len(cells) + cols - 1) // cols
    img = Image.new('RGB', (cw * cols * SS, ch * rows * SS), (236, 238, 240))
    for k, (label, st) in enumerate(cells):
        x0, y0 = (k % cols) * cw * SS, (k // cols) * ch * SS
        cell = Image.new('RGB', (cw * SS, ch * SS), (244, 245, 247))
        cv = Canvas(cell, 0.46 * SS, cw * SS * 0.44, 0.62 * ch * SS)
        draw_character(cv, L, st)
        d = ImageDraw.Draw(cell)
        d.text((cw * SS / 2, (ch - 26) * SS), label, font=font('sans', 22 * SS), fill=(40, 46, 60), anchor='mm')
        img.paste(cell, (x0, y0))
        ImageDraw.Draw(img).rectangle([x0, y0, x0 + cw * SS - 1, y0 + ch * SS - 1], outline=(200, 204, 210), width=2)
    img = img.resize((cw * cols, ch * rows), Image.LANCZOS)
    out = out or os.path.join(project, 'preview', 'sheet_%s.png' % cid)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print('SHEET', out)


def srt(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    lines = json.load(open(os.path.join(project, 'audio', 'lines.json')))
    words, chunks = scene.build_captions(lines, tl.get('captions', {}))

    def ts(x):
        return '%02d:%02d:%02d,%03d' % (x // 3600, x % 3600 // 60, int(x % 60), round((x - int(x)) * 1000) % 1000)
    out = []
    for k, ch in enumerate(chunks):
        a = max(0.0, ch[0]['s'] - 0.05)
        b = ch[-1]['ch_end']
        if k + 1 < len(chunks):
            b = min(b, chunks[k + 1][0]['s'] - 0.07)
        out.append('%d\n%s --> %s\n%s\n' % (k + 1, ts(a), ts(b), ' '.join(w['w'] for w in ch)))
    p = os.path.join(project, 'final', 'captions.srt')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write('\n'.join(out))
    print('SRT', p, len(out), 'cues')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'palette':
        palette(sys.argv[2], sys.argv[3:])
    elif cmd == 'sheet':
        sheet(os.path.abspath(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == 'srt':
        srt(os.path.abspath(sys.argv[2]))
