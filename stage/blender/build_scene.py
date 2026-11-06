"""Build the 3D stage for a short from bake.json + scene.json (stage/author.mjs) and render it.

  blender -b --python stage/blender/build_scene.py -- <work_dir> [options]

  --res WxH         output size (default: scene size)
  --samples N       EEVEE samples (default 24)
  --draft           quick preview for timing and blocking: quarter size, 4 samples, no bloom
  --range A-B       render animation frames A..B (1-based, inclusive; default all)
  --ranges A-B,C-D  several such ranges in one scene build
  --stills f,f,...  render these 0-based frames as stills instead of an animation
  --out DIR         output dir (default <work_dir>/frames or <work_dir>/stills)
  --cam P,L,lens    stills only: camera at px,py,pz looking at lx,ly,lz with this lens (mm)
  --save FILE       also save the static scene as .blend (animation lives in a frame handler)

Every frame is a pure function of its frame number (figures from the bake, camera and props from the resolved cues),
so any range can be re-rendered on its own and match the rest.

scene.json, the parts this file reads:
  envs    {id: {set, ...}}: each built by sets_<set>.py (wiring.py); a shot's `env` picks one
  props   {group: {name: {model, env, ...}}}: each built by its model (wiring.py) and updated every frame
  shots   [{start, end, env, cam, hide: [actor], tone: [r, g, b], ease}]
  cues    [{type, f, frames, ...}]: given to props; type "shake" {amp} also shakes the camera
  figures style for every actor (figures3d.py); actors {name: {uid, expr, moves, ...}}
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
WORK = os.path.abspath(argv[0])
opt = {}
i = 1
while i < len(argv):
    key = argv[i].lstrip("-")
    if key in ("draft",):   # flags without a value
        opt[key] = True
        i += 1
    else:
        opt[key] = argv[i + 1]
        i += 2

bake = json.load(open(os.path.join(WORK, "bake.json")))
scene_spec = json.load(open(os.path.join(WORK, "scene.json")))
if scene_spec.get("modules"):   # the episode's own sets_*.py and prop models
    sys.path.insert(0, os.path.abspath(scene_spec["modules"]))

import figure_kit  # noqa: E402
import figures3d  # noqa: E402
import kit  # noqa: E402
import wiring  # noqa: E402

FPS = scene_spec["fps"]
TOTAL = scene_spec["total"]
K = scene_spec["stage"]["k"]
FLOOR_PX = scene_spec["stage"]["floor_px"]
CX = scene_spec["stage"]["cx"]
frames = bake["frames"]
faces = bake["faces"]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, TOTAL
kit.init(sc)

# ---------------------------------------------------------------- actors
figs = {}
for name, a in scene_spec["actors"].items():
    figs[a["uid"]] = (figures3d.Figure3D(sc, name, a, scene_spec.get("figures", {}), K, CX, FLOOR_PX), a)

# ---------------------------------------------------------------- lights, sets, props, camera
sun = bpy.data.lights.new("sun", "SUN")
sun.angle = math.radians(6)
so = bpy.data.objects.new("sun", sun)
sc.collection.objects.link(so)
fill = bpy.data.lights.new("fill", "AREA")
fill.size = 8
fill.color = (0.8, 0.86, 1.0)
fo = bpy.data.objects.new("fill", fill)
sc.collection.objects.link(fo)
fo.location = (-2, -7, 5)
fo.rotation_euler = (math.radians(70), 0, math.radians(-10))

CLIP = 3000   # the camera's far clip (m), unless a set asks for more
ENVS = {}
for _name, _e in scene_spec.get("envs", {}).items():
    _r = wiring.build_set(_name, _e, scene_spec["cues"])   # sets_<set>.py, by name
    ENVS[_name] = dict(world=_r["world"], sun=_r["sun"], fill=_r["fill"], objs=list(_r["objs"]), ticks=_r.get("ticks", []),
                       clip=_r.get("clip", CLIP))
if not ENVS:
    raise SystemExit("scene.json has no envs: add one to episode.json (\"envs\": {\"main\": {\"set\": \"...\"}})")
DEFAULT_ENV = next(iter(ENVS))
heroes = wiring.heroes(scene_spec, list(ENVS), {fg.name: fg for fg, _ in figs.values()})
for _h in heroes:
    for _e in _h.envs:
        if _e not in ENVS:
            raise SystemExit("props.%s.%s: env %s is not in envs" % (_h.group, _h.name, _e))
        ENVS[_e]["objs"] += _h.obj.objs

cam_data = bpy.data.cameras.new("cam")
cam_data.sensor_fit = "HORIZONTAL"
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
_env = {"name": None}


def set_env(name):
    if _env["name"] == name:
        return
    _env["name"] = name
    e = ENVS[name]
    active = {o.name for o in e["objs"]}
    for v in ENVS.values():
        for o in v["objs"]:
            o.hide_render = o.name not in active
    sc.world = e["world"]
    sun.energy, sun.color = e["sun"][0], e["sun"][1]
    so.rotation_euler = tuple(math.radians(a) for a in e["sun"][2])
    fill.energy = e["fill"]
    cam_data.clip_end = e.get("clip", CLIP)


# ---------------------------------------------------------------- render settings
DRAFT = "draft" in opt
W, H = (int(v) for v in opt.get("res", "%dx%d" % tuple(s // 4 if DRAFT else s for s in scene_spec["size"])).split("x"))
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
for _engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):   # the name changed between Blender versions
    try:
        sc.render.engine = _engine
        break
    except TypeError:
        continue
sc.eevee.taa_render_samples = int(opt.get("samples", 4 if DRAFT else 24))
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.compression = 10
sc.render.use_motion_blur = False

# soft bloom on bright lights (windows, lamps); skipped quietly if this Blender lacks the node, and in drafts
if not DRAFT:
    try:
        ng = bpy.data.node_groups.new("post", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        go = ng.nodes.new("NodeGroupOutput")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = 0.9
        gl.inputs["Strength"].default_value = 0.55
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs["Image"], go.inputs["Image"])
        sc.compositing_node_group = ng
    except Exception as exc:   # noqa: BLE001
        print("bloom off:", exc)

# ---------------------------------------------------------------- per frame
shots = scene_spec["shots"]
cues = scene_spec["cues"]
shakes = [c for c in cues if c["type"] == "shake"]
smoothstep = lambda u: u * u * (3 - 2 * u)


def shake_amount(f):
    amp = 0.0
    for c in shakes:
        if c["f"] <= f < c["f"] + c["frames"]:
            u = (f - c["f"]) / c["frames"]
            amp = max(amp, c.get("amp", 0.05) * math.sin(math.pi * min(1.0, u * 1.4)) ** 0.7)
    return amp


def _rng(v, u):
    """scalar, or [from, to] mixed by u"""
    return v[0] + (v[1] - v[0]) * u if isinstance(v, (list, tuple)) else v


def _pt(v, u):
    """[x,y,z] or {"from":[..],"to":[..]} mixed by u"""
    if isinstance(v, dict):
        return Vector([v["from"][i] + (v["to"][i] - v["from"][i]) * u for i in range(3)])
    return Vector(v)


def _ease(kind, u):
    if kind == "linear":
        return u
    if kind == "in":
        return u * u
    if kind == "out":
        return 1 - (1 - u) ** 2
    return 0.4 * u + 0.6 * smoothstep(u)


def shot_at(f):
    return next((s for s in shots if s["start"] <= f < s["end"]), shots[-1])


def set_camera(f, amp):
    """Shot camera. Either from/to ({pos, look, lens}) or an orbit around a centre:
    orbit {center, r, az (deg, 0 = in front of the stage, + toward +x), h (camera height), look, lens}, where r, az, h
    and lens may each be [from, to]; plus roll (deg), focus point, fstop and dof (false = all sharp)."""
    if "cam" in opt:   # stills: --cam px,py,pz,lx,ly,lz,lens overrides the shot camera
        v = [float(c) for c in opt["cam"].split(",")]
        cam.location = Vector(v[:3])
        cam.rotation_euler = (Vector(v[3:6]) - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = v[6]
        cam_data.dof.use_dof = False
        return
    shot = shot_at(f)
    c = shot["cam"]
    u = _ease(shot.get("ease", "smooth"), (f - shot["start"]) / max(shot["end"] - shot["start"] - 1, 1))
    if "orbit" in c:
        o = c["orbit"]
        ctr = Vector(o["center"])
        r, az, h = _rng(o["r"], u), math.radians(_rng(o["az"], u)), _rng(o["h"], u)
        pos = Vector((ctr.x + r * math.sin(az), ctr.y - r * math.cos(az), h))
        look = _pt(o.get("look", o["center"]), u)
        lens = _rng(o.get("lens", 35), u)
    else:
        a, b = c["from"], c.get("to", c["from"])
        mix = lambda p, q: [p[i] + (q[i] - p[i]) * u for i in range(len(p))]
        pos, look, lens = Vector(mix(a["pos"], b["pos"])), Vector(mix(a["look"], b["look"])), mix([a["lens"]], [b["lens"]])[0]
    if amp >= 0.002:
        pos += Vector((math.sin(f * 2.3), 0, math.cos(f * 3.1))) * amp * 0.9
        look += Vector((math.cos(f * 1.7), 0, math.sin(f * 2.9))) * amp * 0.9
    q = (look - pos).to_track_quat("-Z", "Y")
    roll = _rng(c.get("roll", 0), u)
    if roll:
        q = q @ Quaternion((0, 0, 1), math.radians(roll))
    cam.location = pos
    cam.rotation_euler = q.to_euler()
    cam_data.lens = lens
    cam_data.dof.use_dof = bool(c.get("dof", True))
    focus = _pt(c["focus"], u) if "focus" in c else look
    cam_data.dof.focus_distance = max(0.1, (focus - pos).length)
    cam_data.dof.aperture_fstop = _rng(c.get("fstop", 3.2), u)


def apply(scene, depsgraph=None):
    f = min(max(scene.frame_current - 1, 0), TOTAL - 1)
    set_camera(f, shake_amount(f))   # camera first: the figures turn toward it
    shot = shot_at(f)
    set_env(shot.get("env", DEFAULT_ENV))
    figure_kit.tone_all(shot.get("tone", [1, 1, 1]))
    for uid, (fg, a) in figs.items():
        fg.set_visible(fg.name not in shot.get("hide", []))
        rows = {d[1]: d for d in frames[f] if d[0] == uid}
        fg.update(rows, faces[str(uid)][f], f, cam.location, a.get("expr", []), a.get("moves", []))
    for _tk in ENVS[_env["name"]].get("ticks", []):
        _tk(f)
    for _h in heroes:
        _h.update(f, _env["name"])


bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(apply)

if "save" in opt:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opt["save"]))

t0 = time.time()
if "stills" in opt:
    out = os.path.abspath(opt.get("out", os.path.join(WORK, "stills")))
    os.makedirs(out, exist_ok=True)
    for f in (int(v) for v in opt["stills"].split(",")):
        sc.frame_set(f + 1)
        sc.render.filepath = os.path.join(out, "f%05d.png" % f)
        bpy.ops.render.render(write_still=True)
    print("STILLS_DONE %.1fs" % (time.time() - t0))
else:
    out = os.path.abspath(opt.get("out", os.path.join(WORK, "frames")))
    os.makedirs(out, exist_ok=True)
    spans = [tuple(int(v) for v in r.split("-")) for r in opt.get("ranges", opt.get("range", "1-%d" % TOTAL)).split(",")]
    sc.render.filepath = os.path.join(out, "f#####")
    sc.render.use_file_extension = True
    for a, b in spans:   # one scene build for every section
        sc.frame_start, sc.frame_end = a, b
        bpy.ops.render.render(animation=True)
    print("RENDER_DONE %d frames %.1fs" % (sum(b - a + 1 for a, b in spans), time.time() - t0))
