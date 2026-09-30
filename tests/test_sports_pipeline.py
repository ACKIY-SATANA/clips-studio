"""The Sports toggle in the pipeline: without a sport nothing changes; with one,
a match's moments reach the scorer, a goal becomes a marked clip, and the
Highlights choice keeps what was asked for. Also the job option's way in: the
API's check, the sports list, and a watch's payload."""

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")

import sports

ROOT = Path(__file__).resolve().parent.parent


class Says:
    def __init__(self, answer="{}"):
        self.answer = answer

    def generate(self, *_a, **_k):
        return self.answer


def _segments():
    from core.models import Segment

    segs = [Segment(start=float(s), end=float(s + 5), text="passing it around the back") for s in range(0, 600, 5)]
    for s in segs:
        if s.start == 450:
            s.text = "GOOOAL! what a goal, into the back of the net"
    return segs


@pytest.fixture
def fused(monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from analysis import fusion, highlights
    from core.models import ClipCandidate

    picks = [(0, 30, 62), (100, 130, 64), (440, 470, 58), (200, 230, 61)]

    def score_windows(_segments, _llm, windows, **_k):
        return [ClipCandidate(start=a, end=b, score=55, hook="w", source="signal") for a, b in windows]

    monkeypatch.setattr(highlights, "find_highlights", lambda *_a, **_k: (
        [ClipCandidate(start=a, end=b, score=s, hook="h", reason="r") for a, b, s in picks], []))
    monkeypatch.setattr(highlights, "score_windows", score_windows)
    monkeypatch.setattr(fusion, "reaction_for_window", lambda *_a, **_k: 0.5)

    def run(highlights_choice=None):
        config = {
            "clips": {"min_duration": 10, "max_duration": 60, "min_score": 40, "max_clips_per_video": 0},
            "analysis": {"chunk_seconds": 600, "chunk_overlap_seconds": 30,
                         "long_video_threshold_seconds": 3600, "max_overlap": 0.3,
                         "max_text_similarity": 0.8, "max_segment_reuse": 0.5},
            "scoring": {"rerank_pool": 0, "read_screen": False},
            "tracking": {"detector": "yolov8n.pt"},
        }
        signals = ({"spike": np.zeros(600)}, {"motion": np.zeros(600)})
        sport = None
        if highlights_choice:
            config["clips"]["sport"] = {"name": "soccer", "highlights": highlights_choice}
            sport = sports.profile_for(config)
            crowd = np.zeros(600, dtype=np.float32)
            crowd[452:460] = 0.9
            sport.curves = {"crowd": crowd, "whistle": np.zeros(600, dtype=np.float32)}
        kept, rejected = fusion.find_clips("vod.mp4", _segments(), Says(), config, signals=signals,
                                           measure_reaction=False,
                                           **({"sport": sport} if sport is not None else {}))
        return kept, rejected, sport

    return run


def _key(clips):
    return sorted((round(c.start, 1), round(c.end, 1), c.score) for c in clips)


def test_no_sport_changes_nothing(fused, monkeypatch):
    before, _r, _s = fused()
    monkeypatch.setattr(sports, "profile_for", lambda *_a, **_k: pytest.fail("no sport, no sports code"))
    again, _r, _s = fused()
    assert _key(before) == _key(again)
    assert not any("sport_event" in (c.subscores or {}) for c in again)


def test_a_goal_becomes_a_marked_clip_with_its_bonus(fused):
    kept, _rejected, sport = fused("best")
    goal = [c for c in kept if (c.subscores or {}).get("sport_event") == "goal"]
    assert goal and goal[0].subscores["sport_bonus"] > 0
    assert goal[0].start <= 450 - 10 and goal[0].end >= 450 + 5      # build-up and reaction
    assert sport.report_data["found"] == {"Goal": 1}


def test_all_goals_keeps_only_the_goal(fused):
    kept, rejected, _sport = fused("goals")
    assert kept and all((c.subscores or {}).get("sport_event") == "goal" for c in kept)
    assert any(r.reason == "not_in_highlights" for r in rejected)


def test_a_match_leaves_reactions_neutral():
    from core import modes

    assert not modes.measures_reaction({"clips": {"sport": {"name": "soccer"}}})
    assert modes.sport({"clips": {"sport": {"name": "soccer"}}}) == "soccer"
    assert modes.sport({"clips": {}}) is None


# ---- the way in ---------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("yt_dlp")
    from fastapi.testclient import TestClient

    from main import BUNDLED_CONFIG, load_config
    from server.api import create_app

    settings = tmp_path / "settings.yaml"
    shutil.copy(ROOT / "config" / "settings.yaml", settings)
    config = load_config(BUNDLED_CONFIG)
    config["paths"]["data_dir"] = str(tmp_path / "data")
    return TestClient(create_app(config, settings), base_url="http://127.0.0.1")


URL = "https://www.youtube.com/watch?v=abcdefghijk"


def test_the_sports_are_listed(client):
    listed = client.get("/sports").json()
    assert listed[0]["id"] == "soccer" and listed[0]["highlights"]


def test_a_job_carries_its_sport_cleaned(client):
    job = client.post("/jobs", json={"url": URL, "sport": {"name": "Soccer", "highlights": "goals",
                                                           "teams": "  Team A "}}).json()
    payload = json.loads(client.get(f"/jobs/{job['job_id']}").json()["payload"])
    assert payload["sport"] == {"name": "soccer", "highlights": "goals", "period": "full", "teams": "Team A"}


def test_an_unknown_sport_or_a_clashing_mode_is_refused(client):
    assert client.post("/jobs", json={"url": URL, "sport": {"name": "curling"}}).status_code == 400
    clash = client.post("/jobs", json={"url": URL, "sport": {"name": "soccer"}, "gaming": True})
    assert clash.status_code == 400 and "Sports" in clash.json()["detail"]


def test_a_watch_drops_a_sport_set_beside_gaming():
    pytest.importorskip("fastapi")
    from server.automation import job_payload

    watch = {"options": json.dumps({"sport": {"name": "soccer"}, "gaming": True})}
    assert "sport" not in job_payload(watch, URL)
    alone = {"options": json.dumps({"sport": {"name": "soccer", "highlights": "best", "period": "full"}})}
    assert job_payload(alone, URL)["sport"]["name"] == "soccer"


# ---- Longform, and the shape of the source ---------------------------------------------


REPORT = {"sport": "Soccer", "found": {"Goal": 1}}


class _Match:
    """A read match: what MatchReading.finish() gives the scorer."""

    def __init__(self):
        self.report_data = dict(REPORT)


def _longform(monkeypatch, tmp_path, db, seen):
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    import analysis.fusion as fusion
    import core.pipeline as pipeline
    import llm.registry as registry
    import transcription.transcriber as transcriber
    from core.models import DownloadedVideo
    from longform import process as longform

    source = tmp_path / "match.mp4"
    source.write_bytes(b"not really a video")
    monkeypatch.setattr(pipeline, "_cached_or_download", lambda *_a, **_k: DownloadedVideo(
        video_id="local_match", title="Match", path=source, duration=600.0))
    monkeypatch.setattr(transcriber, "transcribe", lambda *_a, **_k: [])
    monkeypatch.setattr(registry, "create_backend", lambda *_a, **_k: Says())

    class Reading:
        def __init__(self, config, video):
            seen["read"] = True

        def finish(self, hype_out=None):
            return _Match(), None, None

    monkeypatch.setattr(pipeline, "MatchReading", Reading)

    def find(_path, _segments, _llm, _cfg, **kw):
        seen.update(kw)
        return [], []

    monkeypatch.setattr(fusion, "find_clips", find)
    return longform


def _longform_config(tmp_path, **clips):
    return {"clips": {"captions": False, **clips}, "paths": {"data_dir": str(tmp_path)},
            "whisper": {"model": "tiny", "device": "cpu"}, "llm": {}}


def test_longform_reads_the_match_and_keeps_its_report(monkeypatch, tmp_path, db):
    seen: dict = {}
    longform = _longform(monkeypatch, tmp_path, db, seen)
    longform.process_longform("local:match", _longform_config(tmp_path, sport={"name": "soccer"}),
                              db, {"mode": "short_clips"})
    assert seen["read"] and isinstance(seen["sport"], _Match) and seen["measure_reaction"] is False
    assert db.get_outcome("local_match") == {"sport": REPORT, "longform_only": True}
    # The 16:9 pass's report isn't a Shorts run: a Shorts request still runs.
    assert not db.shorts_made("local_match")


def test_longform_without_a_sport_is_as_before(monkeypatch, tmp_path, db):
    seen: dict = {}
    longform = _longform(monkeypatch, tmp_path, db, seen)
    longform.process_longform("local:match", _longform_config(tmp_path), db, {"mode": "short_clips"})
    assert "read" not in seen and "sport" not in seen and "measure_reaction" not in seen
    assert db.get_outcome("local_match") == {}


def test_a_longform_pass_after_the_shorts_keeps_their_outcome(db):
    from longform.process import _record_match

    db.upsert_video("local_both", title="Match")
    shorts = {"clips": 6, "candidates": 40, "sport": {"sport": "Soccer", "found": {"Goal": 6}}}
    db.set_outcome("local_both", shorts)
    _record_match(db, "local_both", {"sport": "Soccer", "found": {"Goal": 5}})
    assert db.get_outcome("local_both") == shorts


class _Stop(Exception):
    """Stops a run where the test has seen what it needs."""


def test_a_match_filmed_9x16_keeps_its_composition(monkeypatch, tmp_path, db):
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    import core.pipeline as pipeline
    from core import modes
    from core.models import DownloadedVideo

    source = tmp_path / "phone.mp4"
    source.write_bytes(b"not really a video")
    monkeypatch.setattr(pipeline, "_cached_or_download", lambda *_a, **_k: DownloadedVideo(
        video_id="local_phone", title="Phone", path=source, duration=600.0))
    monkeypatch.setattr("video.encoding.source_codec", lambda _p: "h264")
    monkeypatch.setattr("analysis.audio_features.extract_audio_features", lambda _p: {})
    monkeypatch.setattr("analysis.visual_features.extract_visual_features", lambda _p: {})
    monkeypatch.setattr("analysis.hype.audience_signals", lambda *_a, **_k: (None, None))
    seen: dict = {}

    class Reading:
        def __init__(self, config, video):
            seen["clips"] = config["clips"]
            raise _Stop

    monkeypatch.setattr(pipeline, "MatchReading", Reading)
    config = {"clips": {"captions": False, "sport": {"name": "soccer"}}, "paths": {"data_dir": str(tmp_path)}}
    for size, kept in (((1080, 1920), True), ((1920, 1080), False)):
        monkeypatch.setattr(modes, "probe_size", lambda _p, s=size: s)
        with pytest.raises(_Stop):
            pipeline.process_video("local:phone", config, db, force=True)
        assert bool(seen["clips"].get("vertical_live")) is kept, size


def test_a_16x9_match_is_framed_by_the_ball_not_a_face(monkeypatch, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    import core.pipeline as pipeline
    import video.cropper as cropper
    import video.tracker as tracker
    from core import modes
    from core.models import ClipCandidate

    def no_faces(*_a, **_k):
        raise AssertionError("face tracking ran")

    rendered: dict = {}

    def render(_clip, tracking, output, *_a, **_k):
        rendered["tracking"] = tracking
        Path(output).write_bytes(b"clip")
        return Path(output)

    monkeypatch.setattr(pipeline, "cut_clip", lambda _s, _c, output, **_k: Path(output).write_bytes(b"cut"))
    monkeypatch.setattr(modes, "probe_size", lambda _p: (1920, 1080))
    monkeypatch.setattr(sports, "framing", lambda name, path, config: {"mode": "track", "path": [(0.0, 0.3)]})
    monkeypatch.setattr(cropper, "render_vertical", render)
    monkeypatch.setattr(tracker, "compute_tracking", no_faces)
    config = {"clips": {"captions": False, "outro": False, "vertical": True, "sport": {"name": "soccer"}},
              "paths": {"data_dir": str(tmp_path)}, "tracking": {"detector": "yolov8n-pose.pt", "sample_fps": 8}}
    final, opts_json = pipeline._render_files(tmp_path / "source.mp4", ClipCandidate(start=10.0, end=40.0, score=80),
                                              [], tmp_path / "clips", config)
    assert final.exists() and rendered["tracking"]["path"] == [(0.0, 0.3)]
    assert json.loads(opts_json)["sport"] == "soccer"
