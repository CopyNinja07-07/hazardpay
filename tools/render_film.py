"""Render the 3D film offline, frame by frame, in a hidden browser (no screen recording), then add voice + score.

    <venv with playwright>/bin/python tools/render_film.py [--test] [--fps 30]
output: ~/Desktop/HazardPay_film.mp4
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FILM = ROOT / "static" / "film"
OUT = Path.home() / "Desktop" / "HazardPay_film.mp4"
TMP = ROOT / "runs" / "render"
URL = "http://localhost:8766/static/film.html?render"
INTRO = "--intro" in sys.argv


def main():
    test = "--test" in sys.argv
    fps = int(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else 30
    TMP.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        pg.goto(URL + ("&intro" if INTRO else ""))
        pg.wait_for_function("window.__ready === true", timeout=120000)
        pg.wait_for_timeout(1500)  # fonts
        film = pg.evaluate("window.__film")
        end = film["END"]
        n = int(end * fps) if not test else 0
        stamps = [10, 20, 40, 60, 80, 100, 120, 140] if test else None
        video = TMP / ("intro_video.mp4" if INTRO else "film_video.mp4")
        ff = None if test else subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-", "-c:v", "libx264",
             "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(video)], stdin=subprocess.PIPE)
        t0 = time.time()
        frames = [s * fps for s in stamps] if test else range(n)
        for i in frames:
            pg.evaluate(f"window.__frame({i / fps})")
            img = pg.screenshot(type="jpeg", quality=92)
            if test:
                (TMP / f"test_{i // fps:03d}.jpg").write_bytes(img)
            else:
                ff.stdin.write(img)
                if i % (fps * 10) == 0:
                    el = time.time() - t0
                    print(f"{i / fps:6.1f}s / {end:.1f}s  ({el:.0f}s elapsed, ~{el / max(1, i) * (n - i):.0f}s left)", flush=True)
        if ff:
            ff.stdin.close(); ff.wait()
        b.close()
    if test:
        print("test frames in", TMP, f"{time.time() - t0:.1f}s")
        return
    if INTRO:
        print(video, end)
        return
    shots = film["shots"]
    mix(video, shots, end)


def mix(video, shots, end):
    inputs, filt, labels, k = ["-i", str(video)], [], [], 1
    for s in shots:
        p = FILM / "vo3" / f"{s['id']}.wav"
        if p.exists():
            ms = int((s["t"] + 0.45) * 1000)
            inputs += ["-i", str(p)]
            filt.append(f"[{k}:a]adelay={ms}|{ms}[v{k}]")
            labels.append(f"[v{k}]")
            k += 1
    filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,volume=1.5[vo]")
    inputs += ["-stream_loop", "-1", "-i", str(FILM / "score.mp3")]
    filt += [f"[{k}:a]volume=0.28,atrim=0:{end:.2f},afade=t=in:d=2,afade=t=out:st={end - 5:.2f}:d=5[mus]",
             "[vo]asplit=2[vo1][vo2]", "[mus][vo2]sidechaincompress=threshold=0.03:ratio=5:attack=40:release=700[duck]",
             "[vo1][duck]amix=inputs=2:normalize=0[aout]"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]",
                    "-t", f"{end:.2f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(OUT)], check=True)
    print(OUT)


if __name__ == "__main__":
    main()
