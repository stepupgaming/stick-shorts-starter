# Stick Shorts Starter

How to make narrated, animated stick-figure shorts (vertical, about a minute long) with free tools that run on your
own computer. It's how we make our history shorts, with the same animation pipeline, and it works for any topic. The
stick figures are posed in time with the narration and rendered in Blender as 3D cartoon characters.

```
script -> voice -> word timings -> poses -> Blender picture -> music + sound effects -> captions -> MP4
```

This repo has a guide (below), a Claude skill for writing the script, the stage (a pose library and skeleton, 3D
characters with ten expressions, a cartoon look for any set, and cameras, poses and props timed to the words), four
Python scripts that voice the script, time every word, make the captions and put the film together, and a worked
example: [`example/short.mp4`](example/short.mp4), an 11-second short about why toast lands butter side down.

## The tools

| Step | What we use | Lighter option |
| --- | --- | --- |
| Voice | [Fish Audio Drama 3](https://huggingface.co/fishaudio/drama-3): the best acted read, but it needs a big GPU | [Audio8 TTS Realistic 0.6B](https://huggingface.co/Edge0/Audio8-TTS-Realistic-0.6b) clones a narrator from a short clip on a mid-range GPU. [KittenTTS 2](https://github.com/KittenML/KittenTTS) runs on the CPU with ready-made voices; `voice.py` uses it |
| Word timings | [Underdog Bark 3.0 Pro](https://huggingface.co/ConwayResearch/Underdog-Bark-3.0-Pro) (speech to text with word times) | [faster-whisper](https://github.com/SYSTRAN/faster-whisper); `words.py` uses it |
| Animation | Our pose library and skeleton (`stage/`): every pose, walk and gesture is timed to a word | Animate by hand in a 2D app such as [StykAnimate](https://stykanimate.com) and export MP4 or PNG frames |
| Picture | [Blender](https://www.blender.org) 5 with EEVEE: the 3D characters, your sets and props, and the cartoon look (`stage/blender/`) | |
| Archival footage | Public-domain newsreels from the [Internet Archive](https://archive.org) | Check every clip's rights before you use it |
| Music | An AI music model, instrumental only, one score per film | The YouTube Audio Library or any royalty-free track |
| Sound effects | Generated with an audio model and a small library of our own | [freesound.org](https://freesound.org) (filter by CC0) |
| Captions and assembly | ffmpeg (`captions.py`, `assemble.py`) | CapCut |

Check each model's licence before you make money from what it produces. Bark 3.0 is CC-BY-4.0, so credit it.

## What makes these work

**Script**
- 220-240 words is about 65 seconds at a fast narrator's pace. Over 60 seconds counts for TikTok's Creator Rewards,
  and YouTube Shorts can run up to 3 minutes.
- The first sentence is a promise or a question, 15 words at most, and never a date or a slow setup: "Your toast
  really does land butter side down".
- Put something at stake in the first 10 seconds, and give the viewer something new every 5-8 seconds.
- Ask for the follow twice: a short line at about 20 seconds ("Follow for more. The strangest part is still to
  come.") and at the end, after a question about the story: "Which side did yours land on? Follow for more, and hit
  like if it was butter side down."
- Check every fact against two sources.

**Voice**
- Use one narrator for every film, so the channel sounds like one person.
- Fast and tight: about 200-220 words a minute, with no pause longer than a quarter of a second.

**Picture**
- The first frame is already moving. Open on the most dramatic moment, not on an establishing shot.
- Cut or move the camera every few seconds (push in, follow something as it falls, a slow arc), so nothing looks
  static or repetitive.
- Faces change with the story, and when a character speaks, their mouth moves.
- Put facts on things in the world, like signs, papers and gauges, not only in the narration.
- Leave the lower third clear enough for captions, and keep text away from the app's buttons on the right.

**Sound**
- Music about 16 dB under the voice, dipping further while someone is speaking.
- A sound for every event on screen: a door, a crash, a gust of wind.
- Finish at -14 LUFS, the loudness YouTube and TikTok play at.

**Export**
- 1080x1920, 30 fps, H.264 and AAC. Upload the full-quality file, not a compressed copy, because the apps compress
  it again.

## Writing the script with Claude

`skills/stick-shorts-script` is the skill we write every script with: the fact sheet, the shape of the story, where the
asks go, how to write for the ear, and a checker (`scripts/check.py`) that fails a script that breaks the rules. Copy the
folder into `~/.claude/skills/` (or your project's `.claude/skills/`) and ask Claude Code for "a script for a short about X".
It writes the fact sheet first, drafts, runs the checker and rewrites until it passes.

You can run the checker on any script yourself: `python skills/stick-shorts-script/scripts/check.py script.txt`. Put a blank
line between the script's paragraphs: the voice and the stage are both timed to them.

## Quick start

You need Python 3.10+, [ffmpeg](https://ffmpeg.org) on your PATH, [Node.js](https://nodejs.org) 24 or newer,
[Blender](https://www.blender.org) 5:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The stage needs no `npm install`. On Windows, run `set PYTHONUTF8=1` first (PowerShell: `$env:PYTHONUTF8=1`);
KittenTTS reads its files as UTF-8.

```bash
python voice.py example/script.txt out/narration.wav --voice Miles
python words.py out/narration.wav out/words.json --script example/script.txt
node stage/author.mjs example/episode.json out/words.json out/work
blender -b -P stage/blender/build_scene.py -- out/work --draft --stills 60,175,255,330
blender -b -P stage/blender/build_scene.py -- out/work
python captions.py out/words.json out/captions.ass
python assemble.py --video "out/work/frames/f%05d.png" --voice out/narration.wav --captions out/captions.ass --music your-music.mp3 -o out/short.mp4
```

- `voice.py` reads each paragraph of the script as one take, shortens long pauses and brings the pace up to 210 words
  a minute without changing the pitch. Run `python voice.py -h` for the options; KittenTTS 2 voices include Miles,
  Jasper, Marcus, Bella and Luna.
- `words.py` finds when each word is said and which paragraph it's in (`l1`, `l2` and so on). With `--script` the
  captions keep your spelling.
- `stage/author.mjs` turns `episode.json` and the word timings into every frame's pose (`bake.json`, the skeleton in
  `stage/skeleton.mjs`), and the shots and cues with their frame numbers (`scene.json`).
- `stage/blender/build_scene.py` builds the sets, characters and props and renders the frames. With `--draft` and
  `--stills` it renders a few small frames in seconds into `out/work/stills`; check them before you render the whole
  film. `--res 540x960` sets another size, and `--range 120-200` renders only those frames.
- `captions.py` writes 1-3 word captions that end at punctuation or pauses.
- `assemble.py` scales your picture to 9:16, adds the narration, ducks the music under the voice, adds an optional
  sound-effects track (`--sfx`), burns in the captions and sets the loudness.

## Making your own short

A short is one `episode.json` plus the sets and props it names, in the same folder. Every time in it is an anchor on
the narration, so when you change the script and run `words.py` again, the picture follows the words.

| Anchor | Means |
| --- | --- |
| `@l2` | the start of the script's second paragraph |
| `@l2:half` | the word "half" in that paragraph (case and punctuation are ignored) |
| `@l2:the#2` | the second "the" in it; "a" and "the" are common, so count them |
| `@floor` | the first "floor" anywhere in the script |
| `@l2:half+4` | four frames after "half" (30 frames a second); `-6` is six frames before |

The parts of [`example/episode.json`](example/episode.json):

- `actors`: each character's look and place. `color` (shirt), `hair`, `cap` (`cap`, `fedora`, `hardhat`, `beret`,
  `glasses`, or a list of them) with `hat` for its colour, `costume` (`plain`, `coat`, `hivis`, `apron`, `cross`),
  `trim`, `sash`, `tie`; `x` and `depth` in metres, `face` (1 faces right, -1 left) and `scale`.
- `tracks`: what each actor does, in order. A `pose` eased in `over` some frames; the built-in poses are in
  `stage/poses.mjs` (stand, present, think, shrug, laugh, cheer, panting, give, receive), and `poses` adds your own as
  ten bone angles. A `walk` or `run` goes to a new `x` over some `frames` (one frame is a cut). `wobble` shakes on top
  of either.
- `faces`: the expression from each anchor on: neutral, deadpan, smug, worried, sad, mad, laugh, grin, surprised or
  awe. Characters blink on their own.
- `shots`: one camera per shot, from its anchor to the next. A `from` and `to`, each a position, a point to look at and
  a lens in mm, or an `orbit` around a point; plus `ease`, `fstop` and `focus` for a soft background, `roll`, and
  `hide` for actors left out of the shot.
- `envs`: the sets. `"set": "kitchen"` runs `build()` in `sets_kitchen.py`. `"set": "toon", "base": "kitchen"` gives
  the same set the flat-colour cartoon look with ink outlines; the `toon` settings change its colour bands and lines.
- `props`: things that move, appear or get carried. `model` names the Python class that builds each one
  (`toast_props.Toast`), and it's updated on every frame with the cues.
- `cues`: timed events for the props, each with an anchor and an `until` anchor or a length in `frames`. A `shake` cue
  shakes the camera.

Write a set the way [`example/sets_kitchen.py`](example/sets_kitchen.py) does, with the boxes, cylinders and materials
in `stage/blender/kit.py`, and props the way [`example/toast_props.py`](example/toast_props.py) does. Keep text and
faces out of the bottom third, where the captions go.

## Licence

MIT ([LICENSE](LICENSE)). The models, music and footage you use have their own licences.
