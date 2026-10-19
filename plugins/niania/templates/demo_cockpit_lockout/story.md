# Cockpit Lockout (reconstruction-style test)

**Premise:** A news-style reconstruction. The captain steps out and finds himself locked out of the cockpit while the first officer stays at the controls.
**Format:** 18 s, 1920×1080, 24 fps, 3 shots. **Look:** `"style": "clay"`. A white clay airliner with faceless mannequins: red = first officer, blue = captain, cyan ghosts = passengers. Broadcast graphics. Built from the user's reference images (cabin aisle, cockpit cutaway, airport miniature).
All names and the flight are fictional.

## Beats
| time | beat |
|---|---|
| 0–4.6 s | Aisle push-in through a full clay cabin. The tag "LEO MARSH · PASSENGER · ROW 13" pins to seat 13C (light blue) |
| 4.6–7.3 s | Exterior cutaway of the nose section above the clouds. The captain walks up the aisle (six steps, weight shifts) under the "WHAT HAPPENED NEXT" title and the 07:05 stamp |
| 7.3–8.6 s | Right hand on the lever, he pulls twice. The door rattles with every pull and his hand stays on the handle |
| 8.9–10.2 s | Left fist knocks three times (shoulder pops) |
| 9.35–11 s | The first officer slowly turns his head toward the door, then back to the panel, leaning in |
| 11.6–18 s | Insert from the cabin side: hand on the lever, the door rattles again, "07:07 · DOOR LOCKED" |

## Narration (`bm_george`, Kokoro, local)
0.4 "Flight four seventeen. Among the passengers, Leo Marsh, in seat thirteen C." · 5.7 "At five past seven, the captain left the cockpit." · 8.9 "When he came back, the door would not open." · 12.4 "Inside, the first officer didn't move." · 15.1 "And no one in the cabin knew."

## Revision log
| round | issue | fix |
|---|---|---|
| 1 | Cutaway boolean silently failed (non-manifold nose) | the fuselage is now built with the cut region left open, then solidified |
| 2 | Inner cockpit and cabin walls hid the interior | matching cut variants for both shells |
| 3 | The cabin part of the cut never opened | the straight fuselage section had a single ring; now it has rings every 0.8 m |
| 4 | Graphics invisible | the overlay camera clipped at exactly 100 units, and the preview compositing broke `/private` paths |
| 5 | One set needed for interior and cutaway shots | furniture/shell split plus per-shot `variant`/`hide` lists |
| 6 | Shot 3 camera started inside a passenger's head | camera moved, front-row passengers hidden in that shot |
| 7 | Pilot's arm beyond reach, then hidden by the bulkhead | blocking moved, left bulkhead panel moved into the shells (low panel in cutaway) |
| 8 | 61 m/s² hip jolt while walking | weight transfer now flows between steps |
| 9 | Fingers into the door | lever given a 4 cm standoff, palm-down pose, hand contacts recorded for QC |
