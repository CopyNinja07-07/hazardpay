"""Split one voice memo (lines read in order, ~2 s pauses) into static/film/vo/<id>.mp3 + vo.json.

    python -m tools.voice_split ~/Desktop/voice.m4a
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILM = ROOT / "static" / "film"


def silences(path, noise="-35dB", d=1.1):
    err = subprocess.run(["ffmpeg", "-i", str(path), "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    total = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()[2]) + 60 * int(
        re.search(r"Duration: (\d+):(\d+)", err).group(2)) + 3600 * int(re.search(r"Duration: (\d+)", err).group(1))
    return starts, ends, total


def main(src):
    ids = list(json.loads((FILM / "lines.json").read_text()))
    for noise, d in (("-35dB", 1.1), ("-32dB", 0.9), ("-38dB", 1.4), ("-30dB", 0.7)):
        starts, ends, total = silences(src, noise, d)
        segs, cur = [], 0.0
        for s, e in zip(starts, ends):
            if s - cur > 0.6:
                segs.append((cur, s))
            cur = e
        if total - cur > 0.6:
            segs.append((cur, total))
        print(f"{noise} {d}s -> {len(segs)} segments")
        if len(segs) >= len(ids):
            break
    if len(segs) < len(ids):
        sys.exit(f"Found {len(segs)} spoken segments but need {len(ids)}: leave clearer 2 s pauses.")
    segs = segs[-len(ids):] if len(segs) > len(ids) else segs  # extra takes at the start are dropped
    (FILM / "vo").mkdir(parents=True, exist_ok=True)
    lens = {}
    for sid, (a, b) in zip(ids, segs):
        out = FILM / "vo" / f"{sid}.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ss", f"{max(0, a - 0.15):.2f}", "-to", f"{b + 0.2:.2f}",
                        "-af", "highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", str(out)], check=True)
        lens[sid] = round(b - a + 0.8, 2)
        print(sid, f"{b - a:.1f}s")
    (FILM / "vo.json").write_text(json.dumps(lens, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
