// Turn anchors such as "@l2:half+4" into frame numbers, using the narration's word timings (words.json from words.py).
//   @l2            start of script line l2 (lines are the script's paragraphs: l1, l2, ...)
//   @l2:word       start of the first word in l2 that matches (case and punctuation are ignored)
//   @l2:word#2     its second occurrence
//   @l2:end        end of the line
//   @word          the first matching word anywhere in the script
//   ...+N / ...-N  N frames later / earlier
// A plain number is already a frame.

const norm = s => s.toLowerCase().replace(/[^a-z0-9']/g, '');

export function makeAnchors(spec, words) {
  const list = Array.isArray(words) ? words : words.words;
  if (!list?.length) throw new Error('words.json has no words');
  const fps = spec.fps;
  const lines = {};
  for (const w of list) (lines[w.line ?? 'l1'] ||= []).push(w);
  const lastEnd = Math.max(...list.map(w => w.end));
  const totalFrames = Math.ceil((lastEnd + (spec.tail ?? 0.4)) * fps);
  const frame = sec => Math.round(sec * fps);
  const re = /^@(\w+)(?::([A-Za-z0-9']+)(?:#(\d+))?)?([+-]\d+)?$/;

  function find(ws, word, nth, ref) {
    const hits = ws.filter(w => norm(w.text) === norm(word));
    const hit = hits[(nth ? Number(nth) : 1) - 1];
    if (!hit) throw new Error(`anchor "${ref}": no word "${word}"${nth ? ` #${nth}` : ''} in: ${ws.map(w => w.text).join(' ')}`);
    return hit.start;
  }

  function at(ref) {
    if (typeof ref === 'number') return ref;
    const m = re.exec(ref);
    if (!m) throw new Error(`bad anchor "${ref}"`);
    const [, head, word, nth, off] = m;
    let sec;
    if (lines[head]) {
      const ws = lines[head];
      if (!word) sec = ws[0].start;
      else if (word === 'end') sec = ws.at(-1).end;
      else sec = find(ws, word, nth, ref);
    } else if (!word) {
      sec = find(list, head, null, ref);   // "@word": search the whole script
    } else {
      throw new Error(`anchor "${ref}": no line "${head}" (have ${Object.keys(lines).join(', ')})`);
    }
    return Math.max(0, frame(sec) + (off ? Number(off) : 0));
  }
  return { at, totalFrames, fps, lines };
}
