"""Environment templates + lighting presets.

A set is built from layers (foreground ground plane with paving lines for perspective,
mid-ground architecture/props, background silhouettes, sky). Colours are pre-mixed toward
the horizon colour by distance (aerial perspective) so depth reads even in flat shading.
Each preset also configures the StudioLook rim/tint values so characters sit in the light.
"""
import math
import bpy
from mathutils import Vector, Matrix
from . import geom, materials, props
from .util import srgb, mix_col

PALETTES = {
    'dusk': dict(sky=[(0.0, '#ffb26b'), (0.18, '#e9897c'), (0.45, '#8a5e9e'), (1.0, '#2e2453')],
                 sun='#ffe3a6', sun_glow='#ff9d5c', key='#ffb070', key_power=3.2, fill='#7f72d6', fill_power=0.55,
                 world='#2b2340', world_power=0.7, ground='#4b3c58', haze='#b77b8c',
                 look=dict(shadow='#4a3a78', lit='#ffe6cc', rim='#ffad5c', rim_strength=1.5, rim_width=0.45, ambient='#3a2c5c'),
                 window='#ffb15e', sun_elev=9.0, sun_az=10.0),
    'night': dict(sky=[(0.0, '#2c3566'), (0.5, '#151a3c'), (1.0, '#07081a')],
                  sun='#dfe8ff', sun_glow='#5f78c8', key='#9fb4ff', key_power=0.9, fill='#3c3a7a', fill_power=0.35,
                  world='#0f1128', world_power=0.6, ground='#22223a', haze='#2f3866',
                  look=dict(shadow='#1b1e45', lit='#dfe6ff', rim='#8fb2ff', rim_strength=1.6, rim_width=0.45, ambient='#1a1c3c'),
                  window='#ffc477', sun_elev=25.0, sun_az=-20.0),
    'day': dict(sky=[(0.0, '#e7f1f7'), (0.4, '#a9d2ec'), (1.0, '#5aa2d6')],
                sun='#fffbe8', sun_glow='#fff1c4', key='#fff1d6', key_power=4.0, fill='#9fc3ff', fill_power=1.0,
                world='#9cb8d8', world_power=0.9, ground='#7f9a62', haze='#cfe2ee',
                look=dict(shadow='#6c7aa8', lit='#fffaf0', rim='#fff4d8', rim_strength=0.8, rim_width=0.4, ambient='#7d8fb8'),
                window='#fff2c8', sun_elev=40.0, sun_az=30.0),
    'golden': dict(sky=[(0.0, '#ffd18a'), (0.3, '#f7b27a'), (1.0, '#6f8fc4')],
                   sun='#fff0c0', sun_glow='#ffc070', key='#ffc27a', key_power=3.6, fill='#8aa0e0', fill_power=0.7,
                   world='#6d6a8c', world_power=0.8, ground='#8c7a5a', haze='#f0c49a',
                   look=dict(shadow='#5a5288', lit='#fff0d8', rim='#ffc070', rim_strength=1.3, rim_width=0.45, ambient='#5a557a'),
                   window='#ffd08a', sun_elev=14.0, sun_az=15.0),
}


def _col(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def haze(color, pal, dist, k=0.012):
    u = 1 - math.exp(-k * max(dist, 0))
    a = srgb(color)
    b = srgb(pal['haze'])
    lin = mix_col(a, b, min(u, 0.85))
    # back to hex (approx) for cached materials
    def to_s(x):
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
    return '#%02x%02x%02x' % tuple(int(max(0, min(1, to_s(c))) * 255) for c in lin[:3])


# ---------------------------------------------------------------- shared pieces
def sky_and_sun(col, pal, dist=320.0):
    sky = geom.make_object('sky', geom.plane(2400, 700, (0, dist, 250), 'Y'),
                           materials.gradient('sky_mat', pal['sky'], 'Z', -100, 600), col)
    sky.visible_shadow = False
    el, az = math.radians(pal['sun_elev']), math.radians(pal['sun_az'])
    d = Vector((math.sin(az), math.cos(az), math.tan(el))).normalized()
    pos = Vector((0, 0, 1.5)) + d * (dist - 20) / d.y
    sun = geom.make_object('sun_disc', geom.plane(1, 1, normal='Y'), materials.radial_glow('sun_core', pal['sun'], 4.0, 0.35, 1.0), col)
    sun.location, sun.scale = pos, (28, 1, 28)
    glow = geom.make_object('sun_glow', geom.plane(1, 1, normal='Y'), materials.radial_glow('sun_glow', pal['sun_glow'], 1.6, 2.0, 0.8), col)
    glow.location, glow.scale = pos + Vector((0, 2, 0)), (260, 1, 200)
    for o in (sun, glow):
        o.visible_shadow = False
    # flat cloud strips
    import random
    rnd = random.Random(7)
    cm = materials.radial_glow('cloud', '#f7b48a', 1.0, 1.2, 0.55)
    for i in range(7):
        c = geom.make_object('cloud%d' % i, geom.plane(1, 1, normal='Y'), cm, col)
        c.location = (rnd.uniform(-300, 300), dist - 5 - i, rnd.uniform(40, 140))
        c.scale = (rnd.uniform(90, 200), 1, rnd.uniform(5, 10))
        c.visible_shadow = False
    return d


def lights(col, pal, sun_dir, rim_dir=None):
    key = bpy.data.lights.new('key', 'SUN')
    key.color = srgb(pal['key'])[:3]
    key.energy = pal['key_power']
    key.angle = math.radians(2.5)
    ko = bpy.data.objects.new('key', key)
    col.objects.link(ko)
    ko.rotation_euler = (-sun_dir).to_track_quat('-Z', 'Y').to_euler()
    fill = bpy.data.lights.new('fill', 'SUN')
    fill.color = srgb(pal['fill'])[:3]
    fill.energy = pal['fill_power']
    try:
        fill.use_shadow = False
    except Exception:
        pass
    fo = bpy.data.objects.new('fill', fill)
    col.objects.link(fo)
    fd = Vector((-0.3, -1.0, 0.6)).normalized()
    fo.rotation_euler = (-fd).to_track_quat('-Z', 'Y').to_euler()
    w = bpy.context.scene.world or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = srgb(pal['world'])
    bg.inputs['Strength'].default_value = pal['world_power']
    lk = dict(pal['look'])
    lk['rim_dir'] = tuple(rim_dir or sun_dir)
    materials.look_group()
    materials.set_look(**lk)
    return ko, fo


def ground(col, pal, y0=-14, y1=2.4, tile=0.6, x=30.0, color=None):
    gm = materials.cel('ground', color or pal['ground'], rim=0.0, shade=0.9)
    g = geom.make_object('ground', geom.plane(2 * x, y1 - y0, (0, (y0 + y1) / 2, 0)), gm, col)
    lm = materials.cel('ground_lines', haze('#2a2035', pal, 0, 0), rim=0.0, shade=0.9)
    parts = []
    n = int((y1 - y0) / tile)
    for i in range(n + 1):
        y = y0 + i * tile
        parts.append(geom.box(2 * x, 0.012, 0.002, (0, y, 0.001)))
    for i in range(int(2 * x / (tile * 2))):
        xx = -x + i * tile * 2
        parts.append(geom.box(0.012, y1 - y0, 0.002, (xx, (y0 + y1) / 2, 0.001)))
    geom.make_object('ground_lines', geom.merge(*parts), lm, col)
    return g


# ---------------------------------------------------------------- templates
def cafe_street(params):
    pal = PALETTES[params.get('time', 'dusk')]
    col = _col('set')
    sun_dir = sky_and_sun(col, pal)
    lights(col, pal, sun_dir)
    ground(col, pal)
    curb = materials.cel('curb', '#3d3049', rim=0.3)
    geom.make_object('curb', geom.box(60, 0.18, 0.13, (0, 2.49, 0.065)), curb, col)
    road = materials.cel('road', '#2a2236', rim=0.0)
    geom.make_object('road', geom.plane(60, 7.0, (0, 6.0, -0.0)), road, col).location.z = -0.002
    stripes = materials.cel('road_lines', '#8a7a8a', rim=0.0)
    geom.make_object('road_lines', geom.merge(*[geom.box(1.6, 0.12, 0.003, (-28 + 4 * i, 6.0, 0.0)) for i in range(15)]),
                     stripes, col)
    geom.make_object('far_walk', geom.plane(60, 3, (0, 11.0, 0.0)), materials.cel('far_walk', haze(pal['ground'], pal, 11), rim=0), col)
    # facade row across the street (gap at the cross street lets the sun through)
    rows = [(-13.0, 5.5, 7.5, '#3a2a4a'), (-7.2, 5.0, 5.2, '#43304f'), (-2.3, 4.4, 4.2, '#4a3352'),
            (5.6, 5.2, 4.6, '#3d2c4c'), (11.0, 5.0, 7.8, '#35284a'), (16.5, 5.5, 5.4, '#3f2d4e')]
    for i, (x, w, h, c) in enumerate(rows):
        aw = ('#c8352f', '#efe2cf') if i == 2 else None
        props.building('bld%d' % i, col, w, 6, h, haze(c, pal, 15), pal['window'], (x, 15.5, 0), floors=2 if h < 6 else 3,
                       cols=3 if w < 5 else 4, lit=0.8, seed=i, awning=aw)
    # warm spill from the café windows onto the far sidewalk
    props.window_glow_light('cafe_spill', col, (-2.3, 12.0, 2.0), (4.0, 2.0), pal['window'], 120.0,
                            (math.radians(80), 0, math.radians(180)))
    # skyline silhouettes
    sk = materials.cel('skyline_near', haze('#3a2a50', pal, 60, 0.02), rim=0.0, shade=0.2)
    sk2 = materials.cel('skyline_far', haze('#4b3563', pal, 120, 0.02), rim=0.0, shade=0.1)
    import random
    rnd = random.Random(3)
    parts, parts2 = [], []
    for i in range(30):
        x = -150 + i * 10 + rnd.uniform(-3, 3)
        if -6 < x < 8:
            continue
        hh = rnd.uniform(8, 22)
        parts.append(geom.box(rnd.uniform(6, 11), 4, hh, (x, 70, hh / 2)))
    for i in range(40):
        x = -260 + i * 13
        hh = rnd.uniform(10, 34)
        parts2.append(geom.box(rnd.uniform(8, 14), 4, hh, (x, 150, hh / 2)))
    geom.make_object('skyline_near', geom.merge(*parts), sk, col)
    geom.make_object('skyline_far', geom.merge(*parts2), sk2, col)
    # street furniture
    for i, x in enumerate((-4.5, 3.4, 10.5, -11.5)):
        props.lamp_post('lamp%d' % i, col, 3.4, '#1b1622', pal['window'], (x, 2.15, 0), power=35.0)
    for i, x in enumerate((-8.5, 7.8, 14.0)):
        props.tree('tree%d' % i, col, 4.5, haze('#1d1527', pal, 12), (x, 10.3, 0), seed=i)
    # reverse-angle backing (buildings behind the camera, front-lit by the sunset)
    for i, (x, w, h) in enumerate(((-9, 6, 6), (-2.5, 6.5, 8), (4.5, 6, 5.5), (11, 7, 7))):
        props.building('rev%d' % i, col, w, 5, h, '#5b3d55', pal['window'], (x, -9.5, 0), floors=2, cols=4, lit=0.4,
                       seed=10 + i, face_dir=1, door=False)
    return dict(palette=pal, sun_dir=sun_dir)


def room_interior(params):
    """Evening room: back wall with a big window onto the sunset, floor boards, lamp, sofa."""
    pal = PALETTES[params.get('time', 'dusk')]
    col = _col('set')
    sun_dir = sky_and_sun(col, pal, 120)
    lights(col, pal, sun_dir)
    floor = materials.cel('floor', '#5a4050', rim=0.0)
    geom.make_object('floor', geom.plane(12, 12, (0, 0, 0)), floor, col)
    lm = materials.cel('floor_lines', '#45303f', rim=0.0)
    geom.make_object('floor_lines', geom.merge(*[geom.box(12, 0.01, 0.002, (0, -6 + 0.25 * i, 0.001)) for i in range(49)]), lm, col)
    wall = materials.cel('wall', '#4a3656', rim=0.0, shade=0.8)
    # back wall with a window opening (x -1.5..1.5, z 0.9..2.4)
    parts = [geom.box(12, 0.15, 0.9, (0, 3.0, 0.45)), geom.box(12, 0.15, 0.6, (0, 3.0, 2.7)),
             geom.box(4.5, 0.15, 1.5, (-3.75, 3.0, 1.65)), geom.box(4.5, 0.15, 1.5, (3.75, 3.0, 1.65))]
    geom.make_object('back_wall', geom.merge(*parts), wall, col)
    frame = materials.cel('window_frame', '#2a1e33', rim=0.4)
    geom.make_object('window_frame', geom.merge(geom.box(3.1, 0.2, 0.06, (0, 3.0, 0.9)), geom.box(3.1, 0.2, 0.06, (0, 3.0, 2.4)),
                                                geom.box(0.06, 0.2, 1.5, (0, 3.0, 1.65)), geom.box(0.06, 0.2, 1.5, (-1.5, 3.0, 1.65)),
                                                geom.box(0.06, 0.2, 1.5, (1.5, 3.0, 1.65))), frame, col)
    geom.make_object('side_wall_L', geom.box(0.15, 12, 3.0, (-5.5, -3, 1.5)), wall, col)
    geom.make_object('side_wall_R', geom.box(0.15, 12, 3.0, (5.5, -3, 1.5)), wall, col)
    sofa = materials.cel('sofa', '#6b4a7a', rim=0.6)
    geom.make_object('sofa', geom.merge(geom.box(2.0, 0.8, 0.42, (-2.8, 2.2, 0.21), bevel=0.05),
                                        geom.box(2.0, 0.2, 0.5, (-2.8, 2.55, 0.65), bevel=0.05)), sofa, col)
    props.lamp_post('floor_lamp', col, 1.5, '#1b1622', '#ffcf8a', (3.2, 2.4, 0), power=25.0)
    # motivated interior light: sunset through the window + warm ceiling bounce + cool front fill
    props.window_glow_light('window_sun', col, (0, 2.7, 1.65), (3.0, 1.5), pal['sun_glow'], 260.0, (math.radians(90), 0, 0))
    props.window_glow_light('ceiling', col, (0, -0.5, 2.9), (3.0, 3.0), '#ffd2a0', 140.0, (0, 0, 0))
    props.window_glow_light('front_fill', col, (1.5, -3.5, 1.6), (2.0, 2.0), '#9a8cff', 90.0,
                            (math.radians(75), 0, math.radians(25)))
    for i in range(3):
        props.building('far%d' % i, col, 4, 4, 6 + 3 * i, haze('#3a2a50', pal, 30), pal['window'], (-5 + 5 * i, 30, 0),
                       floors=3, cols=3, seed=i)
    return dict(palette=pal, sun_dir=sun_dir)


def park(params):
    pal = PALETTES[params.get('time', 'golden')]
    col = _col('set')
    sun_dir = sky_and_sun(col, pal)
    lights(col, pal, sun_dir)
    ground(col, pal, -20, 40, tile=10.0, color=pal['ground'])
    path = materials.cel('path', '#b49c78', rim=0.0)
    geom.make_object('path', geom.plane(2.2, 60, (0, 10, 0.003)), path, col)
    hills = materials.cel('hills', haze('#5a7a4a', pal, 80, 0.02), rim=0.0, shade=0.3)
    geom.make_object('hills', geom.merge(*[geom.ellipsoid(40 + 10 * (i % 3), 10, 8 + 4 * (i % 2), (-120 + 45 * i, 90, -2), 24, 8)
                                           for i in range(7)]), hills, col)
    for i in range(10):
        x = -14 + 3.1 * i + (1.2 if i % 2 else -0.8)
        props.tree('tree%d' % i, col, 4 + (i % 3), haze('#2e4a2c', pal, 14 + 2 * (i % 4)), (x, 14 + 2 * (i % 4), 0), seed=i)
    return dict(palette=pal, sun_dir=sun_dir)


def studio_void(params):
    pal = PALETTES[params.get('time', 'dusk')]
    col = _col('set')
    sun_dir = Vector((0.2, 1.0, 0.3)).normalized()
    lights(col, pal, sun_dir)
    cyc = materials.gradient('cyc', [(0, pal['ground']), (1, pal['sky'][-1][1])], 'Z', 0, 8)
    v, f = geom.lathe([(0, 0), (12, 0)], 48)
    geom.make_object('floor', (v, f), materials.cel('floor', pal['ground'], rim=0), col)
    geom.make_object('cyc', geom.plane(60, 20, (0, 12, 9), 'Y'), cyc, col)
    props.window_glow_light('studio_key', col, (2.5, -3.0, 3.0), (2.5, 2.5), '#ffe8d0', 450.0,
                            (math.radians(55), 0, math.radians(40)))
    props.window_glow_light('studio_back', col, (-1.5, 3.0, 3.0), (2.0, 2.0), pal['look']['rim'], 250.0,
                            (math.radians(-55), 0, math.radians(-20)))
    return dict(palette=pal, sun_dir=sun_dir)


# ============================================================== reconstruction (clay) sets
def clay_lights(col, sun_dir=(0.35, -0.55, 0.75), key=3.2, world='#dfe3ea', world_power=1.0, key_color='#fff6ea',
                angle=6.0, fill=True):
    from . import materials as M
    M.look_group()
    M.set_look(rim_strength=0.0)
    d = Vector(sun_dir).normalized()
    k = bpy.data.lights.new('key', 'SUN')
    k.energy = key
    k.angle = math.radians(angle)
    k.color = srgb(key_color)[:3]
    ko = bpy.data.objects.new('key', k)
    col.objects.link(ko)
    ko.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    w = bpy.context.scene.world or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = srgb(world)
    bg.inputs['Strength'].default_value = world_power
    sc = bpy.context.scene
    for attr, val in (('use_raytracing', True), ('use_shadows', True), ('shadow_ray_count', 2), ('shadow_step_count', 8),
                      ('fast_gi_distance', 2.0), ('use_fast_gi', True)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    try:
        sc.eevee.ray_tracing_options.trace_max_roughness = 0.5
        sc.eevee.ray_tracing_method = 'SCREEN'
    except Exception:
        pass
    return ko


def cloud_bank(col, center, extent, n=60, z=-6.0, seed=1, size=(6, 14), color='#ffffff'):
    import random
    from . import materials as M
    r = random.Random(seed)
    m = M.clay('cloud_m', color, rough=1.0, emit=0.55, spec=0.0)
    parts = []
    for i in range(n):
        cx = center[0] + r.uniform(-extent[0], extent[0])
        cy = center[1] + r.uniform(-extent[1], extent[1])
        base = r.uniform(*size)
        for k in range(r.randint(3, 6)):
            rr = base * r.uniform(0.4, 0.8)
            parts.append(geom.ellipsoid(rr, rr * r.uniform(0.8, 1.2), rr * 0.5,
                                        (cx + r.uniform(-base, base), cy + r.uniform(-base, base), z + r.uniform(0, base * 0.4)), 12, 7))
    ob = geom.make_object('clouds_%d' % seed, geom.merge(*parts), m, col)
    ob.visible_shadow = False
    return ob


def sky_dome(col, top='#5f9fe0', horizon='#dcebf8', radius=1500.0):
    from . import materials as M
    v, f = geom.lathe(geom.sphere_profile(radius, 0.0, 16), 32)
    m = M.gradient('sky_dome_m', [(0.0, horizon), (0.55, top), (1.0, top)], 'Z', -radius * 0.1, radius * 0.6)
    ob = geom.make_object('sky_dome', (v, [tuple(reversed(x)) for x in f]), m, col)
    ob.visible_shadow = False
    return ob


def clay_cabin(params):
    from . import aircraft, materials as M
    M.set_style('clay')
    col = _col('set')
    clay_lights(col, sun_dir=(0.35, -0.3, 1.0), key=1.6, world='#d9dce2', world_power=0.75)
    ob, info = aircraft.cabin_interior(col, rows=params.get('rows', 24), first_row=params.get('first_row', 1))
    # soft ceiling light strips along the cabin
    for i in range(6):
        y = info['front'] - 2 - i * 3.5
        L = bpy.data.lights.new('cab_light%d' % i, 'AREA')
        L.shape, L.size, L.size_y, L.energy = 'RECTANGLE', 0.6, 3.2, 90.0
        lo = bpy.data.objects.new('cab_light%d' % i, L)
        col.objects.link(lo)
        lo.location = (0, y, 2.35)
    # galley wall + cockpit beyond the door (visible if the door opens)
    ck, cinfo = aircraft.cockpit(col, front=info['front'])
    info.update(cinfo)
    return dict(palette=None, sun_dir=Vector((0, 0, 1)), anchors=info)


def cockpit_cutaway(params):
    """One aircraft that serves every shot: shared furniture (seats, cockpit instruments, door) plus
    swappable shells - 'closed' variants for interior shots and 'cut' variants + exterior skin for
    the cutaway view. Use per-shot "hide" lists (see anchors['variants'])."""
    from . import aircraft, materials as M
    M.set_style('clay')
    col = _col('set')
    clay_lights(col, sun_dir=(-0.45, 0.25, 0.85), key=3.0, world='#cfe0f2', world_power=0.9)
    rows = params.get('rows', 22)
    cut_len = params.get('cut_len', 6.2)
    ob, info = aircraft.cabin_furniture(col, rows=rows, front=0.0)
    front, back = info['front'], info['back']
    aircraft.cabin_shell(col, 'cabin_aft_shell', back, front - cut_len, None, front=front)
    aircraft.cabin_shell(col, 'cabin_front_closed', front - cut_len, front, None, front=front)
    aircraft.cabin_shell(col, 'cabin_front_cut', front - cut_len, front, 'left', front=front)
    ck, cinfo = aircraft.cockpit(col, front=front, parts_sel='furniture', name='cockpit_furniture')
    aircraft.cockpit(col, front=front, parts_sel='shell', name='cockpit_closed')
    aircraft.cockpit(col, front=front, cut='left', parts_sel='shell', name='cockpit_cut')
    info.update(cinfo)
    aircraft.airliner_exterior(col, name='fuselage_cutaway', front=front, cut='nose_left', windows=True, gear=False,
                               body=params.get('body', '#eeeff2'), tail=params.get('tail', '#e6e6ea'),
                               stripe=params.get('stripe'), logo=params.get('logo'))
    for i in range(6):                                  # cabin ceiling lights (interior shots)
        y = front - 2 - i * 3.5
        L = bpy.data.lights.new('cab_light%d' % i, 'AREA')
        L.shape, L.size, L.size_y, L.energy = 'RECTANGLE', 0.6, 3.2, 70.0
        lo = bpy.data.objects.new('cab_light%d' % i, L)
        col.objects.link(lo)
        lo.location = (0, y, 2.35)
    sky_dome(col, params.get('sky_top', '#2f7ad4'), params.get('sky_horizon', '#a9cdf0'))
    cloud_bank(col, (0, 0), (180, 180), n=70, z=-14, seed=2, size=(8, 22))
    cloud_bank(col, (-160, 220), (90, 60), n=14, z=6, seed=5, size=(10, 20))
    info['variants'] = {'interior': ['cabin_front_cut', 'cockpit_cut', 'fuselage_cutaway'],
                        'cutaway': ['cabin_front_closed', 'cockpit_closed']}
    return dict(palette=None, sun_dir=Vector((-0.45, 0.25, 0.85)), anchors=info)


def airport(params):
    from . import aircraft, materials as M
    import random
    M.set_style('clay')
    col = _col('set')
    clay_lights(col, sun_dir=(-0.5, -0.4, 0.75), key=2.6, world='#e9ecf1', world_power=0.85)
    white = M.clay('apt_ground', '#f2f2f3', rough=0.85)
    asphalt = M.clay('apt_runway', '#8d8f94', rough=0.8)
    line = M.clay('apt_line', '#ffffff', emit=0.3)
    taxi = M.clay('apt_taxi', '#d6d7da', rough=0.8)
    hi = params.get('highlight', '#e3322b')
    parts = [(geom.plane(4000, 4000, (0, 0, -0.05)), white),
             (geom.box(2400, 48, 0.1, (0, 260, 0)), asphalt)]
    for i in range(60):
        parts.append((geom.box(22, 1.2, 0.02, (-1150 + i * 40, 260, 0.06)), line))
    # taxiway outlines (rounded polylines drawn as thin strips)
    for k, (y, x0, x1) in enumerate(((180, -700, 700), (120, -600, 650))):
        parts.append((geom.box(x1 - x0, 2.0, 0.02, ((x0 + x1) / 2, y, 0.01)), taxi))
        for xx in (x0, x1):
            for a in range(10):
                ang = math.radians(a * 9)
                parts.append((geom.box(2.0, 9.0, 0.02, (xx + (30 * math.sin(ang)) * (1 if xx > 0 else -1), y + 30 - 30 * math.cos(ang), 0.01)), taxi))
    geom.make_object('airport_ground', geom.merge(*[p for p, m in parts if m is white]), white, col)
    geom.make_object('airport_runway', geom.merge(*[p for p, m in parts if m is asphalt]), asphalt, col)
    geom.make_object('airport_lines', geom.merge(*[p for p, m in parts if m is line]), line, col)
    geom.make_object('airport_taxi', geom.merge(*[p for p, m in parts if m is taxi]), taxi, col)
    bld = M.clay('apt_building', '#f4f4f5')
    # main terminal: triangle footprint with a pyramid roof grid (the highlight-able building)
    tri = [(-160, 40), (160, 40), (0, -120)]
    term = geom.extrude_polygon(tri, 0, 8)
    roof = []
    for i in range(14):
        for j in range(14):
            x = -150 + i * 22 + j * 11 - 70
            y = 30 - j * 19
            # inside triangle test
            if y < -110 or y > 32:
                continue
            w_at = 160 * (y + 120) / 160
            if abs(x) > w_at - 12:
                continue
            roof.append(geom.lathe([(0, 8), (8, 8), (0, 14)], 4, phase=math.pi / 4))
            v, f = roof[-1]
            roof[-1] = ([(a + x, b + y, c) for a, b, c in v], f)
    hm = M.subject('apt_highlight', hi) if params.get('highlight_terminal', True) else bld
    geom.make_object('terminal_main', geom.merge(term, *roof), hm, col, smooth=False)
    tower = geom.lathe([(0, 0), (6, 0), (4, 40), (9, 44), (9, 50), (6, 53), (0, 54)], 16)
    geom.make_object('control_tower', geom.transform(tower, Matrix.Translation((-200, 70, 0))), bld, col)
    for i, (x, y, w, d) in enumerate(((-120, 90, 260, 30), (330, 70, 160, 60), (-330, 40, 120, 40))):
        geom.make_object('apt_bld%d' % i, geom.box(w, d, 14, (x, y, 7)), bld, col, smooth=False)
    # parked airliners around the terminal (white)
    rnd = random.Random(4)
    for i, (x, y, r) in enumerate(((-120, -10, 200), (-60, -60, 160), (90, -40, 30), (40, -110, 120), (230, 20, 200),
                                   (-230, 130, 0), (-170, 130, 0), (-110, 130, 0), (300, 150, 180), (360, 150, 180))):
        aircraft.airliner_exterior(col, name='parked%d' % i, front=0, body='#f6f6f7', tail='#f0f0f2', windows=False,
                                   gear=True, scale=1.0, loc=(x, y, 2.9), rot_z=r)
    return dict(palette=None, sun_dir=Vector((-0.5, -0.4, 0.75)), anchors={'runway_y': 260, 'terminal': [0, -20, 10]})


def desert_runway(params):
    from . import aircraft, materials as M
    M.set_style('clay')
    col = _col('set')
    clay_lights(col, sun_dir=(0.2, 0.6, 0.6), key=2.4, world='#c9c1b5', world_power=1.0, key_color='#fff1dc', angle=12)
    sand = M.clay('sand', '#c48f5f', rough=0.95)
    asphalt = M.clay('dr_runway', '#56586a', rough=0.8)
    geom.make_object('desert', geom.plane(6000, 6000, (0, 0, -0.03)), sand, col)
    geom.make_object('dr_runway', geom.box(4000, 45, 0.04, (0, 0, 0)), asphalt, col)
    geom.make_object('dr_taxi', geom.box(4000, 3, 0.05, (0, -60, 0)), asphalt, col)
    trunk = M.clay('palm_trunk', '#6a5640')
    leaf = M.clay('palm_leaf', '#3f6b3a')
    for i in range(14):
        x = -600 + i * 95
        y = 120
        parts = [geom.capsule((x, y, 0), (x + 0.4, y, 9), 0.25, 0.18)]
        lv = []
        for k in range(9):
            a = 2 * math.pi * k / 9
            v, f = geom.ellipsoid(2.6, 0.35, 0.08, (0, 0, 0), 10, 4)
            m = Matrix.Translation((x + 0.4, y, 9)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Translation((2.3, 0, -0.4)) @                 Matrix.Rotation(math.radians(-18), 4, 'Y')
            lv.append(geom.transform((v, f), m))
        geom.make_object('palm%d' % i, geom.merge(*parts), trunk, col)
        geom.make_object('palm%d_leaves' % i, geom.merge(*lv), leaf, col)
    # haze: big gradient backdrop behind
    hz = M.gradient('haze_m', [(0.0, '#c9bfb2'), (1.0, '#b9b6b2')], 'Z', 0, 300)
    geom.make_object('haze', geom.plane(8000, 1200, (0, 1500, 500), 'Y'), hz, col).visible_shadow = False
    return dict(palette=None, sun_dir=Vector((0.2, 0.6, 0.6)), anchors={})


def clay_studio(params):
    """Seamless white cyclorama for isolated explainer shots (objects, maps, models, single figures)."""
    from . import materials as M
    M.set_style('clay')
    col = _col('set')
    clay_lights(col, sun_dir=(0.5, -0.6, 0.8), key=2.2, world=params.get('world', '#eef0f4'), world_power=0.9, angle=10)
    m = M.clay('cyc_white', params.get('color', '#f1f2f4'), rough=0.9)
    prof = [(-30, 0.0)] + [(8 * math.sin(math.radians(a)) + 0.0, 8 - 8 * math.cos(math.radians(a))) for a in range(0, 91, 6)]
    v, f = [], []
    for i, (y, z) in enumerate([(p[0], p[1]) for p in prof]):
        pass
    pts = [(y, z) for y, z in prof]
    verts, faces = [], []
    xs = (-40, 40)
    for i, (y, z) in enumerate(pts):
        verts += [(xs[0], y if i == 0 else 4 + (y if i else 0), z), (xs[1], y if i == 0 else 4 + y, z)]
    for i in range(len(pts) - 1):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    verts.append((xs[0], 12, 30))
    verts.append((xs[1], 12, 30))
    n = len(pts)
    faces.append((2 * (n - 1), 2 * (n - 1) + 1, 2 * n + 1, 2 * n))
    geom.make_object('cyclorama', (verts, faces), m, col)
    return dict(palette=None, sun_dir=Vector((0.5, -0.6, 0.8)), anchors={})


def clay_kitchen(params):
    """White clay kitchen corner (explainer look): floor tiles, two walls with counters, upper cabinets,
    a window with sky, fridge, open shelf with jars, pendant lamps. The corner sits behind the origin
    toward (-X, +Y); cameras looking from (+X, -Y) see both walls. params: accent (fridge/stools colour)."""
    from . import materials as M
    smooth = M.STYLE['mode'] == 'smooth'
    if not smooth:
        M.set_style('clay')
    col = _col('set')
    # palette: white clay by default; pastel 'animated feature' colours in smooth style
    P = dict(floor='#eeeff1', groove='#c9ccd2', wall='#e7e8eb', cab='#eeeff1', top='#f7f7f8', metal='#c9ccd2',
             accent='#d9dde3', sky='#bcd9f4', lamp='#eeeff1', pot='#c9ccd2', leaf='#eeeff1', jar='#eeeff1')
    if smooth:
        P.update(floor='#ead9c4', groove='#d9c3a8', wall='#f5e4d8', cab='#a3d6ca', top='#fbfbfa', metal='#cfd5dd',
                 accent='#f7d983', sky='#bfe2ff', lamp='#f39d8a', pot='#e59a74', leaf='#7cc69c', jar='#fbfbfa')
    P.update(params.get('palette', {}))
    clay_lights(col, sun_dir=params.get('sun', (0.55, -0.35, 0.75)), key=params.get('key', 1.6 if smooth else 2.6),
                world=params.get('world', '#f3eee9' if smooth else '#eef1f6'), world_power=0.45 if smooth else 0.9,
                angle=18 if smooth else 8)
    if smooth:      # soft studio area lights (key from camera side, cool fill, warm top bounce)
        for n, loc, en, size, colr in (('k_softkey', (3.2, -3.0, 3.2), 260, 3.0, '#fff4e8'),
                                       ('k_fill', (-1.0, -3.5, 1.8), 70, 4.0, '#e8f0ff'),
                                       ('k_top', (0.4, -0.3, 3.4), 60, 2.5, '#fff1e0')):
            L = bpy.data.lights.new(n, 'AREA')
            L.energy, L.size, L.color = en, size, srgb(colr)[:3]
            o = bpy.data.objects.new(n, L)
            col.objects.link(o)
            o.location = loc
            o.rotation_euler = (Vector((0.3, 0, 1.0)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    W = M.clay('k_white', P['cab'], rough=0.85)
    W2 = M.clay('k_wall', P['wall'], rough=0.9)
    FL = M.clay('k_floor', P['floor'], rough=0.8)
    TOP = M.clay('k_top', P['top'], rough=0.5)
    GR = M.clay('k_grey', P['metal'], rough=0.7)
    GV = M.clay('k_groove', P['groove'], rough=0.8)
    ACC = M.clay('k_acc', params.get('accent', P['accent']), rough=0.6)
    LMP = M.clay('k_lamp', P['lamp'], rough=0.5)
    POT = M.clay('k_pot', P['pot'], rough=0.6)
    LEAF = M.clay('k_leaf', P['leaf'], rough=0.6)
    JAR = M.clay('k_jar', P['jar'], rough=0.4)
    SKY = M.flat('k_sky', P['sky'], 1.4)
    bx = params.get('back_x', -1.7)        # wall A plane x
    by = params.get('back_y', 1.7)         # wall B plane y

    def box(n, size, c, mat, bevel=0.004):
        geom.make_object(n, geom.box(*size, c, bevel=bevel), mat, col)
    # floor with tile grooves
    box('k_floor', (14, 14, 0.02), (0, 0, -0.01), FL, 0)
    for i in range(-12, 13):
        box('k_gx%d' % i, (0.006, 14, 0.004), (i * 0.5, 0, 0.0005), GV, 0)
        box('k_gy%d' % i, (14, 0.006, 0.004), (0, i * 0.5, 0.0005), GV, 0)
    # walls
    box('k_wallA', (0.1, 8, 3.0), (bx - 0.05, by - 4 + 0.05, 1.5), W2, 0)
    box('k_wallB', (8, 0.1, 3.0), (bx + 4 - 0.05, by + 0.05, 1.5), W2, 0)
    # base cabinets + worktop along wall B (x from bx to bx+3.4) and wall A (y from by down 2.6)
    def run(n, x0, y0, length, along_x):
        dpt, h = 0.62, 0.9
        if along_x:
            c = (x0 + length / 2, y0 - dpt / 2, h / 2)
            box(n + '_body', (length, dpt - 0.04, h - 0.08), (c[0], c[1] + 0.02, (h - 0.08) / 2 + 0.06), W)
            box(n + '_top', (length + 0.02, dpt + 0.02, 0.04), (c[0], c[1], h - 0.02), TOP, 0.006)
            k = int(length / 0.55)
            for i in range(k):
                x = x0 + (i + 0.5) * length / k
                box(n + '_door%d' % i, (length / k - 0.02, 0.014, h - 0.2), (x, y0 - dpt + 0.012, (h - 0.2) / 2 + 0.09), W)
                geom.make_object(n + '_h%d' % i, geom.capsule((x - 0.07, y0 - dpt, h - 0.17), (x + 0.07, y0 - dpt, h - 0.17), 0.007), GR, col)
        else:
            c = (x0 + dpt / 2, y0 - length / 2, h / 2)
            box(n + '_body', (dpt - 0.04, length, h - 0.08), (c[0] - 0.02, c[1], (h - 0.08) / 2 + 0.06), W)
            box(n + '_top', (dpt + 0.02, length + 0.02, 0.04), (c[0], c[1], h - 0.02), TOP, 0.006)
            k = int(length / 0.55)
            for i in range(k):
                y = y0 - (i + 0.5) * length / k
                box(n + '_door%d' % i, (0.014, length / k - 0.02, h - 0.2), (x0 + dpt - 0.012, y, (h - 0.2) / 2 + 0.09), W)
                geom.make_object(n + '_h%d' % i, geom.capsule((x0 + dpt, y - 0.07, h - 0.17), (x0 + dpt, y + 0.07, h - 0.17), 0.007), GR, col)
    run('k_runB', bx, by, 3.0, True)
    run('k_runA', bx, by - 0.62, 2.2, False)
    # sink in run B
    sx = bx + 1.9
    box('k_sink', (0.55, 0.4, 0.02), (sx, by - 0.32, 0.905), GR, 0.01)
    geom.make_object('k_tap', geom.capsule((sx, by - 0.08, 0.9), (sx, by - 0.08, 1.15), 0.014), GR, col)
    geom.make_object('k_tap2', geom.capsule((sx, by - 0.08, 1.15), (sx, by - 0.24, 1.12), 0.012), GR, col)
    # window above the sink with sky + frame
    box('k_win_sky', (1.1, 0.02, 0.8), (sx, by - 0.005, 1.6), SKY, 0)
    for n, size, c in (('t', (1.2, 0.08, 0.06), (sx, by - 0.04, 2.03)), ('b', (1.24, 0.14, 0.05), (sx, by - 0.06, 1.18)),
                       ('l', (0.06, 0.08, 0.86), (sx - 0.58, by - 0.04, 1.6)), ('r', (0.06, 0.08, 0.86), (sx + 0.58, by - 0.04, 1.6)),
                       ('m', (0.03, 0.05, 0.8), (sx, by - 0.03, 1.6))):
        box('k_win_' + n, size, c, TOP)
    # upper cabinets on wall A, open shelf with jars on wall B left
    for i in range(3):
        y = by - 0.75 - i * 0.62
        box('k_up%d' % i, (0.36, 0.6, 0.7), (bx + 0.18, y, 1.85), W)
        geom.make_object('k_uph%d' % i, geom.capsule((bx + 0.37, y - 0.22, 1.56), (bx + 0.37, y - 0.22, 1.66), 0.007), GR, col)
    box('k_shelf', (0.9, 0.24, 0.03), (bx + 0.75, by - 0.12, 1.55), TOP)
    for i, (r, h) in enumerate(((0.05, 0.16), (0.045, 0.2), (0.055, 0.13), (0.04, 0.22))):
        x = bx + 0.42 + i * 0.2
        geom.make_object('k_jar%d' % i, geom.lathe([(0, 0), (r, 0), (r, h), (r * 0.7, h + 0.01), (r * 0.7, h + 0.03), (0, h + 0.03)], 20), JAR, col,
                         location=(x, by - 0.12, 1.565))
    # fridge at the end of run B
    fx = bx + 3.0 + 0.4
    box('k_fridge', (0.78, 0.7, 2.0), (fx, by - 0.36, 1.0), ACC, 0.02)
    box('k_fridge_gap', (0.78, 0.71, 0.01), (fx, by - 0.36, 1.28), GR, 0)
    geom.make_object('k_fh1', geom.capsule((fx - 0.3, by - 0.73, 1.38), (fx - 0.3, by - 0.73, 1.75), 0.012), GR, col)
    geom.make_object('k_fh2', geom.capsule((fx - 0.3, by - 0.73, 0.95), (fx - 0.3, by - 0.73, 1.18), 0.012), GR, col)
    # potted plant on run A
    geom.make_object('k_pot', geom.lathe([(0, 0), (0.07, 0), (0.09, 0.16), (0, 0.16)], 20), POT, col, location=(bx + 0.3, by - 2.3, 0.9))
    for i in range(7):
        a = i * 2 * math.pi / 7
        geom.make_object('k_leaf%d' % i, geom.ellipsoid(0.03, 0.03, 0.12, (bx + 0.3 + 0.05 * math.cos(a), by - 2.3 + 0.05 * math.sin(a), 1.17), 10, 6), LEAF, col)
    # pendant lamps over the work area
    for i, x in enumerate(params.get('pendants', (-0.15, 0.55))):
        y = params.get('pendant_y', -0.2)
        geom.make_object('k_cord%d' % i, geom.capsule((x, y, 2.4), (x, y, 1.95), 0.004), GR, col)
        geom.make_object('k_lamp%d' % i, geom.lathe([(0, 0.0), (0.16, 0.0), (0.05, 0.14), (0.02, 0.17), (0, 0.17)], 28, False, True), LMP, col,
                         location=(x, y, 1.8))
    return dict(palette=None, sun_dir=Vector(params.get('sun', (0.55, -0.35, 0.75))).normalized(), anchors={})


def toon_room(params):
    """Pastel living-room corner for the big-head toon look: plank floor, rug, a side wall (plane x = side_x,
    facing +X) that carries the light switch, a back wall (plane y = back_y) with a night window, a framed
    picture, baseboards, a side table with a plant. Room lights are normal lights (keyed by `light_cues`);
    lights tagged `night` (moonlight through the window + a faint camera-side fill) do the opposite."""
    from . import materials as M
    col = _col('set')
    P = dict(wall='#c9d6cd', wall2='#d3ddd5', floor='#c99c6c', plank='#b48858', base='#f4f0e9', rug='#e2b85c',
             frame='#3d3b39', art='#f1e4cf', art2='#8e1f2a', sky='#22345e', moon='#f5efd9', table='#efe7da', pot='#d98b62', leaf='#6fae84')
    P.update(params.get('palette', {}))
    clay_lights(col, sun_dir=params.get('sun', (0.6, -0.45, 0.7)), key=params.get('key', 1.1),
                world=params.get('world', '#f3eee9'), world_power=params.get('world_power', 0.45), angle=18)
    for n, loc, en, size, colr, aim in (('r_softkey', (2.6, -3.0, 3.0), 230, 3.0, '#fff2e2', (-0.5, 0.2, 1.0)),
                                        ('r_fill', (-0.4, -3.4, 1.8), 60, 4.0, '#e8f0ff', (-0.5, 0.2, 1.0)),
                                        ('r_top', (0.2, 0.3, 3.2), 60, 2.5, '#fff1e0', (-0.5, 0.2, 0.0))):
        L = bpy.data.lights.new(n, 'AREA')
        L.energy, L.size, L.color = en, size, srgb(colr)[:3]
        o = bpy.data.objects.new(n, L)
        col.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sx = params.get('side_x', -1.0)
    by = params.get('back_y', 1.6)
    wx = params.get('window_x', 1.5)
    for n, loc, en, size, colr, aim in (('night_moon', (wx, by - 0.3, 1.9), params.get('moon', 90), 1.2, '#7f9be0', (-0.6, -0.2, 0.9)),
                                        ('night_fill', (0.8, -3.0, 1.7), params.get('night_fill', 22), 3.0, '#5f78c4', (-0.5, 0.0, 1.2))):
        L = bpy.data.lights.new(n, 'AREA')
        L.energy, L.size, L.color = en, size, srgb(colr)[:3]
        L['night'] = True
        o = bpy.data.objects.new(n, L)
        o['night'] = True
        col.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    WALL = M.clay('r_wall', P['wall'], rough=0.9)
    WALL2 = M.clay('r_wall2', P['wall2'], rough=0.9)
    FL = M.clay('r_floor', P['floor'], rough=0.7)
    PL = M.clay('r_plank', P['plank'], rough=0.8)
    BASE = M.clay('r_base', P['base'], rough=0.6)
    RUG = M.clay('r_rug', P['rug'], rough=0.95)
    FR = M.clay('r_frame', P['frame'], rough=0.5)
    ART = M.clay('r_art', P['art'], rough=0.8)
    ART2 = M.clay('r_art2', P['art2'], rough=0.7)
    SKY = M.flat('r_sky', P['sky'], 1.0)
    MOON = M.flat('r_moon', P['moon'], 2.0)
    TAB = M.clay('r_table', P['table'], rough=0.5)
    POT = M.clay('r_pot', P['pot'], rough=0.6)
    LEAF = M.clay('r_leaf', P['leaf'], rough=0.6)

    def box(n, size, c, mat, bevel=0.004):
        geom.make_object(n, geom.box(*size, c, bevel=bevel), mat, col)
    box('r_floor', (14, 14, 0.02), (0, 0, -0.01), FL, 0)
    for i in range(-30, 31):
        box('r_pl%d' % i, (14, 0.005, 0.003), (0, i * 0.18, 0.0003), PL, 0)
    box('r_rug', (1.9, 1.3, 0.012), (0.9, -0.2, 0.006), RUG, 0.004)
    box('r_wallS', (0.1, 9, 3.2), (sx - 0.05, by - 4.5, 1.6), WALL, 0)
    box('r_wallB', (9, 0.1, 3.2), (sx + 4.5, by + 0.05, 1.6), WALL2, 0)
    box('r_baseS', (0.03, 9, 0.11), (sx + 0.015, by - 4.5, 0.055), BASE, 0.003)
    box('r_baseB', (9, 0.03, 0.11), (sx + 4.5, by - 0.015, 0.055), BASE, 0.003)
    # night window on the back wall: sky, moon, frame, mullions, sill
    box('r_win_sky', (1.0, 0.02, 1.0), (wx, by - 0.005, 1.65), SKY, 0)
    if params.get('day'):
        # daylight: soft sky gradient + a warm sun patch through the window instead of the moon
        geom.make_object('r_sun_l', geom.ellipsoid(0.5, 0.005, 0.32, (wx + 0.2, by - 0.012, 1.45), 20, 8),
                         M.flat('r_skyglow', params.get('sky_glow', '#fff3d6'), 1.6), col)
        L = bpy.data.lights.new('day_sun', 'AREA')
        L.energy, L.size, L.color = params.get('sun_power', 260), 1.1, srgb(params.get('sun_color', '#ffd7a0'))[:3]
        o = bpy.data.objects.new('day_sun', L)
        col.objects.link(o)
        o.location = (wx, by + 0.6, 1.9)
        aim = Vector(params.get('sun_aim', (0.0, 0.0, 0.9)))
        o.rotation_euler = (aim - Vector(o.location)).to_track_quat('-Z', 'Y').to_euler()
    else:
        geom.make_object('r_moon', geom.ellipsoid(0.07, 0.005, 0.07, (wx + 0.25, by - 0.018, 1.92), 20, 8), MOON, col)
    for n, size, c in (('t', (1.12, 0.08, 0.06), (wx, by - 0.04, 2.18)), ('b', (1.2, 0.14, 0.05), (wx, by - 0.06, 1.13)),
                       ('l', (0.06, 0.08, 1.06), (wx - 0.53, by - 0.04, 1.65)), ('r', (0.06, 0.08, 1.06), (wx + 0.53, by - 0.04, 1.65)),
                       ('m', (0.03, 0.05, 1.0), (wx, by - 0.03, 1.65)), ('h', (1.0, 0.05, 0.03), (wx, by - 0.03, 1.65))):
        box('r_win_' + n, size, c, BASE)
    # framed picture (a little light-bulb portrait) on the back wall
    px = params.get('picture_x', 0.15)
    box('r_pic_frame', (0.5, 0.04, 0.62), (px, by - 0.02, 1.62), FR, 0.006)
    box('r_pic_art', (0.42, 0.01, 0.54), (px, by - 0.042, 1.62), ART, 0)
    geom.make_object('r_pic_bulb', geom.ellipsoid(0.08, 0.006, 0.09, (px, by - 0.05, 1.66), 20, 8), ART2, col)
    box('r_pic_base', (0.07, 0.008, 0.07), (px, by - 0.05, 1.54), FR, 0.002)
    # side table + plant by the back wall
    tx = params.get('table_x', 2.6)
    geom.make_object('r_tab_top', geom.lathe([(0, 0), (0.26, 0), (0.26, 0.03), (0, 0.03)], 32), TAB, col, location=(tx, by - 0.4, 0.6))
    geom.make_object('r_tab_leg', geom.capsule((tx, by - 0.4, 0.0), (tx, by - 0.4, 0.6), 0.025), TAB, col)
    geom.make_object('r_tab_foot', geom.lathe([(0, 0), (0.16, 0), (0.15, 0.02), (0, 0.02)], 24), TAB, col, location=(tx, by - 0.4, 0.0))
    geom.make_object('r_pot', geom.lathe([(0, 0), (0.08, 0), (0.1, 0.18), (0, 0.18)], 24), POT, col, location=(tx, by - 0.4, 0.63))
    for i in range(8):
        a = i * 2 * math.pi / 8
        geom.make_object('r_leaf%d' % i, geom.ellipsoid(0.035, 0.035, 0.15, (tx + 0.06 * math.cos(a), by - 0.4 + 0.06 * math.sin(a), 0.95), 10, 6),
                         LEAF, col)
    return dict(palette=None, sun_dir=Vector(params.get('sun', (0.6, -0.45, 0.7))).normalized(), anchors={})


def toon_stage(params):
    """Analysis stage: a dark seamless cyc with a round lit platform, cool-blue fill and a warm rim.
    The presenter stands near the origin; screens / models are props."""
    from . import materials as M
    col = _col('set')
    clay_lights(col, sun_dir=params.get('sun', (0.5, -0.5, 0.8)), key=params.get('key', 0.9),
                world=params.get('world', '#28344a'), world_power=params.get('world_power', 0.35), angle=20)
    for n, loc, en, size, colr, aim in (('st_key', (2.2, -2.8, 3.0), params.get('key_area', 260), 2.5, '#fff1de', (0.0, 0.0, 1.2)),
                                        ('st_fill', (-2.8, -2.0, 1.6), params.get('fill', 90), 3.0, '#a9c2ff', (0.0, 0.0, 1.2)),
                                        ('st_rim', (-0.8, 2.4, 2.6), params.get('rim', 260), 1.6, '#ffc88a', (0.0, 0.0, 1.5)),
                                        ('st_rim2', (1.6, 2.2, 2.2), params.get('rim', 260) * 0.6, 1.6, '#ffd2a0', (0.0, 0.0, 1.5))):
        L = bpy.data.lights.new(n, 'AREA')
        L.energy, L.size, L.color = en, size, srgb(colr)[:3]
        o = bpy.data.objects.new(n, L)
        col.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cyc = M.clay('stg_cyc', params.get('color', '#34405a'), rough=0.85)
    prof = [(-20, 0.0)] + [(5 + 4 * math.sin(math.radians(a)), 4 - 4 * math.cos(math.radians(a))) for a in range(0, 91, 6)] + [(9, 14)]
    verts, faces = [], []
    for i, (y, z) in enumerate(prof):
        verts += [(-25, y, z), (25, y, z)]
    for i in range(len(prof) - 1):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    geom.make_object('stg_cyc', (verts, faces), cyc, col)
    disc = M.clay('stg_disc', params.get('disc', '#4a5878'), rough=0.6)
    geom.make_object('stg_disc', geom.lathe([(0, 0), (2.2, 0), (2.2, 0.04), (2.17, 0.06), (0, 0.06)], 64), disc, col)
    ring = M.flat('stg_ring', params.get('ring', '#7fd3e6'), 1.4)
    geom.make_object('stg_ring', geom.lathe([(2.12, 0.061), (2.16, 0.061), (2.16, 0.064), (2.12, 0.064)], 96, False, False), ring, col)
    return dict(palette=None, sun_dir=Vector(params.get('sun', (0.5, -0.5, 0.8))).normalized(), anchors={})


def toon_yard(params):
    """Back yard in daylight: lawn, a house wall (plane y = wall_y, facing -Y) with an open doorway at
    door_x, a path, bushes, round trees and a low fence; soft sky. Wind is done with props/fx."""
    from . import materials as M
    col = _col('set')
    clay_lights(col, sun_dir=params.get('sun', (-0.4, -0.5, 0.7)), key=params.get('key', 2.4),
                world=params.get('world', '#cfe3f2'), world_power=params.get('world_power', 0.9), angle=8, key_color='#fff2dc')
    P = dict(grass='#9cc77f', grass2='#8bb870', wall='#e8d9c4', trim='#f6f1e8', door='#6a8fb0', path='#d9cdb8',
             bush='#6fae6a', trunk='#8a6a4c', leaf='#79b86c', fence='#f3efe6', sky='#bfe0f5')
    P.update(params.get('palette', {}))
    wy, dx = params.get('wall_y', 1.2), params.get('door_x', -0.2)
    G = M.clay('y_grass', P['grass'], rough=0.95)
    G2 = M.clay('y_grass2', P['grass2'], rough=0.95)
    WL = M.clay('y_wall', P['wall'], rough=0.9)
    TR = M.clay('y_trim', P['trim'], rough=0.6)
    DR = M.clay('y_door', P['door'], rough=0.6)
    PT = M.clay('y_path', P['path'], rough=0.9)
    BU = M.clay('y_bush', P['bush'], rough=0.9)
    TK = M.clay('y_trunk', P['trunk'], rough=0.9)
    LF = M.clay('y_leaf', P['leaf'], rough=0.9)
    FN = M.clay('y_fence', P['fence'], rough=0.7)
    SKY = M.gradient('y_sky', [(0.0, '#e9f3f8'), (1.0, P['sky'])], axis='Z', lo=0.0, hi=14.0, strength=1.0)

    def box(n, size, c, mat, bevel=0.004):
        geom.make_object(n, geom.box(*size, c, bevel=bevel), mat, col)
    box('y_ground', (60, 60, 0.02), (0, 0, -0.01), G, 0)
    import random
    r = random.Random(4)
    for i in range(70):
        x, y = r.uniform(-9, 9), r.uniform(-7, 9)
        geom.make_object('y_tuft%d' % i, geom.ellipsoid(r.uniform(0.25, 0.6), r.uniform(0.2, 0.5), 0.004, (x, y, 0.001), 12, 4), G2, col)
    # house wall with a doorway (gap) at door_x, width 0.95, height 2.15; open door swung inside
    dw, dh = 0.95, 2.15
    L, R = dx - dw / 2, dx + dw / 2
    box('y_wallL', (L + 6, 0.25, 3.4), ((L - 6) / 2, wy + 0.125, 1.7), WL, 0)
    box('y_wallR', (6 - R, 0.25, 3.4), ((R + 6) / 2, wy + 0.125, 1.7), WL, 0)
    box('y_wallT', (dw, 0.25, 3.4 - dh), (dx, wy + 0.125, dh + (3.4 - dh) / 2), WL, 0)
    box('y_inside', (dw + 0.4, 0.05, dh), (dx, wy + 1.6, dh / 2), M.clay('y_in', '#c9d6cd', rough=0.9), 0)
    box('y_infloor', (dw + 0.4, 1.6, 0.02), (dx, wy + 0.85, 0.005), M.clay('y_infl', '#c99c6c', rough=0.8), 0)
    for n, size, c in (('l', (0.08, 0.06, dh + 0.06), (L - 0.04, wy - 0.02, (dh + 0.06) / 2)),
                       ('r', (0.08, 0.06, dh + 0.06), (R + 0.04, wy - 0.02, (dh + 0.06) / 2)),
                       ('t', (dw + 0.16, 0.06, 0.08), (dx, wy - 0.02, dh + 0.04))):
        box('y_trim_' + n, size, c, TR)
    door = geom.make_object('y_door', geom.box(dw - 0.02, 0.05, dh - 0.02, (dw / 2 - 0.01, 0.025, (dh - 0.02) / 2), bevel=0.006), DR, col)
    door.location = (L + 0.01, wy + 0.25, 0.0)
    door.rotation_euler.z = math.radians(params.get('door_open', 75))
    box('y_step', (dw + 0.5, 0.45, 0.06), (dx, wy - 0.2, 0.03), TR)
    for i in range(5):
        box('y_path%d' % i, (0.6, 0.45, 0.02), (dx + (0.08 if i % 2 else -0.06), wy - 0.75 - i * 0.62, 0.01), PT, 0.01)
    # windows on the wall
    for x in (dx - 2.0, dx + 1.7):
        box('y_win_%d' % int(x * 10), (1.0, 0.04, 0.9), (x, wy - 0.01, 1.6), M.flat('y_wing', '#a9cde6', 0.9), 0)
        box('y_winf_%d' % int(x * 10), (1.1, 0.06, 1.0), (x, wy + 0.0, 1.6), TR, 0.004)
    # bushes along the wall, trees, fence
    for i, x in enumerate((dx - 1.2, dx - 3.0, dx + 1.0, dx + 2.8)):
        geom.make_object('y_bush%d' % i, geom.ellipsoid(0.45, 0.3, 0.35, (x, wy - 0.3, 0.25), 20, 10), BU, col)
    for i, (x, y, h) in enumerate(params.get('trees', ((-3.6, -1.5, 3.2), (3.4, -2.5, 3.6), (-5.5, -4.0, 3.0), (5.5, -5.0, 3.4)))):
        geom.make_object('y_trunk%d' % i, geom.capsule((x, y, 0), (x, y, h * 0.55), 0.09, 0.07), TK, col)
        geom.make_object('y_crown%d' % i, geom.ellipsoid(0.9, 0.9, 1.0, (x, y, h * 0.7), 24, 14), LF, col)
    for i in range(-12, 13):
        box('y_fp%d' % i, (0.08, 0.05, 0.8), (i * 0.6, -7.0, 0.4), FN)
    box('y_frail', (15, 0.04, 0.06), (0, -7.0, 0.62), FN)
    geom.make_object('y_sky', geom.plane(80, 30, (0, 0, 0), 'Y'), SKY, col).location = (0, 14, 6)
    return dict(palette=None, sun_dir=Vector(params.get('sun', (-0.4, -0.5, 0.7))).normalized(), anchors={})


TEMPLATES = {'toon_room': toon_room, 'toon_stage': toon_stage, 'toon_yard': toon_yard, 'clay_studio': clay_studio, 'cafe_street': cafe_street, 'room_interior': room_interior, 'park': park, 'studio_void': studio_void,
             'clay_cabin': clay_cabin, 'cockpit_cutaway': cockpit_cutaway, 'airport': airport,
             'desert_runway': desert_runway, 'clay_kitchen': clay_kitchen}


def build_set(spec):
    return TEMPLATES[spec.get('template', 'cafe_street')](spec.get('params', {}))
