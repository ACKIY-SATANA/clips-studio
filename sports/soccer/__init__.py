"""Soccer (football): the first sport. config/sports.yaml's `soccer` entry is
its data; this package holds the rules the data can't say, the scoreboard
reader and the framing (see docs/SPORTS.md)."""

from sports.soccer.profile import SoccerProfile


def profile(config: dict, option: dict, video=None) -> SoccerProfile:
    from sports.core.profile import weights_for

    return SoccerProfile(name="soccer", option=dict(option), weights=weights_for(config))
