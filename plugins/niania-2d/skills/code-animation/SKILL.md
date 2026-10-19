---
name: code-animation
description: Make a finished 2D animated MP4 using only code (Python/Pillow frames, Kokoro voices, procedural sound, ffmpeg). No Blender or 3D app. Characters come from user reference sheets or prompts. Use when the user wants a code-only video, a 2D/anime/cartoon explainer or talking-character video, or invokes /niania-2d:create-video.
---

# Code-only animation (niania-2d)

Everything is drawn by code: vector polygons with cel shading and linework, rendered in parallel
with Pillow. The voices are local Kokoro TTS. Music and SFX are synthesised with numpy. ffmpeg
encodes the result. No Blender, no image generation, no paid APIs.

`S="python3 ${CLAUDE_PLUGIN_ROOT}/engine/studio2d.py"`. Read `reference/timeline2d.md` and
`reference/characters.md` before writing a timeline.

## 0. Environment
Run `$S doctor`. Ask before installing anything: `--install` adds Pillow + numpy + soundfile in
`~/.niania2d/venv` (about 20 MB), and `--install-tts` adds Kokoro (about 1 GB, no key).

## 1. Characters from reference sheets or prompts
* Images the user attaches are files. Read them, then copy them into `<project>/assets/`.
* `$S palette assets/sheet.png 0.12,0.30 0.11,0.42` prints the dominant colours and samples at
  normalised points (hair, skin, clothes, accessories). Use those hex values in the cast spec.
* Map what you see onto the spec: hair style (messy/short/long/bun/curly/bald) and part, glasses
  (rect/round/none), eye shape (tired/round/sharp/normal), facial hair, top (vneck/tshirt/hoodie/
  shirt_tie), outer (labcoat/jacket/blazer/none), accessories (stethoscope, pen_pocket, badge,
  mug via the hold_mug pose).
* Run `$S sheet <project> <id>` and Read `preview/sheet_<id>.png` (turnaround, expressions,
  poses). Iterate the spec until it matches the reference. Keep one spec per character.
* If a feature can't be expressed with the spec, extend `engine/puppet.py` instead of
  compromising (add a hair style, outfit or prop). Say what you added.

## 2. Plan
Write `story.md`: premise → beats with times → lines (about 2.6 words/s) → storyboard (framing,
action, graphics, transition). Default is 30 s at 1080x1920 unless the user says otherwise.
Shots run 2–5 s. Never use the same transition twice in a row. Keep whooshes rare (2 per minute at most).

## 3. Timeline → lines → preview (iterate)
```
$S validate <p> && $S lines <p> && $S preview <p>
```
`lines` prints each line's real start and end and warns about overlaps. Move times or shorten text
until there are no warnings. Then Read `preview/sheet.png` (one frame per second plus each shot
start) and check that:
* faces are framed, nothing important is cut off, and gestures stay in frame;
* captions don't sit on busy or bright areas (use `"box": true` there) and don't collide with
  lower thirds;
* the acting reads: expression changes before or with the line, eyes lead turns, a gesture on the key
  word, and holds of at least 0.6 s on reactions.

## 4. Final
```
$S mix <p> && $S render <p> && $S assemble <p> && $S check <p>
```
Rendering is parallel (all cores) and takes about 0.35 s per frame per core at 1080x1920.
Re-render one shot with `$S render <p> --shot NAME`, then `assemble`. Read
`final/contact_sheet.jpg` and `final/media_check.json` (frames, size, LUFS, black segments).

## Honesty
Say plainly what the engine can't do. Characters are front-facing busts with a ±0.6 head turn (no
full turnarounds, walking or full-body action). Hands are simplified. There is no lip-sync for
off-screen narration (only dialogue drives mouths). There is no image or video generation, and
reference sheets are interpreted, not traced. Report the QC numbers you actually measured.
