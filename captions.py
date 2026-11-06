"""Turn words.json into burned-in captions (an .ass file): 1-3 words at a time, big and bold, in the lower middle.

    python captions.py words.json captions.ass --font "Arial Black" --size 96

A caption ends at a sentence or comma, after --max-words words, or at a pause, so each one reads as a small idea.
--margin is the distance from the bottom of a 1080x1920 frame; about a third of the way up keeps captions clear of the
app's buttons and description.
"""
import argparse
import json

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},2,2,80,80,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def stamp(t):
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def chunks(words, max_words, max_gap):
    group = []
    for i, w in enumerate(words):
        group.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (len(group) >= max_words or w["text"][-1:] in ".,!?;:" or nxt is None
                or nxt["start"] - w["end"] > max_gap):
            yield group
            group = []


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("words")
    ap.add_argument("out")
    ap.add_argument("--font", default="Arial Black")
    ap.add_argument("--size", type=int, default=96)
    ap.add_argument("--outline", type=int, default=7)
    ap.add_argument("--margin", type=int, default=620, help="pixels from the bottom of the frame")
    ap.add_argument("--max-words", type=int, default=3)
    ap.add_argument("--max-gap", type=float, default=0.3, help="a pause longer than this starts a new caption")
    ap.add_argument("--upper", action="store_true", help="ALL CAPS")
    a = ap.parse_args()

    words = json.load(open(a.words, encoding="utf-8"))
    groups = list(chunks(words, a.max_words, a.max_gap))
    lines = [HEADER.format(font=a.font, size=a.size, outline=a.outline, margin=a.margin)]
    for i, g in enumerate(groups):
        start = g[0]["start"]
        end = g[-1]["end"] + 0.25
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0]["start"])   # never two captions on screen at once
        text = " ".join(w["text"] for w in g).strip(" ,;:")
        text = text.upper() if a.upper else text
        lines.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Cap,,0,0,0,,{text}\n")
    with open(a.out, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"{a.out}: {len(groups)} captions")


if __name__ == "__main__":
    main()
