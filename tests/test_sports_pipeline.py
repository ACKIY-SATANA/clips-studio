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
