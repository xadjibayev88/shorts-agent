"""Queue for lyric-toon videos: queue_apex/toon/*.json (see samples/lyric_toon_sample.json).

A toon spec adds publishing fields to the renderer spec: title, description,
hashtags, tags. If it carries an audio file, "audio_licensed": true is required,
so a copyrighted track cannot be queued by accident.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("title", "description", "lines")


class ToonSpecError(ValueError):
    """The spec is unusable and should be moved to rejected/."""


def validate_toon(spec: dict) -> dict:
    missing = [k for k in REQUIRED if not spec.get(k)] + (["beam_t"] if "beam_t" not in spec else [])
    if missing:
        raise ToonSpecError(f"missing fields: {', '.join(missing)}")
    if spec.get("audio") and not spec.get("audio_licensed"):
        raise ToonSpecError("audio given without audio_licensed=true")
    prev_end = 0.0
    for i, line in enumerate(spec["lines"]):
        if not str(line.get("text", "")).strip():
            raise ToonSpecError(f"line {i} has no text")
        if not 0 <= line["t0"] < line["t1"] or line["t0"] < prev_end - 0.01:
            raise ToonSpecError(f"line {i} has bad timing")
        prev_end = line["t1"]
    if spec["lines"][0]["t0"] < spec["beam_t"]:
        raise ToonSpecError("first lyric starts before the spotlight")
    return spec


def next_toon(queue: Path, used_titles: set[str]):
    """Return (spec, path) for the first valid spec, moving bad/duplicate ones aside."""
    folder = queue / "toon"
    for path in sorted(folder.glob("*.json")):
        try:
            spec = validate_toon(json.loads(path.read_text(encoding="utf-8")))
        except (ToonSpecError, json.JSONDecodeError, KeyError, TypeError):
            _move(path, folder / "rejected")
            continue
        if spec["title"].lower() in used_titles:
            _move(path, folder / "done")
            continue
        return spec, path
    return None, None


def _move(path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    path.rename(dest / path.name)


def mark_done(path: Path) -> None:
    _move(path, path.parent / "done")
