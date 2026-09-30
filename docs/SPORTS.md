# Sports

**For matches: the goals, saves, cards and big chances of a game, each as its
own clip with the build-up and the reaction, framed to follow the ball.**

A match isn't a stream. Nobody on screen is the streamer, the moments that
matter are over in two seconds, and a 9:16 crop that follows the biggest face
frames the nearest player while the goal goes in off the side. Sports is a
switch of its own that scores and frames a video as a match.

Soccer (football) is the first sport. The design is modular so more can be
added (see [Adding a sport](#adding-a-sport)).

It is off unless you turn it on. With it off, nothing about processing changes
and none of its code runs.

## Turning it on

- **A video or file**: tick **Sports** in the Generate bar. A row appears under
  the video:
  - **Sport**: Soccer.
  - **Highlights**: which moments become clips (below).
  - **Period**: Full match, 1st half, 2nd half or Extra time.
  - **Teams or players** (optional): clips where the commentary names them get
    extra points. Nothing else is left out for it.
- **A queued video**: the same, in its **Settings**.
- **A watched channel**: the same, in the channel's clip settings, so every
  match a channel posts is clipped this way.
- **The API, the assistant and MCP** take `sport` (see
  [the API](#the-api)).

Sports can't be combined with **Podcast** or **Gaming / Reaction**: each scores
and lays out the video its own way. It works with **Longform** (16:9 clips of
the moments) and with **Vertical Live** (a match filmed 9:16 keeps its own
layout).

### Highlights

| Choice | What becomes a clip |
|---|---|
| **Best moments** | Everything, best first, and always every goal the scoreboard confirmed |
| **All goals** | Every goal (penalty goals and own goals too), each with its build-up |
| **Goals + celebrations** | The same with 12 more seconds after each, for the celebration |
| **Best saves** | Saves, and penalties saved or missed |
| **Best chances** | Big chances, shots, and missed penalties |
| **Attacking plays** | Goals, chances, shots, penalties, free kicks, corners |
| **Cards** | Red and yellow cards, and VAR reviews |
| **Penalties** | Penalties given, scored and missed |
| **Custom** | Everything, plus the moments you describe in your own words ("the saves and the late chances"), which get extra points |

With a choice other than Best moments, the clips of those moments are kept even
when their score is under your minimum, and the others are set aside with a
reason ("not in the chosen highlights").

## What it finds, and how

It uses the models the app already runs. There is no second AI stack.

| Signal | From | What it tells |
|---|---|---|
| **The scoreboard** | The score box in the corner, read with the app's OCR (RapidOCR) | A goal, for certain: the score changed. Which side scored. The match clock, so the half and the minute. |
| **The crowd** | The app's sound model (PANNs) | A roar that lasts: something happened |
| **The whistle** | The same | Play stopped: fouls, cards, penalties, the end of a half |
| **The commentary** | Whisper's transcript | What happened, in the commentator's words ("what a save", "penalty", "he's sent off"), in the main football languages |
| **The screen** | The app's OCR | Graphics like "VAR CHECK" or "RED CARD". Off for soccer (`read_screen` in `config/sports.yaml`): on the test final it took two minutes and found nothing the score box didn't |
| **The clip itself** | Your AI model, reading the transcript and the signals | How good the clip is, as for any video |

**The scoreboard is ground truth.** It is found once (a small box of text that
stays put, with a score and a clock), then read from every keyframe of the
match. A goal is a score that changed and stayed changed for two readings, so a
misread digit is never a goal. On a 1h42m official upload of a World Cup final
it read the box 1,541 times (49 seconds on its own, 141 while Whisper was also
running) and found all six goals, with the right side for each.

The box is the score's own line of text, with the clock beside it, not
everything written near it: a stadium's ad boards and banners are left out,
which matters most in a 9:16 frame, where the same strip of the picture holds
far more stadium. Soft text (an upscaled video, a phone filming a screen)
loses the separator and reads a 0 as the letter O ("HOMOOAWO" for HOM 0-0 AWO); once the teams
are known, the score is read from between their codes. On the final that took
the readings with a score from 1,016 to 1,269, and on a 9:16 version of it from
59 of 301 to 213, with all its goals found.

**The crowd dates the goal.** The new score shows up some time after the ball
goes in: 8 seconds after one goal of that final, 40 after another, and on other
broadcasts only after the replays. So a goal is placed where the crowd's
loudest five seconds start, between the score before it and the new one. On
the final, every goal was placed within two seconds of the ball going in, and
the clock read off the box gave the minutes the match record gives: 18', 28',
38', 59', 65', 69'. A goal whose crowd can't be heard is placed half a minute
before the new score.

**A moment is named only when the evidence agrees.** A goal the scoreboard
confirms is a goal, and where the score is being read, nothing else is: "they've
scored four!" said over a cheer, with the score unchanged, is talk about a goal.
Other moments are named only when the commentary names them and at least one
other signal (the crowd, the whistle, the screen) agrees. The commentary alone
is never enough, and a moment the signals mark without a name is kept as a
**big moment**, with the signals it had. The crowd counts when it cheers above
its usual level for two seconds or more; a one-second "ooh" doesn't. Tackles,
dribbles, assists and key passes aren't claimed.

**Replays are grouped, not clipped twice.** Broadcasts replay a goal two or
three times, and each replay has the same words and a smaller roar. A cheer
within 45 seconds after a goal is its celebration (no kick-off comes that
soon). Within 90 seconds, a moment that looks like another goal without the
score changing (or while the score box is hidden, or when the commentator says
"replay" or "watch it again") is a replay of it. Both are grouped with the
goal, and only the goal is clipped.

The voice jump the gaming profile uses (the streamer suddenly twice as loud)
barely fires on a broadcast. The commentary is compressed: in the final above it
reached twice the commentator's usual level 14 times in the match, around one of
the six goals. It is left as it is, and the crowd, the commentary and the
scoreboard carry the detection.

## The clips

Each moment gets its own window, set per type in `config/sports.yaml`:

| Moment | Before | After |
|---|---|---|
| Goal | 14 s (the build-up) | 10 s (the celebration) |
| Penalty goal | 10 s | 10 s |
| Save | 8 s | 6 s |
| Red card | 8 s | 10 s |
| Yellow card | 6 s | 8 s |

The crowd reacts a second or two after the moment, so a moment found by the
crowd is moved back 1.5 s. A window never runs past the video, and when the
clip is too long, the build-up is trimmed first.

Every clip is scored the normal way, then its moment adds up to 20 points (a
goal most, a replay nothing). One clip per moment: when two candidates show the
same goal, the better one is kept. A goal the scoreboard confirmed is kept even
when the words around it score low: on the test final, the words alone rated
two of its six goals 10 and 25 out of 100.

The clip card names the moment ("Goal · 18'", and the side that scored), and
the clip page opens with a short note: what was found, the score read, and
anything that couldn't be confirmed (a moment whose half couldn't be told is
kept, and says so).

## Framing: follow the ball

A 16:9 match cropped to 9:16 keeps a third of the picture, so the crop has to
be where the play is. Sports frames the way the automatic camera systems do
(Veo, Pixellot, Hudl, Trace):

- **The ball**, from the object detector the app already ships (YOLOv8n,
  "sports ball"). A detection is followed only if the ball could have got
  there since the last one, and a new ball is only picked up from a confident
  detection, so a boot or a steward's vest isn't followed.
- **When the ball is lost**, the players near where it was last seen.
- **In a close-up** (a player filling the frame, a celebration), that player.
- **Moves** the way the rest of the app's framing does (a hold, a smooth
  move), a little faster for play, and **cuts** when the broadcast cuts,
  never panning across a camera change.

The ball in a broadcast wide shot is a few pixels across, so the detector runs
at 1280 px. Measured on 200 frames of the final, in the 123 wide shots:

| Detector | Ball found | Time per frame (GPU) |
|---|---|---|
| YOLOv8n at 640 px | 35 | 25 ms |
| YOLOv8n at 960 px | 77 | 28 ms |
| **YOLOv8n at 1280 px** (used) | **90** | **34 ms** |
| YOLOv8s at 1280 px (a 22 MB download) | 78 | 44 ms |

The bigger model found fewer, and was slower, so no new model is needed. The
detector and its size are set in `config/sports.yaml` (`framing`).

## Vertical videos

A match filmed or streamed 9:16 (a phone at the side of the pitch, a vertical
feed) keeps its own picture, as Vertical Live does, with nothing to switch on:
the app notices the shape, doesn't reframe it, and finds the moments the same
way, score box included. On a 9:16 version of 25 minutes of the final it found
all three goals at their minutes, and each clip is the whole vertical picture,
processed in 5 minutes.

With **Longform**, the clips stay 16:9, and they and the Highlights reel are
the match's moments too.

## What it doesn't do yet

- Sideline and phone footage without a score box: goals come from the crowd
  and the commentary alone, which works for a loud crowd and a commentator,
  and not for a silent training match.
- Tackles, dribbles, assists and key passes aren't named.
- Other sports. Soccer is the first.

## The API

`POST /jobs`, `/jobs/batch`, `/videos/local`, `PATCH /jobs/{id}` and a watched
channel's options take `sport`:

```json
{"sport": {"name": "soccer", "highlights": "goals", "period": "full", "teams": "Team A"}}
```

- `highlights`: `best`, `goals`, `goals_celebrations`, `saves`, `chances`,
  `attacking`, `cards`, `penalties`, `custom`.
- `period`: `full`, `first_half`, `second_half`, `extra_time`.
- `teams` (optional): up to 200 characters.
- `request` (optional, with `custom` only): the moments wanted, in words.

`GET /sports` lists the sports and their choices. An unknown sport or choice is
refused with a 400 that lists what is allowed, and so is Sports together with
Gaming / Reaction or Podcast.

A finished run's outcome carries `sport`: the moments found by type, the big
moments, the replays grouped, and the score read. Each clip's scores carry the
moment: `sport_event`, `sport_label`, `sport_minute` (from the clock), `sport_t`
(seconds into the video), `sport_why` (the signals), `sport_team`,
`sport_period` and `sport_bonus`.

## Adding a sport

Everything sport-specific is data and one package:

```
config/sports.yaml     the sport's entry: its moments (importance, window),
                       commentary words in each language, on-screen words,
                       sound weights, highlight choices, periods, framing
sports/
  __init__.py          the registry: SPORTS = {"soccer": "sports.soccer"}
  core/                shared by every sport
    profile.py         SportProfile: what the scoring asks a sport, and the
                       rule for naming a moment (two signals agree)
    events.py          a moment: type, time, confidence, window, signals,
                       replay, group
    detect.py          moments from the crowd, the voice, the commentary,
                       the screen and a scoreboard
    windows.py         the window around a moment
    select.py          which moments a Highlights choice keeps
    clips.py           moments onto the scored clips: the bonus, one clip per
                       moment, the Highlights and Period choices, the report
  soccer/
    __init__.py        profile(), framing(), prepass() (the scoreboard)
    profile.py         what soccer adds: own goals, penalty goals and misses
    scoreboard.py      reading the score box
    ball.py            following the ball, for the framing
```

A new sport needs:

1. An entry in `config/sports.yaml`, like soccer's.
2. A `sports/<name>/` package with a `profile(config, option, video)` function.
   `framing(clip_path, config)` and `prepass(video_path, duration)` are
   optional: without them the clips are framed the standard way, and nothing
   is read before scoring.
3. A line in `SPORTS` in `sports/__init__.py`.

The app then offers it in the Sport menu, with its own highlight and period
choices, and nothing else changes.
