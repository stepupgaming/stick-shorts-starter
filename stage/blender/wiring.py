"""How an episode's sets and props find their code by name, so a new short adds files and edits none of the shared ones.

  envs.<id>.set: "kitchen"                  sets_kitchen.py: build(env spec + {name, cues}) -> {world, sun, fill, objs, ticks?}
  props.<group>.<name>.model: "m.Maker"     m.py: Maker(spec[, name][, figures]) -> .objs and update(f, cues, visible)

Modules are looked up next to this file and in the episode's own folder (scene.json "modules", set by author.mjs).
A prop's `env` (one name or a list) says which sets it is shown in. A model's `CUE` (a class attribute) picks the cues it
is given: those whose type is CUE and whose CUE field names it; a cue that names none goes to the first prop of its group.
Without CUE it gets every cue.
"""
import importlib
import inspect


def _load(modname, what):
    try:
        return importlib.import_module(modname)
    except ModuleNotFoundError as e:
        if e.name != modname:   # the module exists but something it imports does not: show the real error
            raise
        raise SystemExit("%s: there is no %s.py in stage/blender or the episode's folder" % (what, modname)) from None


def build_set(name, env, cues):
    if not env.get("set"):
        raise SystemExit('envs.%s has no "set" naming the sets_<set>.py that builds it' % name)
    return _load("sets_" + env["set"], 'envs.%s.set "%s"' % (name, env["set"])).build(dict(env, name=name, cues=cues))


class Hero:
    def __init__(self, group, name, obj, envs, cues):
        self.group, self.name, self.obj, self.envs, self.cues = group, name, obj, envs, cues

    def update(self, f, env_name):
        self.obj.update(f, self.cues, env_name in self.envs)


def make(model, spec, name, figures=None):
    mod, _, attr = model.rpartition(".")
    if not mod:
        raise SystemExit('model "%s" should be "module.Class"' % model)
    maker = getattr(_load(mod, 'model "%s"' % model), attr, None)
    if maker is None:
        raise SystemExit('model "%s": %s.py has no %s' % (model, mod, attr))
    params = inspect.signature(maker).parameters
    kw = {k: v for k, v in (("name", name), ("figures", figures)) if k in params}
    return maker(spec, **kw)


def heroes(scene_spec, envs, figures=None):
    """Every prop of the scene, built, with its envs and cues. `envs` are the env names (a prop without "env" is in all).
    A maker that takes `figures` gets the actors by name (figures3d.Figure3D), e.g. to put the prop in a hand with hold()."""
    out, cues = [], scene_spec.get("cues", [])
    for group, props in scene_spec.get("props", {}).items():
        first = next(iter(props), None)
        for n, p in props.items():
            if not p.get("model"):
                raise SystemExit('props.%s.%s needs a "model" ("module.Class") naming the code that builds it' % (group, n))
            obj = make(p["model"], p, n, figures)
            cue = getattr(obj, "CUE", None)
            mine = [c for c in cues if c.get("type") == cue and c.get(cue, first) == n] if cue else list(cues)
            where = p.get("env", list(envs))
            out.append(Hero(group, n, obj, where if isinstance(where, list) else [where], mine))
    return out
