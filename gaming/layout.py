"""Where each part of a gaming clip comes from and goes. Pure geometry, no pixels.

A layout (a preset in layouts.json) places ELEMENTS on the 1080x1920 canvas:
the streamer's webcam ("cam", and "cam2" for a duo), the game ("game") and a
piece of the game's own UI ("ui": a scoreboard, a kill feed, a speedrun
timer). Each element goes through the same steps:

    canvas -> the region it is assigned -> the source's shape ->
    crop / scale / letterbox -> position

- cover:   the source is cropped to the region's shape and fills it; never
           stretched.
- contain: the whole source box is shown, as big as fits, ANCHORED to the
           region's outer edge (a game on top starts at the top of the Short,
           one at the bottom ends at its bottom), and a blur of it fills the
           rest of that region only. Only the Blurred layout, which is the
           game alone, sits in the middle.

Preset types:
- stack: rows from top to bottom (webcam band, game band, maybe a UI strip),
         the webcam band's height set by the divider; "order" puts the game
         on top instead.
- full:  the game alone (Fullscreen: zoomed to fill; Blurred: whole on a blur).
- pip:   the game fills the Short and the webcam sits over it near the top,
         inside the platforms' safe zone (Small facecam, Circle facecam, Dual).

The game region is never DETECTED: the old attempts looked for the part of
the screen with the most going on, and scrolling chat won every time. It is
the user's drawn box, or a fixed crop that only moves to leave out a known
webcam. Nothing here reads motion, activity or pixel values.
"""

from dataclasses import dataclass, field

from gaming import framing

LAYOUTS = framing.LAYOUTS
PRESETS: dict = LAYOUTS["presets"]
OUT_W, OUT_H = LAYOUTS["canvas"]
ALIGNS = ("left", "center", "right")
ORDERS = ("cam_top", "game_top")
FITS = ("fit", "fill")
PIP_GAP = 24               # px between two picture-in-picture webcams
PIP_MARGIN = 0.02          # of the canvas height, below the safe zone's top


@dataclass(frozen=True)
class Element:
    role: str                      # cam | cam2 | game | ui
    src: tuple                     # source crop (x, y, w, h) px
    dest: tuple                    # its region on the canvas (x, y, w, h) px
    fit: str = "cover"             # cover | contain
    anchor: str = "center"         # contain: top | bottom | center
    shift: int = 0                 # cover: picture moved down this far (face clear of the UI)
    shape: str = "rect"            # rect | circle


@dataclass(frozen=True)
class Plan:
    preset: str
    elements: tuple = field(default_factory=tuple)
    order: str = "cam_top"
    safe: str = "tiktok"

    def element(self, role: str) -> Element | None:
        return next((e for e in self.elements if e.role == role), None)

    @property
    def kind(self) -> str:
        """"split" when a webcam is shown, "fill" for the game alone."""
        return "split" if self.element("cam") else "fill"


def _even(v: float) -> int:
    """An even size of at least 2 (FFmpeg's crop and scale want even sizes)."""
    return max(2, int(v) // 2 * 2)


def _pos(v: float) -> int:
    """An even position, which can be 0: the frame's own edge."""
    return max(0, int(v) // 2 * 2)


def _clamp_box(box_norm, src_w: int, src_h: int) -> tuple:
    """A normalized (x, y, w, h) box as even source pixels, inside the frame."""
    x, y, w, h = box_norm
    x0 = min(max(0.0, x), 1.0) * src_w
    y0 = min(max(0.0, y), 1.0) * src_h
    x1 = min(max(x + w, 0.0), 1.0) * src_w
    y1 = min(max(y + h, 0.0), 1.0) * src_h
    return (_pos(x0), _pos(y0), _even(max(2.0, x1 - x0)), _even(max(2.0, y1 - y0)))


def _aligned(src_w: int, crop_w: int, align: str) -> int:
    if align == "left":
        return 0
    if align == "right":
        return src_w - crop_w
    return _pos((src_w - crop_w) / 2)


def _clear_of(src_w: int, crop_w: int, cams: list) -> int:
    """The x for a full-height crop that overlaps the webcam boxes least,
    nearest the centre among equals. Exclusion of KNOWN boxes, not a search
    for anything interesting."""
    centre = (src_w - crop_w) / 2
    best, best_key = 0, None
    for x in range(0, src_w - crop_w + 1, 2):
        overlap = sum(max(0, min(x + crop_w, c[0] + c[2]) - max(x, c[0])) for c in cams)
        key = (overlap, abs(x - centre))
        if best_key is None or key < best_key:
            best, best_key = x, key
    return best


def _cover(box: tuple, aspect: float) -> tuple:
    """The largest crop of an (x, y, w, h) pixel box at `aspect`, centred in it."""
    x, y, w, h = box
    if w / h > aspect:
        cw = _even(h * aspect)
        return (_pos(x + (w - cw) / 2), y, cw, h)
    ch = _even(w / aspect)
    return (x, _pos(y + (h - ch) / 2), w, ch)


def _shown(box: tuple, aspect: float) -> float:
    """The area a box covers when fitted whole into a region of this aspect
    (region height 1): how big the game ends up on screen."""
    w, h = box[2], box[3]
    scale = min(aspect / w, 1.0 / h)
    return w * h * scale * scale


def _beside(src_w: int, src_h: int, cam: tuple, aspect: float) -> tuple:
    """The strip of the frame beside the webcam (left, right, above or below
    it, full length) that shows biggest when fitted into the region."""
    cx, cy, cw, ch = cam
    strips = [
        (0, 0, cx, src_h),
        (cx + cw, 0, src_w - cx - cw, src_h),
        (0, 0, src_w, cy),
        (0, cy + ch, src_w, src_h - cy - ch),
    ]
    strips = [s for s in strips if s[2] >= 0.2 * src_w and s[3] >= 0.2 * src_h]
    if not strips:
        return (0, 0, _even(src_w), _even(src_h))
    x, y, w, h = max(strips, key=lambda s: _shown(s, aspect))
    return (_pos(x), _pos(y), _even(w), _even(h))


def resolve(settings: dict) -> dict:
    """A clip's gaming settings with a preset that can actually be drawn.

    Settings from before layouts existed (cam_position / game_fit, no preset)
    become Half, which is what they rendered as. A layout that needs a box it
    doesn't have falls back: no webcam -> the game alone (Blurred, or
    Fullscreen if it was zoomed), no Game UI box -> Split, no second webcam ->
    the one-webcam version."""
    s = dict(settings or {})
    preset = s.get("preset")
    if preset not in PRESETS:
        preset = "half"
        s.setdefault("order", "game_top" if s.get("cam_position") == "bottom" else "cam_top")
        s.setdefault("game_fit", s.get("game_fit") or "fit")
    spec = PRESETS[preset]
    roles = {r for row in spec.get("rows", []) for r in row} | set(spec.get("cams", []))
    if "cam" in roles and not s.get("cam"):
        # No webcam: the game alone, whole on a blur. (Fullscreen is its own
        # choice; a zoomed 9:16 cut of a wide game loses most of it.)
        preset = "blurred"
    elif "ui" in roles and not s.get("ui_box"):
        preset = "split"
    elif "cam2" in roles and not s.get("cam2"):
        preset = {"dual_cam": "small_cam", "duo_split": "split"}.get(preset, preset)
    s["preset"] = preset
    return s


def _stack_regions(spec: dict, order: str, divider: float) -> list:
    """[(role, dest, anchor)] for a stack preset, top to bottom."""
    rows = [list(r) for r in spec["rows"]]
    if order == "game_top":
        rows.reverse()
    lo, hi, default = spec["divider"]
    cam_h = OUT_H * min(max(divider if divider is not None else default, lo), hi)
    heights = []
    for row in rows:
        if "game" in row:
            heights.append(None)
        elif "ui" in row and len(row) == 1:
            heights.append(OUT_H * spec.get("ui_share", 0.12))
        else:
            heights.append(cam_h)
    rest = OUT_H - sum(h for h in heights if h is not None)
    heights = [rest if h is None else h for h in heights]
    # Row edges rounded once, so rows meet exactly and the last one ends at
    # the bottom of the canvas.
    edges = [0]
    for h in heights[:-1]:
        edges.append(_pos(edges[-1] + h))
    edges.append(OUT_H)
    out = []
    for i, row in enumerate(rows):
        anchor = "top" if i == 0 else "bottom" if i == len(rows) - 1 else "center"
        cols = [_pos(j * OUT_W / len(row)) for j in range(len(row))] + [OUT_W]
        for j, role in enumerate(row):
            out.append((role, (cols[j], edges[i], cols[j + 1] - cols[j], edges[i + 1] - edges[i]), anchor))
    return out


def _pip_regions(spec: dict, safe: dict) -> list:
    cams = spec["cams"]
    w = _even(OUT_W * spec["pip_width"])
    h = _even(w / spec["pip_aspect"])
    y = _pos(safe["top"] + PIP_MARGIN * OUT_H)
    total = len(cams) * w + (len(cams) - 1) * PIP_GAP
    x0 = (OUT_W - total) / 2
    return [(role, (_pos(x0 + i * (w + PIP_GAP)), y, w, h)) for i, role in enumerate(cams)]


def _game_src(src_w: int, src_h: int, s: dict, dest: tuple, fit: str, cams: list) -> tuple:
    """The part of the frame the game element shows."""
    aspect = dest[2] / dest[3]
    if s.get("game_box"):
        region = _clamp_box(s["game_box"], src_w, src_h)
        return region if fit == "fit" else _cover(region, aspect)
    if fit == "fit":
        return (0, 0, _even(src_w), _even(src_h)) if not cams else _beside(src_w, src_h, cams[0], aspect)
    crop_w = min(src_w, _even(src_h * aspect))
    align = s.get("game_align") if s.get("game_align") in ALIGNS else "center"
    x = _clear_of(src_w, crop_w, cams) if (cams and align == "center") else _aligned(src_w, crop_w, align)
    crop_h = min(src_h, _even(crop_w / aspect)) if crop_w == src_w else _even(src_h)
    return (_pos(x), _pos((src_h - crop_h) / 2), crop_w, crop_h)


def plan(src_w: int, src_h: int, settings: dict, heads: dict | None = None) -> Plan:
    """The layout for one clip.

    settings: a clip's gaming settings (gaming/run.py lists the keys):
      preset, order, divider, safe, game_fit, game_align, and the normalized
      boxes cam, cam2, game_box, ui_box.
    heads: {"cam": (centre x, top, chin), ...} in source px, the streamer's
      head inside each webcam, for face-safe framing (gaming/framing.py).
    """
    s = resolve(settings)
    preset = s["preset"]
    spec = PRESETS[preset]
    order = s.get("order") if s.get("order") in ORDERS else spec.get("order", "cam_top")
    safe_name = s.get("safe") if s.get("safe") in framing.SAFE_ZONES else "tiktok"
    safe = framing.safe_zone(safe_name)
    # Blurred and Fullscreen ARE the game shown whole or zoomed: the layout
    # decides, not the Whole / Zoom switch.
    fit = spec["game_fit"] if spec["type"] == "full" else (
        s.get("game_fit") if s.get("game_fit") in FITS else spec.get("game_fit", "fill"))
    heads = heads or {}
    cam_boxes = {role: _clamp_box(s[role], src_w, src_h) for role in ("cam", "cam2") if s.get(role)}
    shown_cams = [cam_boxes[r] for r in cam_boxes]

    elements = []

    def camera(role: str, dest: tuple, shape: str = "rect") -> None:
        crop, shift = framing.cam_crop(cam_boxes[role], heads.get(role), dest, safe)
        elements.append(Element(role, crop, dest, "cover", "center", shift, shape))

    def game(dest: tuple, anchor: str) -> None:
        src = _game_src(src_w, src_h, s, dest, fit, shown_cams)
        elements.append(Element("game", src, dest, "contain" if fit == "fit" else "cover", anchor))

    if spec["type"] == "full":
        game((0, 0, OUT_W, OUT_H), "center")
    elif spec["type"] == "pip":
        game((0, 0, OUT_W, OUT_H), "center")
        for role, dest in _pip_regions(spec, safe):
            camera(role, dest, spec.get("shape", "rect"))
    else:
        for role, dest, anchor in _stack_regions(spec, order, s.get("divider")):
            if role == "game":
                game(dest, anchor)
            elif role == "ui":
                ui = _clamp_box(s["ui_box"], src_w, src_h)
                elements.append(Element("ui", ui, dest, "contain", "center"))
            else:
                camera(role, dest)
    return Plan(preset, tuple(elements), order, safe_name)
