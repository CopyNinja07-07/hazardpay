"""Free, local orchestral score with Meta's MusicGen (cue plan from docs/STORYBOARD.md).

    <venv with torch+transformers>/bin/python tools/score.py [total_seconds]

Generates the five cues, crossfades them in order, and writes static/film/score.mp3.
MusicGen weights are CC-BY-NC (fine for a hackathon demo, not for commercial use).
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "film"
CUES = [  # (seconds, prompt)
    (18, "gentle curious orchestral film score opening, solo celesta and soft strings, D major, 84 bpm, sense of wonder, sparse, no drums"),
    (30, "heroic orchestral theme, french horns play a hopeful four-note melody, warm strings ostinato, light timpani, D major, cinematic, no drums"),
    (30, "tense orchestral build, low brass and staccato strings, B minor, 96 bpm, clever suspense, cinematic film score, no drums"),
    (30, "triumphant orchestral theme returns, full strings and horns, then light playful pizzicato pulse, D major, cinematic"),
    (24, "full orchestra finale, grand statement of a heroic theme, final sustained major chord, cinematic film score ending"),
]


def main(total=None):
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    name = "facebook/musicgen-small"
    proc = AutoProcessor.from_pretrained(name)
    model = MusicgenForConditionalGeneration.from_pretrained(name).to(dev)
    sr = model.config.audio_encoder.sampling_rate
    parts = []
    for i, (secs, prompt) in enumerate(CUES):
        tokens = int(secs * 50)  # ~50 audio tokens per second
        x = proc(text=[prompt], padding=True, return_tensors="pt").to(dev)
        with torch.no_grad():
            a = model.generate(**x, max_new_tokens=tokens, do_sample=True, guidance_scale=3.5)
        y = a[0, 0].float().cpu().numpy()
        parts.append(y / (np.abs(y).max() + 1e-6) * 0.8)
        print(f"cue {i + 1}: {len(y) / sr:.1f}s")
    xf = int(1.5 * sr)  # 1.5 s crossfades
    out = parts[0]
    for p in parts[1:]:
        fade = np.linspace(0, 1, xf)
        out = np.concatenate([out[:-xf], out[-xf:] * (1 - fade) + p[:xf] * fade, p[xf:]])
    OUT.mkdir(parents=True, exist_ok=True)
    w = OUT / "score.wav"
    wav.write(w, sr, (out * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af", "loudnorm=I=-20,afade=t=in:d=1.5", "-b:a", "192k",
                    str(OUT / "score.mp3")], check=True)
    print(OUT / "score.mp3", f"{len(out) / sr:.1f}s")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else None)
