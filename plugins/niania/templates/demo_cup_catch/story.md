# Cup Catch

**Premise:** A stylized character notices a falling cup, shifts her weight, catches it, and reacts.
**Format:** 15 s, 1920×1080, 24 fps, 3 shots. **Look:** `cafe_street` at dusk, backlit silhouette with warm rim light.

## Cast
| id | spec | movement personality |
|---|---|---|
| mia | red hoodie, yellow beanie with pompom, silhouette body | relaxed and dreamy, then very fast, then sheepish |

## Beat sheet
| # | time | beat |
|---|---|---|
| 1 | 0–1.4 s | Mia savours her coffee while watching the sunset (cup raised, eyes closed, shoulders rise with the breath) |
| 2 | 1.45–2.2 s | Without looking, she sets the cup down with its base hanging over the table edge |
| 3 | 2.4–2.7 s | The cup teeters (pivot physics) and tips off. A small tick sound makes her eyes snap to it. Time slows to 0.1× |
| 4 | 2.7–4.25 s | Anticipation (rise, lean back) → weight onto the left foot → right step outward → lunge, left arm out for balance, right hand converges on the tumbling cup |
| 5 | 4.25 s | Catch: the fingers close on the cup body, the hand gives with the impact, and droplets spill to the ground |
| 6 | 4.3–7.9 s | Relief, she rises with the cup and pulls it in, time returns to normal, "Phew." with a shoulder drop, two recovery steps |
| 7 | 7.9–9.4 s | She looks at the cup proudly, then at the camera, and gives a triumphant lift that stops sharply |
| 8 | 9.1–9.4 s | Momentum flicks one drop onto her cheek → wince |
| 9 | 9.7–12.6 s | Sheepish grin → laugh (shoulder and head bounces) |
| 10 | 12.8–15 s | Content smile, raises the cup, gazes off down the street |

## Narration (Kokoro `am_michael`) and dialogue (`af_heart`)
* 0.35 s — "Mia never looks away from a sunset."
* 3.30 s — "But in the half second it takes a cup to fall, her body is already moving." (speed 1.1)
* 7.20 s — Mia: "Phew."
* 7.85 s — "Not a single drop spilled."
* 10.05 s — "Well... almost."
* 12.70 s — "Reflexes, ten. Coffee, nine."

## Storyboard
| shot | time | size and angle | camera motivation | action | cut reason |
|---|---|---|---|---|---|
| s1_wide | 0–3.0 s | wide, 3/4 front, backlit by the sunset | slow push-in toward the table (sets up the cup) | savour, blind placement, topple | cut on the action as the cup tips |
| s2_catch | 3.0–7.6 s | low side angle from her right (same side of the action line) | the camera tilts down after the falling cup, then tilts up as she rises | notice, weight shift, step, lunge, catch, rise | cut on the "Phew" settle |
| s3_reaction | 7.6–15 s | medium close-up, 3/4 front | slow push-in on the reaction | pride, flick, wince, laugh, toast | end |

## Revision log
| round | issue (found by QC or by looking at the preview) | fix |
|---|---|---|
| 1 | Hand beyond reach by up to 27 cm: the grip was chosen before the shoulder position was known | estimate the shoulder from the stance |
| 2 | Knees bent backward and elbows flared (QC intersections, visible in renders) | the IK pole-angle sign was inverted, fixed in `character.py` |
| 3 | Forearm passed through the held mug | grip and hold twist chosen by a cost function (wrist bend, forearm clearance, handle opposite the palm), lower elbow poles |
| 4 | Head went into the table during the lunge, and the catch was unreadable from the front | step outward and turn toward the cup, moved the camera to her right side |
| 5 | 81 m/s² jolt at 7.25 s from two steps fighting over weight | second step moved later, weight shift starts after the first plant |
| 6 | Chest whipped 45° in 3 frames, face turned away in shot 3 (look yaw singular below the head, unstable filter, unwrapped angle) | exact critically damped filter, yaw hold near vertical, wrap and clamp |
| 7 | Thumb in the mug on release, cup grazing the thigh after the catch | back the hand off before opening, route the pull-in through an outward waypoint |
| 8 | 4 mm heel motion at heel-strike | heel-strike now pivots about the heel |
| 9 | Hat cropped at the top of frame (QC tested a point below the hat) | QC now tests the crown, and all three shots were reframed |
