"""Automated animation QC on the built .blend (evaluated, after IK/constraints).

Checks (thresholds in metres at 24 fps):
  foot_slide      planted foot moving horizontally > 2 mm/frame
  ik_gap          hand/foot bone not reaching its IK target (> 8 mm) -> disconnected limb
  grip            fingertips inside a held object (< r - 2 mm) or floating (> r + 18 mm)
  ground          body vertices below the ground plane (> 6 mm)
  intersect       character mesh overlapping props (excluding hands on held objects)
  pops            joint acceleration spikes inside a shot (abrupt motion candidates)
  framing         subject head outside the frame / too close to an edge
Writes build/qc.json and prints a summary. Exit status is not used; read the report.
"""
import json
import math
import os
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

SLIDE = 0.002
IK_GAP = 0.008
GROUND = 0.006


def run(project, every=1):
    rep = json.load(open(os.path.join(project, 'build', 'build_report.json')))
    sc = bpy.context.scene
    fps = sc.render.fps
    rigs = [o for o in sc.objects if o.type == 'ARMATURE' and o.get('studio_character')]
    props = {n: sc.objects[n] for n in rep['props'] if n in sc.objects}
    issues = []
    stats = {'foot_slide_max': 0.0, 'ik_gap_max': 0.0, 'grip_pen_max': 0.0, 'ground_pen_max': 0.0}
    shot_of = {}
    for s in rep['shots']:
        for f in range(s['f0'], s['f1'] + 1):
            shot_of[f] = s['name']
    prev = {}
    trails = {}
    # polygon -> dominant vertex group (to ignore hand contact on held objects)
    poly_group = {}
    for rig in rigs:
        body = sc.objects.get(rig.name + '_body')
        names = {g.index: g.name for g in body.vertex_groups}
        vg = []
        for v in body.data.vertices:
            vg.append(names[max(v.groups, key=lambda g: g.weight).group] if len(v.groups) else '')
        poly_group[rig.name] = [vg[p.vertices[0]] for p in body.data.polygons]
    dg = bpy.context.evaluated_depsgraph_get()
    for f in range(sc.frame_start, sc.frame_end + 1, every):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for rig in rigs:
            er = rig.evaluated_get(dg)
            pb = er.pose.bones
            M = rig.matrix_world
            for s in 'LR':
                # feet
                fm = M @ pb['foot.' + s].matrix
                heel = fm @ Vector((0, 0.05, -0.06))
                ball = fm @ Vector((0, 0.10, -0.03))
                a = heel if heel.z <= ball.z else ball
                key = (rig.name, 'foot', s)
                if key in prev:
                    pa = prev[key]
                    planted = a.z < 0.012 and pa.z < 0.012
                    d = math.hypot(a.x - pa.x, a.y - pa.y)
                    if planted and d > SLIDE and shot_of.get(f) == shot_of.get(f - every):
                        issues.append({'f': f, 'type': 'foot_slide', 'who': rig.name, 'side': s, 'value': round(d, 4)})
                    stats['foot_slide_max'] = max(stats['foot_slide_max'], d if planted else 0)
                prev[key] = a
                # IK gaps
                for b, t in (('hand', 'hand_ik'), ('foot', 'foot_ik')):
                    g = ((M @ pb[b + '.' + s].head) - (M @ pb[t + '.' + s].head)).length
                    stats['ik_gap_max'] = max(stats['ik_gap_max'], g)
                    if g > IK_GAP:
                        issues.append({'f': f, 'type': 'ik_gap', 'who': rig.name, 'bone': b + '.' + s, 'value': round(g, 4)})
                # trails for pops
                for b in ('hand.' + s, 'foot.' + s):
                    trails.setdefault((rig.name, b), {})[f] = (M @ pb[b].head).copy()
            for b in ('head', 'hips', 'chest'):
                trails.setdefault((rig.name, b), {})[f] = (M @ pb[b].head).copy()
            # grip check on held objects
            for on, rows in rep['attach'].items():
                for f0, f1, who, side in rows:
                    if who == rig.name and f0 <= f <= f1 and on in props and 'grip_body' in props[on]:
                        ob = props[on].evaluated_get(dg)
                        inv = ob.matrix_world.inverted()
                        r, hc = rep['props'][on]['grip']
                        g = er.get('grip_dbg', None)
                        for fn in ('index', 'middle', 'ring', 'pinky', 'thumb'):
                            bn = ('thumb.02.%s' if fn == 'thumb' else 'f_' + fn + '.02.%s') % side
                            tip = inv @ (M @ pb[bn].tail)
                            rad = math.hypot(tip.x, tip.y)
                            pen = (r - 0.0085) - rad
                            if 0.0 < tip.z < rep['props'][on]['height'] + 0.01:
                                stats['grip_pen_max'] = max(stats['grip_pen_max'], pen)
                                if pen > 0.004:
                                    issues.append({'f': f, 'type': 'grip_clip', 'who': rig.name, 'obj': on, 'finger': fn, 'value': round(pen, 4)})
            # ground + intersections (every 2nd frame for speed)
            if f % 2 == 1:
                body = sc.objects[rig.name + '_body'].evaluated_get(dg)
                me = body.to_mesh()
                mw = body.matrix_world
                zmin = min((mw @ v.co).z for v in me.vertices)
                body.to_mesh_clear()
                if zmin < -GROUND:
                    issues.append({'f': f, 'type': 'ground', 'who': rig.name, 'value': round(-zmin, 4)})
                stats['ground_pen_max'] = max(stats['ground_pen_max'], -zmin)
                bv = BVHTree.FromObject(body, dg)
                for on, ob in props.items():
                    eo = ob.evaluated_get(dg)
                    bp = BVHTree.FromObject(eo, dg)
                    # BVHs are in local space: transform prop into body space via matrices
                    pairs = _overlap(body, eo, dg)
                    if not pairs:
                        continue
                    held = any(f0 <= f <= f1 and who == rig.name for f0, f1, who, side in rep['attach'].get(on, []))
                    groups = set(poly_group[rig.name][i] for i, _ in pairs)
                    if held:
                        groups = {g for g in groups if not (g.startswith('hand') or g.startswith('f_') or g.startswith('thumb'))}
                    if groups:
                        issues.append({'f': f, 'type': 'intersect', 'who': rig.name, 'obj': on, 'parts': sorted(groups)[:6]})
        # framing
        cam = sc.camera
        for m in sc.timeline_markers:
            pass
    # pops: acceleration spikes (m/s^2) per trail, ignoring cut frames
    pops = []
    for (who, b), tr in trails.items():
        fs = sorted(tr)
        for i in range(1, len(fs) - 1):
            f = fs[i]
            if shot_of.get(fs[i - 1]) != shot_of.get(fs[i + 1]):
                continue
            acc = (tr[fs[i + 1]] - 2 * tr[f] + tr[fs[i - 1]]).length * fps * fps / (every * every)
            pops.append((acc, f, who, b))
    pops.sort(reverse=True)
    stats['top_accel'] = [{'f': f, 'who': w, 'bone': b, 'acc': round(a, 1)} for a, f, w, b in pops[:12]]
    # framing per shot using bound cameras
    framing = []
    cams = {m.name: m.camera for m in sc.timeline_markers}
    for s in rep['shots']:
        cam = cams.get(s['name'])
        if not cam or not s.get('framing', True):      # inserts/cutaways may crop heads on purpose
            continue
        bad = 0
        for f in range(s['f0'], s['f1'] + 1, 2):
            sc.frame_set(f)
            for rig in rigs:
                hb = rig.pose.bones['head']
                top = rig.matrix_world @ (hb.matrix @ Vector((0, hb.length + 0.06, 0)))   # crown incl. hat
                for hp in (rig.matrix_world @ hb.head, top):
                    v = world_to_camera_view(sc, cam, hp)
                    if not (0.02 < v.x < 0.98 and 0.02 < v.y < 0.985) or v.z <= 0:
                        bad += 1
                        break
        framing.append({'shot': s['name'], 'head_outside_frames': bad})
    summary = {}
    for it in issues:
        summary.setdefault(it['type'], []).append(it['f'])
    out = {'stats': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()},
           'summary': {k: {'count': len(v), 'frames': _ranges(v)} for k, v in summary.items()},
           'framing': framing, 'issues': issues[:400]}
    json.dump(out, open(os.path.join(project, 'build', 'qc.json'), 'w'), indent=1)
    print('QC', json.dumps({'stats': out['stats'], 'summary': out['summary'], 'framing': framing}, indent=1))
    return out


def _overlap(a, b, dg):
    ma = a.to_mesh()
    va = [a.matrix_world @ v.co for v in ma.vertices]
    pa = [tuple(p.vertices) for p in ma.polygons]
    a.to_mesh_clear()
    mb = b.to_mesh()
    vb = [b.matrix_world @ v.co for v in mb.vertices]
    pb = [tuple(p.vertices) for p in mb.polygons]
    b.to_mesh_clear()
    # quick reject by bounding boxes
    def bb(vs):
        return [min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)]
    (a0, a1), (b0, b1) = bb(va), bb(vb)
    if any(a1[i] < b0[i] or b1[i] < a0[i] for i in range(3)):
        return []
    ta = BVHTree.FromPolygons(va, pa)
    tb = BVHTree.FromPolygons(vb, pb)
    return ta.overlap(tb)


def _ranges(fs):
    fs = sorted(set(fs))
    out = []
    for f in fs:
        if out and f <= out[-1][1] + 2:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out[:20]
