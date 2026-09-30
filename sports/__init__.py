"""Sports (docs/SPORTS.md): sport-specific intelligence on top of the normal
clipping pipeline, one sport per package. Soccer first.

A job with the Sports toggle on carries `sport`, for example
{"name": "soccer", "highlights": "goals", "period": "full", "teams": "Team A"}
(and with Custom highlights, `request`: the moments in the person's words).
Without it nothing here runs and the video is clipped exactly as before.

It adds no pipeline of its own. The sport's profile plugs into the same
scoring the gaming profile uses (analysis/fusion.py), with the same Whisper,
the same AI (any provider), the same renderer, queue, watches and publishing.

Adding a sport: an entry in config/sports.yaml, a sports/<name>/ package with
a `profile(config, option, video)` function, and a line in SPORTS below.
"""

import importlib
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sports.yaml"

# Each sport and the package that knows it, imported only when a job asks.
SPORTS = {"soccer": "sports.soccer"}

TEAMS_MAX = 200


@lru_cache(maxsize=1)
def knowledge() -> dict:
    import yaml

    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def spec(name: str) -> dict:
    """A sport's entry in config/sports.yaml, or {}."""
    return knowledge().get(name) or {}


def available() -> list[dict]:
    """The sports the app offers, with their highlight and period choices,
    for the Sports toggle's menus."""
    out = []
    for name in SPORTS:
        s = spec(name)
        if not s:
            continue
        out.append({
            "id": name,
            "label": s.get("label") or name.title(),
            "highlights": [{"id": k, "label": v.get("label") or k}
                           for k, v in (s.get("highlights_choices") or {}).items()],
            "periods": [{"id": k, "label": v} for k, v in (s.get("periods") or {}).items()],
        })
    return out


def clean(raw) -> dict:
    """A job's sport option reduced to valid values: the API's check, so a
    job can't be queued for a sport or choice that doesn't exist. Raises
    ValueError with what is allowed."""
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        raise ValueError("sport must be an object like {\"name\": \"soccer\"}")
    name = str(raw.get("name") or "").strip().lower()
    s = spec(name) if name in SPORTS else {}
    if not s:
        raise ValueError(f"unknown sport {name!r}; available: {', '.join(SPORTS)}")
    choices = s.get("highlights_choices") or {}
    highlights = str(raw.get("highlights") or "best")
    if highlights not in choices:
        raise ValueError(f"highlights must be one of: {', '.join(choices)}")
    periods = s.get("periods") or {}
    period = str(raw.get("period") or "full")
    if period not in periods:
        raise ValueError(f"period must be one of: {', '.join(periods)}")
    out = {"name": name, "highlights": highlights, "period": period}
    teams = " ".join(str(raw.get("teams") or "").split())[:TEAMS_MAX]
    if teams:
        out["teams"] = teams
    # Custom highlights: the moments described in the person's own words,
    # which become a clip direction (analysis/intent.py). Only with Custom.
    request = " ".join(str(raw.get("request") or "").split())[:TEAMS_MAX]
    if request and highlights == "custom":
        out["request"] = request
    return out


def direction(opt: dict) -> str:
    """What a sport option asks for in words, as a clip direction
    (analysis/intent.py): Custom's description, then the teams or players.
    "" when it asks for nothing in words."""
    parts = []
    if opt.get("request"):
        parts.append(f"{str(opt['request']).rstrip('.')}.")
    if opt.get("teams"):
        parts.append(f"More clips involving {opt['teams']}.")
    return " ".join(parts)


def option(config_or_opts: dict | None) -> dict | None:
    """The sport a job config (its clips section) or a clip's render options
    carries, or None."""
    if not config_or_opts:
        return None
    raw = config_or_opts.get("sport")
    if raw is None and isinstance(config_or_opts.get("clips"), dict):
        raw = config_or_opts["clips"].get("sport")
    if not raw:
        return None
    try:
        return clean(raw)
    except ValueError:
        return None


def profile_for(config: dict, video=None):
    """The sport's profile for this job, or None when it has none."""
    opt = option(config)
    if opt is None:
        return None
    module = importlib.import_module(SPORTS[opt["name"]])
    return module.profile(config, opt, video)


def framing(name: str, clip_path, config: dict) -> dict | None:
    """The sport's crop path for one clip ({"mode": "track", "path": ...}),
    or None when the sport has no framing of its own."""
    if name not in SPORTS:
        return None
    module = importlib.import_module(SPORTS[name])
    frame = getattr(module, "framing", None)
    return frame(clip_path, config) if frame is not None else None


def prepass(config: dict, video_path, duration: float) -> dict:
    """What the sport reads from the video itself while Whisper runs (soccer:
    the scoreboard), as attributes for its profile. {} for a sport with none."""
    opt = option(config)
    if opt is None:
        return {}
    module = importlib.import_module(SPORTS[opt["name"]])
    read = getattr(module, "prepass", None)
    return read(video_path, duration) if read is not None else {}
