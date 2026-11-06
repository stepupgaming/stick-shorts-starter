"""Scene-building helpers shared by the stage script and the set builders (Blender side).

call init(scene) once after the scene exists; everything else creates objects in that scene.
"""

import math

import bmesh
import bpy

sc = None
BASE = {}


def init(scene):
    global sc
    sc = scene
    for k in ("sphere", "cyl", "cone", "cube"):
        BASE[k] = unit_mesh(k)


def lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


_mats = {}


def mat(rgb, rough=0.6, metal=0.0, emit=None, name=None):
    key = (tuple(rgb), rough, metal, tuple(emit) if emit else None, name)
    if key not in _mats:
        m = bpy.data.materials.new(name or "m")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (lin(rgb[0]), lin(rgb[1]), lin(rgb[2]), 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if emit:
            b.inputs["Emission Color"].default_value = (lin(emit[0]), lin(emit[1]), lin(emit[2]), 1)
            b.inputs["Emission Strength"].default_value = 0.0 if name else 1.0
        _mats[key] = m
    return _mats[key]


def smooth(me):
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))


def unit_mesh(kind):
    if kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=14)
    elif kind == "cyl":
        bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=1, vertices=28)
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add(radius1=1, radius2=0, depth=1, vertices=20)
    else:
        bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    me = o.data
    bpy.data.objects.remove(o)
    if kind != "cube":
        smooth(me)
    return me




def obj(kind, material, name, parent=None, loc=(0, 0, 0), scl=(1, 1, 1), rot=(0, 0, 0), bake=False):
    me = BASE[kind].copy()
    me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.location, o.scale = loc, scl
    o.rotation_mode = "XYZ"
    o.rotation_euler = rot
    if parent:
        o.parent = parent
    if bake:   # put the scale into the mesh so object space is metres (textures keep a constant density)
        from mathutils import Matrix
        o.data.transform(Matrix.Diagonal((scl[0], scl[1], scl[2], 1.0)))
        o.scale = (1.0, 1.0, 1.0)
    return o


def empty(name, parent=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    sc.collection.objects.link(e)
    e.location, e.rotation_euler = loc, rot
    if parent:
        e.parent = parent
    return e


def lathe(profile, name, material, steps=64):
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in profile]
    es = [bm.edges.new((vs[j], vs[j + 1])) for j in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), dvec=(0, 0, 0), angle=2 * math.pi, steps=steps)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    return o


def plane(name, material, x0, x1, y0, y1, z, axis="z"):
    """Axis-aligned quad with real-size coordinates (so Object-space textures are in metres)."""
    if axis == "z":
        vs = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    else:  # wall facing -Y at y=z, spanning x and (y0..y1 used as z range)
        vs = [(x0, z, y0), (x1, z, y0), (x1, z, y1), (x0, z, y1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], [(0, 1, 2, 3)] if axis == "z" else [(0, 3, 2, 1)])
    me.update()
    me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    return o


class collect:
    """with collect() as g: ...  -> g.objs are the objects linked to the scene inside the block."""

    def __enter__(self):
        self.before = {o.name for o in sc.collection.objects}
        self.objs = []
        return self

    def __exit__(self, *exc):
        self.objs = [o for o in sc.collection.objects if o.name not in self.before]
        return False
