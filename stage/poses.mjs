// Pose vocabulary for the Blue figure (10 bones, absolute screen angles in radians, y down).
// Order: torso, head, L upper arm, L forearm, R upper arm, R forearm, L thigh, L shin, R thigh, R shin.
// All poses are authored for a figure facing right; `mirror` flips them for a figure facing left.

const UP = -Math.PI / 2;
const DOWN = Math.PI / 2;

export const LIMB = { thigh: 66, shin: 63 };
export const BONES = ['torso', 'head', 'lUpperArm', 'lForearm', 'rUpperArm', 'rForearm', 'lThigh', 'lShin', 'rThigh', 'rShin'];

export const POSES = {
  stand:   [UP, UP, 1.40, 1.50, 1.74, 1.66, 1.45, DOWN, 1.70, DOWN],
  // gesture toward something on the right, other arm relaxed
  present: [UP + 0.04, UP + 0.06, -0.35, -0.20, 1.80, 1.70, 1.45, DOWN, 1.70, DOWN],
  think:   [UP + 0.02, UP - 0.12, 1.15, -2.05, 1.85, 1.75, 1.45, DOWN, 1.70, DOWN],
  shrug:   [UP, UP - 0.1, 0.45, -0.85, 2.70, -2.30, 1.45, DOWN, 1.70, DOWN],
  laugh:   [UP - 0.18, UP - 0.40, 1.00, 0.20, 1.30, 0.50, 1.40, DOWN, 1.75, DOWN],
  cheer:   [UP, UP, -0.95, -1.20, -2.20, -1.95, 1.30, DOWN, 1.85, DOWN],
  panting: [UP + 0.38, UP + 0.46, 1.15, 1.35, 1.35, 1.50, 1.30, 1.75, 1.85, 1.50],
  // arm held out forward, palm up (rider hands over a scroll / scholar receives it)
  give:    [UP + 0.10, UP + 0.12, 0.10, 0.02, 1.70, 1.62, 1.45, DOWN, 1.70, DOWN],
  receive: [UP + 0.04, UP + 0.05, 0.15, 0.05, 1.75, 1.65, 1.45, DOWN, 1.70, DOWN],
};

// Side-on walk/run cycle. phase in radians; returns angles for a figure facing right.
export function gaitAngles(phase, gait = 'walk') {
  const run = gait === 'run';
  const A = run ? 0.82 : 0.50;       // thigh swing
  const K = run ? 1.15 : 0.80;       // knee lift
  const armSwing = run ? 0.75 : 0.45;
  const s = Math.sin(phase);
  const c = Math.cos(phase);
  const lThigh = DOWN + A * s;
  const rThigh = DOWN - A * s;
  // shin trails (larger angle = further back) while the leg swings forward
  const lShin = lThigh + (run ? 0.22 : 0.12) + K * Math.max(0, -c);
  const rShin = rThigh + (run ? 0.22 : 0.12) + K * Math.max(0, c);
  const lean = run ? 0.30 : 0.06;
  const lUpper = 1.45 - armSwing * s - (run ? 0.35 : 0);
  const rUpper = 1.45 + armSwing * s - (run ? 0.35 : 0);
  const bend = run ? 1.1 : 0.35;
  return [UP + lean, UP + lean + 0.03, lUpper, lUpper - bend, rUpper, rUpper - bend, lThigh, lShin, rThigh, rShin];
}

// Distance travelled per full cycle (px at scale 1): each foot's stance covers ~ 2 * reach.
export function stridePx(gait = 'walk') {
  const A = gait === 'run' ? 0.82 : 0.50;
  return 4 * (LIMB.thigh + LIMB.shin) * Math.sin(A) * (gait === 'run' ? 0.85 : 1.0);
}

export function mirror(angles) {
  return angles.map(a => Math.PI - a);
}

// Vertical distance from hip (root) to the lowest foot, in px at scale 1.
export function footDrop(angles) {
  const leg = (t, s) => LIMB.thigh * Math.sin(angles[t]) + LIMB.shin * Math.sin(angles[s]);
  return Math.max(leg(6, 7), leg(8, 9));
}

export function lerpAngles(a, b, u) {
  return a.map((v, i) => v + (b[i] - v) * u);
}
