# timeline.json (niania-2d)

One file drives the video. Times are seconds. Screen positions are fractions of the frame (0..1,
y down). Working example: `templates/demo_doctor/timeline.json`.

## Top level
| key | meaning |
|---|---|
| `title`, `premise` | text (`title` names the MP4) |
| `fps` (30), `resolution` ([1080,1920]), `duration` | output format |
| `style` | `{"grade": none/night/warm/cool/noir/vintage/vivid, "grain": 0.02, "vignette": 0.3, "bloom": 0.25}` |
| `fade_out` | seconds of fade at the end (0 = none) |
| `cast` | `{id: character spec}`, see characters.md (`voice` sets the dialogue voice) |
| `shots` | contiguous list covering 0..duration |
| `performance` | acting events (below) |
| `graphics` | global screen graphics (each shot can also have its own `graphics`) |
| `captions` | `{"on": true, "size": 0.036, "y": 0.74, "box": false, "box_alpha": 0.6, "highlight": ["62"], "highlight_color": "#ff3b2f", "max_words": 4}` |
| `audio` | voices, sfx, ambience, music (below) |

## Shots
```json
{"name": "s2_tip", "start": 4.6, "end": 10.2, "in": "cut|dip|flash|flicker|slowfade|whip",
 "bg": {"type": "radial", "inner": "#1d3a44", "outer": "#071014"},
 "cam": {"zoom": [1.0, 1.05], "pan": [[0, 0], [0.02, 0]], "shake": 0.0},
 "chars": [{"id": "doc", "x": 0.42, "y": 0.72, "scale": 1.05, "flip": false, "z": 1,
            "to": {"x": 0.45, "scale": 1.1}, "enter": "left|right|bottom", "enter_dur": 0.5}],
 "graphics": [...], "captions": {"box": true}}
```
* `x`, `y` place the character's **neck base**. `scale` 1.0 is a medium shot (the head is about 23 % of
  the frame height on 1080x1920); 1.4–1.6 is a close-up; 0.8–1.0 leaves room for a graphic.
* `flip` mirrors the character so it faces the other way, for two-shots.
* `bg.type`: `solid {color}`, `gradient {top,bottom}`, `radial {inner,outer,center,radius}`,
  `bokeh` (radial + blurred lights: `lights`, `count`, `band`), `room {wall,wall2,floor,floor_y,
  window,window_color,shelf}`, `sky {top,horizon,clouds}`, `image {file,blur,dim}` (a user asset).
  Any type also accepts `lights` (bokeh dots) and `grid: true`.

## Performance (`{"char": id, "t": s, "do": verb, ...}`)
| verb | params |
|---|---|
| `expr` | `set`: neutral smile happy laugh worried sad surprised exhausted angry focused thinking, or a dict of `brow_in brow_out brow_up lid wide smile open oshape`; `dur` 0.3 |
| `look` | `x, y` in -1..1 (eyes), `dur` |
| `turn` | `yaw` -0.6..0.6 (head turn; + = toward screen right), `dur` |
| `tilt` | `deg`, `dur` |
| `gesture` | `side` L/R, `pose`: rest open_palm point wave hold_mug chin present shrug chest; `dur` 0.45; `hold` (wave) |
| `nod`, `shake` | `n` repeats |
| `blink` | extra blink (blinks are also automatic) |
Dialogue lines drive the mouth (lip-sync), and talking adds small nods and tilts automatically.

## Graphics (`"t": [start, end]`, `pos` = [x, y], `size` = fraction of the frame height)
| type | fields |
|---|---|
| `title` / `text` | `text, font (sans/sans_regular/mono/condensed/type/serif/path), align, color, accent, anim (rise/type/fade), underline` |
| `lower_third` | `title, sub, accent` |
| `badge` | `text` (red blinking dot + mono text, e.g. "DRAMATIZED RECONSTRUCTION") |
| `panel` | `title, items[], w, h, stagger, accent` (box with bullets revealed one by one) |
| `counter` | `from, to, format, label, count_dur` |
| `arrow` | `from [x,y], to [x,y], label, grow` |
| `icon` | `icon` plane/heart/check/cross/warning/clock, `angle`, `animate_angle`, `outline` |
| `image` | `file` (project asset), `w` |
All graphics fade in and out (`fade`, `fade_out`).

## Audio
```json
"audio": {"narrator_voice": "bm_george", "narrator_speed": 1.0,
  "narration": [{"t": 0.5, "text": "...", "show": "caption text if different", "voice": "...", "speed": 0.95}],
  "dialogue":  [{"t": 2.0, "char": "doc", "text": "...", "voice": "am_michael"}],
  "sfx": [{"t": 3.0, "type": "pop|click|chime|ding|beep|alert|whoosh|thunder|heartbeat|boom|typing|paper", "gain": 0.5}],
  "ambience": "room|rain|wind|city|cabin|office|none" or a list, "music": "tension|drone|warm_pad|gentle|upbeat|none",
  "silence": [[52.4, 55.4]], "duck_db": -12, "lufs": -14, "gains": {"voice": 1, "sfx": 0.55, "ambience": 0.25, "music": 0.3}}
```
Voices: am_michael (warm US male), am_fenrir (deep US male), af_heart (bright US female),
af_bella (soft US female), bm_george (UK male), bf_emma (UK female). `show` lets captions print
"2016" while the voice says "twenty sixteen" (keep the same word count, or words are mapped proportionally).
