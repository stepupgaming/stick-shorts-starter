"""Word timings for a narration with faster-whisper, written as words.json for captions.py.

    python words.py narration.wav words.json --script script.txt

The narration should be a WAV or FLAC file (voice.py writes WAV).

With --script, the captions use your script's spelling (names, numbers, punctuation) and only the timings come from
what Whisper heard. Without it, the captions show Whisper's words.

Each word also gets a `line`: "l1", "l2", ... for the script's paragraphs (separated by a blank line), so the stage can
anchor shots and poses to them ("@l2:half"). Without --script every word is in "l1".
"""
import argparse
import difflib
import json
import re


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def onto_script(script_words, heard):
    """Give each script word a time from the heard words: matching runs copy timings, the rest share their span."""
    out = []
    sm = difflib.SequenceMatcher(a=[norm(w) for w in script_words], b=[norm(h["text"]) for h in heard], autojunk=False)
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            out += [dict(heard[b0 + k], text=script_words[a0 + k]) for k in range(a1 - a0)]
            continue
        if a1 == a0:
            continue   # heard but not in the script: drop it
        if b1 > b0:
            start, end = heard[b0]["start"], heard[b1 - 1]["end"]
        else:   # in the script but not heard: squeeze it in at the previous word's end
            start = end = out[-1]["end"] if out else 0.0
        step = (end - start) / (a1 - a0)
        out += [{"text": script_words[a0 + k], "start": round(start + k * step, 3), "end": round(start + (k + 1) * step, 3)}
                for k in range(a1 - a0)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--script", help="the script the narration reads, for correct spelling in the captions")
    ap.add_argument("--model", default="small.en", help="faster-whisper model: tiny.en, base.en, small.en, medium.en")
    ap.add_argument("--device", default="cpu", help="cpu, or cuda if you have the CUDA libraries installed")
    a = ap.parse_args()

    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel

    # read the audio here (16 kHz mono, as Whisper wants it) instead of through faster-whisper's own decoder
    y, sr = sf.read(a.audio, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    t = np.arange(int(len(y) * 16000 / sr)) / 16000
    audio = np.interp(t, np.arange(len(y)) / sr, y).astype(np.float32)

    model = WhisperModel(a.model, device=a.device, compute_type="int8" if a.device == "cpu" else "float16")
    segments, _ = model.transcribe(audio, language="en", word_timestamps=True)
    heard = [{"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
             for s in segments for w in s.words]
    if a.script:
        paras = [p.split() for p in re.split(r"\n\s*\n", open(a.script, encoding="utf-8").read()) if p.strip()]
        lines = ["l%d" % (i + 1) for i, p in enumerate(paras) for _ in p]
        words = [dict(w, line=ln) for w, ln in zip(onto_script([w for p in paras for w in p], heard), lines)]
    else:
        words = [dict(w, line="l1") for w in heard]
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=1, ensure_ascii=False)
    print(f"{a.out}: {len(words)} words, last ends at {words[-1]['end']:.2f} s" if words else "no words heard")


if __name__ == "__main__":
    main()
