"""Put a short together with ffmpeg: picture + narration + music ducked under the voice + optional sound effects +
burned-in captions, out as a 1080x1920, 30 fps MP4 at -14 LUFS.

    python assemble.py --video picture.mp4 --voice narration.wav --captions captions.ass --music score.mp3 -o short.mp4

--video can be a video file or an image sequence such as "frames/%05d.png". It is scaled and cropped to fill 9:16.
The film runs as long as the narration plus --tail seconds; a shorter picture holds its last frame, a longer one is cut.
The music sits --music-under dB under the voice and dips a further 8 dB or so while someone is speaking.
--sfx is one finished sound-effects track (a WAV/MP3 the length of the film).
"""
import argparse
import json
import os
import subprocess


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--captions")
    ap.add_argument("--music")
    ap.add_argument("--sfx")
    ap.add_argument("--music-under", type=float, default=16, help="music level under the voice, in dB")
    ap.add_argument("--tail", type=float, default=0.3, help="seconds after the last word")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    for k in ("video", "voice", "music", "sfx", "out"):   # absolute, because ffmpeg runs from the captions' folder
        if getattr(a, k):
            setattr(a, k, os.path.abspath(getattr(a, k)))

    length = duration(a.voice) + a.tail
    is_sequence = "%" in a.video
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats"]
    cmd += ["-framerate", str(a.fps), "-i", a.video] if is_sequence else ["-i", a.video]
    cmd += ["-i", a.voice]
    inputs = 2
    if a.music:
        cmd += ["-stream_loop", "-1", "-i", a.music]
        music_in, inputs = inputs, inputs + 1
    if a.sfx:
        cmd += ["-i", a.sfx]
        sfx_in = inputs

    v = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps={a.fps},"
         f"tpad=stop_mode=clone:stop_duration={length:.2f},trim=duration={length:.2f},setsar=1")
    if a.captions:
        # the ass filter is picky about Windows paths, so ffmpeg runs from the captions' folder
        v += f",ass={os.path.basename(a.captions)}"
    graph = [v + "[v]", "[1:a]aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[voice][key]"]
    mix = ["[voice]"]
    if a.music:
        graph.append(f"[{music_in}:a]aresample=48000,loudnorm=I={-16 - a.music_under}:LRA=7[bed]")
        graph.append("[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=400:makeup=1[music]")
        mix.append("[music]")
    else:
        graph.append("[key]anullsink")
    if a.sfx:
        graph.append(f"[{sfx_in}:a]aresample=48000[sfx]")
        mix.append("[sfx]")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,"
                 f"apad,atrim=duration={length:.2f},loudnorm=I=-14:TP=-1:LRA=11,aresample=48000[a]")

    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    cwd = os.path.dirname(os.path.abspath(a.captions)) if a.captions else None
    subprocess.run(cmd, check=True, cwd=cwd)
    print(f"{a.out}: {length:.1f} s")


if __name__ == "__main__":
    main()
