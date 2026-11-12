"""Gemini (REST): the attacker's hypotheses, site photos -> hazards, adjuster notes."""
import base64
import json
import os
import re

import httpx

KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
FALLBACKS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-robotics-er-2-preview")  # embodied reasoning for site photos
LAST = {"model": MODEL}


def live() -> bool:
    return bool(KEY) and os.getenv("DEMO_MODE", "").lower() not in {"1", "true", "yes"}


COOL = {"until": 0.0}  # after every model is out of quota, don't keep a user waiting on retries


def _call(parts, temperature=0.4, json_mode=False, system=None, model=None):
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": temperature}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    import time
    if time.time() < COOL["until"]:
        raise RuntimeError("Gemini over quota; using the fallback for a few minutes")
    chain = [model or MODEL] + [m for m in [MODEL] + FALLBACKS if m != (model or MODEL)]
    for m in chain:  # under load Gemini answers 503/429: retry, then fall back to the next model
        r = None
        for attempt in range(2):
            try:
                r = httpx.post(URL.format(m=m), headers={"x-goog-api-key": KEY}, json=body, timeout=40)
            except httpx.HTTPError:
                r = None
                continue
            if r.status_code not in (429, 500, 503) or "quota" in r.text.lower():
                break
            time.sleep(1.5 * (attempt + 1))
        if r is None:
            continue
        if r.status_code == 200:
            LAST["model"] = m
            break
        if r.status_code not in (404, 429, 500, 503):
            break
    if r is None or r.status_code != 200:
        if r is not None and r.status_code == 429:
            COOL["until"] = time.time() + 300
        raise RuntimeError("Gemini unavailable" if r is None else f"Gemini {r.status_code}: {r.text[:300]}")
    return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"].get("parts", []))


def text(prompt: str, temperature=0.4) -> str:
    return _call([{"text": prompt}], temperature).strip()


def json_call(prompt: str, temperature=0.4, system=None, image_b64: str | None = None, mime="image/jpeg", model=None) -> dict:
    parts = [{"text": prompt}]
    if image_b64:
        if "," in image_b64[:80]:
            image_b64 = image_b64.split(",", 1)[1]
        base64.b64decode(image_b64[:64] + "==", validate=False)
        parts.append({"inline_data": {"mime_type": mime, "data": image_b64}})
    out = _call(parts, temperature, json_mode=True, system=system, model=model)
    return json.loads(re.sub(r"^```(json)?|```$", "", out.strip()).strip())
