"""Hazard Pay: robot insurance priced by an AI adversary that tries to break the robot first."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_env = ROOT / ".env"
if _env.exists():  # tiny .env loader; real environment variables win
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
