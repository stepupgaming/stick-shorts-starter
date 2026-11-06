"""Narrate a script with KittenTTS 2. It runs on the CPU, so no GPU is needed.

    python voice.py script.txt narration.wav --voice Miles --wpm 210

script.txt is plain text. Blank lines split it into paragraphs; each paragraph is voiced as one take and the takes are
joined with a short pause. Pauses longer than --max-pause inside a take are shortened from the middle. Shorts sound best
fast, so a read slower than --wpm words a minute is sped up to it without changing the pitch (at most 1.4 times, so it
never sounds rushed; needs ffmpeg on PATH). --wpm 0 keeps the model's own pace.
"""
import argparse
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf


def shorten_pauses(y, sr, max_pause, floor_db=-40.0):
    """Cut every silence longer than max_pause down to max_pause, keeping its edges so words don't get clipped."""
    hop = int(sr * 0.01)
    n = len(y) // hop
    if n == 0:
        return y
    frames = y[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9
    silent = 20 * np.log10(rms / (np.abs(y).max() + 1e-9)) < floor_db
    keep = np.ones(n, bool)
    limit = int(max_pause / 0.01)
    i = 0
    while i < n:
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < n and silent[j]:
            j += 1
        if j - i > limit:
            start = i + limit // 2
            keep[start:start + (j - i - limit)] = False
        i = j
    return np.concatenate([frames[keep].reshape(-1), y[n * hop:]])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--voice", default="Miles", help="a KittenTTS 2 voice, e.g. Miles, Jasper, Marcus, Bella")
    ap.add_argument("--seed", type=int, default=7, help="same seed + same text = same read")
    ap.add_argument("--wpm", type=float, default=210, help="target pace in words a minute (0 = as read)")
    ap.add_argument("--max-pause", type=float, default=0.25, help="longest pause to keep, in seconds")
    ap.add_argument("--model", default="KittenML/kitten-tts-2")
    a = ap.parse_args()

    from kittenml import KittenTTS

    text = open(a.script, encoding="utf-8").read()
    paragraphs = [" ".join(p.split()) for p in text.split("\n\n") if p.strip()]
    model = KittenTTS(a.model)
    sr = model.sample_rate
    gap = np.zeros(int(0.35 * sr), np.float32)
    pieces = [np.zeros(int(0.25 * sr), np.float32)]
    for i, p in enumerate(paragraphs, 1):
        print(f"voicing paragraph {i}/{len(paragraphs)}")
        take = np.asarray(model.generate(p, voice=a.voice, preset="stable", advanced={"seed": a.seed}), np.float32)
        pieces += [shorten_pauses(take, sr, a.max_pause), gap]
    audio = np.concatenate(pieces)
    audio *= 0.89 / (np.abs(audio).max() + 1e-9)   # peak at -1 dB

    words = len(text.split())
    pace = words / (len(audio) / sr) * 60
    tempo = min(max(a.wpm / pace, 1.0), 1.4) if a.wpm else 1.0
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if tempo == 1.0:
        sf.write(a.out, audio, sr)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw.wav")
            sf.write(raw, audio, sr)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"atempo={tempo:.4f}", a.out], check=True)
    seconds = sf.info(a.out).duration
    print(f"{a.out}: {seconds:.1f} s, {words} words, {words / seconds * 60:.0f} words a minute"
          + (f" (read at {pace:.0f}, sped up {tempo:.2f}x)" if tempo != 1.0 else ""))


if __name__ == "__main__":
    main()
