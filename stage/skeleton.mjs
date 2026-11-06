// The stick figure's skeleton: ten bones hung from the hip, posed by ten absolute screen angles (radians, y down, the
// order of BONES in poses.mjs). `segments` turns a pose into each bone's two end points, in canvas pixels; the 3D
// figures in stage/blender/figures3d.py are built on those points.
//
//   hip ── torso ──> neck ── head (a circle; its segment is the diameter, neck to crown)
//                    neck ── upper arm ──> elbow ── forearm ──> wrist     (left and right)
//   hip ── thigh ──> knee ── lower leg ──> ankle                          (left and right)

import { LIMB } from './poses.mjs';

// [segment name, angle index, length (px at scale 1), starts at, ends at, drawn as a circle, line thickness]
export const SEGMENTS = [
  ['Torso', 0, 78, 'hip', 'neck', false, 16],
  ['Head', 1, 44, 'neck', 'crown', true, 0],
  ['Left upper arm', 2, 53, 'neck', 'lElbow', false, 12],
  ['Left forearm', 3, 48, 'lElbow', 'lWrist', false, 12],
  ['Right upper arm', 4, 53, 'neck', 'rElbow', false, 12],
  ['Right forearm', 5, 48, 'rElbow', 'rWrist', false, 12],
  ['Left thigh', 6, LIMB.thigh, 'hip', 'lKnee', false, 14],
  ['Left lower leg', 7, LIMB.shin, 'lKnee', 'lAnkle', false, 14],
  ['Right thigh', 8, LIMB.thigh, 'hip', 'rKnee', false, 14],
  ['Right lower leg', 9, LIMB.shin, 'rKnee', 'rAnkle', false, 14],
];

// Each segment's end points for a figure with its hip at (x, y): [{name, a: [x, y], b: [x, y], circle, thickness}].
export function segments(angles, x, y, scale = 1) {
  const at = { hip: [x, y] };
  return SEGMENTS.map(([name, i, len, from, to, circle, thickness]) => {
    const a = at[from];
    const b = [a[0] + Math.cos(angles[i]) * len * scale, a[1] + Math.sin(angles[i]) * len * scale];
    at[to] = b;
    return { name, a, b, circle, thickness: thickness * scale };
  });
}
