"""A cartoon restyle over another set: `"set": "toon", "base": "<set>"` on an env in episode.json.

The base set (`sets_<base>.py`) is built as usual; then, before the first frame renders, every lit surface in the scene
(sets and props: any material with a Principled BSDF) is turned into a cel-shaded flat colour, and the compositor draws ink
lines where surfaces turn or depth jumps. Figures are untouched: they are unlit with their own outline. Everything is driven
by the env's `toon` dict (a set's materials take the style of the first env using them; an env whose lines differ from the
first env's marks its surfaces so the ink there is drawn its way):

  detail   share of a texture's own detail kept over its mean colour (0 = flat colour, 1 = the photo texture)
  sat, val saturation and value scale of every surface colour
  bands    [[luma, [r, g, b]], ...]: the cel ramp, light luma -> a tint the surface colour is multiplied by
  exposure light luma scale before the ramp
  ink      [r, g, b] line colour, or null for no lines; ink_width (px of a 1080-wide frame), ink_alpha,
           ink_normal / ink_depth (edge thresholds)
  alpha_step [lo, hi]: fading or soft-edged things (puffs, spray) step from clear to solid over this alpha range
  day_sky  [horizon, mid, zenith, cloud, cloud shade]: a painted sky dome for an outdoor set, 0-255
  haze     false: drop the base set's world volume (EEVEE jitters it every frame, so light shafts shimmer)
"""

import bpy
import numpy as np

import kit
import wiring

_envs = []        # (objects, style) per toon env, in build order
_mat_style = {}   # material name -> the style of the first env that uses it
_done = {"mats": False}


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgba(rgb):
    return (_lin(rgb[0]), _lin(rgb[1]), _lin(rgb[2]), 1.0)


_BUMPS = {"ShaderNodeBump", "ShaderNodeNormalMap", "ShaderNodeDisplacement"}


def _upstream_images(sock):
    """Every image texture node the socket's value is computed from (not through bump or normal maps)."""
    found, seen, todo = [], set(), [sock]
    while todo:
        for lk in todo.pop().links:
            n = lk.from_node
            if n.as_pointer() in seen or n.bl_idname in _BUMPS:
                continue
            seen.add(n.as_pointer())
            if n.bl_idname == "ShaderNodeTexImage" and n.image:
                found.append(n)
            todo.extend(n.inputs)
    return found


_means = {}


def _image_mean(img):
    if img.name not in _means:
        try:
            a = np.empty(len(img.pixels), dtype=np.float32)
            img.pixels.foreach_get(a)
            a = a.reshape(-1, img.channels)
            _means[img.name] = tuple(float(v) for v in a[:, :3].mean(axis=0)) + (1.0,)
        except Exception:   # noqa: BLE001
            _means[img.name] = None
    return _means[img.name]


def _toon_material(m, st):
    nt = m.node_tree
    bs = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None) or \
        next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    if bs is None or out is None:
        return False
    N = nt.nodes.new
    L = nt.links.new
    # the surface colour: flat (the texture's mean) with a little of the texture kept, then saturated
    base_in = bs.inputs["Base Color"]
    if base_in.links:
        # each photo texture feeding the colour is flattened toward its own mean where it comes out, so tints, masks and
        # procedural patterns after it (tinted grass, checker carpet) still shape the colour
        for img_node in _upstream_images(base_in):
            mean = _image_mean(img_node.image)
            if mean is None:
                continue
            outs = [lk for lk in img_node.outputs["Color"].links if lk.to_node.bl_idname not in _BUMPS]
            flat = N("ShaderNodeRGB")
            flat.outputs[0].default_value = mean
            mix = N("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.inputs[0].default_value = st.get("detail", 0.3)
            L(flat.outputs[0], mix.inputs[6])
            L(img_node.outputs["Color"], mix.inputs[7])
            for lk in outs:
                to = lk.to_socket
                nt.links.remove(lk)
                L(mix.outputs[2], to)
        col = base_in.links[0].from_socket
    else:
        flat = N("ShaderNodeRGB")
        flat.outputs[0].default_value = tuple(base_in.default_value)
        col = flat.outputs[0]
    hs = N("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = st.get("sat", 1.3)
    hs.inputs["Value"].default_value = st.get("val", 1.0)
    L(col, hs.inputs["Color"])
    # the light: diffuse lighting (shadows included) to a luma, stepped by the cel ramp into a tint
    dif = N("ShaderNodeBsdfDiffuse")
    dif.inputs["Color"].default_value = (1, 1, 1, 1)
    if bs.inputs["Normal"].links:   # keep bump so bricks and planks still catch the light
        L(bs.inputs["Normal"].links[0].from_socket, dif.inputs["Normal"])
    s2r = N("ShaderNodeShaderToRGB")
    L(dif.outputs[0], s2r.inputs[0])
    bw = N("ShaderNodeRGBToBW")
    L(s2r.outputs["Color"], bw.inputs[0])
    ex = N("ShaderNodeMath")
    ex.operation = "MULTIPLY"
    ex.inputs[1].default_value = st.get("exposure", 1.0)
    L(bw.outputs[0], ex.inputs[0])
    ramp = N("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = st.get("interp", "CONSTANT")
    bands = st.get("bands", [[0.0, [0.55, 0.5, 0.78]], [0.25, [0.86, 0.84, 0.9]], [0.6, [1.06, 1.02, 0.95]]])
    els = ramp.color_ramp.elements
    while len(els) < len(bands):
        els.new(0.5)
    for e, (pos, tint) in zip(els, bands):
        e.position, e.color = pos, (tint[0], tint[1], tint[2], 1.0)
    L(ex.outputs[0], ramp.inputs["Fac"])
    mul = N("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    L(hs.outputs[0], mul.inputs[6])
    L(ramp.outputs["Color"], mul.inputs[7])
    em = N("ShaderNodeEmission")
    L(mul.outputs[2], em.inputs["Color"])
    surf = em.outputs[0]
    # glowing parts (lamps, windows) keep their glow on top
    es = bs.inputs.get("Emission Strength")
    if es is not None and (es.links or es.default_value > 0):
        add = N("ShaderNodeAddShader")
        L(surf, add.inputs[0])
        glow = N("ShaderNodeEmission")
        ec = bs.inputs["Emission Color"]
        if ec.links:
            L(ec.links[0].from_socket, glow.inputs["Color"])
        else:
            glow.inputs["Color"].default_value = tuple(ec.default_value)
        if es.links:
            L(es.links[0].from_socket, glow.inputs["Strength"])
        else:
            glow.inputs["Strength"].default_value = es.default_value
        L(glow.outputs[0], add.inputs[1])
        surf = add.outputs[0]
    # cut-outs (leaf cards) stay cut out
    al = bs.inputs["Alpha"]
    fading = al.links and not _upstream_images(al)
    if fading or (not al.links and al.default_value < 0.999):
        # see-through and fading things (spray, drops, foam, glass): blended, which keeps them out of the passes the ink
        # is drawn from, so small drops are not inked solid black and see-through sheets draw no outline
        m.surface_render_method = "BLENDED"
    if al.links or al.default_value < 0.999:
        tr = N("ShaderNodeBsdfTransparent")
        ms = N("ShaderNodeMixShader")
        if fading and st.get("alpha_step"):   # a soft puff or a fade becomes a hard-edged cartoon shape
            stp = N("ShaderNodeMapRange")
            stp.clamp = True
            stp.inputs["From Min"].default_value, stp.inputs["From Max"].default_value = st["alpha_step"]
            L(al.links[0].from_socket, stp.inputs["Value"])
            L(stp.outputs["Result"], ms.inputs[0])
        elif al.links:
            L(al.links[0].from_socket, ms.inputs[0])
        else:
            ms.inputs[0].default_value = al.default_value
        L(tr.outputs[0], ms.inputs[1])
        L(surf, ms.inputs[2])
        surf = ms.outputs[0]
    for lk in list(out.inputs["Surface"].links):
        nt.links.remove(lk)
    L(surf, out.inputs["Surface"])
    return True


def _painted_sky(c):
    """A painted day sky for a set lit by a photo sky: an inside-out dome, a smooth gradient from a warm horizon to a
    deep zenith, with flat two-tone clouds stretched along the horizon. The photo sky still lights the scene.
    `c` = [horizon, mid, zenith, cloud, cloud shade], 0-255."""
    R = 700.0
    m = bpy.data.materials.new("toon_sky")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    em = N("ShaderNodeEmission")
    tc = N("ShaderNodeTexCoord")
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["Object"], sep.inputs["Vector"])
    zn = N("ShaderNodeMath")
    zn.operation = "DIVIDE"
    zn.inputs[1].default_value = R
    L(sep.outputs["Z"], zn.inputs[0])
    grad = N("ShaderNodeValToRGB")
    g = grad.color_ramp.elements
    g[0].position, g[0].color = 0.0, _rgba(c[0])
    g[1].position, g[1].color = 0.45, _rgba(c[2])
    g.new(0.12).color = _rgba(c[1])
    L(zn.outputs["Value"], grad.inputs["Fac"])
    mp = N("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.005, 0.005, 0.03)
    L(tc.outputs["Object"], mp.inputs["Vector"])
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.4
    nz.inputs["Detail"].default_value = 1.5
    L(mp.outputs["Vector"], nz.inputs["Vector"])
    col = grad.outputs["Color"]
    for thr, tone in ((0.57, c[4]), (0.61, c[3])):
        gt = N("ShaderNodeMath")
        gt.operation = "GREATER_THAN"
        gt.inputs[1].default_value = thr
        L(nz.outputs["Fac"], gt.inputs[0])
        mx = N("ShaderNodeMix")
        mx.data_type = "RGBA"
        L(gt.outputs[0], mx.inputs[0])
        L(col, mx.inputs[6])
        mx.inputs[7].default_value = _rgba(tone)
        col = mx.outputs[2]
    L(col, em.inputs["Color"])
    L(em.outputs[0], out.inputs["Surface"])
    o = kit.obj("sphere", m, "toon_sky_dome", loc=(0, 40, 0), scl=(R, R, R), bake=True)
    o.visible_shadow = False
    return o


def _ink(sc, st, fine_st=None):
    """Ink lines in the compositor: edges of the normal pass (surfaces turning) and of inverse depth (silhouettes)."""
    vl = sc.view_layers[0]
    vl.use_pass_normal = True
    vl.use_pass_z = True
    ng = sc.compositing_node_group
    if ng is None:
        ng = bpy.data.node_groups.new("post", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl0 = ng.nodes.new("CompositorNodeRLayers")
        go0 = ng.nodes.new("NodeGroupOutput")
        ng.links.new(rl0.outputs["Image"], go0.inputs["Image"])
        sc.compositing_node_group = ng
    rl = next(n for n in ng.nodes if n.bl_idname == "CompositorNodeRLayers")
    go = next(n for n in ng.nodes if n.bl_idname == "NodeGroupOutput")
    final = go.inputs["Image"].links[0].from_socket
    N, L = ng.nodes.new, ng.links.new

    def filt(sock, kind="Sobel"):
        f = N("CompositorNodeFilter")
        try:
            f.inputs["Type"].default_value = kind
        except Exception:   # noqa: BLE001
            f.filter_type = kind.upper()
        L(sock, f.inputs["Image"])
        return f.outputs["Image"]

    def math(op, a, b=None):
        n = N("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L(v, n.inputs[i])
        return n.outputs[0]

    def luma(sock):
        sep = N("CompositorNodeSeparateColor")
        L(sock, sep.inputs[0])
        return math("ADD", math("ADD", math("ABSOLUTE", sep.outputs[0]), math("ABSOLUTE", sep.outputs[1])), math("ABSOLUTE", sep.outputs[2]))

    def step(v, lo, hi):
        r = N("ShaderNodeMapRange")
        r.clamp = True
        L(v, r.inputs["Value"])
        r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = lo, hi
        return r.outputs["Result"]

    en = step(luma(filt(rl.outputs["Normal"])), st.get("ink_normal", 1.2), st.get("ink_normal", 1.2) * 1.6)
    inv = math("DIVIDE", 1.0, math("MAXIMUM", rl.outputs["Depth"], 0.05))
    comb = N("CompositorNodeCombineColor")
    L(inv, comb.inputs[0])
    L(inv, comb.inputs[1])
    L(inv, comb.inputs[2])
    ed = step(luma(filt(comb.outputs[0])), st.get("ink_depth", 0.06), st.get("ink_depth", 0.06) * 2.0)
    edge = math("MAXIMUM", en, ed)
    px = sc.render.resolution_x / 1080   # line weights are pixels of a 1080-wide frame (a quarter-size draft draws hairlines)

    def weight(sock, width, kind="Feather"):
        size = max(0, round((int(width) - 1) * px))
        if not size:
            return sock
        de = N("CompositorNodeDilateErode")
        de.inputs["Size"].default_value = size
        de.inputs["Type"].default_value = kind
        L(sock, de.inputs[0])
        return de.outputs[0]

    main, fine = st, fine_st or st
    line = math("MULTIPLY", weight(edge, main.get("ink_width", 1)), main.get("ink_alpha", 0.85))
    if fine_st:   # envs with finer lines mark their surfaces in an AOV; the mark is spread over the lines that border them
        mark = weight(rl.outputs[AOV], max(main.get("ink_width", 1), 2) + 1, "Distance")
        thin = math("MULTIPLY", weight(edge, fine.get("ink_width", 1)), fine.get("ink_alpha", 0.85))
        blend = N("ShaderNodeMix")
        L(math("MINIMUM", mark, 1.0), blend.inputs[0])
        L(line, blend.inputs[2])
        L(thin, blend.inputs[3])
        line = blend.outputs[0]
    mix = N("ShaderNodeMix")
    mix.data_type = "RGBA"
    L(line, mix.inputs[0])
    L(final, mix.inputs[6])
    mix.inputs[7].default_value = _rgba(st["ink"])
    L(mix.outputs[2], go.inputs["Image"])


AOV = "toon_fine"


def _ink_key(st):
    return (st.get("ink_width", 1), st.get("ink_alpha", 0.85))


def _mark_fine(m):
    """Write 1 to the fine-line AOV from this material, whatever its surface is."""
    nt = m.node_tree
    aov = nt.nodes.new("ShaderNodeOutputAOV")
    try:
        aov.aov_name = AOV
    except AttributeError:
        aov.name = AOV
    aov.inputs["Value"].default_value = 1.0


def _restyle(scene, *_):
    """Once, as the first render job starts (after build_scene has added the props and its own compositing): restyle
    every material and add the ink. Nothing here changes per frame: a compositor changed while an animation renders
    takes effect a frame late, or blanks the frames after the change."""
    if _done["mats"]:
        return
    _done["mats"] = True
    main = _envs[0][1]
    n = 0
    for m in list(bpy.data.materials):
        if not (m.use_nodes and m.node_tree):
            continue
        # each set's own materials take its env's style; props take the first env's
        st = _mat_style.get(m.name, main)
        n += _toon_material(m, st)
        if st.get("ink") and _ink_key(st) != _ink_key(main):
            _mark_fine(m)
    if main.get("ink"):
        fine = next((st for _, st in _envs if st.get("ink") and _ink_key(st) != _ink_key(main)), None)
        try:
            vl = scene.view_layers[0]
            if fine and AOV not in vl.aovs:
                a = vl.aovs.add()
                a.name, a.type = AOV, "VALUE"
            _ink(scene, main, fine)
        except Exception as exc:   # noqa: BLE001
            print("toon: ink off:", repr(exc))
    print("toon: %d materials restyled" % n)


def build(spec):
    st = spec.get("toon", {})
    if not _envs:
        bpy.app.handlers.render_init.append(_restyle)
    r = wiring.build_set(spec["name"], dict(spec, set=spec["base"]), spec.get("cues", []))
    if st.get("haze", True) is False and r.get("world") is not None and r["world"].node_tree:
        nt = r["world"].node_tree
        for ln in list(nt.links):
            if ln.to_node.type == "OUTPUT_WORLD" and ln.to_socket.name == "Volume":
                nt.links.remove(ln)
    if st.get("day_sky"):
        r = dict(r, objs=list(r["objs"]) + [_painted_sky(st["day_sky"])])
    for o in r["objs"]:
        for slot in getattr(o, "material_slots", []):
            if slot.material:
                _mat_style.setdefault(slot.material.name, st)
    _envs.append((list(r["objs"]), st))
    return r
