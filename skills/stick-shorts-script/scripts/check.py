"""Check a narrated short's script against the rules in ../SKILL.md.

  python check.py script.txt [--wpm 210]

The script is plain text, one paragraph per idea, with a blank line between paragraphs. The first sentence is the hook and
the last paragraph is the call to action; a paragraph before it that asks the viewer to follow or subscribe is the mid-roll.

Fails (exit 1) on the hook and call-to-action rules, a script outside 220-240 words, and what a listener hears as written
by AI: dashes, semicolons, "not just X but Y", "it's not X, it's Y", filler and fake suspense, the AI word list, metaphor
punchlines, hedging, emoji, more than one one-word sentence, and questions in the body. Warns on long sentences, a late mid-roll and stretches with no re-hook (a
number, a turn or a time jump), timed at the narrator's pace.
"""

import argparse
import re
import sys

HOOK_WORDS, CTA_WORDS, MID_WORDS = 15, 20, 10
STORY_WORDS = (220, 240)
REHOOK_S, MID_BY_S, LONG_SENTENCE = 8.0, 25.0, 32

FAIL = [
    (r"—|–| - ", "a dash (nobody speaks one)"),
    (r";", "a semicolon"),
    (r"(?i)\bnot just\b.*\bbut\b", '"not just X but Y"'),
    (r"(?i)\b(it|this|that)(?:'s| is| was) not (?:about )?\w+[^.]*?, (it|this|that)(?:'s| is| was)\b", '"it\'s not X, it\'s Y"'),
    (r"(?i)here'?s the thing|let that sink in|the truth is|in today'?s world|buckle up|imagine this|it'?s worth noting|"
     r"at the end of the day|whether you'?re a", "filler"),
    (r"(?i)\b(spoiler|plot twist)\s*:|here'?s where it gets interesting|the best part\?", "fake suspense"),
    (r"(?i)\b(delve|unlock|unleash|harness|leverage|seamless|robust|cutting[- ]edge|game[- ]?changer|revolutionary|"
     r"transformative|landscape|realm|tapestry|elevate|empower|supercharge|deep dive|next level|dive in)\b", "an AI word"),
    (r"(?i)\b(goldmine|gold mine|secret sauce|silver bullet|panic button|perfect storm)\b", "a metaphor punchline (say the plain fact)"),
    (r"(?i)\b(arguably|potentially|in many ways|in a sense|somewhat)\b", "hedging (say it or cut it)"),
    (r"(?i)\b(pivotal|testament to|indelible|breathtaking|groundbreaking|nestled|vibrant|renowned|stunning)\b",
     "puffery (say what happened)"),
    (r"(?i)\b(experts (?:say|believe|agree)|some (?:say|believe|argue)|many (?:say|believe)|it is said)\b",
     "a vague attribution (name who)"),
    (r"(?i)\b(serves as|stands as|boasts)\b", 'a fancy "is" (say is or has)'),
    (r"(?i)the future looks bright|a lesson for us all|only time will tell", "a generic ending"),
    (r"[\U0001F300-\U0001FAFF☀-➿]", "an emoji"),
]
NUMBER = (r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
          r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|"
          r"first|second|third|half|twice|once)\b")
TURN = (r"(?i)\b(but|then|until|suddenly|instead|later|after|before|when|today|now|finally|yet|so|only|never|"
        r"morning|night|year|years|days|hours|minutes|seconds)\b")
DATE = r"(?i)^(in |on |by |back in )?(the )?(\d{3,4}s?|(january|february|march|april|may|june|july|august|september|october|november|december)\b)"
ASK = r"(?i)\b(follow|subscribe)\b"


def sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]


def words(text: str) -> int:
    return len(text.split())


def check(paragraphs: list, wps: float) -> tuple:
    fails, warns = [], []
    *story, cta = paragraphs
    text = " ".join(paragraphs)
    for rx, why in FAIL:
        for m in re.finditer(rx, text):
            fails.append('%s: "...%s..."' % (why, text[max(0, m.start() - 25):m.end() + 25].strip()))

    hook = sentences(story[0])[0]
    if words(hook) > HOOK_WORDS:
        fails.append("the hook is %d words (%d at most): \"%s\"" % (words(hook), HOOK_WORDS, hook))
    if re.match(DATE, hook):
        fails.append('the hook opens on a date; open on the promise and give the date later: "%s"' % hook)

    if words(cta) > CTA_WORDS:
        fails.append("the call to action is %d words (%d at most)" % (words(cta), CTA_WORDS))
    if "?" not in cta:
        fails.append("the call to action asks no question about the story")
    if not re.search(ASK, cta):
        fails.append("the call to action never asks the viewer to follow or subscribe")
    elif re.search(r"(?i)\blike\b", cta) and re.search(r"(?i)\blike\b", cta).start() < re.search(ASK, cta).start():
        fails.append("the call to action asks for a like before the follow; the follow comes first")

    n = sum(words(p) for p in story)
    if not STORY_WORDS[0] <= n <= STORY_WORDS[1]:
        fails.append("the story is %d words (%d-%d, the mid-roll included)" % (n, *STORY_WORDS))

    mids = [k for k, p in enumerate(story) if re.search(ASK, p)]
    if not mids:
        warns.append("no mid-roll: a short line asking viewers to follow for more, before second %.0f" % MID_BY_S)
    for k in mids:
        at = sum(words(p) for p in story[:k]) / wps
        if words(story[k]) > MID_WORDS:
            fails.append("the mid-roll is %d words (%d at most): \"%s\"" % (words(story[k]), MID_WORDS, story[k]))
        if at > MID_BY_S:
            warns.append("the mid-roll starts at about %.0f s; by then many viewers have gone (aim for about 20 s)" % at)

    sents = [s for p in story for s in sentences(p)]
    one = [s for s in sents if words(s) == 1]
    if len(one) > 1:
        fails.append("%d one-word sentences (one at most): %s" % (len(one), one))
    fails += ['a question in the body: "%s"' % s for s in sents[1:] if s.endswith("?")]
    warns += ['a sentence over %d words: "%s..."' % (LONG_SENTENCE, s[:60]) for s in sents if words(s) > LONG_SENTENCE]

    t, worst = 0.0, (0.0, "")
    for s in sents[1:]:
        if re.search(NUMBER, s, re.I) or re.search(TURN, s):
            t = 0.0
        else:
            t += words(s) / wps
            if t > worst[0]:
                worst = (t, s)
    if worst[0] > REHOOK_S:
        warns.append('about %.0f s with no re-hook (a number, a turn or a time jump), ending at "%s"' % (worst[0], worst[1][:60]))

    total = n + words(cta)
    return fails, warns, "%d words, about %.0f s at %.0f words a minute" % (total, total / wps, wps * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--wpm", type=float, default=210, help="the narrator's pace after speed-up (default 210)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    text = open(a.script, encoding="utf-8").read()
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) < 2:
        raise SystemExit("put a blank line between paragraphs; the last one is the call to action")
    fails, warns, info = check(paragraphs, a.wpm / 60)
    print(info)
    for f in fails:
        print("  FAIL ", f)
    for w in warns:
        print("  warn ", w)
    print("  PASS" if not fails else "  REWRITE")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
