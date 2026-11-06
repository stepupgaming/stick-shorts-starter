// Episode spec + word timings -> every frame's figure poses, for the Blender stage.
//
//   node stage/author.mjs <episode.json> <words.json> <work_dir>
//
// Writes <work_dir>/bake.json   every frame's skeleton (stage/skeleton.mjs), read by stage/blender/build_scene.py
//        <work_dir>/scene.json  shots, cues, actors and sets with every anchor resolved to a frame number

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeAnchors } from './anchors.mjs';
import { POSES, gaitAngles, stridePx, mirror, footDrop, lerpAngles } from './poses.mjs';
import { segments } from './skeleton.mjs';

const clamp01 = v => Math.min(1, Math.max(0, v));
const ease = u => u * u * (3 - 2 * u);
const CX = 540;   // the stage's centre line, in canvas pixels

// The pose library plus the episode's own `poses` (same 10 angles as poses.mjs).
export function episodePoses(spec) {
  for (const [n, a] of Object.entries(spec.poses ?? {})) {
    if (POSES[n]) throw new Error(`episode pose "${n}" is already in poses.mjs; give it another name`);
    if (!Array.isArray(a) || a.length !== POSES.stand.length) throw new Error(`episode pose "${n}" needs ${POSES.stand.length} angles, as in poses.mjs`);
  }
  return { ...POSES, ...spec.poses };
}

// One actor's track: a list of events, each at an anchor. An event is a pose (eased in over `over` frames), a walk or
// run to a new x (metres), or either with a `wobble` (a shake on top). Returns the actor's skeleton angles on any frame.
function actorTimeline(name, def, events, A, k, floorPx, poses) {
  const total = A.totalFrames;
  const ev = events.map(e => ({ ...e, f: A.at(e.at) })).sort((a, b) => a.f - b.f);
  const gaitOf = e => (e.run ? 'run' : e.walk ? 'walk' : null);
  const scale = def.scale ?? 1;
  const init = { x: def.x ?? 0, face: def.face ?? 1, angles: poses[def.pose ?? 'stand'] };
  const starts = [];
  const endOf = i => ev[i + 1]?.f ?? total - 1;

  function startState(i) {
    if (i === 0) return init;
    return (starts[i] ||= evalEvent(i - 1, ev[i].f));
  }
  function evalEvent(i, f) {
    const e = ev[i];
    const s = startState(i);
    const t = f - e.f;
    let st;
    const gait = gaitOf(e);
    if (gait) {
      const to = (e.run || e.walk).to;
      const dur = Math.max(1, (e.run || e.walk).frames ?? endOf(i) - e.f);
      const u = clamp01(t / dur);
      const cycles = Math.abs(to - s.x) / k / (stridePx(gait) * scale);
      const w = ease(clamp01(t / 6));
      st = { x: s.x + (to - s.x) * u, face: Math.sign(to - s.x) || s.face, angles: lerpAngles(s.angles, gaitAngles(Math.PI * 2 * cycles * u, gait), w) };
      if (e.face && u >= 1) st.face = e.face;
    } else {
      const target = poses[e.pose];
      if (!target) throw new Error(`actor ${name}: unknown pose "${e.pose}" (have ${Object.keys(poses).join(', ')})`);
      const u = e.over ? ease(clamp01(t / e.over)) : 1;
      st = { x: e.x ?? s.x, face: e.face ?? s.face, angles: lerpAngles(s.angles, target, u) };
    }
    if (e.wobble) {
      const { amp, hz = 3 } = e.wobble;
      const ph = Math.PI * 2 * hz * (t / A.fps);
      const fade = clamp01(t / 5);
      const a = st.angles.slice();
      a[0] += amp * Math.sin(ph) * fade;
      a[1] += amp * 1.4 * Math.sin(ph + 0.6) * fade;
      for (const j of [2, 3, 4, 5]) a[j] += amp * 2 * Math.sin(ph + 1.2) * fade;
      st.angles = a;
    }
    return st;
  }
  function at(f) {
    let i = 0;
    while (i + 1 < ev.length && ev[i + 1].f <= f) i++;
    return ev.length && f >= ev[0].f ? evalEvent(i, f) : init;
  }
  function pose(f) {
    const st = at(f);
    const angles = st.face < 0 ? mirror(st.angles) : st.angles;
    return { angles, root_x: CX + st.x / k, root_y: floorPx - footDrop(angles) * scale };
  }
  return { pose, name, face: f => at(f).face, moves: ev.map(e => e.f).filter(f => f > 0) };
}

export function author(spec, words) {
  const A = makeAnchors(spec, words);
  const k = spec.stage?.k ?? 0.0072;          // metres per canvas pixel
  const floorPx = spec.stage?.floor_px ?? 1500;
  const [W, H] = spec.size ?? [1080, 1920];
  const total = A.totalFrames;

  const names = Object.keys(spec.actors ?? {});
  const poses = episodePoses(spec);
  const tls = names.map(n => actorTimeline(n, spec.actors[n], spec.tracks?.[n] ?? [], A, k, floorPx, poses));

  // every frame: [actor id, segment, circle, x0, y0, x1, y1, thickness, r, g, b, alpha, draw order] per segment
  const r1 = n => Math.round(n * 100) / 100;
  const baked = [];
  for (let f = 0; f < total; f++) {
    baked.push(tls.flatMap((tl, ai) => {
      const def = spec.actors[tl.name];
      const p = tl.pose(f);
      return segments(p.angles, p.root_x, p.root_y, def.scale ?? 1).map((s, z) => [
        ai + 1, s.name, s.circle ? 1 : 0, r1(s.a[0]), r1(s.a[1]), r1(s.b[0]), r1(s.b[1]),
        r1(s.thickness), ...(def.color ?? [0, 0, 0]), 1, z + 1,
      ]);
    }));
  }

  const shots = (spec.shots ?? []).map(s => ({ ...s, start: A.at(s.at) })).sort((a, b) => a.start - b.start);
  if (!shots.length) throw new Error('the episode has no shots');
  shots[0].start = 0;
  shots.forEach((s, i) => { s.end = shots[i + 1]?.start ?? total; delete s.at; });
  const cues = (spec.cues ?? []).map(c => ({ ...c, f: A.at(c.at) })).sort((a, b) => a.f - b.f);
  for (const c of cues) {
    delete c.at;
    if (c.frames === 'end') c.frames = total - c.f;
    if (c.until) { c.frames = A.at(c.until) - c.f; delete c.until; }
  }
  const scene = {
    id: spec.id, fps: spec.fps, size: [W, H], total,
    stage: { k, floor_px: floorPx, cx: CX },
    figures: spec.figures ?? {}, envs: spec.envs ?? {}, props: spec.props ?? {}, render: spec.render ?? {},
    // `faces`: { actor: [{ at, expr }] } -> expression changes on frames
    actors: Object.fromEntries(names.map((n, i) => [n, {
      uid: i + 1, ...spec.actors[n],
      expr: (spec.faces?.[n] ?? []).map(e => ({ f: A.at(e.at), expr: e.expr })).sort((a, b) => a.f - b.f),
      moves: tls[i].moves,
    }])),
    shots, cues,
  };
  const faces = Object.fromEntries(tls.map((tl, i) => [i + 1, Array.from({ length: total }, (_, f) => (tl.face(f) < 0 ? -1 : 1))]));
  return { bake: { w: W, h: H, fps: spec.fps, total, frames: baked, faces }, scene };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [specPath, wordsPath, work] = process.argv.slice(2);
  if (!work) {
    console.error('usage: node stage/author.mjs <episode.json> <words.json> <work_dir>');
    process.exit(2);
  }
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  const words = JSON.parse(fs.readFileSync(wordsPath, 'utf8'));
  fs.mkdirSync(work, { recursive: true });
  const t0 = Date.now();
  const out = author(spec, words);
  // set modules and props named by the episode live next to it
  out.scene.modules = path.dirname(path.resolve(specPath)).replace(/\\/g, '/');
  fs.writeFileSync(path.join(work, 'bake.json'), JSON.stringify(out.bake));
  fs.writeFileSync(path.join(work, 'scene.json'), JSON.stringify(out.scene, null, 1));
  console.log(JSON.stringify({ frames: out.bake.total, shots: out.scene.shots.length, seconds: (Date.now() - t0) / 1000 }));
}
