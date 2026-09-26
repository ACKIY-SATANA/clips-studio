"""Gaming / Reaction layouts: where each part goes on the 1080x1920 Short.

Geometry and framing are pure Python (no numpy), so most of this runs in CI;
the real renders need FFmpeg and OpenCV and are skipped without them.
"""

import re
import subprocess
from pathlib import Path

import pytest

from gaming import framing, layout

ROOT = Path(__file__).resolve().parent.parent
W, H = 1920, 1080
CAM = (0.0, 0.0, 0.25, 1 / 3)                       # a webcam in the top-left corner
TIKTOK = framing.safe_zone("tiktok")


def _plan(preset, cam=CAM, heads=None, **settings):
    return layout.plan(W, H, {"preset": preset, "cam": list(cam) if cam else None, **settings}, heads)


# ---- the layouts ------------------------------------------------------------------------


@pytest.mark.parametrize("preset", sorted(layout.PRESETS))
def test_every_layout_stays_on_the_canvas_in_even_sizes(preset):
    extra = {"ui_box": [0.3, 0.0, 0.4, 0.08], "cam2": [0.75, 0.0, 0.25, 1 / 3]}
    p = _plan(preset, **extra)
    assert p.preset == preset
    for e in p.elements:
        x, y, w, h = e.dest
        assert 0 <= x and 0 <= y and x + w <= 1080 and y + h <= 1920, (preset, e)
        assert all(v % 2 == 0 for v in (*e.dest, *e.src)), (preset, e)
        sx, sy, sw, sh = e.src
        assert 0 <= sx and 0 <= sy and sx + sw <= W and sy + sh <= H, (preset, e)


@pytest.mark.parametrize("preset", [k for k, v in layout.PRESETS.items() if v["type"] == "stack"])
def test_stacked_rows_meet_exactly_top_to_bottom(preset):
    p = _plan(preset, ui_box=[0.3, 0.0, 0.4, 0.08], cam2=[0.75, 0.0, 0.25, 1 / 3])
    edges = sorted({(e.dest[1], e.dest[1] + e.dest[3]) for e in p.elements})
    assert edges[0][0] == 0 and edges[-1][1] == 1920
    assert all(a[1] == b[0] for a, b in zip(edges, edges[1:]))


def test_camera_top_puts_the_camera_at_the_top_and_game_top_the_game():
    p = _plan("split", order="cam_top")
    assert p.element("cam").dest[1] == 0 and p.element("game").dest[1] + p.element("game").dest[3] == 1920
    p = _plan("split", order="game_top")
    assert p.element("game").dest[1] == 0 and p.element("cam").dest[1] + p.element("cam").dest[3] == 1920
    assert _plan("basecam").element("game").dest[1] == 0          # Basecam is game on top


def test_the_divider_sets_the_camera_band_within_the_layouts_range():
    assert _plan("split", divider=0.3).element("cam").dest[3] == 576
    assert _plan("split", divider=0.9).element("cam").dest[3] == 960      # capped at half
    assert _plan("split", divider=0.1).element("cam").dest[3] == 480      # at least a quarter
    assert _plan("half", divider=0.3).element("cam").dest[3] == 960       # Half is always half


def test_a_whole_game_sits_against_its_own_edge_never_in_the_middle():
    """The whole game used to float in the middle of its band, blur above and
    below. It is anchored to the edge of the Short its region touches."""
    assert _plan("split", game_fit="fit", order="cam_top").element("game").anchor == "bottom"
    assert _plan("split", game_fit="fit", order="game_top").element("game").anchor == "top"
    for preset, spec in layout.PRESETS.items():
        if spec["type"] == "stack":
            g = _plan(preset, game_fit="fit", ui_box=[0.3, 0, 0.4, 0.08], cam2=[0.75, 0, 0.25, 0.3]).element("game")
            assert g.anchor in ("top", "bottom"), preset
    assert _plan("blurred").element("game").anchor == "center"        # the game alone, by design


def test_layouts_fall_back_when_a_box_they_need_is_missing():
    assert _plan("split", cam=None).preset == "blurred"
    assert _plan("fullscreen", cam=None).preset == "fullscreen"
    assert _plan("game_ui").preset == "split"                       # no Game UI box drawn
    assert _plan("mosaic").preset == "split"
    assert _plan("dual_cam").preset == "small_cam"                  # no second webcam
    assert _plan("duo_split").preset == "split"


def test_settings_from_before_layouts_render_as_they_did():
    p = layout.plan(W, H, {"cam": [0.0, 0.69, 0.17, 0.31], "cam_position": "bottom", "game_fit": "fit"})
    assert p.preset == "half" and p.order == "game_top" and p.element("game").fit == "contain"
    assert p.element("cam").dest == (0, 960, 1080, 960)


def test_a_zoomed_game_leaves_the_webcam_and_edge_chat_out():
    for preset in ("split", "half", "fullscreen"):
        g = _plan(preset, game_fit="fill").element("game")
        gx, _gy, gw, _gh = g.src
        assert gx >= CAM[2] * W - 2 or preset == "fullscreen", preset       # clear of the webcam
        assert gx + gw <= 1600 + 150, preset                                  # a chat panel at 1600+
    assert _plan("fullscreen", cam=None, game_fit="fill", game_align="left").element("game").src[0] == 0


def test_a_drawn_game_area_leaves_out_the_chat_under_the_game():
    game = [0.17, 0.0, 0.83, 0.83]
    assert _plan("split", game_box=game, game_fit="fit").element("game").src == (326, 0, 1592, 896)
    x, y, w, h = _plan("split", game_box=game, game_fit="fill").element("game").src
    assert y + h <= 0.83 * H + 2 and x >= 0.17 * W - 2 and x + w <= W


def test_a_small_facecam_sits_inside_the_platforms_safe_zone():
    for preset in ("small_cam", "circle_cam", "dual_cam"):
        for safe in ("tiktok", "reels", "shorts"):
            p = _plan(preset, safe=safe, cam2=[0.75, 0, 0.25, 0.3])
            zone = framing.safe_zone(safe)
            for e in p.elements:
                if e.role.startswith("cam"):
                    assert e.dest[1] >= zone["top"] and e.dest[0] >= zone["left"], (preset, safe)
                    assert e.dest[0] + e.dest[2] <= 1080 - zone["right"] or preset == "dual_cam", (preset, safe)
    assert _plan("circle_cam").element("cam").shape == "circle"


# ---- the streamer's face -----------------------------------------------------------------


# Measured on a hero-shooter stream: the webcam's top border at 0.268 of the
# frame height, the streamer's head top at 0.288, head centre 0.361. Rendered
# with the webcam band on top, the head landed 2-26 px from the top of the
# Short, under TikTok's top bar.
HIGH_CAM = (0.0396, 0.270, 0.1417, 0.243)
HIGH_HEAD = (0.11 * W, 0.288 * H, 0.41 * H)


@pytest.mark.parametrize("preset", ["split", "half", "small_cam", "circle_cam"])
def test_a_streamer_high_in_their_webcam_keeps_their_head_below_the_top_bar(preset):
    p = _plan(preset, cam=HIGH_CAM, heads={"cam": HIGH_HEAD})
    e = p.element("cam")
    top, _chin = framing.head_on_canvas(HIGH_HEAD, e.src, e.dest, e.shift)
    assert top >= TIKTOK["top"] - 1
    assert framing.face_clear(HIGH_HEAD, e.src, e.dest, e.shift, TIKTOK)["top"]


def test_the_picture_moves_down_only_when_the_webcam_has_no_room_above_the_head():
    roomy = (0.0, 0.1, 0.3, 0.5)
    head = (0.15 * W, 0.3 * H, 0.45 * H)                  # plenty of webcam above the head
    assert _plan("split", cam=roomy, heads={"cam": head}).element("cam").shift == 0
    assert _plan("split", cam=HIGH_CAM, heads={"cam": HIGH_HEAD}).element("cam").shift > 0


@pytest.mark.parametrize(("where", "head"), [
    ("top", (0.15, 0.13, 0.25)), ("bottom", (0.15, 0.3, 0.42)), ("left", (0.05, 0.2, 0.32)),
    ("right", (0.25, 0.2, 0.32)), ("centre", (0.15, 0.2, 0.32)),
])
def test_the_face_stays_in_its_band_wherever_it_sits_in_the_webcam(where, head):
    cam = (0.0, 0.05, 0.3, 0.4)
    h = (head[0] * W, head[1] * H, head[2] * H)
    for order in ("cam_top", "game_top"):
        e = _plan("split", cam=cam, heads={"cam": h}, order=order).element("cam")
        top, chin = framing.head_on_canvas(h, e.src, e.dest, e.shift)
        x_on_canvas = e.dest[0] + (h[0] - e.src[0]) * e.dest[2] / e.src[2]
        assert e.dest[1] <= top and top < chin, (where, order)
        assert e.dest[0] < x_on_canvas < e.dest[0] + e.dest[2], (where, order)
        if order == "cam_top":
            assert top >= TIKTOK["top"] - 1, where


def test_with_no_head_to_go_on_the_crop_is_centred():
    e = _plan("split", cam=(0.1, 0.1, 0.2, 0.4)).element("cam")
    sx, sy, sw, sh = e.src
    assert abs((sx + sw / 2) - 0.2 * W) <= 2 and abs((sy + sh / 2) - 0.3 * H) <= 2 and e.shift == 0


def test_a_face_under_the_caption_area_is_flagged():
    """A small webcam scaled up into a bottom band can put the chin under
    TikTok's captions; the editor shows it rather than hiding it."""
    e = _plan("basecam", cam=HIGH_CAM, heads={"cam": HIGH_HEAD}).element("cam")
    assert framing.face_clear(HIGH_HEAD, e.src, e.dest, e.shift, TIKTOK)["bottom"] is False


def test_nothing_in_the_layout_or_framing_reads_motion_or_pixels():
    """The old failure was choosing the region that moved most (chat). Layout
    and framing are geometry only."""
    for name in ("layout.py", "framing.py"):
        src = (ROOT / "gaming" / name).read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""|#.*', "", src, flags=re.S)
        for banned in ("np.", "cv2", "diff(", "std(", "activity", "motion", "video_capture"):
            assert banned not in code, (name, banned)


# ---- the render ---------------------------------------------------------------------------


def test_the_graph_places_every_element_at_its_region():
    from gaming import compose

    p = _plan("split", game_fit="fit", heads={"cam": (0.12 * W, 0.02 * H, 0.2 * H)})
    graph = compose.filter_graph(p)
    for e in p.elements:
        assert f"overlay={e.dest[0]}:{e.dest[1]}" in graph
    assert "overlay=(W-w)/2:H-h" in graph                        # whole game against the bottom edge
    circle = compose.filter_graph(_plan("circle_cam"))
    assert "geq=" in circle and "hypot(X-W/2,Y-H/2)" in circle
    zoom = compose.filter_graph(_plan("fullscreen", cam=None, game_fit="fill"), vf_extra="eq=saturation=1.1",
                                ass_name="c.ass")
    assert zoom.endswith(";[v]eq=saturation=1.1[v];[v]subtitles=c.ass[v]")


def _ffmpeg_or_skip() -> str:
    from core.binaries import ffmpeg

    binary = ffmpeg()
    try:
        subprocess.run([binary, "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("FFmpeg isn't available")
    return binary


@pytest.fixture
def stream(tmp_path):
    """A 1080p "stream": blue game, red webcam top-left, green chat down the right edge."""
    pytest.importorskip("cv2")
    source = tmp_path / "stream.mp4"
    subprocess.run([_ffmpeg_or_skip(), "-v", "error",
                    "-f", "lavfi", "-i", ",".join(["color=c=blue:s=1920x1080:r=30:d=2",
                                                   "drawbox=x=0:y=0:w=480:h=360:color=red:t=fill",
                                                   "drawbox=x=1720:y=0:w=200:h=1080:color=green:t=fill"]),
                    "-f", "lavfi", "-i", "sine=frequency=440:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)],
                   check=True)
    return source


def _render(stream, tmp_path, p):
    import cv2

    from gaming import compose

    out = compose.render(stream, tmp_path / f"{p.preset}.mp4", p)
    cap = cv2.VideoCapture(str(out))
    cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
    ok, frame = cap.read()
    cap.release()
    assert ok and frame.shape[:2] == (1920, 1080)
    return frame


def _share(region, channel):
    """Share of pixels where one BGR channel clearly dominates."""
    import numpy as np

    others = [c for c in range(3) if c != channel]
    return float(np.mean((region[..., channel] > 150) & (region[..., others].max(axis=-1) < 90)))


def test_a_real_camera_top_split(stream, tmp_path):
    frame = _render(stream, tmp_path, _plan("split", game_fit="fill"))
    cam_h = _plan("split").element("cam").dest[3]
    assert _share(frame[:cam_h], 2) > 0.9                     # the webcam band is the webcam
    game = frame[cam_h:]
    assert _share(game, 0) > 0.9 and _share(game, 1) < 0.01 and _share(game, 2) < 0.01


def test_a_real_game_top_with_the_whole_game_starts_at_the_top_of_the_short(stream, tmp_path):
    p = _plan("basecam", game_fit="fit")
    frame = _render(stream, tmp_path, p)
    assert _share(frame[:40], 0) > 0.6                        # the game itself, not a blur, at y=0
    cam = p.element("cam").dest
    assert _share(frame[cam[1]:], 2) > 0.9                    # the webcam at the bottom


def test_a_real_camera_top_with_the_whole_game_ends_at_the_bottom_of_the_short(stream, tmp_path):
    frame = _render(stream, tmp_path, _plan("split", game_fit="fit"))
    assert _share(frame[-40:], 0) > 0.6                       # the game reaches the bottom edge


def test_a_real_circle_facecam_shows_the_game_in_its_corners(stream, tmp_path):
    p = _plan("circle_cam")
    frame = _render(stream, tmp_path, p)
    x, y, w, h = p.element("cam").dest
    assert _share(frame[y + h // 2 - 20:y + h // 2 + 20, x + w // 2 - 20:x + w // 2 + 20], 2) > 0.8   # centre: webcam
    assert _share(frame[y:y + 20, x:x + 20], 0) > 0.8                                                  # corner: game


def test_a_real_blurred_layout_has_no_black_bars(stream, tmp_path):
    frame = _render(stream, tmp_path, _plan("blurred", cam=None))
    assert float(frame[:200].max(axis=-1).mean()) > 40 and float(frame[-200:].max(axis=-1).mean()) > 40


def test_blurred_and_fullscreen_decide_how_the_game_is_shown():
    """They ARE the game whole on a blur and the game zoomed: the Whole / Zoom
    switch (set for another layout) doesn't turn one into the other."""
    assert _plan("blurred", cam=None, game_fit="fill").element("game").fit == "contain"
    assert _plan("fullscreen", cam=None, game_fit="fit").element("game").fit == "cover"
