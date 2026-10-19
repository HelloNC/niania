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


TEMPLATES = {'clay_studio': clay_studio, 'cafe_street': cafe_street, 'room_interior': room_interior, 'park': park, 'studio_void': studio_void,
             'clay_cabin': clay_cabin, 'cockpit_cutaway': cockpit_cutaway, 'airport': airport,
             'desert_runway': desert_runway}


def build_set(spec):
    return TEMPLATES[spec.get('template', 'cafe_street')](spec.get('params', {}))
