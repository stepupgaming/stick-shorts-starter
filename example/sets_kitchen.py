"""The example's kitchen: checker floor, mint walls, cabinets and counter, a window, a fridge, a pendant lamp and the
kitchen table (its top at 0.76 m, two and a half feet). Coordinates in metres: z up, the back wall at y = 2.25, the open
front toward the camera (-y). The table stands at the origin.

A set module is any sets_<name>.py with build(spec) -> dict(objs, world, sun, fill[, ticks, clip]):
  objs   every object the set made (shown only while a shot uses this env)
  world  a bpy world (the ambient light and background)
  sun    (energy, (r, g, b), (rx, ry, rz) degrees) for the stage's shared sun; fill: the shared fill light's energy
  ticks  functions called with the frame number every frame (something that moves on its own)
Put it next to episode.json (or in stage/blender to share it) and name it in an env: "set": "kitchen".
"""
import bpy

import kit
from kit import mat, obj


def box(name, m, loc, size, rot=(0, 0, 0)):
    return obj("cube", m, name, loc=loc, scl=size, rot=rot, bake=True)


def rod(name, m, loc, r, length, rot=(0, 0, 0)):
    return obj("cyl", m, name, loc=loc, scl=(r, r, length), rot=rot)


def checker(c1, c2, scale):
    m = bpy.data.materials.new("kitchen_floor")
    m.use_nodes = True
    nt = m.node_tree
    chk = nt.nodes.new("ShaderNodeTexChecker")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    chk.inputs["Scale"].default_value = scale
    chk.inputs["Color1"].default_value = tuple(kit.lin(v) for v in c1) + (1,)
    chk.inputs["Color2"].default_value = tuple(kit.lin(v) for v in c2) + (1,)
    nt.links.new(tc.outputs["Object"], chk.inputs["Vector"])
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.5
    nt.links.new(chk.outputs["Color"], b.inputs["Base Color"])
    return m


def table(name, x, y, top_z, wood, legs):
    """A table 1.2 x 0.8 m with its top at top_z."""
    parts = [box(name + "_top", wood, (x, y, top_z - 0.025), (1.2, 0.8, 0.05))]
    for dx, dy in ((-0.54, -0.34), (0.54, -0.34), (-0.54, 0.34), (0.54, 0.34)):
        parts.append(rod(name + "_leg", legs, (x + dx, y + dy, (top_z - 0.05) / 2), 0.03, top_z - 0.05))
    return parts


def build(spec):
    with kit.collect() as grp:
        wall = mat([191, 227, 214], 0.9)
        cab = mat([255, 243, 220], 0.6)
        counter = mat([233, 226, 214], 0.4)
        metal = mat([201, 204, 210], 0.3, 0.4)
        ink = mat([29, 27, 34], 0.4)
        red = mat([229, 72, 63], 0.5)
        glass = mat([191, 230, 255], 0.2, emit=[191, 230, 255])
        wood = mat([185, 119, 63], 0.5)
        wood_dark = mat([138, 85, 48], 0.55)
        white = mat([250, 250, 250], 0.3)

        kit.plane("kitchen_floor", checker([243, 227, 198], [226, 167, 122], 4.0), -5, 5, -6, 2.3, 0.0)   # 25 cm tiles
        box("back_wall", wall, (0, 2.3, 2.2), (10, 0.1, 4.4))
        box("left_wall", wall, (-3.25, -1.8, 2.2), (0.1, 8.2, 4.4))
        box("ceiling", cab, (0, -1.8, 4.45), (10, 8.2, 0.1)).visible_shadow = False
        for x in (-2.4, -1.6, 0.8, 1.6):
            box("lower_cabinet", cab, (x, 1.9, 0.43), (0.78, 0.6, 0.86))
            obj("sphere", metal, "knob", loc=(x, 1.58, 0.7), scl=(0.025,) * 3)
        box("counter", counter, (-0.4, 1.9, 0.885), (5.2, 0.66, 0.05))
        for x in (-2.4, -1.6, 1.6):
            box("upper_cabinet", cab, (x, 2.05, 2.0), (0.78, 0.35, 0.8))
        box("window_frame", cab, (-0.2, 2.24, 1.75), (1.3, 0.06, 1.0))
        box("window", glass, (-0.2, 2.22, 1.75), (1.15, 0.05, 0.85))
        box("window_bar", cab, (-0.2, 2.2, 1.75), (0.04, 0.07, 0.85))
        box("fridge", metal, (2.55, 1.8, 0.95), (0.8, 0.7, 1.9))
        rod("fridge_handle", ink, (2.25, 1.42, 1.3), 0.018, 0.5)
        rod("lamp_cord", ink, (0.0, 0.1, 3.6), 0.008, 1.6)
        obj("cone", red, "lamp_shade", loc=(0.0, 0.1, 2.75), scl=(0.28, 0.28, 0.25))
        table("table", 0.0, 0.0, 0.76, wood, wood_dark)
        rod("plate", white, (-0.3, 0.05, 0.79), 0.13, 0.015)

    world = bpy.data.worlds.new("kitchen")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (kit.lin(223), kit.lin(238), kit.lin(240), 1)
    bg.inputs["Strength"].default_value = 0.7
    return dict(objs=grp.objs, world=world, sun=(2.6, (1.0, 0.96, 0.9), (50, -12, -35)), fill=300)
