# QC and revision workflow

Run in this order after every change to `timeline.json`:
`build` → `qc` → `preview` (look at the sheet) → fix → repeat, and only then `mix` → `render` →
`assemble` → `check`.

## Automated checks (`studio.py qc` → build/qc.json, plus build notes)
| check | threshold | usual cause | fix |
|---|---|---|---|
| build note `hand X beyond reach by d` | any d > 0.01 | target farther than arm reach (≈0.51 m) | move the target closer (`hold.at`), add `hips` crouch, chest `bend`, or `step` toward it; for catches lower `at_height` or move the step |
| build note `leg overreach` | any | feet too far apart | smaller step |
| `foot_slide` | > 2 mm/frame while planted | foot moved outside a `step` | only move feet with `step` |
| `ik_gap` | > 8 mm | limb can't reach the target | as for reach |
| `grip_clip` | finger tip > 4 mm inside object | wrong grip radius | use the prop's `grip_body` |
| `intersect` | any overlap (hands on held objects ignored) | body through table, forearm through mug, head into props | restage (move the table/character, change `hold.at` out/fwd), raise a camera to hide a near miss only as a last resort |
| `ground` | > 6 mm below the floor | crouch too deep for the foot pitch | reduce crouch |
| `top_accel` | review anything > 40 m/s² that isn't intentional (reflex snaps) | abrupt motion: two verbs fighting, too-short `dur` | lengthen `dur`, use `auto`/`inout`, remove overlapping verbs |
| `framing` | head outside frame | camera aim/lens | change shot keys, lens, or aim offset |

## Visual review (always do this; the numbers do not judge acting)
Read `preview/sheet.png` (6 frames per shot) and inspect:
* Does each shot read in silhouette? Is the key object (cup, ball) visible at the key moment?
* Feet planted? Hands touching what they hold? Nothing passing through props?
* Do eyes lead the action? Is there anticipation before the big move, and a settle after?
* Are faces visible when the beat is emotional? (Otherwise move the camera to the front side,
  on the same side of the action line.)
* Do lighting and colour stay consistent between shots?
For a close inspection of one moment, render single frames: `studio.py preview <p> 98,104,110 --pct 60`.

## Re-rendering only what failed
* Shots render to `render/<shot>/fNNNN.png`. Re-render one shot with
  `studio.py render <p> --shot s2_catch`, then `assemble` (other shots are reused).
* Timing changes that move events (catch time, steps) also move SFX. Re-run `mix`.
* Narration text changes need `lines` → `build` (lip-sync) → `mix`.
* Log each round in `story.md` → *Revision log*.

## Media checks (`studio.py check`)
These verify duration, frame count, resolution, audio presence and length, black frames, and
narration onset vs plan (± 0.12 s). They also write `final/contact_sheet.jpg` (1 fps). Read the
contact sheet before delivering.
