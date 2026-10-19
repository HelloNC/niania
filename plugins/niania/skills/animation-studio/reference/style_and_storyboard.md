# Style, acting and storyboard guide

These notes come from reviewing the user's quality reference ("What If Your Reaction Time Was 10x
Faster", Ifverse, 7:13, 24 fps). I sampled about 100 frames: a contact sheet every 12 s, dense
4 fps runs of the opening café/cup scene and a football scene, plus 92 detected cuts. Use the
principles below, not the exact designs.

## Look
* Silhouette characters: near-black bodies, big round heads, white facial marks, and **one strong
  clothing colour each** (red hoodie, yellow cap). A thin warm **rim light** separates them from
  the background. The engine reproduces this with the StudioLook rim group.
* **Complementary light.** Purple/indigo ambient with warm orange keys from windows, the sun and
  lamps. Interiors glow warm against cool exteriors.
* **Layered depth.** A foreground prop or shoulder, the mid-ground action, a lit facade, then
  silhouettes, then the sky gradient. Distant layers fade toward the horizon colour.
* **Shallow focus** on close-ups (blurred windows become bokeh). Bloom on light sources.

## Camera and editing (measured: 92 cuts in 433 s, about 4.7 s per shot)
* Establish wide and backlit, then move to a medium shot, then an insert or close-up for the
  detail that matters (hand, cup, ball). Return wide to show consequences.
* Use an overhead shot for spatial clarity when two characters interact (ping-pong, café table).
* Cut on action or on a look. Inserts are short (1–2 s). Reactions get held.
* Motivated moves: a slow push-in on realisation, a tilt or follow with a falling object, a
  low angle for heroic moments. A locked camera with a small handheld drift is the default.
* Slow motion marks the "reaction time" moments, with a timer/focus-ring graphic and a muffled
  soundscape. The engine has `time_remap` and `slowmo_filter`.

## Acting rules (apply to every beat)
1. **Eyes first.** Eyes snap to the stimulus, the head follows about 0.1 s later and the body
   last (`look` with `speed` 2–3).
2. **Anticipation.** Every big move starts with a small opposite move: a rise before a crouch,
   a lean back before a lunge (`anticipate`).
3. **Weight before steps.** Shift onto the support foot before lifting the other (`step` does
   this). Keep the hips over the support polygon. Feet stay planted unless a step moves them.
4. **Arcs and ease.** Hands travel on arcs (`arc` 0.05–0.1). Use `inout` for deliberate moves,
   `snap` for reflexes and `back` for overshoot.
5. **Follow-through and settle.** After a catch the hand gives (`give`), the body settles, and
   secondary parts (pompom, drawstrings) keep moving. Spine overlap is automatic.
6. **Contact is exact.** Use `hold`/`place`/`catch` so objects and hands share one transform.
   Never fake contact with positions that merely look close.
7. **One clear silhouette per beat.** The action must read in silhouette against a lighter
   background. Choose camera angles where limbs separate from the torso.
8. **Free hand has a job.** Balance arm out during lunges, hand on hip, gesture with dialogue.
9. **Reactions are held.** At least 0.6 s on a reaction expression before the next beat. Add
   shrug pulses for breath or laughter.

## Storyboard procedure (for a 30 s piece: 6–8 shots)
1. Write the premise as *want → obstacle → physical event → reaction → button*.
2. Beat sheet with times (see `templates/story_template.md`). Fit narration at about 2.6 words/s.
3. For every beat choose the shot size that shows the *information* (wide for space, medium for
   body acting, close-up for faces/hands) and one camera motivation.
4. Block the staging top-down in metres. Put characters near the origin. Keep the action line
   and all cameras on one side. Check reach: hand targets ≤ 0.5 m from the shoulder, and use
   `hips` crouch/`bend`/`step` to bring the shoulder closer.
5. Only then write `timeline.json`.


# Second style: news / explainer reconstruction (from the user's airline reference images)
* A **white clay world** with soft daylight and AO. Detail comes from geometry, not texture.
* **Faceless mannequins.** The subjects are one saturated colour each (red = the person acting,
  blue = the person affected). Bystanders are white clay or translucent cyan ghosts. Never more
  than 2–3 accent colours on screen.
* **Cutaways** show cause and effect in one frame (cockpit and cabin together). Aisle push-ins
  establish scale. A low insert on the hand shows the critical action (handle, button, lever).
* **Graphics carry facts:** a name tag the first time a person matters, a red callout for key
  objects, a timestamp stamp when time matters, and a title card to mark a turn. Keep text short
  and uppercase.
* **Acting:** the bodies are faceless, so staging and posture do the work. Locked-out pulling,
  knocking, a slow head turn, a still figure at the controls. Hold still moments.
* **Narration:** short factual sentences, a neutral newsreader voice (`bm_george` or
  `am_michael`), with tension music low under it.
