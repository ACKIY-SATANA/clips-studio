"""The score bug, read: the scoreboard is ground truth.

A broadcast keeps the score and the match clock in a small box, usually along
the top. When the score changes, a goal went in shortly before; the clock says
which half a moment is in. HypeCut's broadcast profile puts it plainly: "the
scoreboard is ground truth, not a proxy."

Cost, measured on a 1 h 42 min 1080p final:
- Finding the box needs OCR's text search on whole bands of a few frames:
  about 1.5 s a band, so it stops as soon as five frames agree.
- Reading it then needs no search at all. One ffmpeg pass decodes only the
  keyframes (every few seconds) cropped to the box: 1,510 crops in 19 s.
  Each is read as a single line by the recogniser alone: about 16 ms, against
  a second for a full OCR.
It uses the OCR the app already ships for games (RapidOCR, analysis/game_text.py).

Nothing is guessed. A score counts only when two readings in a row agree, a
change of more than one goal at once is left to the other signals, and a video
with no readable score bug (sideline footage, a stream) is scored without it.
"""

import re
import subprocess
import threading
from collections import Counter
from dataclasses import dataclass, field

# Team code, score, team code, as the recogniser reads a bug's line:
#   "HOM 1-0 AWO", "(> HOM  1: 0 AW0  26:47", "(HOM1:1AW037:37", "(HOM4·2|AW069:17".
# A 0 inside a team code is an O ("AW0" is AWO); the codes may touch the
# score and the clock may follow straight on.
TEAMS_SCORE = re.compile(
    r"(?<![A-Z0-9])([A-Z][A-Z0]{1,3})[\s|:·.,>(]*?(\d{1,2})\s*[-–:·.|]?\s*(\d{1,2})[\s|:·.,)]*([A-Z0][A-Z0]{1,3})(?![A-Z])")
# Without team codes, only a dash counts: "1 - 0". A clock's colon never does.
DASH_SCORE = re.compile(r"(?<![\d:])(\d{1,2})\s*[-–]\s*(\d{1,2})(?![\d:])")
# ffmpeg's showinfo line for each frame it passes on, with the frame's time.
PTS_TIME = re.compile(r"pts_time:\s*(-?\d+(?:\.\d+)?)")
O_AFTER = re.compile(r"(?<=\d)(\s*[:\-–·.|]\s*)[Oo](?![A-Za-z])")
O_BEFORE = re.compile(r"(?<![A-Za-z])[Oo](\s*[:\-–·.|]\s*)(?=\d)")
CLOCK = re.compile(r"(?<!\d)(\d{1,3})[:.'](\d{2})(?!\d)")

FIND_FRAMES = 14         # most frames looked at, spread through the match, to find the box
FOUND_AFTER = 5          # ...stopping once this many agree
FOUND_IN = 3             # the fewest frames the box must be seen in
BANDS = ((0.0, 0.0, 1.0, 0.22), (0.0, 0.78, 1.0, 1.0))   # (left, top, right, bottom): top, bottom
READ_WIDTH = 480         # a band is resized to this width for the text search
SAME_RUN = 0.04          # a gap this wide (share of the band's width) still joins text into one run
CLOCK_GAP = 8.0          # ...and the clock joins the score from up to this many text heights away
MIN_CONFIDENCE = 0.5
EVERY = 10.0             # seconds between readings when frames have to be sought one by one
GOAL_LOOKBACK = 180.0    # a bug updates after the celebration and replays: the
                         # goal itself can be this long before the new score shows

_rec_engine = None


@dataclass
class Reading:
    t: float
    score: tuple | None = None       # (home, away)
    teams: tuple | None = None       # ("HOM", "AWO"), when the bug names them
    minute: int | None = None        # the match clock's minutes
    clock: int | None = None         # ...and the whole clock, in seconds
    visible: bool = False            # anything was read in the box at all
    text: str = ""                   # what was read, for a second look once the teams are known


@dataclass
class ScoreChange:
    lo: float                        # the goal went in between lo and hi
    hi: float
    before: tuple
    after: tuple
    team: str = ""                   # the side whose number went up, when named

    def label(self) -> str:
        who = f" ({self.team})" if self.team else ""
        return f"score {self.after[0]}-{self.after[1]}{who}"


@dataclass
class Scoreboard:
    box: tuple | None = None                      # (left, top, right, bottom), frame fractions
    readings: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    halftime: float | None = None                 # when the second half starts (video time)

    def final(self) -> tuple | None:
        for r in reversed(self.readings):
            if r.score is not None:
                return r.score
        return None

    def teams(self) -> tuple | None:
        for r in self.readings:
            if r.teams:
                return r.teams
        return None

    def period_at(self, t: float) -> str:
        """first_half, second_half, extra_time, or "" when the clock wasn't read."""
        minutes = [(r.t, r.minute) for r in self.readings if r.minute is not None]
        if not minutes:
            return ""
        near = min(minutes, key=lambda x: abs(x[0] - t))
        if abs(near[0] - t) > 300:
            return ""
        if near[1] >= 95 and any(m >= 105 for _, m in minutes):
            return "extra_time"
        if self.halftime is not None:
            return "first_half" if t < self.halftime else "second_half"
        return "first_half" if near[1] < 45 else "second_half"

    def minute_at(self, t: float) -> int | None:
        """The match minute at video time t the way a match report gives it
        (17:23 on the clock is the 18th minute). The clock runs with the
        video, so each reading within two minutes (in the same half) says how
        far ahead of the video it is, and the median of those says it best: a
        single reading can be a misread digit, seconds out. None when the
        clock wasn't read there."""
        half = None if self.halftime is None else t >= self.halftime
        ahead = sorted(r.clock - r.t for r in self.readings
                       if r.clock is not None and abs(r.t - t) <= 120
                       and (half is None or (r.t >= self.halftime) == half))
        if not ahead:
            return None
        return int(max(0.0, t + ahead[len(ahead) // 2]) // 60) + 1

    def hidden(self, lo: float, hi: float) -> bool:
        """Whether the bug was off screen for most readings in [lo, hi]: the
        broadcast hides it for replays and celebrations."""
        inside = [r for r in self.readings if lo <= r.t <= hi]
        return bool(inside) and sum(not r.visible for r in inside) > len(inside) / 2


def parse(texts: list[str]) -> Reading:
    """What a bug's text says: the score, the teams and the clock."""
    line = " ".join(" ".join(str(t).split()) for t in texts)
    # A 0 read as the letter O beside a score's separator ("1:O", "O-2"): soft
    # text (a phone filming a screen, an upscaled frame) reads it that way.
    line = O_AFTER.sub(r"\g<1>0", line)
    line = O_BEFORE.sub(r"0\g<1>", line)
    out = Reading(t=0.0, visible=bool(line.strip()), text=line)
    upper = line.upper()
    rest = line
    m = TEAMS_SCORE.search(upper)
    if m:
        out.teams = (m.group(1).replace("0", "O"), m.group(4).replace("0", "O"))
        out.score = (int(m.group(2)), int(m.group(3)))
        rest = line[m.end():]
    else:
        d = DASH_SCORE.search(line)
        if d:
            out.score = (int(d.group(1)), int(d.group(2)))
    c = CLOCK.search(rest)
    if c and int(c.group(2)) < 60 and int(c.group(1)) < 130:
        out.minute = int(c.group(1))
        out.clock = out.minute * 60 + int(c.group(2))
    return out


# ---- finding the box ---------------------------------------------------------------


def _texts(img, ocr) -> list[tuple[tuple, str]]:
    """(box in the image's fractions, text) for each line the full OCR finds."""
    import cv2

    h, w = img.shape[:2]
    scale = READ_WIDTH / max(w, 1)
    img = cv2.resize(img, (READ_WIDTH, max(2, round(h * scale))), interpolation=cv2.INTER_LINEAR)
    height, width = img.shape[:2]
    out = []
    for box, text, conf in ocr(img) or []:
        if float(conf) < MIN_CONFIDENCE:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append(((min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height), str(text)))
    return out


def _crop(img, box):
    h, w = img.shape[:2]
    left, top, right, bottom = box
    return img[int(h * top):max(int(h * top) + 2, int(h * bottom)),
               int(w * left):max(int(w * left) + 2, int(w * right))]


def _score_lines(lines: list[tuple[tuple, str]], aspect: float) -> list[tuple[tuple, str]]:
    """The bug's own lines among everything read in a band: the run of text
    on one row, with no wide gap in it, that reads as a score. A band holds
    more than the bug (ad boards, a stadium's banners), and far more of it
    in a portrait frame, where the same share of the height is a tall strip
    of stadium. `aspect`: the band's height over its width, to measure a gap
    against the text's height. [] when no run reads as a score."""
    rows: list[dict] = []
    for box, text in sorted(lines, key=lambda x: (x[0][1] + x[0][3]) / 2):
        mid = (box[1] + box[3]) / 2
        row = next((r for r in rows if r["top"] <= mid <= r["bottom"]), None)
        if row is None:
            rows.append({"top": box[1], "bottom": box[3], "lines": [(box, text)]})
        else:
            row["lines"].append((box, text))
            row["top"], row["bottom"] = min(row["top"], box[1]), max(row["bottom"], box[3])
    for row in rows:
        # The row's height in the width's units.
        height = max(row["bottom"] - row["top"], 1e-6) * aspect
        runs: list[list] = []
        for box, text in sorted(row["lines"], key=lambda x: x[0][0]):
            # A gap wider than a few characters starts another run: the bug
            # is one tight line, anything else on its row stands apart.
            if runs and box[0] - runs[-1][-1][0][2] <= max(3 * height, SAME_RUN):
                runs[-1].append((box, text))
            else:
                runs.append([(box, text)])
        for i, run in enumerate(runs):
            if parse([" ".join(t for _, t in run)]).score is not None:
                # The match clock often stands a little apart in the box
                # ("AWO     15:07"): the nearest run on the row that is a clock
                # belongs to it.
                clocks = [other for other in runs[:i] + runs[i + 1:]
                          if CLOCK.search(" ".join(t for _, t in other))
                          and _gap(run, other) <= CLOCK_GAP * height]
                if clocks:
                    run = sorted(run + min(clocks, key=lambda other: _gap(run, other)),
                                 key=lambda x: x[0][0])
                return run
    return []


def _gap(a: list, b: list) -> float:
    """The horizontal space between two runs of text boxes."""
    return max(0.0, max(min(x[0][0] for x in b) - max(x[0][2] for x in a),
                        min(x[0][0] for x in a) - max(x[0][2] for x in b)))


def find_box(grab, duration: float, ocr, frames: int = FIND_FRAMES) -> tuple | None:
    """Where the score bug is: the run of text in the top or bottom band
    where a score shows up on the sampled frames. None when fewer than
    FOUND_IN show one."""
    seen: list[tuple] = []
    for i in range(frames):
        img = grab(duration * (i + 1) / (frames + 1))
        if img is None:
            continue
        for band in BANDS:
            strip = _crop(img, band)
            lines = _score_lines(_texts(strip, ocr), strip.shape[0] / max(strip.shape[1], 1))
            if not lines:
                continue
            # The bug, in whole-frame fractions.
            bl, bt, br, bb = band
            boxes = [(bl + x0 * (br - bl), bt + y0 * (bb - bt), bl + x1 * (br - bl), bt + y1 * (bb - bt))
                     for (x0, y0, x1, y1), _ in lines]
            seen.append((min(b[0] for b in boxes), min(b[1] for b in boxes),
                         max(b[2] for b in boxes), max(b[3] for b in boxes)))
            break
        if len(seen) >= FOUND_AFTER:
            break
    if len(seen) < FOUND_IN:
        return None
    # The box most frames agree on: sorted by position, the middle one. A
    # one-off graphic (a scorer's full-width caption) sorts to an end.
    seen.sort(key=lambda b: ((b[1] + b[3]) / 2, (b[0] + b[2]) / 2))
    left, top, right, bottom = seen[len(seen) // 2]
    pad_x, pad_y = (right - left) * 0.08, (bottom - top) * 0.25
    return (max(0.0, left - pad_x), max(0.0, top - pad_y), min(1.0, right + pad_x), min(1.0, bottom + pad_y))


# ---- reading it ---------------------------------------------------------------------


def rec_line(img) -> str:
    """The box read as one line by the recogniser alone (no text search)."""
    global _rec_engine
    import cv2

    if _rec_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _rec_engine = RapidOCR()
    h, w = img.shape[:2]
    if h < 64:
        img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    result, _elapsed = _rec_engine(img, use_det=False, use_cls=False, use_rec=True)
    if not result:
        return ""
    first = result[0]
    return str(first[0] if isinstance(first, (list, tuple)) else first)


def from_readings(readings: list[Reading], box: tuple | None = None) -> Scoreboard:
    readings = sorted(readings, key=lambda r: r.t)
    teams = known_teams(readings)
    if teams is not None:
        for r in readings:
            with_known_teams(r, teams)
    board = Scoreboard(box=box, readings=readings)
    board.changes = changes(board.readings)
    board.halftime = second_half_start(board.readings)
    return board


def known_teams(readings: list[Reading]) -> tuple | None:
    """The two team codes the box shows: the pair most readings agree on, a
    code with a letter too many in front (the flag beside it, read as "D"
    or ">") taken as the code it ends in when that is read too."""
    pairs = Counter(r.teams for r in readings if r.teams)
    if not pairs:
        return None
    seen = Counter()
    for pair, n in pairs.items():
        for code in pair:
            seen[code] += n

    def plain(code: str) -> str:
        return next((other for other in sorted(seen, key=len)
                     if other != code and len(other) >= 3 and code.endswith(other) and seen[other] >= 2), code)

    merged = Counter()
    for (a, b), n in pairs.items():
        merged[(plain(a), plain(b))] += n
    a, b = merged.most_common(1)[0][0]
    return (a, b) if a != b else None


# The recogniser's letters for digits, where a score is known to be.
AS_DIGITS = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "i": "1"})


def with_known_teams(r: Reading, teams: tuple) -> None:
    """A reading put right once the teams are known: their codes as the box
    writes them, and a score read from between the two codes when the parse
    missed it. Soft text loses the separator and reads 0 as a letter: in
    "HOMOOAW0" the score is the "OO"."""
    if r.teams:
        r.teams = teams
    if r.score is not None or not r.text:
        return
    upper = r.text.upper().replace("0", "O")
    first, second = (code.replace("0", "O") for code in teams)
    i = upper.find(first)
    j = upper.find(second, i + len(first)) if i >= 0 else -1
    if i < 0 or j < 0:
        return
    groups = re.findall(r"\d+", upper[i + len(first):j].translate(AS_DIGITS))
    if len(groups) == 1 and len(groups[0]) == 2:
        groups = [groups[0][0], groups[0][1]]         # "OO": two scores, their separator lost
    if len(groups) == 2 and all(len(g) <= 2 for g in groups):
        r.score = (int(groups[0]), int(groups[1]))
        r.teams = teams


def changes(readings: list[Reading]) -> list[ScoreChange]:
    """Confirmed goals: the score going up by one, seen on two readings in a
    row. Dated from GOAL_LOOKBACK before the new score (or the last reading of
    the old one, if earlier) to the first reading of the new one."""
    scored = [r for r in readings if r.score is not None]
    out: list[ScoreChange] = []
    current: tuple | None = None
    last_old_t = 0.0
    for i, r in enumerate(scored):
        if current is None:
            if i + 1 < len(scored) and scored[i + 1].score == r.score:
                current, last_old_t = r.score, r.t
            continue
        if r.score == current:
            last_old_t = r.t
            continue
        confirmed = i + 1 < len(scored) and scored[i + 1].score == r.score
        if not confirmed:
            continue                                  # a misread: the next reading decides
        one_goal = sum(r.score) == sum(current) + 1 and all(n >= o for n, o in zip(r.score, current))
        if one_goal:
            side = 0 if r.score[0] > current[0] else 1
            teams = r.teams or next((x.teams for x in scored if x.teams), None)
            out.append(ScoreChange(lo=max(0.0, min(last_old_t, r.t - GOAL_LOOKBACK)), hi=r.t,
                                   before=current, after=r.score, team=teams[side] if teams else ""))
        # Anything else (two goals at once, a goal taken back) is followed
        # without being called a goal.
        current, last_old_t = r.score, r.t
    return out


def second_half_start(readings: list[Reading]) -> float | None:
    """When the second half starts: the first reading of minute 46-59, after a
    reading of 45 or earlier."""
    seen_first = False
    for r in readings:
        if r.minute is None:
            continue
        if r.minute <= 45:
            seen_first = True
        elif seen_first and 45 < r.minute < 60:
            return r.t
    return None


def read(grab, duration: float, find_ocr=None, rec=None, every: float = EVERY, cancel=None) -> Scoreboard:
    """The match's scoreboard, seeking a frame every `every` seconds. `grab`
    (seconds -> frame), `find_ocr` and `rec` stand in for the video and the
    OCR in tests; read_video() is the fast path for a file."""
    if find_ocr is None:
        from analysis.game_text import _ocr as find_ocr
    rec = rec or rec_line
    box = find_box(grab, duration, find_ocr)
    if box is None:
        return Scoreboard()
    readings = []
    t = 0.0
    while t < duration:
        if cancel is not None:
            cancel()
        img = grab(t)
        if img is not None:
            r = parse([rec(_crop(img, box))])
            r.t = t
            readings.append(r)
        t += every
    return from_readings(readings, box)


def _keyframe_crops(path, box: tuple, size: tuple[int, int], on_frame, cancel=None) -> list[float]:
    """Decode only the keyframes, cropped to `box`, calling on_frame(index,
    image) for each; returns each frame's time. One pass over the file."""
    import numpy as np

    from core.binaries import ffmpeg

    width, height = size
    x, y = int(width * box[0]) // 2 * 2, int(height * box[1]) // 2 * 2
    w = max(2, int(width * (box[2] - box[0])) // 2 * 2)
    h = max(2, int(height * (box[3] - box[1])) // 2 * 2)
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "info", "-skip_frame", "nokey", "-i", str(path), "-an",
           "-vf", f"crop={w}:{h}:{x}:{y},showinfo", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    times: list[float] = []

    def drain(stream) -> None:
        for raw in stream:
            found = PTS_TIME.search(raw.decode("utf-8", "ignore"))
            if found:
                times.append(float(found.group(1)))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    reader = threading.Thread(target=drain, args=(proc.stderr,), daemon=True)
    reader.start()
    frame_bytes = w * h * 3
    index = 0
    try:
        while True:
            if cancel is not None:
                cancel()
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            on_frame(index, np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3))
            index += 1
    finally:
        proc.stdout.close()
        proc.wait()
        reader.join(timeout=10)
    return times


def read_video(path, duration: float, cancel=None) -> Scoreboard:
    """read() on a video file: the box found on a few sought frames, then every
    keyframe's crop read in one pass. Falls back to seeking when the file has
    too few keyframes to date a goal by."""
    import cv2

    from core.modes import probe_size
    from video.capture import video_capture

    with video_capture(path, required=False) as cap:
        if cap is None:
            return Scoreboard()

        def grab(t: float):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, img = cap.read()
            return img if ok else None

        from analysis.game_text import _ocr

        box = find_box(grab, duration, _ocr)
        if box is None:
            return Scoreboard()
        texts: dict[int, str] = {}
        try:
            times = _keyframe_crops(path, box, probe_size(path),
                                    lambda i, img: texts.__setitem__(i, rec_line(img)), cancel)
        except OSError:
            times = []
        if len(times) >= max(10, duration / (EVERY * 3)):
            readings = []
            for i, t in enumerate(times):
                if i in texts:
                    r = parse([texts[i]])
                    r.t = t
                    readings.append(r)
            return from_readings(readings, box)
        board = read(grab, duration, find_ocr=_ocr, cancel=cancel)
        return board
