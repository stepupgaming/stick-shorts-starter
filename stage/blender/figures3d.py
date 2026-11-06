"""The 3D characters: a round shaded head with an even ink outline, hair and hats modelled in the round, a rounded
clothed body (collar, belt, buttons, pockets), and thin black stick limbs with round hands and shoes.

The baked skeleton (bake.json, from stage/author.mjs and stage/skeleton.mjs) drives every frame: `update` places the head, body and
limbs from the skeleton's segments. The skeleton is flat, so the head and body turn a little toward the side the figure
faces, the whole figure turns toward the camera, and an arm that crosses the body is drawn in front of it.

Everything is shaded with a soft painted light fixed to the camera (upper left), so a character reads the same in every
set; a shot's `tone` still tints it (figure_kit.tone_all) and the set's lights still cast its floor shadow.

Actor options (episode.json "actors"): color, skin, hair (rgb, or null for none), cap ("none", "cap", "fedora",
"hardhat", "beret", "glasses", or a list), hat (rgb), costume ("plain", "coat", "hivis", "apron", "cross"), trim, sash (belt),
collar, tie, strap, apron, scale, depth (metres toward the back), x (metres), face (1 right, -1 left).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import figure_kit as F

INK = F.INK
LIGHT = Vector((-0.50, 0.62, -0.60)).normalized()   # camera space (x right, y up, z into the picture): from upper left
HALF = (LIGHT + Vector((0.0, 0.0, -1.0))).normalized()
HEAD_AX, HEAD_AY, HEAD_AZ = 1.0, 0.93, 0.97          # the head: a ball a little shallower than wide
EYE_X, EYE_Z = 0.30, 0.08
HEAD_YAW, BODY_YAW = 0.42, 0.28                      # how far head and body turn toward the facing side (radians)
HAIR = [(70, 46, 32), (40, 32, 30), (118, 76, 44), (92, 60, 40)]


# ------------------------------------------------------------------------------------------------ materials
def _maprange(nt, src, a, b, lo, hi, smooth=True):
    r = nt.nodes.new("ShaderNodeMapRange")
    r.clamp = True
    if smooth:
        r.interpolation_type = "SMOOTHSTEP"
    nt.links.new(src, r.inputs["Value"])
    r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = a, b
    r.inputs["To Min"].default_value, r.inputs["To Max"].default_value = lo, hi
    return r.outputs["Result"]


def mat(rgb, name, kind="cloth"):
    """Unlit painted shading from a camera-fixed light. kind: flat (no shading), skin (soft, pale shadow), cloth, shiny
    (cloth with a hard gloss spot, for hats, hair and shoes). Registered with figures.tone_all through its colour input."""
    key = (tuple(rgb), "c3d_%s_%s" % (name, kind))
    if key in F._flat:
        return F._flat[key][2]
    m = bpy.data.materials.new(key[1])
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    em = N("ShaderNodeEmission")
    L(em.outputs[0], out.inputs["Surface"])
    hs = N("ShaderNodeHueSaturation")   # passes its colour through; tone_all writes the tinted colour here
    hs.inputs["Color"].default_value = (F._lin(rgb[0]), F._lin(rgb[1]), F._lin(rgb[2]), 1)
    col = hs.outputs["Color"]
    if kind != "flat":
        geo = N("ShaderNodeNewGeometry")
        vt = N("ShaderNodeVectorTransform")
        vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
        L(geo.outputs["Normal"], vt.inputs[0])
        dot = N("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L(vt.outputs[0], dot.inputs[0])
        dot.inputs[1].default_value = tuple(LIGHT)
        lo = {"skin": 0.80, "cloth": 0.64, "shiny": 0.58}[kind]
        shade = _maprange(nt, dot.outputs["Value"], -0.45, 0.75, lo, 1.0)
        lw = N("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.5
        rim = _maprange(nt, lw.outputs["Facing"], 0.55, 1.0, 1.0, 0.86 if kind == "skin" else 0.78)
        mul = N("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        L(shade, mul.inputs[0])
        L(rim, mul.inputs[1])
        mix = N("ShaderNodeMix")
        mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        L(col, mix.inputs[6])
        L(mul.outputs[0], mix.inputs[7])
        col = mix.outputs[2]
        if kind == "shiny":
            d2 = N("ShaderNodeVectorMath")
            d2.operation = "DOT_PRODUCT"
            L(vt.outputs[0], d2.inputs[0])
            d2.inputs[1].default_value = tuple(HALF)
            spot = _maprange(nt, d2.outputs["Value"], 0.955, 0.975, 0.0, 0.75)
            gl = N("ShaderNodeMix")
            gl.data_type = "RGBA"
            L(spot, gl.inputs[0])
            L(col, gl.inputs[6])
            gl.inputs[7].default_value = (1.0, 0.97, 0.9, 1.0)
            col = gl.outputs[2]
    L(col, em.inputs["Color"])
    F._flat[key] = (hs, tuple(rgb), m)
    return m


_outline = {}


def outline_mat():
    """The ink shell behind a part (inverted hull): only its far side shows, as an even rim around the silhouette."""
    if "m" not in _outline:
        m = bpy.data.materials.new("c3d_outline")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (F._lin(INK[0]), F._lin(INK[1]), F._lin(INK[2]), 1)
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        m.use_backface_culling = True
        _outline["m"] = m
    return _outline["m"]


def part(sc, me, rgb, name, parent, kind="cloth", outline=True, ol=0.055):
    """An object with a painted material and, with `outline`, an ink shell `ol` thick (in the mesh's own units)."""
    me.materials.append(mat(INK, "ink", "flat") if (rgb is INK and kind == "flat") else mat(rgb, name, kind))
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.parent = parent
    if outline:
        me.materials.append(outline_mat())
        sm = o.modifiers.new("ink", "SOLIDIFY")
        sm.thickness = ol
        sm.offset = 1.0
        sm.use_flip_normals = True
        sm.use_rim = False
        sm.use_even_offset = True
        sm.material_offset = 1
    return o


def surf(x, z, lift, ax=1.0, ay=0.93, az=0.97, c=(0.0, 0.0, 0.0)):
    """A point on the front (-y) of an ellipsoid at (x, z) from its middle, lifted toward the camera."""
    q = 1 - (x / ax) ** 2 - (z / az) ** 2
    return (c[0] + x, c[1] - ay * math.sqrt(max(q, 0.0)) - lift, c[2] + z)


def set_pts(o, pts):
    o.data.vertices.foreach_set("co", [v for p in pts for v in p])
    o.data.update()


# ------------------------------------------------------------------------------------------------ meshes
def _mesh(name, verts, faces, smooth=True, fix=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    if fix:   # outward normals: the hull outline and the shading both need them
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    me.update()
    return me


def _lathe_pts(prof, segs=40, sx=1.0, sy=1.0, closed=False):
    """Revolve an (r, z) profile about z. A point with r = 0 is a pole. closed joins the last ring back to the first."""
    verts, rings, faces = [], [], []
    for r, z in prof:
        if r < 1e-6:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            rings.append(list(range(len(verts), len(verts) + segs)))
            verts += [(r * sx * math.cos(2 * math.pi * k / segs), r * sy * math.sin(2 * math.pi * k / segs), z) for k in range(segs)]
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(segs):
            k1 = (k + 1) % segs
            if len(a) == 1:
                faces.append([a[0], b[k], b[k1]])
            elif len(b) == 1:
                faces.append([a[k], a[k1], b[0]])
            else:
                faces.append([a[k], a[k1], b[k1], b[k]])
    return verts, faces


def _lathe(name, prof, segs=40, sx=1.0, sy=1.0, closed=False, xform=None):
    v, f = _lathe_pts(prof, segs, sx, sy, closed)
    if xform is not None:
        v = [xform @ Vector(p) for p in v]
    return _mesh(name, v, f)


def _ball(name, sx=1.0, sy=1.0, sz=1.0, segs=32, rings=16):
    prof = [(math.sin(math.pi * i / rings), math.cos(math.pi * i / rings)) for i in range(rings + 1)]
    prof[0], prof[-1] = (0.0, 1.0), (0.0, -1.0)
    v, f = _lathe_pts(prof, segs)
    return _mesh(name, [(x * sx, y * sy, z * sz) for x, y, z in v], f)


def _tube(name, segs=14):
    v, f = _lathe_pts([(1.0, 0.0), (1.0, 1.0)], segs)
    return _mesh(name, v, f)


def _ring(name, R, r, segs=32, tsegs=10):
    """A torus in the x-z plane facing -y (a spectacle rim)."""
    prof = [(R + r * math.cos(2 * math.pi * i / tsegs), r * math.sin(2 * math.pi * i / tsegs)) for i in range(tsegs)]
    return _lathe(name, prof, segs, closed=True, xform=Matrix.Rotation(math.pi / 2, 3, "X"))


def _interp(prof, z):
    """Radius of a top-to-bottom (r, z) profile at height z."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if (z0 - z) * (z1 - z) <= 0 and z0 != z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[0][0] if abs(z - prof[0][1]) < abs(z - prof[-1][1]) else prof[-1][0]


# ------------------------------------------------------------------------------------------------ the figure
class Figure3D:
    """One actor. build_scene calls update() every frame; a prop model can put an object in a hand with hold()."""

    def __init__(self, sc, name, spec, style, K, cx, floor_px):
        self.sc, self.name, self.spec = sc, name, spec
        self.K, self.CX, self.FLOOR = K, cx, floor_px
        self.uid = spec["uid"]
        self.depth = spec.get("depth", 0.0)
        self.scale = spec.get("scale", 1.0)
        self.head_scale = style.get("head", 1.9)
        self.billboard = style.get("billboard", 0.8)
        self.limb_k = style.get("limb3d", 0.075)      # limb radius, in head radii
        self.ol = style.get("outline3d", 0.055)       # ink outline, in head radii
        self.torso_len = style.get("torso", 2.1)     # body length below the collar, in head radii
        self.arm_drop = style.get("arm_drop", 0.55)
        self.shoulders = style.get("shoulders", 1.0)
        self.color = spec["color"]
        self.skin = spec.get("skin", F.SKIN)
        self.costume = spec.get("costume", "plain")
        self.trim = spec.get("trim", [226, 188, 92])
        self.root = bpy.data.objects.new("%s_root" % name, None)
        sc.collection.objects.link(self.root)
        self.objs, self.props, self.extras = [], [], []
        self.visible = True
        self.details, self.hat_parts, self.hat_rgb = set(), 0, set()
        self._build()

    # ------------------------------------------------------------------ construction
    def _obj(self, me, rgb, name, parent, kind="cloth", outline=True, ol=None):
        o = part(self.sc, me, rgb, "%s_%s" % (self.name, name), parent, kind, outline, self.ol if ol is None else ol)
        self.objs.append(o)
        return o

    def _empty(self, name, parent):
        e = bpy.data.objects.new("%s_%s" % (self.name, name), None)
        self.sc.collection.objects.link(e)
        e.parent = parent
        e.rotation_mode = "ZYX"   # yaw about its own axis first, then the tilt in the picture plane
        return e

    def _build(self):
        self.head = self._empty("head", self.root)
        self.body = self._empty("body", self.root)
        self._build_head()
        self._build_body()
        lmat = INK
        self.tubes, self.joints = {}, {}
        for seg in ("Left upper arm", "Left forearm", "Right upper arm", "Right forearm",
                    "Left thigh", "Left lower leg", "Right thigh", "Right lower leg"):
            self.tubes[seg] = self._obj(_tube("limb"), lmat, seg, self.root, "flat", outline=False)
            self.joints[seg] = self._obj(_ball("joint", segs=14, rings=8), lmat, seg + "_joint", self.root, "flat", outline=False)
        self.neck = self._obj(_tube("neck"), lmat, "neck", self.root, "flat", outline=False)
        self.hands = {s: self._obj(_ball("hand", segs=20, rings=10), INK, s + "_hand", self.root, "shiny", outline=False)
                      for s in ("Left forearm", "Right forearm")}
        self.feet = {s: self._obj(_ball("shoe", 1.0, 0.62, 0.5, 20, 10), INK, s + "_shoe", self.root, "shiny", outline=False)
                     for s in ("Left lower leg", "Right lower leg")}
        F.build_shadow(self)

    # ---- head
    @staticmethod
    def _surf(x, z, lift):
        """A point on the head's front at face coordinates (x, z), lifted toward the camera."""
        return surf(x, z, lift, HEAD_AX, HEAD_AY, HEAD_AZ)

    def _feature(self, me, rgb, name, kind="flat"):
        o = self._obj(me, rgb, name, self.head, kind, outline=False)
        return o

    def _build_head(self):
        sp = self.spec
        self._obj(_ball("skull", HEAD_AX, HEAD_AY, HEAD_AZ, 48, 24), self.skin, "skull", self.head, "skin")
        hair = sp.get("hair", HAIR[self.uid % len(HAIR)])
        if hair:   # a cap of hair over the back and top, its front edge high on the forehead
            th = [math.radians(a) for a in range(0, 100, 5)]
            prof = [(1.045 * math.sin(t), 1.045 * math.cos(t)) for t in th]
            prof[0] = (0.0, 1.045)
            xf = Matrix.Diagonal((HEAD_AX, HEAD_AY, HEAD_AZ)) @ Matrix.Rotation(-math.radians(52), 3, "X")
            self._obj(_lathe("hair", prof, 40, xform=xf), hair, "hair", self.head, "shiny")
        blush = [int(0.6 * s + 0.4 * c) for s, c in zip(self.skin, (236, 120, 128))]
        self.cheek = [self._feature(F._disc("cheek", 24), blush, "cheek%d" % i) for i in range(2)]
        self.eye = [self._feature(F._disc("eye", 28), INK, "eye%d" % i) for i in range(2)]
        self.glint = [self._feature(F._disc("glint", 14), (255, 255, 255), "glint%d" % i) for i in range(2)]
        self.eye_arc = [self._feature(F._strip("eyearc", 9), INK, "eyearc%d" % i) for i in range(2)]
        self.brow = [self._feature(F._poly("brow", 2 * (F.CAP_N + 1)), INK, "brow%d" % i) for i in range(2)]
        self.mouth = self._feature(F._strip("mouth", 9), INK, "mouth")
        self.sweat = self._feature(F._disc("sweat", 16), (120, 190, 250), "sweat")
        kinds = sp.get("cap", "none")
        for kind in ([kinds] if isinstance(kinds, str) else kinds):
            self._build_hat(kind)

    def _hat(self, me, rgb, name, kind="shiny", outline=True):
        self.hat_parts += 1
        self.hat_rgb.add(tuple(rgb))
        return self._obj(me, rgb, "hat_" + name, self.head, kind, outline)

    def _build_hat(self, kind):
        H = self._hat
        hat_rgb = self.spec.get("hat", None)
        if kind == "fedora":
            c = hat_rgb or [104, 90, 80]
            H(_lathe("crown", [(0.0, 1.07), (0.30, 1.17), (0.60, 1.18), (0.78, 1.04), (0.84, 0.80), (0.86, 0.56), (0.0, 0.56)],
                     40, sy=0.98), c, "crown")
            H(_lathe("brim", [(0.78, 0.50), (1.52, 0.46), (1.62, 0.51), (1.55, 0.56), (0.80, 0.60)], 48, sy=0.98, closed=True),
              [int(v * 0.92) for v in c], "brim")
            H(_lathe("band", [(0.875, 0.60), (0.88, 0.76), (0.0, 0.76), (0.0, 0.60)], 40, sy=0.98, closed=True), [44, 34, 30], "band", "cloth")
            H(_ball("feather", 0.07, 0.04, 0.24), [178, 64, 50], "feather", "cloth").location = (-0.80, 0.18, 0.80)
        elif kind == "hardhat":
            c = hat_rgb or [240, 192, 44]
            H(_lathe("dome", [(0.0, 1.24), (0.42, 1.20), (0.78, 1.03), (0.98, 0.74), (1.05, 0.52), (1.06, 0.44), (0.0, 0.44)], 48),
              c, "dome")
            H(_lathe("brim", [(1.0, 0.42), (1.20, 0.40), (1.22, 0.45), (1.04, 0.50)], 48, sx=1.0, sy=1.04, closed=True),
              [int(v * 0.9) for v in c], "brim")
            r = H(_ball("ridge", 0.13, 0.62, 0.12, 24, 12), [int(min(255, v * 1.06)) for v in c], "ridge")
            r.location = (0.0, 0.02, 1.16)
            b = H(_ball("badge", 0.13, 0.04, 0.13, 20, 10), [60, 132, 92], "badge", "cloth", outline=False)
            b.location = (0.0, -0.98, 0.72)
        elif kind == "cap":   # a baseball cap, its peak to the front
            c = hat_rgb or [229, 72, 63]
            H(_lathe("dome", [(0.0, 1.17), (0.45, 1.13), (0.80, 0.98), (0.99, 0.76), (1.05, 0.58), (0.0, 0.58)], 48), c, "dome")
            pk = H(_ball("peak", 0.66, 0.58, 0.07, 32, 12), [int(v * 0.88) for v in c], "peak")
            pk.location, pk.rotation_euler = (0.0, -0.92, 0.62), (0.14, 0.0, 0.0)
            H(_ball("button", 0.11, 0.11, 0.06, 16, 8), [int(v * 0.85) for v in c], "button", outline=False).location = (0.0, 0.0, 1.17)
        elif kind == "beret":
            c = hat_rgb or [156, 44, 58]
            xf = Matrix.Translation((-0.10, 0.04, 0.0)) @ Matrix.Rotation(0.22, 4, "Y")
            H(_lathe("beret", [(0.0, 1.20), (0.55, 1.18), (0.98, 1.04), (1.12, 0.90), (1.02, 0.76), (0.84, 0.66), (0.0, 0.70)],
                     44, xform=xf.to_3x3()), c, "beret").location = (-0.10, 0.04, 0.0)
            H(_lathe("edge", [(0.86, 0.62), (0.90, 0.70), (0.0, 0.72), (0.0, 0.62)], 44, closed=True, xform=xf.to_3x3()),
              [int(v * 0.78) for v in c], "edge", "cloth").location = (-0.10, 0.04, 0.0)
            s = H(_tube("stalk", 8), INK, "stalk", "flat", outline=False)
            s.location, s.scale = (0.18, 0.04, 1.16), (0.035, 0.035, 0.12)
            p = H(_ball("pin", 0.07, 0.04, 0.07, 16, 8), [214, 172, 70], "pin", "shiny", outline=False)
            p.location = (0.45, -0.93, 0.80)
        elif kind == "glasses":
            for sd in (-1, 1):
                rim = H(_ring("rim", 0.19, 0.028), INK, "rim%d" % sd, "shiny", outline=False)
                rim.location = self._surf(sd * EYE_X, EYE_Z, 0.07)
            br = H(_tube("bridge", 8), INK, "bridge", "flat", outline=False)
            br.location = (-0.11, -0.97, EYE_Z + 0.04)
            br.rotation_euler = (0, math.pi / 2, 0)
            br.scale = (0.022, 0.022, 0.22)
        elif kind != "none":
            raise ValueError("unknown cap %r for a 3D figure" % kind)

    # ---- body
    def _body_prof(self):
        H = self.torso_len
        # a soft bean: round shoulders, widest low down, a round seat (no rim, so no barrel)
        return [(0.0, -0.02), (0.34, -0.05), (0.58, -0.13), (0.72, -0.28), (0.79, -0.50), (0.83, -0.85), (0.87, -H + 0.62),
                (0.88, -H + 0.40), (0.84, -H + 0.22), (0.74, -H + 0.09), (0.52, -H + 0.015), (0.0, -H)]

    BODY_SY = 0.70

    def _bsurf(self, x, z, lift):
        r = _interp(self.prof, z)
        return (x, -self.BODY_SY * math.sqrt(max(r * r - x * x, 0.0)) - lift, z)

    def _patch(self, corners, rgb, name, lift=0.012, ink=True, nu=6, nv=4):
        """A flat piece sewn on the body (collar, pocket, straps), bent onto its surface, with an ink border."""
        def grid(cs, lf):
            (ax, az), (bx, bz), (cx, cz), (dx, dz) = cs
            v = []
            for j in range(nv + 1):
                t = j / nv
                lx, lz = ax + (dx - ax) * t, az + (dz - az) * t
                rx, rz = bx + (cx - bx) * t, bz + (cz - bz) * t
                for i in range(nu + 1):
                    u = i / nu
                    v.append(self._bsurf(lx + (rx - lx) * u, lz + (rz - lz) * u, lf))
            f = [[j * (nu + 1) + i, j * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i]
                 for j in range(nv) for i in range(nu)]
            return v, f
        if ink:
            big = F._offset_polygon(list(corners), self.ol * 0.7)
            v, f = grid(big, lift * 0.5)
            self._obj(_mesh(name + "_ink", v, f, fix=False), INK, name + "_ink", self.body, "flat", outline=False)
        v, f = grid(corners, lift)
        o = self._obj(_mesh(name, v, f, fix=False), rgb, name, self.body, "cloth", outline=False)
        o["detail"] = name
        self.details.add(name)
        return o

    def _band(self, z0, z1, rgb, name, grow=0.025):
        prof = [(_interp(self.prof, z0) + grow, z0), (_interp(self.prof, z1) + grow, z1)]
        o = self._obj(_lathe(name, [(0.0, z0)] + prof + [(0.0, z1)], 44, sy=self.BODY_SY + 0.02, closed=False), rgb, name, self.body, "cloth",
                      ol=self.ol * 0.45)
        self.details.add(name)
        return o

    def _bead(self, x, z, r, rgb, name, lift=0.01):
        o = self._obj(_ball(name, r, r * 0.6, r, 16, 8), rgb, name, self.body, "shiny", outline=False)
        o.location = self._bsurf(x, z, lift)
        self.details.add(name)
        return o

    def _build_body(self):
        sp, c, T = self.spec, self.color, self.trim
        self.prof = self._body_prof()
        Hl = self.torso_len
        self._obj(_lathe("torso", self.prof, 48, sy=self.BODY_SY), c, "torso", self.body, "cloth")
        belt = sp.get("sash", [int(v * 0.55) for v in c])
        zb = -Hl * 0.62
        self._band(zb + 0.06, zb - 0.06, belt, "belt", grow=0.012)
        metal = T if sum(abs(a - b) for a, b in zip(T, belt)) > 90 else [int(v * 0.55) for v in T]
        bk = self._patch([(-0.13, zb - 0.10), (0.13, zb - 0.10), (0.13, zb + 0.10), (-0.13, zb + 0.10)], metal, "buckle", 0.045)
        self._patch([(-0.07, zb - 0.055), (0.07, zb - 0.055), (0.07, zb + 0.055), (-0.07, zb + 0.055)], belt, "buckle_in", 0.05, ink=False)
        collar = sp.get("collar", [244, 240, 228])
        for sd in (-1, 1):   # two collar points either side of the throat
            self._patch([(0.0, -0.06), (sd * 0.42, -0.08), (sd * 0.26, -0.34), (sd * 0.02, -0.22)][:: sd], collar, "collar", 0.02)
        kind = self.costume
        if kind == "cross":
            strap = sp.get("strap", [40, 30, 24])
            for sd in (-1, 1):
                self._patch([(sd * 0.62, -0.30), (sd * 0.48, -0.24), (-sd * 0.62, zb + 0.06), (-sd * 0.70, zb - 0.02)][:: sd], strap, "straps", 0.016)
            self._bead(0.0, -0.60, 0.075, T, "buttons", 0.03)
        else:
            for i in range(3):
                self._bead(0.0, -0.46 - 0.22 * i, 0.05, T, "buttons", 0.012)
        if kind == "coat":
            pk = [int(v * 0.8) for v in c]
            self._patch([(-0.56, -0.62), (-0.24, -0.62), (-0.24, -0.42), (-0.56, -0.42)], pk, "pocket", 0.016)
            self._patch([(-0.50, -0.42), (-0.30, -0.42), (-0.33, -0.33), (-0.47, -0.31)], collar, "pocket_square", 0.02)
            if sp.get("tie"):
                self._patch([(-0.07, -0.20), (0.07, -0.20), (0.11, zb + 0.10), (-0.11, zb + 0.10)], sp["tie"], "tie", 0.022)
        elif kind == "hivis":
            refl = [226, 230, 232]
            for sd in (-1, 1):
                self._patch([(sd * 0.40, -0.16), (sd * 0.26, -0.18), (sd * 0.24, zb + 0.08), (sd * 0.40, zb + 0.08)][:: sd], refl, "reflective_braces", 0.016)
            self._patch([(-0.62, zb - 0.38), (0.62, zb - 0.38), (0.62, zb - 0.26), (-0.62, zb - 0.26)], refl, "reflective_band", 0.016, nu=12)
        elif kind == "apron":
            self._patch([(-0.5, zb - 0.08), (0.5, zb - 0.08), (0.56, -Hl + 0.3), (-0.56, -Hl + 0.3)], sp.get("apron", [248, 246, 240]), "apron", 0.02)
        elif kind not in ("plain", "cross"):
            raise ValueError("unknown costume %r for a 3D figure" % kind)

    # ------------------------------------------------------------------ interface shared with figures.Figure
    def hold(self, o, arm="Right", end=True):
        """Keep object o at this figure's hand (end=True) or shoulder on every frame. arm: "Left" or "Right"."""
        self.props.append((o, arm + " forearm", end))

    def set_visible(self, visible):
        if visible != self.visible:
            self.visible = visible
            for o in self.objs + self.extras:
                o.hide_render = not visible

    # ------------------------------------------------------------------ per frame
    @staticmethod
    def _place_tube(o, a, b, r):
        d = b - a
        ln = d.length
        o.location = a
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d) if ln > 1e-9 else (1, 0, 0, 0)
        o.scale = (r, r, max(ln, 1e-5))

    @staticmethod
    def _set(o, pts):
        o.data.vertices.foreach_set("co", [c for p in pts for c in p])
        o.data.update()

    def update(self, rows, face, f, cam, expr_events, moves=()):
        K, FLOOR, R = self.K, self.FLOOR, rows
        pel = R["Torso"]
        x0 = pel[3]
        rx = (x0 - self.CX) * K
        self.root.location = (rx, self.depth, 0.0)
        dx, dy = cam.x - rx, cam.y - self.depth
        self.root.rotation_euler = (0, 0, max(-1.0, min(1.0, math.atan2(dx, -dy))) * self.billboard)

        def L(x, y):
            return ((x - x0) * K, (FLOOR - y) * K)

        hrow = R["Head"]
        ha, hb = L(hrow[3], hrow[4]), L(hrow[5], hrow[6])
        hr0 = math.hypot(hb[0] - ha[0], hb[1] - ha[1]) / 2
        Rh = hr0 * self.head_scale
        hd = ((hb[0] - ha[0]) / (2 * hr0 + 1e-9), (hb[1] - ha[1]) / (2 * hr0 + 1e-9))
        hc = (ha[0] + hd[0] * Rh * 1.06, ha[1] + hd[1] * Rh * 1.06)
        neck, hip = L(pel[5], pel[6]), L(pel[3], pel[4])
        ux, uz = neck[0] - hip[0], neck[1] - hip[1]
        ul = math.hypot(ux, uz) or 1e-9
        ux, uz = ux / ul, uz / ul

        # head
        self.head.location = (hc[0], 0.0, hc[1])
        self.head.rotation_euler = (0.0, math.atan2(hd[0], hd[1]), HEAD_YAW * face)
        self.head.scale = (Rh, Rh, Rh)
        # body: hangs from just under the head along the torso, turned a little toward the facing side
        top = (neck[0] - ux * 0.10 * Rh, neck[1] - uz * 0.10 * Rh)
        self.body.location = (top[0], 0.0, top[1])
        self.body.rotation_euler = (0.0, math.atan2(ux, uz), BODY_YAW * face)
        self.body.scale = (Rh, Rh, Rh)
        bm = self.body.matrix_basis.copy()
        self._place_tube(self.neck, Vector((top[0], 0.0, top[1])), Vector((hc[0], 0.0, hc[1])), self.limb_k * Rh * 1.4)

        lr = self.limb_k * Rh

        def body_front(p):
            """How far in front of the body's centre plane a point inside its outline must sit (0 outside it)."""
            vx, vz = p[0] - top[0], p[1] - top[1]
            t = -(vx * ux + vz * uz) / Rh            # head radii down the body
            lat = abs(vx * uz - vz * ux) / Rh        # head radii out from its axis
            if t < 0.05 or t > self.torso_len:
                return 0.0
            r = _interp(self.prof, -t)
            if lat >= r:
                return 0.0
            return (self.BODY_SY * math.sqrt(r * r - lat * lat) + 1.6 * self.limb_k) * Rh

        # arms: rooted on the body's sides below the shoulder; each arm takes the side its upper arm points to
        side = {}
        for sd in (-1, 1):
            zz = -0.24 - self.arm_drop * 0.45
            loc = bm @ Vector((sd * (_interp(self.prof, zz) - 0.06), -0.05, zz))
            side[sd] = loc
        pts = {}
        for nm in ("Left", "Right"):
            up, fo = R[nm + " upper arm"], R[nm + " forearm"]
            j, e, w = L(up[3], up[4]), L(up[5], up[6]), L(fo[5], fo[6])
            # each arm keeps its own side of the body (a hanging arm down the middle of the chest read as a stripe);
            # the skeleton's left arm reaches to screen right on a figure facing right, and swaps when it turns
            root = side[face if nm == "Left" else -face]
            off = (root.x - j[0], root.z - j[1])
            el = (e[0] + off[0], e[1] + off[1])
            wr = (w[0] + off[0], w[1] + off[1])
            p_el = Vector((el[0], -body_front(el), el[1]))
            p_wr = Vector((wr[0], -body_front(wr), wr[1]))
            pts[nm] = (root, p_el, p_wr)
            self._place_tube(self.tubes[nm + " upper arm"], root, p_el, lr)
            self._place_tube(self.tubes[nm + " forearm"], p_el, p_wr, lr)
            for seg, p in ((nm + " upper arm", p_el), (nm + " forearm", p_wr)):
                self.joints[seg].location, self.joints[seg].scale = p, (lr, lr, lr)
            d = (p_wr - p_el)
            d = d / (d.length or 1e-9)
            hand = p_wr + d * 0.05 * Rh
            self.hands[nm + " forearm"].location = hand
            hr = 0.15 * Rh
            self.hands[nm + " forearm"].scale = (hr, hr, hr)
            pts[nm] = pts[nm] + (hand,)
        # legs: from the hips (a little apart) under the body
        for nm, sd in (("Left", -1), ("Right", 1)):
            th, sh = R[nm + " thigh"], R[nm + " lower leg"]
            dxl = sd * 0.20 * Rh
            a, k, ft = L(th[3], th[4]), L(th[5], th[6]), L(sh[5], sh[6])
            pa, pk, pf = (Vector((a[0] + dxl, 0.0, a[1])), Vector((k[0] + dxl, 0.0, k[1])), Vector((ft[0] + dxl, 0.0, ft[1])))
            self._place_tube(self.tubes[nm + " thigh"], pa, pk, lr)
            self._place_tube(self.tubes[nm + " lower leg"], pk, pf, lr)
            self.joints[nm + " thigh"].location, self.joints[nm + " thigh"].scale = pk, (lr, lr, lr)
            self.joints[nm + " lower leg"].location, self.joints[nm + " lower leg"].scale = pf, (lr, lr, lr)
            shoe = self.feet[nm + " lower leg"]
            shoe.location = (pf.x + face * 0.07 * Rh, -0.02 * Rh, pf.z + 0.03 * Rh)
            s = 0.19 * Rh
            shoe.scale = (s, s, s)

        # face
        p = F.expr_params(self, f, expr_events, moves)
        S = self._surf
        for i, sd in enumerate((-1, 1)):
            ex = sd * EYE_X
            happy = p["happy"] > 0.5
            rx_, rz_ = 0.105 * (0.9 + 0.1 * p["open"]), max(0.018, 0.15 * p["open"]) if not happy else 0.0
            n = len(self.eye[i].data.vertices)
            self._set(self.eye[i], [S(ex + rx_ * math.cos(2 * math.pi * k / n), EYE_Z + rz_ * math.sin(2 * math.pi * k / n), 0.012)
                                    for k in range(n)])
            gr = 0.035 if (p["open"] > 0.45 and not happy) else 0.0
            ng = len(self.glint[i].data.vertices)
            self._set(self.glint[i], [S(ex - 0.035 + gr * math.cos(2 * math.pi * k / ng), EYE_Z + 0.05 + gr * math.sin(2 * math.pi * k / ng), 0.02)
                                      for k in range(ng)])
            arc = F.arc(0.11, 0.85, 0.05, 0.0, up=True) if happy else [(0.0, 0.0)] * 18
            self._set(self.eye_arc[i], [S(ex + x, EYE_Z - 0.02 + z, 0.012) for x, z in arc])
            ang = (p["bl"] if sd < 0 else p["br"]) * face
            c = (ex, EYE_Z + 0.27 + p["lift"])
            h = 0.14
            a = (c[0] - h * math.cos(ang), c[1] - h * math.sin(ang))
            b = (c[0] + h * math.cos(ang), c[1] + h * math.sin(ang))
            self._set(self.brow[i], [S(x, z, 0.016) for x, z in F._capsule(a, b, 0.042)])
            ck = [(ex + sd * 0.12 + 0.13 * math.cos(2 * math.pi * k / 24), -0.13 + 0.07 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
            self._set(self.cheek[i], [S(x, z, 0.006) for x, z in ck])
        mo = F.arc(p["mw"] * 1.05, p["curve"], 0.07, p["mopen"])
        self._set(self.mouth, [S(x, z - 0.36, 0.012) for x, z in mo])
        if p["sweat"] > 0.5:
            drip = (f * 0.045) % 1.0
            sc = [(-0.68 + 0.07 * math.cos(2 * math.pi * k / 16), 0.6 - 0.3 * drip + 0.10 * math.sin(2 * math.pi * k / 16)) for k in range(16)]
            self._set(self.sweat, [S(x, z, 0.02) for x, z in sc])
        else:
            self._set(self.sweat, [(0.0, -0.5, 0.0)] * 16)

        for prop, seg, end in self.props:
            nm = seg.split(" ")[0]
            q = pts[nm][3] if end else pts[nm][0]
            prop.location = q
            prop.scale.x = face   # a held thing points the way the figure faces
