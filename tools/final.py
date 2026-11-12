"""Final film: the music-only 3D intro + the live app demo in Suryansh's own voice (footage sped up, voice natural).

    python -m tools.final
inputs:  runs/render/intro_video.mp4                               the 3D intro (rendered offline, no screen recording)
         runs/screen1.mov + runs/rec_start1.txt + runs/live_marks.json   the live app run
         static/film/vo/<shot>.mp3                                   Suryansh's voice lines
         static/film/score.mp3                                       orchestral score
output:  ~/Desktop/HazardPay_FINAL.mp4
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
FILM = ROOT / "static" / "film"
OUT = Path.home() / "Desktop" / "HazardPay_FINAL.mp4"
CROP = "crop=iw:iw*9/16:0:ih*0.095,"
SHOTS = ["s3b", "s4", "s5", "s6", "s7", "s8", "s9", "s10"]   # the intro already told the story (s1-s3)
SKIP = {"s8": 150.0}   # seconds into the claim shot when the demo window was back in front
LIMIT = 178.0


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def main():
    tmp = RUNS / "final2"
    tmp.mkdir(exist_ok=True)
    intro = RUNS / "render" / "intro_video.mp4"
    intro_len = dur(intro)
    lm = json.loads((RUNS / "live_marks.json").read_text())
    off = lm["wall"] - float((RUNS / "rec_start1.txt").read_text())
    order = [k for k in lm if k not in ("wall",)]
    vo = {k: dur(FILM / "vo" / f"{k}.mp3") for k in SHOTS}
    budget = LIMIT - intro_len
    want = {k: vo[k] + 1.0 for k in SHOTS}
    k_scale = min(1.0, budget / sum(want.values()))
    parts, starts, t = [], {}, intro_len
    for sid in SHOTS:
        a = lm[sid] + SKIP.get(sid, 0)
        b = lm[order[order.index(sid) + 1]]
        tgt = want[sid] * k_scale
        speed = max(1.0, (b - a) / tgt)
        out = tmp / f"{sid}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off + a:.3f}", "-t", f"{b - a:.3f}", "-i", str(RUNS / "screen1.mov"),
                        "-vf", f"setpts=PTS/{speed:.4f},{CROP}scale=1920:1080,fps=30,format=yuv420p",
                        "-t", f"{tgt:.3f}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(out)], check=True)
        starts[sid] = t
        t += dur(out)
        parts.append(out)
        print(f"{sid:>4}: {b - a:6.1f}s of app -> {dur(out):5.1f}s ({speed:.1f}x), voice {vo[sid]:.1f}s")
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in [intro, *parts]))
    video = tmp / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30", str(video)], check=True)
    total = dur(video)
    inputs, filt, labels, n = ["-i", str(video)], [], [], 1
    for sid in SHOTS:
        inputs += ["-i", str(FILM / "vo" / f"{sid}.mp3")]
        ms = int((starts[sid] + 0.3) * 1000)
        filt.append(f"[{n}:a]adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
        n += 1
    filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,volume=1.5[vo]")
    inputs += ["-stream_loop", "-1", "-i", str(FILM / "score.mp3")]
    # the score carries the music-only intro, then sits under the voice
    filt += [f"[{n}:a]atrim=0:{total:.2f},volume='if(lt(t,{intro_len:.2f}),0.75,0.28)':eval=frame,"
             f"afade=t=in:d=2,afade=t=out:st={total - 5:.2f}:d=5[mus]",
             "[vo]asplit=2[vo1][vo2]", "[mus][vo2]sidechaincompress=threshold=0.03:ratio=5:attack=40:release=700[duck]",
             "[vo1][duck]amix=inputs=2:normalize=0[aout]"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]",
                    "-t", f"{total:.2f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(OUT)], check=True)
    print(OUT, f"{dur(OUT):.1f}s (intro {intro_len:.1f}s + app {total - intro_len:.1f}s)")


if __name__ == "__main__":
    main()
