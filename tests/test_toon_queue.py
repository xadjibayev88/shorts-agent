import json

import pytest

from agent.toon_queue import ToonSpecError, next_toon, validate_toon


def _spec(**over):
    spec = {"title": "T1", "description": "d", "beam_t": 6.0,
            "lines": [{"t0": 6.5, "t1": 8.0, "text": "bir"}, {"t0": 8.2, "t1": 9.0, "text": "ikki"}]}
    spec.update(over)
    return spec


def test_valid_spec_passes():
    assert validate_toon(_spec())["title"] == "T1"


def test_unlicensed_audio_is_rejected():
    with pytest.raises(ToonSpecError):
        validate_toon(_spec(audio="song.wav"))


def test_licensed_audio_is_accepted():
    assert validate_toon(_spec(audio="song.wav", audio_licensed=True))


def test_lyric_before_spotlight_is_rejected():
    with pytest.raises(ToonSpecError):
        validate_toon(_spec(beam_t=7.0))


def test_overlapping_lines_are_rejected():
    bad = [{"t0": 6.5, "t1": 8.0, "text": "a"}, {"t0": 7.0, "t1": 9.0, "text": "b"}]
    with pytest.raises(ToonSpecError):
        validate_toon(_spec(lines=bad))


def test_missing_title_is_rejected():
    with pytest.raises(ToonSpecError):
        validate_toon(_spec(title=""))


def test_queue_moves_bad_and_duplicate_and_returns_first_good(tmp_path):
    toon = tmp_path / "toon"
    toon.mkdir()
    (toon / "01_bad.json").write_text("{not json", encoding="utf-8")
    (toon / "02_dup.json").write_text(json.dumps(_spec(title="Used")), encoding="utf-8")
    (toon / "03_ok.json").write_text(json.dumps(_spec(title="Fresh")), encoding="utf-8")
    spec, path = next_toon(tmp_path, {"used"})
    assert spec["title"] == "Fresh" and path.name == "03_ok.json"
    assert (toon / "rejected" / "01_bad.json").exists()
    assert (toon / "done" / "02_dup.json").exists()


def test_empty_queue_returns_none(tmp_path):
    assert next_toon(tmp_path, set()) == (None, None)
