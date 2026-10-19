"""Stylised materials: cel shading with a scene-wide rim light (the 'StudioLook' node group).

Every cel material samples real scene lighting (Diffuse -> Shader to RGB), quantises it
into soft bands, tints shadows/lights from the look preset and adds a directional rim
(Fresnel x facing-the-backlight mask). Changing the StudioLook group re-lights everything.
"""
import bpy
from .util import srgb

LOOK = 'StudioLook'


def _sock(ng, name, kind, default=None):
    s = ng.interface.new_socket(name, in_out='OUTPUT', socket_type=kind)
    return s


def look_group():
    ng = bpy.data.node_groups.get(LOOK)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(LOOK, 'ShaderNodeTree')
    for n, k in (('ShadowTint', 'NodeSocketColor'), ('LitTint', 'NodeSocketColor'),
                 ('RimColor', 'NodeSocketColor'), ('RimDir', 'NodeSocketVector'),
                 ('RimStrength', 'NodeSocketFloat'), ('RimWidth', 'NodeSocketFloat'),
                 ('Ambient', 'NodeSocketColor')):
        _sock(ng, n, k)
    out = ng.nodes.new('NodeGroupOutput')
    vals = {}
    for i, (n, kind) in enumerate((('ShadowTint', 'RGB'), ('LitTint', 'RGB'), ('RimColor', 'RGB'),
                                   ('RimDir', 'XYZ'), ('RimStrength', 'VAL'), ('RimWidth', 'VAL'),
                                   ('Ambient', 'RGB'))):
        if kind == 'RGB':
            nd = ng.nodes.new('ShaderNodeRGB')
        elif kind == 'VAL':
            nd = ng.nodes.new('ShaderNodeValue')
        else:
            nd = ng.nodes.new('ShaderNodeCombineXYZ')
        nd.name = nd.label = n
        nd.location = (-300, -i * 160)
        if kind == 'XYZ':
            ng.links.new(nd.outputs[0], out.inputs[n])
        else:
            ng.links.new(nd.outputs[0], out.inputs[n])
        vals[n] = nd
    set_look(shadow='#3a2f5c', lit='#fff1e0', rim='#ffb25c', rim_dir=(0, 1, 0.3), rim_strength=1.0,
             rim_width=0.5, ambient='#2a2440')
    return ng


def set_look(shadow=None, lit=None, rim=None, rim_dir=None, rim_strength=None, rim_width=None, ambient=None):
    ng = bpy.data.node_groups[LOOK]
    N = ng.nodes
    if shadow:
        N['ShadowTint'].outputs[0].default_value = srgb(shadow)
    if lit:
        N['LitTint'].outputs[0].default_value = srgb(lit)
    if rim:
        N['RimColor'].outputs[0].default_value = srgb(rim)
    if ambient:
        N['Ambient'].outputs[0].default_value = srgb(ambient)
    if rim_dir is not None:
        from mathutils import Vector
        d = Vector(rim_dir).normalized()
        for i, k in enumerate('XYZ'):
            N['RimDir'].inputs[k].default_value = d[i]
    if rim_strength is not None:
        N['RimStrength'].outputs[0].default_value = rim_strength
    if rim_width is not None:
        N['RimWidth'].outputs[0].default_value = rim_width


def _math(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new('ShaderNodeMath')
    n.operation = op
    n.use_clamp = clamp
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def _mix(nt, fac, a, b, blend='MIX'):
    n = nt.nodes.new('ShaderNodeMix')
    n.data_type = 'RGBA'
    n.blend_type = blend
    for sock, x in ((n.inputs[0], fac), (n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(x, (int, float)):
            sock.default_value = x
        elif isinstance(x, tuple):
            sock.default_value = x
        else:
            nt.links.new(x, sock)
    return n.outputs[2]


STYLE = {'mode': 'cel'}       # 'cel' (silhouette/rim look) or 'clay' (white reconstruction look)


def set_style(mode):
    STYLE['mode'] = mode


def clay(name, color='#e9e9ea', rough=0.62, emit=0.0, spec=0.25):
    """Physically lit matte material (soft shadows + AO) for the clay/reconstruction look."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    b.inputs['Base Color'].default_value = srgb(color)
    b.inputs['Roughness'].default_value = rough
    for k in ('Specular IOR Level', 'Specular'):
        if k in b.inputs:
            b.inputs[k].default_value = spec
            break
    if emit > 0:
        b.inputs['Emission Color'].default_value = srgb(color)
        b.inputs['Emission Strength'].default_value = emit
    nt.links.new(b.outputs[0], out.inputs['Surface'])
    m.diffuse_color = srgb(color)
    return m


def subject(name, color, emit=0.12):
    """Saturated solid colour that marks the subject of a reconstruction (red/blue mannequin)."""
    return clay(name, color, rough=0.42, emit=emit, spec=0.35)


def ghost(name, color='#9fd8ff', strength=1.6, alpha=0.35, edge=0.55):
    """Translucent glowing hologram (bystanders, past positions)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    lw = nt.nodes.new('ShaderNodeLayerWeight')
    lw.inputs['Blend'].default_value = 0.35
    a = _math(nt, 'ADD', _math(nt, 'MULTIPLY', lw.outputs['Facing'], edge), alpha, clamp=True)
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = srgb(color)
    em.inputs['Strength'].default_value = strength
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(a, mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    m.surface_render_method = 'BLENDED'
    m.use_backface_culling = True
    try:
        m.use_transparency_overlap = False
    except Exception:
        pass
    return m


def image_mat(name, path, emit=1.0, alpha=True, lit=False):
    """Material from an image file (attached reference, logo, photo, backdrop)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.extension = 'CLIP'
    if lit:
        b = nt.nodes.new('ShaderNodeBsdfPrincipled')
        b.inputs['Roughness'].default_value = 0.6
        nt.links.new(tex.outputs['Color'], b.inputs['Base Color'])
        surf = b.outputs[0]
    else:
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Strength'].default_value = emit
        nt.links.new(tex.outputs['Color'], em.inputs['Color'])
        surf = em.outputs[0]
    if alpha:
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(tex.outputs['Alpha'], mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(surf, mx.inputs[2])
        surf = mx.outputs[0]
        m.surface_render_method = 'BLENDED'
    nt.links.new(surf, out.inputs['Surface'])
    return m


def cel(name, color, rim=1.0, shade=1.0, emit=0.0, bands='soft', gloss=0.0):
    """Cel-shaded material. color: hex. rim: rim-light multiplier. emit: self-illumination (0..1).
    In 'clay' style the same call returns a matte physically-lit material in that colour."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    if STYLE['mode'] == 'clay':
        return clay(name, color, emit=emit * 0.5)
    look = look_group()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    g = nt.nodes.new('ShaderNodeGroup')
    g.node_tree = look
    dif = nt.nodes.new('ShaderNodeBsdfDiffuse')
    dif.inputs['Color'].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new('ShaderNodeShaderToRGB')
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    nt.links.new(s2r.outputs[0], bw.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    if bands == 'hard':
        cr.interpolation = 'CONSTANT'
        cr.elements[0].position, cr.elements[0].color = 0.0, (0, 0, 0, 1)
        cr.elements[1].position, cr.elements[1].color = 0.22, (1, 1, 1, 1)
    else:
        cr.interpolation = 'EASE'
        cr.elements[0].position, cr.elements[0].color = 0.04, (0, 0, 0, 1)
        e = cr.elements.new(0.16)
        e.color = (0.55, 0.55, 0.55, 1)
        cr.elements[-1].position, cr.elements[-1].color = 0.5, (1, 1, 1, 1)
    nt.links.new(bw.outputs[0], ramp.inputs[0])
    tint = _mix(nt, ramp.outputs[0], g.outputs['ShadowTint'], g.outputs['LitTint'])
    base = srgb(color)
    col = _mix(nt, 1.0, tint, base, 'MULTIPLY')
    col = _mix(nt, 1.0 - shade, col, base)               # shade=0 -> flat colour
    # ambient lift so shadows are never pure black
    amb = _mix(nt, 1.0, g.outputs['Ambient'], base, 'MULTIPLY')
    col = _mix(nt, 0.35, col, amb, 'ADD')
    # rim light
    if rim > 0:
        lw = nt.nodes.new('ShaderNodeLayerWeight')
        lw.inputs['Blend'].default_value = 0.5
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        lo = _math(nt, 'SUBTRACT', 1.0, g.outputs['RimWidth'])
        fres = _math(nt, 'SUBTRACT', lw.outputs['Facing'], lo)
        fres = _math(nt, 'MULTIPLY', fres, 8.0, clamp=True)
        dot = nt.nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        nt.links.new(geo.outputs['Normal'], dot.inputs[0])
        nt.links.new(g.outputs['RimDir'], dot.inputs[1])
        dmask = _math(nt, 'MULTIPLY', _math(nt, 'ADD', dot.outputs['Value'], 0.15), 2.2, clamp=True)
        k = _math(nt, 'MULTIPLY', _math(nt, 'MULTIPLY', fres, dmask), g.outputs['RimStrength'])
        k = _math(nt, 'MULTIPLY', k, rim, clamp=False)
        rimc = _mix(nt, 1.0, g.outputs['RimColor'], (0, 0, 0, 1), 'MIX')
        rimc = _mix(nt, k, (0, 0, 0, 1), g.outputs['RimColor'])
        col = _mix(nt, 1.0, col, rimc, 'ADD')
    if emit > 0:
        col = _mix(nt, emit, col, base, 'ADD')
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(col, em.inputs['Color'])
    if gloss > 0:
        gl = nt.nodes.new('ShaderNodeBsdfGlossy')
        gl.inputs['Roughness'].default_value = 0.25
        add = nt.nodes.new('ShaderNodeAddShader')
        mixf = nt.nodes.new('ShaderNodeMixShader')
        mixf.inputs[0].default_value = gloss
        nt.links.new(em.outputs[0], add.inputs[0])
        nt.links.new(gl.outputs[0], add.inputs[1])
        nt.links.new(em.outputs[0], mixf.inputs[1])
        nt.links.new(add.outputs[0], mixf.inputs[2])
        nt.links.new(mixf.outputs[0], out.inputs['Surface'])
    else:
        nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m


def flat(name, color, strength=1.0, alpha=1.0):
    """Unlit colour (face decals, lit windows, sky elements)."""
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
    em.inputs['Strength'].default_value = strength
    if alpha < 1.0:
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


def radial_glow(name, color, strength=1.0, power=2.0, alpha=1.0):
    """Soft round glow sprite (uses generated/object coords of a unit plane centred at 0)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    ln = nt.nodes.new('ShaderNodeVectorMath')
    ln.operation = 'LENGTH'
    nt.links.new(tc.outputs['Object'], ln.inputs[0])
    a = _math(nt, 'SUBTRACT', 1.0, _math(nt, 'MULTIPLY', ln.outputs['Value'], 2.0), clamp=True)
    a = _math(nt, 'POWER', a, power)
    a = _math(nt, 'MULTIPLY', a, alpha)
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = srgb(color)
    em.inputs['Strength'].default_value = strength
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(a, mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    m.surface_render_method = 'BLENDED'
    return m


def gradient(name, stops, axis='Z', lo=0.0, hi=1.0, strength=1.0):
    """Unlit vertical gradient over object-space `axis` from lo..hi. stops: [(pos, hex), ...]."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    nt.links.new(sep.outputs['XYZ'.index(axis)], mr.inputs['Value'])
    mr.inputs['From Min'].default_value = lo
    mr.inputs['From Max'].default_value = hi
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    cr.interpolation = 'EASE'
    cr.elements[0].position, cr.elements[0].color = stops[0][0], srgb(stops[0][1])
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], srgb(stops[-1][1])
    for p, c in stops[1:-1]:
        e = cr.elements.new(p)
        e.color = srgb(c)
    nt.links.new(mr.outputs[0], ramp.inputs[0])
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Strength'].default_value = strength
    nt.links.new(ramp.outputs[0], em.inputs['Color'])
    nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m


def soft_shadow(name='contact_shadow', color='#120c1e', alpha=0.6):
    """Blob shadow decal: unit disc, darkest at centre."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = radial_glow(name, color, 1.0, 1.5, alpha)
    return m
