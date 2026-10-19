# timeline.json reference

One file drives everything. All coordinates are metres, Z up, ground at z = 0. Facing angles are
degrees CCW from +X (0 = +X, 90 = +Y, -90 = -Y). Times are **video seconds**; any time field may
instead be an event string `"<event>+<offset>"` (events listed below). Working example:
`templates/demo_cup_catch/timeline.json` (15 s, 3 shots, catch + reaction).

## Top level
| key | meaning |
|---|---|
| `title`, `premise` | text |
| `fps` (24), `resolution` ([1920,1080]), `duration` (s) | output format |
| `set` | `{"template": "cafe_street" \| "room_interior" \| "park" \| "studio_void", "params": {"time": "dusk" \| "night" \| "day" \| "golden"}}` |
| `look` | optional StudioLook override: `shadow, lit, rim, rim_dir, rim_strength, rim_width, ambient` |
| `post` | `{"bloom": 0.3, "bloom_threshold": 0.9}` |
| `time_remap` | `[[t, speed], ...]` slow motion. Physics (falls, spills) runs on story time, so gravity stays correct. Authored acting is in video time: make it slower and smoother inside slow-mo windows. |
| `cast` | characters (below) |
| `props` | objects + their motion (below) |
| `performance` | list of verbs (below), any order |
| `fx` | liquid spills / flung droplets |
| `shots` | contiguous camera shots covering 0..duration |
| `audio` | narration, dialogue, sfx, ambience, music |

Set layout notes. In `cafe_street` the sidewalk is y < 2.4, the road is y 2.5–9.5 and the facade row
is at y ≈ 12.5. The sun sits low toward +Y, so cameras looking +Y get backlit silhouettes and rim
light. Reverse angles look −Y toward the front-lit buildings at y ≈ −9.5. Keep action near the
origin.

## Cast
```json
"mia": {"top": "#d8352c", "top_style": "hoodie", "hat": "beanie" | "cap" | null, "hat_color": "#f2c12e",
        "pompom": true, "skin": "#0c0a12", "legs": "#0c0a12", "shoes": "#141118", "face": "#fdf7ee",
        "scale": 1.0, "brows": true, "rim": 1.0,
        "start": {"pos": [x, y], "facing": deg, "width": 0.2}}
```
The character is about 1.75 m tall at scale 1, with arm reach about 0.51 m from the shoulder.
Shoulders sit at z ≈ 1.25 and hips at z ≈ 0.85. One spec per character makes proportions,
clothing and colours identical in every shot. Use different `top` and `hat_color` values to tell
characters apart.

## Performance verbs (`{"char": id, "do": verb, "t": time, ...}`)
| verb | params | notes |
|---|---|---|
| `stance` | `pos [x,y], facing, width` | instant placement (usually only from `start`) |
| `step` | `foot L/R, to [x,y]` or `by [right, fwd]`, `dur 0.45, facing, lift 0.07, weight_after 0.5, shift_first 0.12, toe_off 20` | weight shifts onto the other foot first, heel peels, arc, heel strike, plant. Feet never slide. |
| `shift` | `to "L"/"R"/"center"/0..1, dur` | moves the hips over the support foot (balance) |
| `hips` | `dur, crouch m, offset [right,fwd,up], rot [pitch,roll,yaw]` | the leg-length limit auto-lowers the hips, so knees can't pop |
| `bend` | `bone chest/spine/neck/head or list, rot [pitch fwd, roll right, yaw left], dur, ease` | lagged up the chain for overlap |
| `anticipate` | `dur, crouch (-0.012 = rise), lean [r,f,u]` | counter-move before a big action |
| `shrug` | `dur, amount (-1..1), side` | pulses shoulders. Repeat for laughs and breaths. Negative values are a relieved drop. |
| `hand` | `side, dur, ease, arc, spec` | hand targets (below) |
| `grip` | `side, amount 0..1.2, dur` | finger curl. On a held object it stops at the surface. |
| `spread` | `side, amount 0..1` | open/splayed fingers (reaching, balance) |
| `expr` | `set: preset or {key: value}` | presets: neutral content happy surprised alarm focused relieved proud laugh wince sheepish. Keys: blink_L blink_R happy wide squint smile open o_shape frown brow_up brow_down brow_worried |
| `blink` | `dur 0.16` | auto-blinks are added anyway |
| `look` | `target [x,y,z] / {"object":n} / {"char":n,"bone":"head_center"} / {"camera":true} / null, speed` | eyes lead, head follows, chest last. `speed` 3 = snap |

Eases: `auto` (smooth through keys, default), `inout`, `in`, `out`, `snap` (explosive start),
`back` (overshoot and settle), `anticip`, `linear`.

### Hand specs
* `{"preset": "relaxed" | "hip" | "chest" | "ready" | "pocket"}`
* `{"rel": "shoulder" | "chest" | "hips" | "head", "pos": [out, fwd, up], "fingers": [o,f,u], "palm": [o,f,u]}`
  is body-relative and mirrors automatically for L/R ("out" = away from the midline).
* `{"world": [x,y,z], "fingers": [...], "palm": [...]}`
* `{"hold": prop, "at": {"rel": "chest", "pos": [...]} | [x,y,z], "orient": "upright" | "keep", "tilt": deg, "up": [...]}`
  places the *held object* there. The hand follows from the grip, and the twist is chosen
  automatically so the wrist stays natural and the forearm clears the object.
  For `rel: chest`, the origin is the base of the ribcage (z ≈ 1.10). Comfortable holds are
  out 0.1–0.2, fwd 0.25–0.35, up −0.2…+0.25.

## Props
```json
"cup": {"type": "mug" | "ball" | "book" | "bistro_table" | "chair" | "lamp_post" | "tree",
        "pos": [x,y,z], "rot": deg, "color": "#hex", "motion": [ ...segments... ]}
```
Motion segments (sorted by `t`):
* `{"t":0, "do":"held", "char":"mia", "side":"R"}` starts the scene in the hand.
* `{"t":1.45, "do":"place", "dur":0.75, "pos":[x,y,z], "release":0.2}` makes the holder's hand
  carry the object there, after which the fingers open.
* `{"t":2.4, "do":"topple", "dir":[dx,dy], "nudge":0.7, "support":"table", "release_deg":55}`
  makes the object pivot over the support's edge and then fall.
* `{"t":..., "do":"fall"}` is ballistic from the current motion.
* `{"do":"catch", "at_height":0.56, "char":"mia", "side":"R", "approach":0.95, "give":0.025}`
  gives the catch time automatically from physics. The hand converges on the moving object and
  matches its velocity, the fingers close, and the hand gives with the impact.
* `{"t":..., "do":"static", "pos":[...], "rot":deg}`

## FX
* `{"t": "leave_edge:cup+0.15", "do": "spill", "from": "cup", "count": 4, "dur": 0.5, "speed": 0.25}`
  spills droplets that splat on the ground.
* `{"t": 9.11, "do": "fling", "from": "cup", "dur": 0.29, "to": {"char": "mia", "face": [u, v]}}`
  flings one drop that sticks to the face (u = char-left +, v = up, in metres from the head centre).

## Shots
```json
{"name": "s2_catch", "start": 3.0, "end": 7.6, "fstop": 2.8, "shake": 0.1, "lag": 0.3,
 "keys": [{"t": 3.0, "pos": [x,y,z], "aim": <point spec>, "lens": 26, "roll": 0}, ...],
 "focus": <point spec>}
```
Point spec is `[x,y,z]`, `{"object": n, "offset": [..]}` or
`{"char": n, "bone": "head_center" | "hips" | "chest" | "hand_target.R", "offset": [..]}`.
`lag` is operator follow delay (motivated reframing), `shake` is handheld degrees, and the
f-stop gives depth of field. Shots must be contiguous. Use an event time (`"catch:cup+0.2"`) for
a key that should land on an action.

## Events (usable as `t`, and as `"at"` in sfx)
`place:<prop>` (contact), `topple:<prop>`, `leave_edge:<prop>`, `catch:<prop>`,
`step:<char>:<foot>:<n>` (plant time of the n-th step), `splat:<particle>` (droplet impacts, used
by `{"auto": "splats"}`).

## Audio
```json
"audio": {"narrator_voice": "am_michael", "narrator_speed": 1.0,
  "narration": [{"t": 0.35, "text": "...", "speed": 1.1}],
  "dialogue":  [{"t": 7.2, "char": "mia", "voice": "af_heart", "text": "Phew."}],
  "sfx": [{"at": "catch:cup", "type": "catch", "gain": 0.8}, {"t": 3.05, "type": "heartbeat"}, {"auto": "splats", "type": "drip"}],
  "ambience": "evening_street" | "park" | null, "music": "warm_pad" | null, "slowmo_filter": true,
  "narration_mode": "tts" | "supplied"}
```
The SFX library is `clink tick whoosh_soft heartbeat step catch plip drip cloth pop`. Dialogue
drives lip-sync automatically. Narration speaks at about 2.6 words/s. `studio.py lines` warns
when a line runs into the next. Voices: `am_michael` (warm US male), `af_heart` (bright US
female), `bm_george` (UK male), `bf_emma`, `af_bella`, `am_fenrir`.

---------------------------------------------------------------------------------------------------
# Reconstruction / explainer style (clay world, mannequins, aircraft, graphics)
Working example: `templates/demo_cockpit_lockout/timeline.json` (18 s, 3 shots, crowds, cutaway, graphics).

## Style
`"style": "clay"` sets matte white physically lit materials, soft shadows and ray-traced AO, with
no rim light. Every set, prop and `cel()` material switches automatically. `"exposure": -0.55`
(default -0.35). `"tonemap": "standard" | "agx"`.

## Sets (clay)
| template | contents | anchors |
|---|---|---|
| `clay_cabin` | narrow-body cabin (3+3 rows, bins, windows, galley door) + cockpit | `seat:<row><letter>` (e.g. `seat:13C`), `seat:captain`, `seat:first_officer`, `door_handle`, `pedestal`, `panel` |
| `cockpit_cutaway` | the same aircraft built so one set serves interior **and** exterior cutaway shots: shared furniture + swappable shells (`cabin_front_closed`/`cabin_front_cut`, `cockpit_closed`/`cockpit_cut`, `fuselage_cutaway`), sky dome, clouds | as above + `variants`: `"interior"`, `"cutaway"` |
| `airport` | miniature airport: runway, taxiways, triangular terminal with pyramid roof (`highlight` colour), tower, parked airliners | `runway_y`, `terminal` |
| `desert_runway` | sand, runway, palm rows, haze backdrop | — |
| `clay_studio` | seamless white cyclorama for isolated objects, models, figures | — |
Aircraft frame: the fuselage runs along +Y (nose +Y), the cabin floor is z = 0, the aisle is x = 0, and the cockpit door is at y = 0 (cockpit y > 0, rows y < 0, row pitch 0.81 m). Seats face +Y (facing 90).

## Mannequin characters
```json
"pilot": {"body": "mannequin", "material": "subject" | "clay" | "ghost", "color": "#2c6fe6",
          "hat": "pilot_cap" | "cap" | null, "hair": "bun" | "short" | null, "head_scale": 1.18,
          "start": {"seat": "captain"} | {"pos": [x, y], "facing": 90}}
```
`subject` is a saturated solid colour (who matters), `ghost` is a translucent glowing hologram
(bystanders, earlier positions), and `clay` is white. Mannequins use the same rig, so every verb
works on them. They are faceless, so they act with the body: posture, head, hands.

## Seated pose and crowds
* Verb `{"do": "sit", "t": 0, "dur": 0.01, "seat": "13C" | [x,y,z], "facing": 90, "feet_fwd": 0.44, "lean": -6}`.
  With a long `dur` the character sits down from standing.
* Top-level `"crowds"` list:
  `{"name": "pax", "seats": "all" | ["1A", ...], "fill": 0.93, "seed": 3, "spec": {mannequin spec}, "special": {"13C": {"material": "subject", "color": "#a9c4f2"}}}`.
  These are static posed instances: cheap, varied head/arm poses, consistent proportions. Each
  one becomes the anchor `crowd:<name>:<seat>` at head height, usable for labels, focus and look
  targets.

## Per-shot visibility
A shot can carry `"variant": "interior" | "cutaway"` (from the set) and/or `"hide": ["name", "prefix*"]`.
Use this to swap clay crowds and ghost crowds, or closed and cutaway shells, so one set serves
every shot. Objects not listed stay visible. Use `"framing": false` on inserts or close-ups that
crop heads on purpose.

## Props for this style
* `{"type": "existing", "object": "cockpit_door"}` animates an object the set created.
* `{"type": "drone", "color": "#2f7bf0", "span": 30}` (its child `drone_prop` spins:
  `{"type": "existing", "motion": [{"t": 0, "do": "spin", "axis": "Y", "rps": 12}]}`).
* `{"type": "airliner", "pos": [...], "rot": deg, "body": "#hex", "tail": "#hex", "stripe": "#hex", "logo": "assets/logo.png", "scale": 1}`.
* `{"type": "lever", "pos": [...]}` is a grippable handle (cylinder grip).

## More motion segments (props.motion)
* `{"t": 7.8, "do": "rattle", "dur": 0.8, "amp": 1.6, "freq": 9, "axis": "Z"}` shakes a locked door or handle (decaying).
* `{"t": 3, "do": "swing", "dur": 0.8, "angle": 95, "axis": "Z", "ease": "inout"}` opens a door about its hinge (the object origin).
* `{"t": 0, "do": "path", "dur": 4, "points": [[x,y,z], ...], "bank": 25, "ease": "linear"}` is a flight path. Local +Y faces along the path and the object banks into turns.
* `{"t": 0, "do": "spin", "axis": "Y", "rps": 12}` gives continuous rotation (propellers, wheels).

## Hand pinned to a moving object
`{"on": "cockpit_door", "local": [x, y, z], "fingers": [..], "palm": [..]}`. The coordinates are in
that object's local frame, so the hand stays on the handle while the door rattles. QC treats this
as deliberate contact.

## Graphics overlay (`"graphics"` list, rendered as a transparent pass and composited per shot)
| type | fields | look |
|---|---|---|
| `tag` | `title, sub, anchor, offset [px]` | dark name card pinned to a 3D point ("ADAM POLO / PASSENGER · ROW 13") |
| `callout` | `text, anchor, offset, side left/right, color` | red label with a pointer ("DRONE") |
| `title` | `text, pos` | white bold title with a red plus ("WHAT HAPPENED NEXT") |
| `stamp` | `text, pos, color, tilt` | red mono timestamp in a double frame ("07:05 · DXB") |
| `badge` | `text, pos` | light outlined mono badge ("RECONSTRUCTION") |
`t: [start, end]` (event strings allowed). `pos` is one of `top_left`, `top_right`, `bottom_left`,
`bottom_right`, `top_center`, or `xy: [px, px]`. `anchor` takes any point spec
(`{"char":..}`, `{"object":..}`, `{"anchor": "crowd:pax:13C"}`, `[x,y,z]`). Items pop in with
overshoot and fade out.

## Assets from the user (attached images, logos, photos, 3D models)
Copy the files into `<project>/assets/` and reference them relative to the project:
* `{"type": "image", "file": "assets/ref.webp", "width": 3.0, "pos": [x,y,z], "rot3": [90,0,0], "emit": 1.0, "lit": false}`
  is an image plane with the aspect ratio preserved. Use it for posters, screens, backdrops and maps.
* `{"type": "model", "file": "assets/thing.glb", "pos": [...], "rot3": [...], "scale": 1.0, "material": "clay" | "subject" | "ghost", "color": "#hex"}`
  imports glTF/GLB, OBJ, FBX, STL, PLY or USD. The optional material override makes it match the
  clay style.
* Airliner `logo` takes an image file and puts it on the tail.

## Audio additions
SFX `knock`, `rattle`, `beep`. `{"auto": "steps", "char": "pilot", "type": "step"}` places a
footstep at every plant. Ambience `aircraft_cabin`. Music `tension`.
