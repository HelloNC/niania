# niania

**One premise in, a finished animated MP4 out**, inside Claude Code.

niania writes the script and storyboard, builds rigged 3D characters and sets, animates real
performances, adds cameras, narration, sound and on-screen graphics, renders, and checks its own
work. It runs on your computer with free tools: Blender, the Kokoro voice model and ffmpeg. There
are no API keys or paid services.

```
/niania:create-video A cat knocks a cup off a table and a kid catches it in slow motion
```

## Two looks
* **Cel / silhouette.** Rim-lit stylised characters with expressive faces in street, room and park
  sets at dusk, night, day or golden hour.
* **Clay reconstruction.** A news-explainer style: a white clay world, faceless mannequins in solid
  "subject" colours or translucent "ghost" bystanders, seated crowds, an airliner cabin, cockpit
  and exterior cutaway, an airport miniature, a desert runway, a white studio, and broadcast
  graphics (name tags pinned to people, callouts, titles, timestamp stamps).

## What the animation does
* **Bodies:** IK legs and arms, balance-driven hips, real steps with heel and toe roll and planted
  feet, anticipation, overlap and follow-through, eyes that lead head turns, and spring-driven
  secondary motion.
* **Hands and objects:** fingers wrap held objects without clipping. Objects can be placed, topple,
  fall and be caught, with slow motion that keeps gravity correct.
* **Shots and sound:** per-shot cameras with motivated moves and depth of field. Local narration
  and dialogue with lip sync, procedural sound effects, ambience and a music bed.
* **Self-checks:** automated QC for foot sliding, detached limbs, clipping, abrupt motion, framing
  and audio/video sync. It renders preview contact sheets and fixes problems before the final
  render.
* **Your assets:** attached images become screens, backdrops or logos. glTF, OBJ, FBX, STL, PLY and
  USD models are imported.
* **Re-renders:** every project keeps its sources (`timeline.json`, `story.md`, the Blender scene
  and audio stems), so you can re-render a single shot.

## Requirements
* Claude Code: the desktop app's Code tab or the `claude` CLI. It does not run in claude.ai web chat.
* [Blender](https://www.blender.org/download/) 4.2 or newer (free). On macOS, put it in `/Applications`.
  Elsewhere, put it on your PATH or set the `BLENDER` environment variable.
* Python 3.10+. On first use niania runs a setup check and **asks before** installing the free
  Kokoro text-to-speech model and ffmpeg into `~/.animation-studio/venv`, a download of about 1 GB.

Rendering happens locally, at roughly 2 s per 1080p frame on an Apple-silicon Mac, so a 30-second
video takes about 25 minutes.

## Install
```bash
claude plugin marketplace add <github-user>/<repo>
claude plugin install niania@niania-plugins
```
Then start a new Claude Code session and run `/niania:create-video <your idea>`.

## Limits
Static (posed) crowds, humanoid characters only, no cloth or hair simulation (springs only), and
procedural rather than photoreal sets. It cannot generate images or video with AI; everything is
built in Blender or comes from files you provide. Tested on macOS with Blender 5.2.
