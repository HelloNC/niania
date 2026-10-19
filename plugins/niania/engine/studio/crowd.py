"""Seated crowds (passengers, audiences) as static posed mannequin instances.

A few pose variants are built on the real rig, posed by the Performer, frozen into meshes and
instanced (linked duplicates) on seat anchors. Cheap to render, consistent proportions.

crowd spec (timeline "crowds" list):
  {"name": "pax", "seats": "all" | ["13C", ...], "exclude": ["13A"], "fill": 0.9, "seed": 3,
   "spec": {"body": "mannequin", "material": "clay"},          # base look
   "variants": 4,
   "special": {"13C": {"material": "subject", "color": "#8fb4ff"}}}   # per-seat overrides
Each placed passenger becomes an anchor  "crowd:<name>:<seat>"  (head position) for labels/cameras.
"""
import math
import random
import bpy
from mathutils import Vector, Matrix, Quaternion
from . import character
from .perform import Performer


class _NullWorld:
    frame = 1
    cameras = {}

    def resolve_point(self, spec, t):
        return None

    def held_by(self, *a):
        return None

    def grasp_target(self, *a):
        return None


def _snapshot(name, spec, pose, col):
    """Build a character, pose it seated (pose: dict of tweaks), freeze to a mesh. Returns (mesh, head_offset)."""
    tmp = bpy.data.collections.new('tmp_' + name)
    bpy.context.scene.collection.children.link(tmp)
    rig, body, face = character.build_character(name, spec, tmp)
    p = Performer(name, rig, bpy.context.scene)
    p.sit(0.0, 0.01, seat=(0, 0, 0.47), facing=-90.0)
    p.auto_blink = False
    p.bend(0.0, 0.01, 'head', tuple(pose.get('head', (0, 0, 0))))
    p.bend(0.0, 0.01, 'chest', tuple(pose.get('chest', (0, 0, 0))))
    for s in 'LR':
        p.hand(0.0, 0.01, s, dict(pose.get('hand_' + s, {'preset': 'lap'})))
        p.grip_(0.0, 0.01, s, pose.get('grip', 0.25))
    p.springs = {}
    p.evaluate(1, 0.0, 1 / 24, _NullWorld())
    basis, props = p.out[1]
    for b, M in basis.items():
        pb = rig.pose.bones[b]
        pb.matrix_basis = M
    for k, v in props.items():
        rig[k] = v
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(body.evaluated_get(dg), preserve_all_data_layers=False, depsgraph=dg)
    me.name = name + '_mesh'
    hb = rig.pose.bones['head']
    head = rig.matrix_world @ (hb.matrix @ Vector((0, 0.18, 0)))
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    return me, head


def build_crowd(cs, anchors, col):
    seats = {s['id']: s for s in anchors.get('seats', [])}
    want = list(seats) if cs.get('seats', 'all') == 'all' else list(cs['seats'])
    excl = set(cs.get('exclude', []))
    rnd = random.Random(cs.get('seed', 1))
    nvar = cs.get('variants', 4)
    base = {'body': 'mannequin', 'material': 'clay'}
    base.update(cs.get('spec', {}))
    poses = [
        {'head': (0, 0, 0)},
        {'head': (6, 0, 12), 'chest': (0, 0, 4)},
        {'head': (-4, 4, -10), 'hand_L': {'rel': 'hips', 'pos': (0.2, 0.18, 0.18), 'fingers': (0, 1, -0.3), 'palm': (-1, 0, -0.4)}},
        {'head': (10, -3, 0), 'chest': (6, 0, 0)},
        {'head': (2, 6, 18)},
    ]
    meshes = {}
    placed = {}

    def mesh_for(key, spec, pose_i):
        if key not in meshes:
            meshes[key] = _snapshot('%s_v%s' % (cs['name'], key), spec, poses[pose_i % len(poses)], col)
        return meshes[key]
    for sid in want:
        if sid in excl or sid not in seats:
            continue
        sp = cs.get('special', {}).get(sid)
        if not sp and rnd.random() > cs.get('fill', 1.0):
            continue
        vi = rnd.randrange(nvar)
        if sp:
            spec = dict(base)
            spec.update(sp)
            key = sid
        else:
            spec, key = base, 'v%d' % vi
        me, head = mesh_for(key, spec, vi)
        s = seats[sid]
        ob = bpy.data.objects.new('%s_%s' % (cs['name'], sid), me)
        col.objects.link(ob)
        yaw = math.radians(s['facing'] + 90.0)
        ob.matrix_world = Matrix.Translation((s['pos'][0], s['pos'][1], 0.0)) @ Matrix.Rotation(yaw, 4, 'Z')
        if spec.get('material') == 'ghost':
            ob.visible_shadow = False
        placed['crowd:%s:%s' % (cs['name'], sid)] = list(ob.matrix_world @ head)
    return placed
