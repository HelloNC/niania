"""timeline.json -> animated .blend (characters, props, set, cameras, fx, audio strip).

Run inside Blender:
  blender -b --factory-startup --python engine/tools/bl_build.py -- <project_dir>
"""
import json
import math
import os
import bpy
from mathutils import Vector, Matrix, Quaternion
from bpy_extras import anim_utils
from . import character, props, sets, materials, geom, camera, fx
from .perform import Performer
from .world import World
from .util import DEG


# ----------------------------------------------------------------------------- keys
class KeyWriter:
    """Collects per-frame values then writes LINEAR f-curves in one go (Blender 5 slotted actions)."""

    def __init__(self):
        self.data = {}      # id -> {(path, index): {frame: value}}

    def put(self, idb, path, index, f, v):
        self.data.setdefault(idb, {}).setdefault((path, index), {})[f] = v

    def put_matrix(self, idb, prefix, f, M, scale=True):
        loc, rot, sc = M.decompose()
        for i in range(3):
            self.put(idb, prefix + 'location', i, f, loc[i])
        for i in range(4):
            self.put(idb, prefix + 'rotation_quaternion', i, f, rot[i])
        if scale:
            for i in range(3):
                self.put(idb, prefix + 'scale', i, f, sc[i])

    def flush(self):
        for idb, chans in self.data.items():
            ad = idb.animation_data or idb.animation_data_create()
            act = bpy.data.actions.new(idb.name + '_anim')
            ad.action = act
            slot = act.slots.new(id_type='OBJECT' if isinstance(idb, bpy.types.Object) else 'CAMERA', name=idb.name)
            ad.action_slot = slot
            cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)
            # quaternion hemisphere continuity
            quat_groups = {}
            for (path, idx) in chans:
                if path.endswith('rotation_quaternion'):
                    quat_groups.setdefault(path, True)
            for path in quat_groups:
                frames = sorted(chans[(path, 0)])
                prev = None
                for f in frames:
                    q = Quaternion([chans[(path, i)][f] for i in range(4)])
                    if prev is not None and q.dot(prev) < 0:
                        q.negate()
                        for i in range(4):
                            chans[(path, i)][f] = q[i]
                    prev = q
            for (path, idx), fv in chans.items():
                fc = cb.fcurves.new(path, index=idx)
                frames = sorted(fv)
                fc.keyframe_points.add(len(frames))
                co = []
                for f in frames:
                    co += [f, fv[f]]
                fc.keyframe_points.foreach_set('co', co)
                fc.keyframe_points.foreach_set('interpolation', [1] * len(frames))
                fc.update()


# ----------------------------------------------------------------------------- scene setup
def setup_scene(tl, nframes):
    sc = bpy.context.scene
    fps = tl.get('fps', 24)
    sc.render.fps = fps
    sc.frame_start, sc.frame_end = 1, nframes
    w, h = tl.get('resolution', [1920, 1080])
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.engine = 'BLENDER_EEVEE'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = tl.get('motion_blur', 0.45)
    sc.render.filter_size = 1.2
    try:
        sc.eevee.taa_render_samples = 32
        sc.eevee.use_shadows = True
        sc.eevee.shadow_ray_count = 2
        sc.eevee.shadow_step_count = 8
    except Exception:
        pass
    try:
        sc.render.use_simplify = False
    except Exception:
        pass
    setup_compositor(sc, tl.get('post', {}))
    return sc


def setup_compositor(sc, post):
    """Bloom (glare) + gentle vignette. Blender 5 uses scene.compositing_node_group."""
    try:
        ng = bpy.data.node_groups.new('StudioPost', 'CompositorNodeTree')
        ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        rl = ng.nodes.new('CompositorNodeRLayers')
        out = ng.nodes.new('NodeGroupOutput')
        gl = ng.nodes.new('CompositorNodeGlare')
        if 'Type' in gl.inputs:
            gl.inputs['Type'].default_value = 'Bloom'
        else:
            gl.glare_type = 'BLOOM'
        for k, v in (('Threshold', post.get('bloom_threshold', 0.85)), ('Strength', post.get('bloom', 0.35)),
                     ('Size', 0.6)):
            if k in gl.inputs:
                try:
                    gl.inputs[k].default_value = v
                except Exception:
                    pass
        ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
        ng.links.new(gl.outputs['Image'], out.inputs['Image'])
        sc.compositing_node_group = ng
        sc.render.use_compositing = True
    except Exception as e:
        print('compositor setup skipped:', e)


# ----------------------------------------------------------------------------- generated verbs
def object_events(tl, world):
    """Hand verbs implied by object motion (place/catch/held)."""
    evs = []
    for name, o in world.objs.items():
        for i, s in enumerate(o.segs):
            if s['do'] == 'place':
                side = s.get('side') or world._holder_side(o, i)
                char = s.get('char') or world._holder(o, i)
                spec = {'hold': name, 'at': list(s['pos']), 'orient': 'upright', 'arc': s.get('arc', 0.08)}
                evs.append({'char': char, 'do': 'hand', 't': s['t'], 'dur': s.get('dur', 0.5), 'side': side,
                            'spec': spec, 'ease': s.get('ease', 'inout')})
                rel = s.get('release', 0.18)
                evs.append({'char': char, 'do': 'grip', 't': s['t'] + s.get('dur', 0.5) + 0.06, 'dur': rel, 'side': side,
                            'amount': 0.0})
                evs.append({'char': char, 'do': 'spread', 't': s['t'] + s.get('dur', 0.5), 'dur': rel, 'side': side,
                            'amount': 0.5})
                evs.append({'char': char, 'do': 'hand', 't': s['t'] + s.get('dur', 0.5) + 0.02, 'dur': 0.22,
                            'side': side, 'ease': 'out',
                            'spec': {'release_from': name, 'idx': world._attach_idx(o, i), 'back': s.get('back', 0.07)}})
            elif s['do'] == 'catch':
                side, char = s.get('side', 'R'), s['char']
                ap = s.get('approach', 0.45)
                t = s['t']
                evs.append({'char': char, 'do': 'spread', 't': t - ap, 'dur': 0.18, 'side': side, 'amount': 1.0})
                evs.append({'char': char, 'do': 'grip', 't': t - ap, 'dur': 0.15, 'side': side, 'amount': 0.0})
                evs.append({'char': char, 'do': 'hand', 't': t - ap, 'dur': ap, 'side': side,
                            'spec': {'object': name, 'grip': 'body', 'at': t, 'char': char}, 'ease': s.get('ease', 'inout')})
                evs.append({'char': char, 'do': 'grip', 't': t - 0.04, 'dur': s.get('close', 0.1), 'side': side, 'amount': 1.0, 'ease': 'out'})
                evs.append({'char': char, 'do': 'spread', 't': t - 0.04, 'dur': 0.1, 'side': side, 'amount': 0.0})
                give = s.get('give', 0.05)
                if give:
                    M = world.free_matrix(o, t - 1e-4)
                    M1 = world.free_matrix(o, t - 0.03)
                    v = (M.translation - M1.translation)
                    v = v.normalized() if v.length > 1e-6 else Vector((0, 0, -1))
                    p = M.translation + v * give
                    evs.append({'char': char, 'do': 'hand', 't': t, 'dur': s.get('give_dur', 0.3), 'side': side,
                                'spec': {'hold': name, 'at': list(p), 'orient': 'keep'}, 'ease': 'out'})
    return evs


def apply_light_cues(tl, fps):
    """`light_cues`: [[t, level], ...] (level 0 = room lights off, 1 = on), stepped (constant keys).
    Room lights, world and tagged emissive materials (`lamp_emit`) scale with the level (down to
    `light_dim`); lights tagged `night` fade the other way, so the dark state stays readable."""
    cues = tl.get('light_cues')
    if not cues:
        return
    dim = tl.get('light_dim', 0.0)
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = 'CONSTANT'
    try:
        for o in [o for o in bpy.data.objects if o.type == 'LIGHT']:
            base = o.data.energy
            night = bool(o.get('night') or o.data.get('night'))
            for t, lvl in cues:
                o.data.energy = base * ((1 - lvl) if night else (dim + (1 - dim) * lvl))
                o.data.keyframe_insert('energy', frame=int(round(t * fps)) + 1)
        w = bpy.context.scene.world
        bg = w.node_tree.nodes.get('Background') if w and w.use_nodes else None
        if bg:
            base = bg.inputs['Strength'].default_value
            wd = tl.get('world_dim', 0.04)
            for t, lvl in cues:
                bg.inputs['Strength'].default_value = base * (wd + (1 - wd) * lvl)
                bg.inputs['Strength'].keyframe_insert('default_value', frame=int(round(t * fps)) + 1)
        for m in bpy.data.materials:
            if 'lamp_emit' in m.keys() and m.use_nodes:
                b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if b is None:
                    continue
                for t, lvl in cues:
                    b.inputs['Emission Strength'].default_value = m['lamp_emit'] * lvl
                    b.inputs['Emission Strength'].keyframe_insert('default_value', frame=int(round(t * fps)) + 1)
    finally:
        prefs.keyframe_new_interpolation_type = old


# ----------------------------------------------------------------------------- main
def build(project):
    tl = json.load(open(os.path.join(project, 'timeline.json')))
    fps = tl.get('fps', 24)
    nframes = int(round(tl['duration'] * fps))
    # clean factory scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    sc = setup_scene(tl, nframes)
    materials.set_style(tl.get('style', 'cel'))
    set_info = sets.build_set(tl.get('set', {}))
    anchors = {}
    ainfo = set_info.get('anchors', {}) or {}
    for st in ainfo.get('seats', []) + ainfo.get('pilot_seats', []):
        anchors['seat:' + st['id']] = st
    for k, v in ainfo.items():
        if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
            anchors[k] = v
    if tl.get('style') in ('clay', 'smooth'):
        if tl.get('tonemap', 'agx' if tl.get('style') == 'smooth' else 'standard') == 'agx':
            sc.view_settings.view_transform = 'AgX'
            for lk in (tl.get('look_transform', 'AgX - Punchy'), 'Punchy', 'AgX - Medium High Contrast'):
                try:
                    sc.view_settings.look = lk
                    break
                except Exception:
                    pass
        else:
            sc.view_settings.view_transform = 'Standard'
        sc.view_settings.exposure = tl.get('exposure', -0.35 if tl.get('style') == 'clay' else 0.0)
    if 'look' in tl:
        materials.set_look(**tl['look'])
    cast_col = bpy.data.collections.new('cast')
    sc.collection.children.link(cast_col)
    prop_col = bpy.data.collections.new('props')
    sc.collection.children.link(prop_col)
    cam_col = bpy.data.collections.new('cameras')
    sc.collection.children.link(cam_col)
    fx_col = bpy.data.collections.new('fx')
    sc.collection.children.link(fx_col)

    # crowds (static seated instances) become anchors too
    if tl.get('crowds'):
        from . import crowd
        crowd_col = bpy.data.collections.new('crowds')
        sc.collection.children.link(crowd_col)
        for cs in tl['crowds']:
            anchors.update(crowd.build_crowd(cs, ainfo, crowd_col))

    def seat_of(v):
        if isinstance(v, str):
            a = anchors['seat:' + v] if ('seat:' + v) in anchors else anchors[v]
            return a['pos'], a.get('facing', -90.0)
        return v, None

    perfs, rigs = {}, {}
    for name, spec in tl['cast'].items():
        rig, body, face = character.build_character(name, spec, cast_col)
        rigs[name] = rig
        perfs[name] = Performer(name, rig, sc)
        perfs[name].auto_blink = spec.get('autoblink', True)
        st = spec.get('start', {})
        if 'seat' in st:
            pos, fac = seat_of(st['seat'])
            perfs[name].sit(0.0, 0.01, seat=pos, facing=st.get('facing', fac if fac is not None else -90.0),
                            **{k: v for k, v in st.items() if k in ('feet_fwd', 'width', 'lean')})
        else:
            perfs[name].stance(0.0, st.get('pos', (0, 0)), st.get('facing', -90), st.get('width', 0.2))
    objs = {}
    for name, spec in tl.get('props', {}).items():
        spec = dict(spec, _project=project)
        objs[name] = props.build_prop(name, spec, prop_col)
    world = World(tl, objs, perfs, fps)
    world.anchors = {k: (v['pos'] if isinstance(v, dict) else v) for k, v in anchors.items()}

    def rt(lst):
        out = []
        for e in lst:
            e = dict(e)
            e['t'] = world.time(e['t'])
            out.append(e)
        return out
    tl['fx'] = rt(tl.get('fx', []))
    for sh in tl['shots']:
        sh['start'], sh['end'] = world.time(sh['start']), world.time(sh['end'])
        for k in sh['keys']:
            k['t'] = world.time(k['t'])
    events = rt(tl.get('performance', [])) + object_events(tl, world)
    for ev in events:
        if ev.get('do') == 'sit' and isinstance(ev.get('seat'), str):
            pos, fac = seat_of(ev['seat'])
            ev['seat'] = pos
            ev.setdefault('facing', fac)
    events.sort(key=lambda e: e['t'])
    for ev in events:
        perfs[ev['char']].apply(ev)

    # dialogue lip-sync envelopes from the audio step (optional)
    lines_path = os.path.join(project, 'audio', 'lines.json')
    mouth = {n: {} for n in perfs}
    if os.path.exists(lines_path):
        for ln in json.load(open(lines_path)).get('dialogue', []):
            if ln.get('char') in mouth:
                for i, v in enumerate(ln['env']):
                    f = int(round(ln['start'] * fps)) + 1 + i
                    mouth[ln['char']][f] = max(mouth[ln['char']].get(f, 0), v)

    shots = [camera.Shot(s) for s in tl['shots']]
    dt = 1.0 / fps
    for f in range(1, nframes + 1):
        t = (f - 1) / fps
        world.frame = f
        world.cameras['active'] = camera.camera_world_pos(shots, t)
        for n, p in perfs.items():
            p.evaluate(f, t, dt, world)
            if f in mouth[n]:
                bas, pr = p.out[f]
                pr['open'] = min(1.0, pr['open'] + mouth[n][f] * 0.9)
        world.update_objects(f, t)

    # ---- write keys
    kw = KeyWriter()
    for n, p in perfs.items():
        rig = rigs[n]
        for f, (basis, pr) in p.out.items():
            for b, M in basis.items():
                pre = 'pose.bones["%s"].' % b
                loc, rot, _ = M.decompose()
                if b in ('hips',) or b.startswith('foot_ik') or b.startswith('hand_ik'):
                    for i in range(3):
                        kw.put(rig, pre + 'location', i, f, loc[i])
                for i in range(4):
                    kw.put(rig, pre + 'rotation_quaternion', i, f, rot[i])
            for k, v in pr.items():
                kw.put(rig, '["%s"]' % k, 0, f, v)
    for n, o in world.objs.items():
        o.ob.rotation_mode = 'QUATERNION'
        for f, M in o.mats.items():
            kw.put_matrix(o.ob, '', f, M, scale=False)

    cams = camera.create_objects(shots, cam_col)
    camdata = camera.compute(shots, world, fps, nframes)
    for sh in shots:
        ob = cams[sh.name]
        ob.rotation_mode = 'QUATERNION'
        for f, (M, lens, fd) in camdata[sh.name].items():
            kw.put_matrix(ob, '', f, M, scale=False)
            kw.put(ob.data, 'lens', 0, f, lens)
            if ob.data.dof.use_dof:
                kw.put(ob.data, 'dof.focus_distance', 0, f, fd)
    # per-shot visibility ("hide": [object names] and/or "variant": name from the set's anchors['variants'])
    variants = ainfo.get('variants', {})
    hide_by_shot, hide_names = {}, set()
    for sh_spec, sh in zip(tl['shots'], shots):
        hs = set(sh_spec.get('hide', [])) | set(variants.get(sh_spec.get('variant'), []))
        hide_by_shot[sh.name] = hs
        hide_names |= hs
    if hide_names:
        shot_at = {}
        for sh in shots:
            for f in range(int(round(sh.start * fps)) + 1, int(round(sh.end * fps)) + 1):
                shot_at[f] = sh.name
        def matches(nm):
            if nm.endswith('*'):
                return [o for o in bpy.data.objects if o.name.startswith(nm[:-1])]
            o = bpy.data.objects.get(nm)
            return [o] if o else []
        for nm in hide_names:
            obs = matches(nm)
            if not obs:
                print('WARNING hide: no object', nm)
            for ob in obs:
                for f in range(1, nframes + 1):
                    hs = hide_by_shot.get(shot_at.get(f, shots[0].name), set())
                    hidden = any((h.endswith('*') and ob.name.startswith(h[:-1])) or h == ob.name for h in hs)
                    kw.put(ob, 'hide_render', 0, f, 1.0 if hidden else 0.0)

    # markers bind cameras at cuts
    for sh in shots:
        m = sc.timeline_markers.new(sh.name, frame=int(round(sh.start * fps)) + 1)
        m.camera = cams[sh.name]
    sc.camera = cams[shots[0].name]

    # ---- broadcast graphics overlay (separate transparent scene)
    from . import graphics
    ovl = graphics.build(tl, world, camdata, shots, fps, nframes, sc, kw)

    # ---- fx
    parts = fx.flatten(fx.simulate(world, tl.get('fx', []), nframes))
    for pt in parts:
        if pt['kind'] == 'splat':
            vis = [f for f, (M, v) in sorted(pt['frames'].items()) if v > 0]
            if vis:
                world.events['splat:' + pt['name']] = (vis[0] - 1) / fps
        if pt['kind'] == 'drop':
            ob = props.droplet(pt['name'], fx_col, 0.0065 * pt['size'], tl.get('liquid', '#4a2a17'))
        else:
            ob = props.splat(pt['name'], fx_col, 0.018 * pt['size'], tl.get('liquid_splat', '#3b2213'))
        ob.rotation_mode = 'QUATERNION'
        for f, (M, vis) in pt['frames'].items():
            loc, rot, scl = M.decompose()
            M2 = Matrix.LocRotScale(loc, rot, scl * max(vis, 1e-4))
            kw.put_matrix(ob, '', f, M2)
    kw.flush()

    # ---- audio strip for preview inside Blender
    mix = os.path.join(project, 'audio', 'mix.wav')
    if os.path.exists(mix):
        se = sc.sequence_editor_create()
        try:
            se.strips.new_sound('mix', mix, 1, 1)
        except Exception as e:
            print('audio strip skipped', e)

    attach = {}
    # deliberate hand contacts with set objects ({"on": obj} hand specs) are treated like holds by QC
    for n, p in perfs.items():
        for sd in 'LR':
            rows = []
            for f in range(1, nframes + 1):
                sa, sb, u = p.hands[sd].state((f - 1) / fps)
                spec = sb if u > 0.5 else sa
                obj = (spec.get('on') or spec.get('twist')) if isinstance(spec, dict) else None
                if obj:
                    if rows and rows[-1][1] == f - 1 and rows[-1][4] == obj:
                        rows[-1][1] = f
                    else:
                        rows.append([f, f, n, sd, obj])
            for r in rows:
                attach.setdefault(r[4], []).append(r[:4])
    for n, o in world.objs.items():
        rows = []
        for f in range(1, nframes + 1):
            a = world.is_attached(o, (f - 1) / fps)
            if a:
                if rows and rows[-1][1] == f - 1 and rows[-1][2:] == [a[0], a[1]]:
                    rows[-1][1] = f
                else:
                    rows.append([f, f, a[0], a[1]])
        attach.setdefault(n, []).extend(rows)
    report = {'frames': nframes, 'fps': fps, 'attach': attach, 'overlay': bool(tl.get('graphics')),
              'props': {n: {'radius': o.radius, 'height': o.height, 'grip': list(o.grip)} for n, o in world.objs.items()},
              'shots': [{'name': s.name, 'start': s.start, 'end': s.end, 'framing': s.spec.get('framing', True),
                         'f0': int(round(s.start * fps)) + 1, 'f1': int(round(s.end * fps))} for s in shots],
              'notes': {n: sorted(set(x[1] for x in p.notes)) for n, p in perfs.items()},
              'events': dict(world.events, **{'step:%s:%s:%d' % (n, e[1], i): e[2] for n, p in perfs.items()
                                                for i, e in enumerate(p.events)}),
              'note_frames': {n: [x for x in p.notes] for n, p in perfs.items()}}
    os.makedirs(os.path.join(project, 'build'), exist_ok=True)
    json.dump(report, open(os.path.join(project, 'build', 'build_report.json'), 'w'), indent=1)
    apply_light_cues(tl, fps)
    sc.frame_set(1)
    out = os.path.join(project, 'build', 'scene.blend')
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print('BUILD OK', out, report['notes'])
    return out
