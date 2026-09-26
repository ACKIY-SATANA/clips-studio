# Gaming / Reaction

**For game streams and reaction videos: the streamer's webcam and the game (or
the video they're reacting to) laid out together in a 9:16 Short, in the layout
you choose.**

A game stream is one wide picture with the game in the middle, a webcam in a
corner, and chat, alerts and panels around the edges. Cropping it to 9:16 the
standard way follows the biggest face, and on a game stream that can be a game
character, a portrait, or the person in a video the streamer is reacting to.

It is a switch of its own, off unless you turn it on, and it can't be combined
with Vertical Live, Podcast or Longform. With it off, nothing about processing
changes. If anything in it fails, that clip is made the standard way.

**It is for streamers on a real camera.** The detection is built to find
people. VTubers aren't supported: an avatar is never taken for the streamer,
so a VTuber stream gets the game on its own.

## Layouts

Eleven layouts, chosen from cards that show the video's own frame in each one.
All of them are data (`gaming/layouts.json`), not code.

| Layout | What it is | Boxes it uses |
|---|---|---|
| **Split** | Webcam band on top, the game fills the rest. The divider sets the webcam's share, 25–50% (38% to start). | Webcam, Game |
| **Basecam** | Split with the game on top and the webcam at the bottom. | Webcam, Game |
| **Half** | Webcam and game 50/50. | Webcam, Game |
| **Fullscreen** | The game cropped to fill the Short, no webcam. | Game |
| **Blurred** | The whole game in the middle, on a blurred copy of itself. | Game |
| **Small facecam** | The game fills the Short, a small webcam near the top. | Webcam, Game |
| **Circle facecam** | The same with a round webcam. | Webcam, Game |
| **Game UI** | Webcam on top, a strip of game UI (a scoreboard, a map, a timer), the game below. | Webcam, Game UI, Game |
| **Mosaic** | Webcam and a game UI panel side by side on top, the game below. | Webcam, Game UI, Game |
| **Dual facecam** | The game fills the Short, two small webcams near the top (duo streams). | Webcam, Webcam 2, Game |
| **Duo split** | Two webcams side by side on top, the game below. | Webcam, Webcam 2, Game |

**On top** switches the webcam and the game in Split, Half, Game UI, Mosaic and
Duo split; Basecam is the same switch set the other way.

Every region is filled in the same order: the region on the 1080×1920 canvas,
then the source cut to that region's shape (never stretched), then either
**cover** (cropped to fill it) or **contain** (shown whole). A whole game sits
against its region's outer edge: at the very top when the game is on top, at
the very bottom when it's underneath, with a blurred copy of itself filling the
rest of its region. Nothing is centred on the whole canvas except in Blurred,
and there are no black bars.

With no webcam found, a layout that needs one falls back to Blurred. A layout
that needs a Game UI or second webcam box that was never drawn falls back to
Split or Small facecam.

## Faces clear of the platform's buttons

TikTok, Reels and Shorts draw their own buttons, captions and top bar over the
video. A webcam crop that is only centred can put the streamer's head under
the top bar: measured on one Marvel Rivals stream, the head sat 2–26 px from
the top of every clip, because that webcam has barely any room above the head.

So the webcam is placed from the streamer's head, not the middle of the box:

- the head is found in the webcam box of each clip (the pose model, a few
  frames, inside the box only; it places the crop, it never decides who);
- the head's top lands at least 6% of the region below its top **and** below the
  chosen platform's top bar, and the chin above the caption area where the
  region allows it;
- when the webcam itself has too little room above the head, the picture
  moves down inside its region (by just what's missing, at most 30% of the
  region), with a blurred copy above it rather than a cut-off head;
- small and round webcams go inside the platform's safe area.

The same stream re-rendered: the head top at 135–158 px with the webcam on top
(TikTok's top bar ends at 140), about 200 px in Small and Circle facecam.

Safe areas, on a 1080×1920 Short (from the platforms' published guides, which
agree to within tens of pixels):

| Platform | Top | Bottom | Left | Right |
|---|---|---|---|---|
| TikTok | 140 | 420 | 60 | 180 |
| Instagram Reels | 140 | 500 | 60 | 130 |
| YouTube Shorts | 160 | 320 | 60 | 150 |
| All three | 160 | 500 | 60 | 180 |

The platform is chosen in the preview (TikTok to start), which shades its
top bar and caption area and says whether the face is clear of them: "✓ Face
clear of TikTok's UI", or what to change. Camera on top is usually the fix:
with the game on top, the webcam band sits in the caption area.

## Choose the layout before processing

Every game and every stream overlay is different, so the layout can be set up
on the video's own frames before any processing starts. Tick **Gaming /
Reaction** on a video in the Generate bar (a YouTube, Twitch or Kick link, or a
file) and **Choose a layout** opens:

- **Layouts**: the eleven cards, each a live miniature of this frame;
- **the frame**, with a box for each thing the layout uses (Webcam, Game, Game
  UI, Webcam 2): drag a box to move it, a corner to resize it. The dashed line
  inside is exactly what the layout will show. **Snap to the webcam's border**
  pulls the webcam box out to the overlay's own edge;
- **Moment**: a slider over the whole video and five frames spread across it
  (nothing is downloaded for a link; each frame is read straight from the
  stream);
- **Preview**: the 9:16 result, live, with the platform overlay and the face
  check. Drag the line between the webcam and the game to change their shares;
- **On top**: Camera or Game. **Webcam**: *Find it*, *Draw it* or *None*.
  **Game**: *Whole* or *Zoom to fill* (and then Left, Centre or Right).
  **Draw the game area** around just the game leaves chat, alerts and panels
  out.

When it opens, Clips Kitty suggests a webcam box: a person in the same spot on
at least four of the five frames, no more than a third of the picture, with a
real border round at least two of its inner sides. A game character moves
between frames minutes apart, chat has no person in it, and an avatar has no
webcam border, so none of them are suggested. It's only a starting point, drawn
for you to check. With no suggestion, *Find it* leaves the webcam to TalkNet
when processing.

**Use this layout** sends it with the video. **Remember for this creator's
next videos** keeps it for them, so their next videos (and a watched
channel's) start from it. **Change layout…** in the Generate bar opens it
again.

The same editor is in the **clip editor** (Effects → Layout → **Gaming /
Reaction** → *Change layout…*) to change one clip: shown in *Update preview*,
saved on *Apply*.

## Who the streamer is, when it's found automatically

**TalkNet decides**: the streamer is the face that speaks in sync with the
stream's audio. Size never decides. This is the same fix that ended the
"largest face" problem in standard processing: a character can be as big as it
likes, but it doesn't move its mouth with the stream's audio.

Measured on real streams, "who is speaking in this clip" isn't always "who the
streamer is", so four things sit around TalkNet:

- **On screen for most of the clip.** TalkNet scores whatever face it is given.
  A driver glimpsed through a car window in GTA for 3% of a clip got a full
  speaking score. A webcam is on screen the whole time.
- **The most confident speaker.** When two faces both speak (a watch party, the
  streamer and the person in the video), the one TalkNet is surest of wins:
  3.3 against 0.3 on the stream we measured.
- **A real person.** Game characters that lip-flap to voice acting (a 3D visual
  novel) and VTuber avatars score as speaking, but TalkNet is never confident
  about them. A webcam's confidence reached at least 0.3 in some clip of every
  stream measured. Characters and avatars stayed at -0.2 or below.
- **The whole video, not one clip.** In a reaction the person in the watched
  video can out-talk the streamer for a whole clip. So the webcam is decided
  once per video, from four of its clips spread through it: the face that
  speaks from the same spot in the most of them.

The webcam box starts as the streamer's own box, with no margin (a margin ran
past a speedrunner's webcam into the chat beside it). Each side then grows out
to the webcam overlay's own border where there is a clear one, and stops just
inside it, so the half shows the webcam and nothing beside it. On six streams
with a webcam, every side of every box landed inside the hand-marked webcam.

## Where the game comes from

The game area is **never detected**. Earlier attempts looked for the part of
the screen with the most going on, and scrolling chat won every time. So:

- **Whole game**: the biggest picture beside the webcam that leaves it out
  (left, right, above or below it), so the streamer isn't shown twice. With no
  webcam, the whole stream. A chat panel at the side of the stream is part of
  that picture; *Zoom to fill* or a drawn game area leaves it out.
- **Zoom to fill**: a crop at the region's shape from the middle, full height,
  where chat panels and alerts at the edges fall outside it, slid clear of the
  webcam. A chat box *under* the game can still be inside it: draw the game
  area.
- **A drawn game area** replaces both.

## Scoring

Finding the moments works as usual, with one change: the "reaction" signal
(is a person on screen, being emphasised?) is left neutral. On a game stream it
counts game characters as people, and a top-down game as nobody at all. The
streamer's reactions are in their voice, which the audio and transcript
signals already score.

## Tested on

September 2026, public Twitch VODs, three 40-second windows from each of 13
streams. Webcam positions were marked by hand from a frame of each and compared
with what was found.

| Game | Stream | Result |
|---|---|---|
| Zelda: Breath of the Wild | speedrun, webcam bottom-left, splits timer and chat around it | ✓ split: webcam found, inside the hand-marked box on every side |
| Zelda: Tears of the Kingdom | VTuber | not supported: the avatar wasn't taken for the streamer, and the game shows alone |
| "Zelda" category (really a gacha RPG) | no webcam, a large anime character on screen | ✓ the game alone; the character was not taken for the streamer |
| World of Warcraft | webcam bottom-left, bags and action bars | ✓ split |
| World of Warcraft | just chatting, camera fills the frame | ✓ framed the standard way |
| Grand Theft Auto V | roleplay, no webcam | ✓ the game alone; a driver seen for a moment was not taken for the streamer |
| Grand Theft Auto V | reacting to a bodycam video, small webcam | ✗ webcam not found: the streamer mostly listened, and TalkNet was never confident about their face. Draw it in the setup. |
| League of Legends | lobby and loading screens, webcam bottom-right | ✓ split, inside the hand-marked box on every side |
| League of Legends category | a watch party: two webcams and a documentary | ✓ split with the streamer's webcam; when her camera went full screen, framed the standard way |
| Rust | webcam top-left, chat under it | ✓ split, chat left out of the webcam half |
| Dota 2 | two casters' webcams and a player cam | ✓ split with a caster's webcam |
| Persona 3 Reload | VTuber, voiced characters | ✓ the game alone: no character was taken for a webcam |
| Pixel-art game | VTuber | not supported: the game shows alone |

Time on an RTX 3060: finding the webcam looks at four 40-second pieces of the
video, about 15 seconds each (6 for person tracking, 8 for TalkNet). Each clip
then checks that the webcam is there, a few seconds, instead of the standard
face tracking. A split set up before processing skips the search.

`scripts/gaming_detect_bench.py` repeats the measurement on any footage.

## Known limits

- **VTubers aren't supported.** The detection is for people on camera.
- **One layout per clip.** A clip that moves between the game and a
  full-screen camera keeps one layout.
- **The Game UI and second webcam boxes are drawn by hand.** Nothing looks
  for a scoreboard or a second streamer.
- **YouTube frames for the editor are read over IPv4.** On some networks
  FFmpeg's IPv6 connection to YouTube hangs for minutes; the editor's frames go
  through a small local relay that forces IPv4.
- **Separate recordings** (the game and the webcam as two files, as some
  recorders make) aren't supported yet.
