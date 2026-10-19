# Blender entry: render shots or preview frames.
#   blender -b <project>/build/scene.blend --python bl_render.py -- <project_dir> shot <name|all> [--samples N] [--pct P]
#   blender -b <project>/build/scene.blend --python bl_render.py -- <project_dir> frames 10,40,72 [--samples N] [--pct P] [--out dir]
import sys, os, json
import bpy
a = sys.argv[sys.argv.index('--') + 1:]
project, mode, what = os.path.abspath(a[0]), a[1], a[2]
opts = {a[i]: a[i + 1] for i in range(3, len(a) - 1) if a[i].startswith('--')}
sc = bpy.context.scene
sc.render.image_settings.media_type = 'IMAGE'
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.render.resolution_percentage = int(opts.get('--pct', 100))
sc.eevee.taa_render_samples = int(opts.get('--samples', 48))
rep = json.load(open(os.path.join(project, 'build', 'build_report.json')))
cams = {m.name: m.camera for m in sc.timeline_markers}


def cam_for(f):
    cur = None
    for s in rep['shots']:
        if s['f0'] <= f:
            cur = s['name']
    return cams[cur]


if mode == 'shot':
    names = [s['name'] for s in rep['shots']] if what == 'all' else what.split(',')
    for s in rep['shots']:
        if s['name'] not in names:
            continue
        d = os.path.join(project, 'render', s['name'])
        os.makedirs(d, exist_ok=True)
        for fn in os.listdir(d):
            if fn.endswith('.png'):
                os.remove(os.path.join(d, fn))
        sc.camera = cams[s['name']]
        # markers would switch cameras; render the shot range with its own camera only
        for m in list(sc.timeline_markers):
            m.camera = cams[s['name']]
        sc.frame_start, sc.frame_end = s['f0'], s['f1']
        sc.render.filepath = os.path.join(d, 'f')
        bpy.ops.render.render(animation=True, scene=sc.name)
        ov = bpy.data.scenes.get('Overlay')
        if ov and rep.get('overlay'):
            od = os.path.join(project, 'render', s['name'] + '_ovl')
            os.makedirs(od, exist_ok=True)
            for fn in os.listdir(od):
                if fn.endswith('.png'):
                    os.remove(os.path.join(od, fn))
            ov.render.image_settings.media_type = 'IMAGE'
            ov.render.image_settings.file_format = 'PNG'
            ov.render.image_settings.color_mode = 'RGBA'
            ov.render.resolution_percentage = sc.render.resolution_percentage
            ov.frame_start, ov.frame_end = s['f0'], s['f1']
            ov.render.filepath = os.path.join(od, 'f')
            bpy.ops.render.render(animation=True, scene=ov.name)
        print('SHOT DONE', s['name'], s['f0'], s['f1'])
else:
    out = opts.get('--out', os.path.join(project, 'preview'))
    os.makedirs(out, exist_ok=True)
    for f in [int(x) for x in what.split(',')]:
        sc.frame_set(f)
        sc.camera = cam_for(f)
        sc.render.filepath = os.path.join(out, 'p%04d.png' % f)
        bpy.ops.render.render(write_still=True, scene=sc.name)
        ov = bpy.data.scenes.get('Overlay')
        if ov and rep.get('overlay'):
            ov.frame_set(f)
            ov.render.resolution_percentage = sc.render.resolution_percentage
            ov.render.image_settings.media_type = 'IMAGE'
            ov.render.image_settings.file_format = 'PNG'
            ov.render.image_settings.color_mode = 'RGBA'
            ov.render.filepath = os.path.join(out, 'o%04d.png' % f)
            bpy.ops.render.render(write_still=True, scene=ov.name)
    print('FRAMES DONE')
