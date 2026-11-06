"""The example's props: the toast that falls, the ten-foot table, and the height rulers.

A prop model is any class named in episode.json as props.<group>.<name>.model = "module.Class". It builds its objects in
__init__(spec[, name][, figures]) and lists them in .objs; build_scene calls update(f, cues, visible) on every frame
(visible: whether the shot's env is one the prop is in). Its cues are the episode's, with every anchor already a frame:
a class with CUE = "show" gets the cues of type "show" whose "show" field names it.
"""
import math

import bpy

import kit
from kit import mat, obj

TOAST = [217, 148, 74]
CRUST = [154, 90, 38]
BUTTER = [255, 224, 102]
SIGN = [214, 51, 43]


def toast(name, loc):
    root = kit.empty(name, loc=loc)
    parts = [
        obj("cube", mat(TOAST, 0.8), name + "_bread", root, (0, 0, 0), (0.12, 0.12, 0.016)),
        obj("cube", mat(CRUST, 0.8), name + "_crust", root, (0, 0, -0.001), (0.128, 0.128, 0.012)),
        obj("cube", mat(BUTTER, 0.25), name + "_butter", root, (0.01, 0, 0.013), (0.05, 0.04, 0.012)),
    ]
    return root, parts


def _show(objs, on):
    for o in objs:
        o.hide_render = not on


class Toast:
    """Sits on the table, slides to the edge during the "slide" cue, then tips over and turns half a flip on the way
    down during the "fall" cue, landing butter side down with a splat. spec: start [x, y, z], land_z."""

    def __init__(self, spec):
        self.x, self.y, self.z = spec["start"]
        self.z1 = spec.get("land_z", 0.022)
        self.root, parts = toast("toast", tuple(spec["start"]))
        self.splat = obj("sphere", mat(BUTTER, 0.25), "splat", loc=(self.x, self.y - 0.265, 0.004), scl=(0.07, 0.05, 0.003))
        self.objs = parts + [self.splat]

    def update(self, f, cues, visible):
        slide = next(c for c in cues if c["type"] == "slide")
        fall = next(c for c in cues if c["type"] == "fall")
        r = math.radians
        edge = self.y - 0.095
        if f < slide["f"]:
            loc, rot = (self.x, self.y, self.z), (0, 0, r(8))
        elif f < fall["f"]:
            u = (f - slide["f"]) / max(fall["f"] - slide["f"], 1)
            u = u * u * (3 - 2 * u)
            loc, rot = (self.x, self.y + (edge - self.y) * u, self.z), (r(10) * u, 0, r(8) + r(2) * u)
        else:
            u = min(1.0, (f - fall["f"]) / max(fall["frames"], 1))
            loc = (self.x, edge - 0.17 * u, self.z - (self.z - self.z1) * u * u)
            rot = (r(10) + r(170) * u ** 1.15, 0, r(10))
        self.root.location, self.root.rotation_euler = loc, rot
        landed = f - (fall["f"] + fall["frames"])
        k = 0.0 if landed < 0 else min(1.0, (landed + 1) / 5)
        self.splat.scale = (0.07 * (0.15 + 0.85 * k), 0.05 * (0.15 + 0.85 * k), 0.003)
        _show(self.objs[:-1], visible)
        _show([self.splat], visible and landed >= 0)


class Show:
    """Objects that appear only during this prop's "show" cues."""
    CUE = "show"

    def update(self, f, cues, visible):
        _show(self.objs, visible and any(c["f"] <= f < c["f"] + c["frames"] for c in cues))


class GiantTable(Show):
    """The ten-foot table (its top at 3.05 m) with a slice of toast on it. spec: at [x, y], top_z."""

    def __init__(self, spec):
        x, y = spec["at"]
        z = spec.get("top_z", 3.05)
        wood, legs = mat([185, 119, 63], 0.5), mat([138, 85, 48], 0.55)
        self.objs = [obj("cube", wood, "giant_top", loc=(x, y, z - 0.025), scl=(1.2, 0.8, 0.05))]
        for dx, dy in ((-0.54, -0.34), (0.54, -0.34), (-0.54, 0.34), (0.54, 0.34)):
            self.objs.append(obj("cyl", legs, "giant_leg", loc=(x + dx, y + dy, (z - 0.05) / 2), scl=(0.03, 0.03, z - 0.05)))
        _, parts = toast("toast_up_high", (x + 0.3, y - 0.37, z + 0.04))
        self.objs += parts


class Ruler(Show):
    """A measuring line from the floor up to `height` with end ticks and a label that turns to the camera.
    spec: at [x, y], height, text, size (letter height, m), shift [dx, dy] (moves the label off the line)."""

    def __init__(self, spec, name):
        x, y = spec["at"]
        h = spec["height"]
        thick = 0.008 if h < 1 else 0.016
        m = mat(SIGN, 0.5, emit=SIGN)
        self.objs = [obj("cyl", m, name + "_line", loc=(x, y, h / 2), scl=(thick, thick, h))]
        for z in (0.004, h):
            self.objs.append(obj("cyl", m, name + "_tick", loc=(x, y, z), scl=(thick, thick, 10 * thick),
                                 rot=(0, math.pi / 2, 0)))
        cu = bpy.data.curves.new(name + "_text", "FONT")
        cu.body, cu.size, cu.extrude = spec["text"], spec.get("size", 0.1), 0.01
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        self.label = bpy.data.objects.new(name + "_text", cu)
        kit.sc.collection.objects.link(self.label)
        dx, dy = spec.get("shift", (0.0, 0.0))
        self.label.location = (x + dx, y + dy, h * 0.55)
        cu.materials.append(m)
        self.objs.append(self.label)

    def update(self, f, cues, visible):
        super().update(f, cues, visible)
        cam = bpy.context.scene.camera
        self.label.rotation_euler = (cam.location - self.label.location).to_track_quat("Z", "Y").to_euler()
