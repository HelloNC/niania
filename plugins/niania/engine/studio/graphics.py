"""Broadcast-style graphics overlay (explainer / news reconstruction look).

Rendered as a separate transparent 'Overlay' scene (orthographic, 1 unit = 1 pixel, origin bottom-left)
and composited over each shot by `studio.py assemble`. Items pinned to 3D anchors are projected
through the shot camera every frame, so labels follow characters and objects.

timeline "graphics": [
  {"type": "tag",     "t": [0.6, 3.6], "title": "ADAM POLO", "sub": "PASSENGER · ROW 13",
                      "anchor": {"anchor": "crowd:pax:13C"}, "offset": [-40, 70]},
  {"type": "callout", "t": [1, 4], "text": "DRONE", "anchor": {"object": "drone"}, "offset": [90, 0], "color": "#e3322b"},
  {"type": "title",   "t": [4, 9], "text": "WHAT HAPPENED NEXT", "pos": "top_right"},
  {"type": "stamp",   "t": [0, 3], "text": "07:05 · DXB", "pos": "bottom_left"},
  {"type": "badge",   "t": [0, 4], "text": "RECONSTRUCTION", "pos": "top_right"}
]   (t entries may be event strings like "catch:cup+0.2")
"""
import math
import os
import bpy
from mathutils import Vector, Matrix
from .util import srgb, ease, clamp

FONTS = {
    'bold': ['/System/Library/Fonts/Supplemental/Arial Black.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'],
    'sans': ['/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'],
    'mono': ['/System/Library/Fonts/SFNSMono.ttf', '/System/Library/Fonts/Supplemental/Courier New Bold.ttf',
             '/System/Library/Fonts/Supplemental/Andale Mono.ttf'],
    'condensed': ['/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'],
}


def font(kind):
    for p in FONTS[kind]:
        if os.path.exists(p):
            return bpy.data.fonts.load(p, check_existing=True)
    return bpy.data.fonts[0] if bpy.data.fonts else None


def emat(name, color, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = srgb(color)
    if alpha < 1:
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader')
        mx.inputs[0].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs['Surface'])
        m.surface_render_method = 'BLENDED'
    else:
        nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m


class Overlay:
    def __init__(self, main_scene):
        W, H = main_scene.render.resolution_x, main_scene.render.resolution_y
        self.W, self.H = W, H
        sc = bpy.data.scenes.get('Overlay') or bpy.data.scenes.new('Overlay')
        self.sc = sc
        sc.render.resolution_x, sc.render.resolution_y = W, H
        sc.render.resolution_percentage = 100
        sc.render.fps = main_scene.render.fps
        sc.frame_start, sc.frame_end = main_scene.frame_start, main_scene.frame_end
        sc.render.engine = 'BLENDER_EEVEE'
        sc.render.film_transparent = True
        sc.render.use_motion_blur = False
        sc.view_settings.view_transform = 'Standard'
        sc.render.image_settings.color_mode = 'RGBA'
        try:
            sc.eevee.taa_render_samples = 16
        except Exception:
            pass
        cam = bpy.data.objects.new('ovl_cam', bpy.data.cameras.new('ovl_cam'))
        sc.collection.objects.link(cam)
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = W
        cam.data.sensor_fit = 'HORIZONTAL'
        cam.location = (W / 2, H / 2, 100)
        cam.data.clip_start, cam.data.clip_end = 1.0, 1000.0
        sc.camera = cam
        self.items = []

    # ------------------------------------------------------------------ primitives
    def text(self, body, size, kind, color, parent, x=0, y=0, align='LEFT', spacing=1.0):
        cu = bpy.data.curves.new('txt', 'FONT')
        cu.body = body
        cu.size = size
        cu.font = font(kind)
        cu.align_x = align
        cu.align_y = 'BOTTOM'
        cu.space_character = spacing
        ob = bpy.data.objects.new('txt', cu)
        self.sc.collection.objects.link(ob)
        ob.data.materials.append(emat('ovl_' + color, color))
        ob.parent = parent
        ob.location = (x, y, 1)
        return ob

    def rect(self, w, h, color, parent, x=0, y=0, z=0, alpha=1.0, name='rect'):
        me = bpy.data.meshes.new(name)
        me.from_pydata([(0, 0, 0), (w, 0, 0), (w, h, 0), (0, h, 0)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new(name, me)
        self.sc.collection.objects.link(ob)
        me.materials.append(emat('ovl_%s_%d' % (color, int(alpha * 100)), color, alpha))
        ob.parent = parent
        ob.location = (x, y, z)
        return ob

    def tri(self, pts, color, parent, z=0):
        me = bpy.data.meshes.new('tri')
        me.from_pydata([(x, y, 0) for x, y in pts], [], [tuple(range(len(pts)))])
        ob = bpy.data.objects.new('tri', me)
        self.sc.collection.objects.link(ob)
        me.materials.append(emat('ovl_' + color, color))
        ob.parent = parent
        ob.location = (0, 0, z)
        return ob

    def measure(self, ob):
        vl = self.sc.view_layers[0]
        vl.update()
        dg = vl.depsgraph
        e = ob.evaluated_get(dg)
        try:
            me = e.to_mesh()
            xs = [v.co.x for v in me.vertices] or [0]
            ys = [v.co.y for v in me.vertices] or [0]
            w, h = (max(xs) - min(xs)) * ob.scale.x, (max(ys) - min(ys)) * ob.scale.y
            e.to_mesh_clear()
            return w, h
        except Exception:
            return ob.dimensions.x, ob.dimensions.y

    def group(self, name):
        g = bpy.data.objects.new(name, None)
        self.sc.collection.objects.link(g)
        return g

    # ------------------------------------------------------------------ item builders (return root, pivot, size)
    def tag(self, it):
        g = self.group('tag')
        pad = 22
        t1 = self.text(it['title'], it.get('size', 46), 'bold', it.get('fg', '#ffffff'), g, pad, 0)
        w1, h1 = self.measure(t1)
        t2 = self.text(it.get('sub', ''), it.get('size', 46) * 0.5, 'mono', it.get('fg2', '#c9cbd2'), g, pad, 0, spacing=1.08)
        w2, h2 = self.measure(t2) if it.get('sub') else (0, 0)
        H = pad * 0.8 + h2 + 12 + h1 + pad * 0.8
        W = max(w1, w2) + 2 * pad
        t2.location.y = pad * 0.8
        t1.location.y = pad * 0.8 + h2 + 12 if it.get('sub') else pad
        self.rect(W, H, it.get('bg', '#14141c'), g, 0, 0, -1, alpha=it.get('bg_alpha', 0.94))
        self.rect(W, H, it.get('border', '#2a2a36'), g, -2, -2, -2)
        self.items_size = (W, H)
        return g, (W / 2, H / 2), (W, H)

    def callout(self, it):
        g = self.group('callout')
        pad = 18
        t = self.text(it['text'], it.get('size', 50), 'bold', it.get('fg', '#ffffff'), g, pad, pad * 0.7)
        w, h = self.measure(t)
        W, H = w + 2 * pad, h + pad * 1.4
        col = it.get('color', '#e3322b')
        self.rect(W, H, col, g, 0, 0, -1)
        side = it.get('side', 'left')            # pointer side
        if side == 'left':
            self.tri([(0, H * 0.3), (0, H * 0.7), (-H * 0.32, H * 0.5)], col, g, -1)
            pivot = (-H * 0.32, H * 0.5)
        else:
            self.tri([(W, H * 0.3), (W + H * 0.32, H * 0.5), (W, H * 0.7)], col, g, -1)
            pivot = (W + H * 0.32, H * 0.5)
        return g, pivot, (W, H)

    def title(self, it):
        g = self.group('title')
        t = self.text(it['text'], it.get('size', 62), 'bold', it.get('fg', '#ffffff'), g, 70, 0)
        w, h = self.measure(t)
        col = it.get('color', '#e3322b')
        s = h * 0.95
        self.rect(s * 0.3, s, col, g, 8 + s * 0.35, (h - s) / 2, 0)          # plus sign
        self.rect(s, s * 0.3, col, g, 8, (h - s * 0.3) / 2, 0)
        for k, (dx, dy, a) in enumerate(((3, -3, 0.6),)):   # drop shadow
            sh = self.text(it['text'], it.get('size', 62), 'bold', '#000000', g, 70 + dx, dy)
            sh.location.z = 0.2 + k * 0.1
            sh.data.materials[0] = emat('ovl_shadow%d' % k, '#0b0d14', a)
            sh.location.z = -0.5 - k * 0.1
        return g, (0, 0), (w + 70, h)

    def stamp(self, it):
        g = self.group('stamp')
        pad = 30
        col = it.get('color', '#f0505a')
        t = self.text(it['text'], it.get('size', 58), 'mono', col, g, pad, pad)
        w, h = self.measure(t)
        W, H = w + 2 * pad, h + 2 * pad
        self.rect(W, H, '#0d0d10', g, 0, 0, -2, 0.92)
        for k, inset in ((0, 10), (1, 16)):
            th = 3
            for (x, y, ww, hh) in ((inset, inset, W - 2 * inset, th), (inset, H - inset - th, W - 2 * inset, th),
                                   (inset, inset, th, H - 2 * inset), (W - inset - th, inset, th, H - 2 * inset)):
                self.rect(ww, hh, col, g, x, y, -1, 0.85)
        g.rotation_euler.z = math.radians(it.get('tilt', 2.0))
        return g, (0, 0), (W, H)

    def badge(self, it):
        g = self.group('badge')
        pad = 16
        t = self.text(it['text'], it.get('size', 30), 'mono', it.get('fg', '#3a3d45'), g, pad, pad * 0.8, spacing=1.25)
        w, h = self.measure(t)
        W, H = w + 2 * pad, h + pad * 1.6
        self.rect(W, H, it.get('bg', '#eef0f3'), g, 0, 0, -1, 0.92)
        self.rect(W + 4, H + 4, it.get('border', '#a9adb7'), g, -2, -2, -2)
        return g, (0, 0), (W, H)


def screen_pos(item, size, W, H, margin=56):
    pos = item.get('pos', 'top_right')
    w, h = size
    x = {'left': margin, 'center': (W - w) / 2, 'right': W - w - margin}
    y = {'top': H - h - margin, 'middle': (H - h) / 2, 'bottom': margin}
    vy, hx = pos.split('_') if '_' in pos else ('middle', pos)
    if isinstance(item.get('xy'), (list, tuple)):
        return item['xy']
    return x.get(hx, margin), y.get(vy, margin)


def project(cam_M, lens, p, W, H):
    q = cam_M.inverted() @ Vector(p)
    if q.z >= -1e-4:
        return None
    k = lens / 36.0 * W
    return W / 2 + q.x / -q.z * k, H / 2 + q.y / -q.z * k


def build(tl, world, camdata, shots, fps, nframes, main_scene, keywriter):
    items = tl.get('graphics', [])
    if not items:
        return None
    ov = Overlay(main_scene)
    W, H = ov.W, ov.H
    shot_of = {}
    for sh in shots:
        for f in range(int(round(sh.start * fps)) + 1, int(round(sh.end * fps)) + 1):
            shot_of[f] = sh.name
    for it in items:
        t0, t1 = world.time(it['t'][0]), world.time(it['t'][1])
        g, pivot, size = getattr(ov, it['type'])(it)
        g.rotation_mode = 'QUATERNION' if it['type'] != 'stamp' else 'XYZ'
        pin = it.get('anchor')
        off = it.get('offset', [60, 60] if it['type'] == 'tag' else [70, 0])
        base = None if pin else screen_pos(it, size, W, H, it.get('margin', 56))
        smooth = None
        for f in range(1, nframes + 1):
            t = (f - 1) / fps
            u_in = clamp((t - t0) / 0.22)
            u_out = clamp((t1 - t) / 0.18)
            vis = 0.0 if (t < t0 or t > t1) else min(ease('back', u_in), ease('inout', u_out))
            if pin:
                world.frame = f
                p3 = world.resolve_point(pin, t)
                sn = shot_of.get(f)
                cd = camdata.get(sn, {}).get(f) if sn else None
                xy = project(cd[0], cd[1], p3, W, H) if (cd and p3 is not None) else None
                if xy is None:
                    vis = 0.0
                    xy = (W / 2, H / 2)
                x, y = xy[0] + off[0] - pivot[0], xy[1] + off[1] - pivot[1]
                if smooth is not None and shot_of.get(f) == shot_of.get(f - 1):
                    x, y = smooth[0] * 0.35 + x * 0.65, smooth[1] * 0.35 + y * 0.65
                smooth = (x, y)
            else:
                x, y = base
            sc = max(vis, 1e-4)
            cx, cy = x + size[0] / 2, y + size[1] / 2          # scale about the item centre
            keywriter.put(g, 'location', 0, f, cx - size[0] / 2 * sc)
            keywriter.put(g, 'location', 1, f, cy - size[1] / 2 * sc)
            keywriter.put(g, 'location', 2, f, 0.0)
            for i in range(3):
                keywriter.put(g, 'scale', i, f, sc if i < 2 else 1.0)
    return ov.sc
