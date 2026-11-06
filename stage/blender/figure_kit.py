"""Shared pieces of the 3D figures: colours, the expression vocabulary, flat face meshes and the soft floor shadow."""
import math

import bpy

INK = (14, 12, 18)
SKIN = (250, 247, 240)

# Expression vocabulary: eye openness, eyes drawn as happy arcs, brow angle (left/right, + = inner end up),
# brow lift, mouth curve (+ smile), mouth openness, mouth half-width, sweat drop.
EXPR = {
    "neutral":   dict(open=1.0, happy=0, bl=0.0, br=0.0, lift=0.00, curve=0.00, mopen=0.00, mw=0.17, sweat=0),
    "deadpan":   dict(open=0.55, happy=0, bl=-0.05, br=0.05, lift=-0.04, curve=0.00, mopen=0.00, mw=0.15, sweat=0),
    "smug":      dict(open=0.62, happy=0, bl=0.30, br=-0.08, lift=0.04, curve=0.55, mopen=0.00, mw=0.20, sweat=0),
    "worried":   dict(open=1.15, happy=0, bl=0.42, br=-0.42, lift=0.10, curve=-0.30, mopen=0.00, mw=0.15, sweat=1),
    "sad":       dict(open=0.9, happy=0, bl=0.50, br=-0.50, lift=0.05, curve=-0.65, mopen=0.00, mw=0.16, sweat=0),
    "mad":       dict(open=0.8, happy=0, bl=-0.45, br=0.45, lift=-0.02, curve=-0.45, mopen=0.00, mw=0.18, sweat=0),
    "laugh":     dict(open=0.0, happy=1, bl=0.10, br=-0.10, lift=0.10, curve=0.80, mopen=0.50, mw=0.30, sweat=0),
    "grin":      dict(open=0.9, happy=0, bl=0.12, br=-0.12, lift=0.08, curve=0.75, mopen=0.28, mw=0.27, sweat=0),
    "surprised": dict(open=1.45, happy=0, bl=0.0, br=0.0, lift=0.22, curve=0.00, mopen=0.55, mw=0.10, sweat=0),
    "awe":       dict(open=1.35, happy=0, bl=0.20, br=-0.20, lift=0.20, curve=0.35, mopen=0.35, mw=0.15, sweat=0),
}
PARAMS = list(EXPR["neutral"].keys())

_flat = {}    # (rgb, name) -> (colour node, base rgb, material); tone_all tints them all

def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def flat_mat(rgb, name=None):
    key = (tuple(rgb), name)
    if key in _flat:
        return _flat[key][2]
    m = bpy.data.materials.new(name or "flat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    em.inputs["Color"].default_value = (_lin(rgb[0]), _lin(rgb[1]), _lin(rgb[2]), 1)
    _flat[key] = (em, tuple(rgb), m)
    return m


def tone_all(tone):
    """Tint every flat material (figures are unlit, so the scene's mood is applied here)."""
    for em, rgb, _ in _flat.values():
        em.inputs["Color"].default_value = (_lin(rgb[0] * tone[0]), _lin(rgb[1] * tone[1]), _lin(rgb[2] * tone[2]), 1)



# ------------------------------------------------------------------------------------------ flat meshes
def _poly(name, n):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0)] * n, [], [list(range(n))])
    me.update()
    return me


def _set_poly(me, pts):
    me.vertices.foreach_set("co", [c for x, z in pts for c in (x, 0.0, z)])
    me.update()


def _disc(name, n=40):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(math.cos(2 * math.pi * i / n), 0, math.sin(2 * math.pi * i / n)) for i in range(n)], [], [list(range(n))])
    me.update()
    return me

CAP_N = 6


def _strip(name, n):
    """A shape whose outline is a left side (n points, top to bottom) then a right side (n points, bottom to top), filled
    with quads between facing points. Unlike one n-gon it stays filled when the outline goes concave and moves each frame."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0)] * (2 * n), [], [[i, i + 1, 2 * n - 2 - i, 2 * n - 1 - i] for i in range(n - 1)])
    me.update()
    return me



def _capsule(a, b, r):
    """Flat stadium around the segment a-b (a limb): 2*(CAP_N+1) points."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    pts = [(b[0] + r * math.cos(ang - math.pi / 2 + math.pi * i / CAP_N), b[1] + r * math.sin(ang - math.pi / 2 + math.pi * i / CAP_N)) for i in range(CAP_N + 1)]
    pts += [(a[0] + r * math.cos(ang + math.pi / 2 + math.pi * i / CAP_N), a[1] + r * math.sin(ang + math.pi / 2 + math.pi * i / CAP_N)) for i in range(CAP_N + 1)]
    return pts


def _offset_polygon(pts, t):
    """Grow a polygon outward by t (mitred), for the outline behind a flat shape."""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = (p1[0] - p0[0], p1[1] - p0[1])
        e2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1 = math.hypot(*e1)
        l2 = math.hypot(*e2)
        if l1 < 1e-7 and l2 < 1e-7:
            out.append(p1)
            continue
        n1 = (e1[1] / l1, -e1[0] / l1) if l1 >= 1e-7 else None
        n2 = (e2[1] / l2, -e2[0] / l2) if l2 >= 1e-7 else None
        n1, n2 = n1 or n2, n2 or n1   # a repeated point (where two sides of a strip meet) takes its neighbour's normal
        bx, bz = n1[0] + n2[0], n1[1] + n2[1]
        k = 1 + n1[0] * n2[0] + n1[1] * n2[1]
        out.append((p1[0] + t * bx / max(k, 0.2), p1[1] + t * bz / max(k, 0.2)))
    cx = sum(p[0] for p in pts) / n
    cz = sum(p[1] for p in pts) / n
    inward = sum((o[0] - cx) ** 2 + (o[1] - cz) ** 2 for o in out) < sum((p[0] - cx) ** 2 + (p[1] - cz) ** 2 for p in pts)
    if inward:
        out = [(2 * p[0] - o[0], 2 * p[1] - o[1]) for p, o in zip(pts, out)]
    return out


def _lerp(a, b, u):
    return a + (b - a) * u




def arc(w, curve, th, mopen, up=False):
    """Ribbon along x in -w..w: centre line bends by `curve` (+ smile), `mopen` drops the lower edge."""
    n = 9
    xs = [-w + 2 * w * i / (n - 1) for i in range(n)]
    sign = -1.0 if up else 1.0
    upper = [(x, -sign * curve * w * (1 - (x / w) ** 2)) for x in xs]
    lower = [(x, z - th - mopen * w * 1.6 * max(0.0, 1 - (x / w) ** 2) ** 0.6) for x, z in upper]
    return upper + lower[::-1]


def expr_params(fig, f, expr_events, moves=()):
    """The face on frame f: the latest expression eased in over 4 frames, a squint just before a move, and blinks."""
    name, t0, prev = "neutral", -999, "neutral"
    for e in expr_events:
        if e["f"] <= f:
            prev, name, t0 = name, e["expr"], e["f"]
        else:
            break
    u = min(1.0, (f - t0) / 4.0)
    u = u * u * (3 - 2 * u)
    a, b = EXPR[prev], EXPR[name]
    p = {k: _lerp(a[k], b[k], u) for k in PARAMS}
    if any(m - 6 <= f < m for m in moves):   # anticipation: the eyes narrow just before anything else moves
        p["open"] *= 0.55
        p["lift"] -= 0.03
    period = 88 + (fig.uid * 23) % 31
    ph = (f + fig.uid * 37) % period
    if ph < 4 and p["happy"] < 0.5:
        p["open"] *= (0.08, 0.35, 0.35, 0.08)[ph]
    return p


def build_shadow(fig):
    """A soft shadow on the floor under the figure."""
    n = 28
    me = bpy.data.meshes.new("shadow")
    me.from_pydata([(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0) for i in range(n)], [], [list(range(n))])
    me.update()
    m = bpy.data.materials.new("shadow")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    dark = nt.nodes.new("ShaderNodeEmission")
    dark.inputs["Color"].default_value = (0.02, 0.015, 0.02, 1.0)
    mix.inputs[0].default_value = 0.42
    nt.links.new(clear.outputs["BSDF"], mix.inputs[1])
    nt.links.new(dark.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:   # noqa: BLE001
        pass
    me.materials.append(m)
    fig.shadow = bpy.data.objects.new("%s_shadow" % fig.name, me)
    fig.sc.collection.objects.link(fig.shadow)
    fig.shadow.parent = fig.root
    fig.shadow.location = (0.0, 0.0, 0.004)
    fig.shadow.scale = (0.50 * fig.scale, 0.20 * fig.scale, 1.0)
    fig.extras = [fig.shadow]

