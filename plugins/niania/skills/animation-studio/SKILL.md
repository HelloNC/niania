---
name: animation-studio
description: Produce a complete animated MP4 (stylised 3D characters with IK rigs, real character animation, cameras, narration, SFX, music) from one premise, using local Blender + Kokoro TTS. Use when the user asks to create, animate, render, revise or re-render an animated video/short/scene, or invokes /create-video.
---

# Animation Studio

This skill uses a deterministic production engine (Blender 5, headless) driven by one
`timeline.json` per project. You write the story and the timeline. The engine does the rigs,
balance, IK, grips, physics, cameras, rendering, audio and QC. Paths below are relative to the
plugin root `${CLAUDE_PLUGIN_ROOT}`.

`S="python3 ${CLAUDE_PLUGIN_ROOT}/engine/tools/studio.py"`

## 0. Environment (first use in a session)
Run `$S doctor`. It needs Blender 4.2+ (`/Applications/Blender.app`), a Python with
`kokoro`+`soundfile` for narration, and ffmpeg. If TTS is missing, **ask the user** before
running `$S doctor --install-tts` (free download of about 1 GB, no API key). Without TTS,
narration must be supplied as `audio/narration_supplied.wav` (`"narration_mode": "supplied"`).
Say plainly that the video is then not fully prompt-only. Never use paid services or API keys
without asking.

## Using the user's assets and reference images
* Images attached in the chat exist as files (their paths appear with the image). Copy them into
  `<project>/assets/` and use them as `image` props (backdrops, screens, posters, maps), airliner
  logos, or simply as style references that you analyse before choosing a set, palette and
  graphics. 3D models the user provides (glTF/OBJ/FBX/STL/PLY/USD) import as `model` props.
* Pick the style from the references:
  * Silhouette, rim light and dusk mood: `style` cel with the cafe/park/room sets.
  * White clay world, mannequins and news graphics: `"style": "clay"` with the
    `clay_cabin`/`cockpit_cutaway`/`airport`/`desert_runway` sets.
  * For anything the kit lacks, write a new builder in `engine/studio` instead of faking it.
* Claude cannot generate images or video, and conversational voice mode cannot export audio.
  Narration comes from local Kokoro. Never use paid services without asking.

## 1. Plan (write `story.md` in the project)
Read `reference/style_and_storyboard.md` first. Then:
* Premise → beat sheet with times → narration script (about 2.6 words/s) → storyboard table
  (shot size, angle, motivation, action, sound, cut reason) → top-down blocking in metres.
* Default is 30 s, 1920×1080, 24 fps, 6–8 shots, unless the user said otherwise.
* Make creative decisions yourself. Don't ask for approval per scene.

## 2. Author `timeline.json`
Read `reference/timeline.md`. Start from `$S new <project> --duration 30 --size 1920x1080` or
copy a tested example: `templates/demo_cup_catch/timeline.json` (cel style: place, topple,
slow-mo catch, reaction) or `templates/demo_cockpit_lockout/timeline.json` (clay reconstruction:
crowds, cutaway, door rattle, knocks, graphics overlay).
* Cast specs are defined once and reused by every shot (consistency).
* Every contact uses `hold` / `place` / `catch` (never approximate positions).
* Feet move only through `step`. Big actions get `anticipate` before and a settle after.
* Use event times (`"catch:cup+0.3"`) for anything that must sync to physics.

## 3. Build → QC → look → fix (iterate)
```
$S validate <p> && $S lines <p> && $S build <p> && $S qc <p> 2 && $S preview <p>
```
Read the build notes and `qc.json` summary, then **look at `preview/sheet.png` with the Read
tool**. Fix per `reference/qc_and_revision.md` until there are no reach notes, foot slides, IK
gaps or unintended intersections, the key action reads in each shot, and faces are visible on
emotional beats. Typically this takes 2–5 rounds.

## 4. Final
```
$S mix <p> && $S render <p> && $S assemble <p> && $S check <p>
```
The render takes about 2 s per frame at 1080p, so 30 s is about 25 min. Run it in the
background and keep working. Re-render only failing shots with `--shot <name>`. Read
`final/contact_sheet.jpg` and `final/media_check.json` before delivering. Deliver
`final/<title>.mp4` plus the editable sources: `timeline.json`, `story.md`, `build/scene.blend`
(open in Blender to tweak keys), and the `audio/` stems.

## Honesty rules
* Report QC numbers and known weaknesses. Don't claim checks you didn't run.
* If TTS was unavailable, say narration was supplied or omitted.
* Unsupported today: lip-sync for the narrator (only dialogue drives mouths), cloth/hair
  simulation (springs only), quadrupeds/non-humanoid rigs, animated crowds (crowds are static
  posed instances), automatic walk cycles (list the `step`s), AI image/video generation, and exact
  replicas of real aircraft interiors (the kit is a stylised narrow-body).
