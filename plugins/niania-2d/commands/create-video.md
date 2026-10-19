---
description: Code-only video - premise (+ optional character reference sheets) to a finished 2D animated MP4, no Blender
argument-hint: <premise> [--duration 30] [--size 1080x1920]
---

Create a complete code-only animated video from this premise:

$ARGUMENTS

Use the **code-animation** skill of the niania-2d plugin (load it now) and follow it end to end
without asking for approval per scene:

0. If the user attached character reference sheets or images, Read them first. Copy them into the
   project's `assets/`, sample their colours with `studio2d.py palette`, and write one cast spec per
   character. With no images, design the characters from the prompt.
1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/engine/studio2d.py doctor`. If something is missing, explain it
   and ask before installing (`--install` = Pillow/numpy/soundfile, about 20 MB; `--install-tts` =
   Kokoro, about 1 GB).
2. `studio2d.py new ./animation_projects/<slug> --duration <s> --size <WxH>` (default 30 s, 1080x1920).
3. Write `story.md` (beats, lines, storyboard), then `timeline.json`. Run `studio2d.py sheet <p> <id>`
   for every character and compare it with the reference until it matches.
4. `validate → lines → preview` and **look at `preview/sheet.png`**. Fix timing, framing, overlaps and
   captions until it reads.
5. `mix → render → assemble → check`. Read `final/contact_sheet.jpg`.
6. Reply with the MP4 path, the editable sources (timeline.json, story.md, audio stems, frames),
   the QC numbers and the known limitations.
