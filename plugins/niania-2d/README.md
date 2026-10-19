# niania-2d: code-only video

One premise in, finished MP4 out, made **only with code**. There's no Blender, no 3D app, no image
generation and no API keys.

- **2D cel characters:** each is a JSON spec (hair, glasses, eyes, outfit layers, accessories,
  colours) with expressions, head turns, blinks, gestures and dialogue lip-sync.
- **Your reference sheets:** Claude reads them, `palette` samples their exact colours, and `sheet`
  draws the coded character's turnaround so you can compare.
- **Scenes:** backgrounds, camera push and pan, graphics (titles, panels, lower thirds, counters,
  arrows, icons, images), word-by-word captions with highlights, colour grades and transitions.
- **Audio:** local Kokoro voices, procedural SFX, ambience and music, −12 dB ducking under speech,
  mastered to −14 LUFS.
- **Rendering:** parallel Pillow rendering on all cores, ffmpeg encode, media QC and a contact sheet.

## Install
```bash
claude plugin marketplace add HelloNC/niania
claude plugin install niania-2d@niania-plugins
```
Then run `/niania-2d:create-video <premise>` (attach reference sheets if you have them).

## Requirements
Python 3, ffmpeg, Pillow + numpy + soundfile (`studio2d.py doctor --install`), and optionally
Kokoro TTS (`studio2d.py doctor --install-tts`, about 1 GB).

## CLI
`engine/studio2d.py doctor | new | validate | palette | sheet | lines | preview | render | mix | assemble | check | all`

## Limitations
Characters are front-facing busts with up to about a ±35° head turn. There's no walking or
full-body action, hands are simplified, and narration doesn't move mouths (dialogue does).
