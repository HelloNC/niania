# niania - Claude Code animation plugin

One premise in, a finished animated MP4 out. Rendering, narration and sound run locally
(Blender, Kokoro TTS, ffmpeg); no API keys or paid services. Full description: [plugins/niania/README.md](plugins/niania/README.md).

## Install
```bash
claude plugin marketplace add <github-user>/<repo>      # or a local path to this folder
claude plugin install niania@niania-plugins
claude plugin list            # niania@niania-plugins, enabled, user scope
```
After editing the source in `plugins/niania/`, bump `version` in `plugins/niania/.claude-plugin/plugin.json`
and `.claude-plugin/marketplace.json`, then run:
`claude plugin marketplace update niania-plugins` and `claude plugin update niania@niania-plugins`.
The installed copy lives in `~/.claude/plugins/cache/niania-plugins/niania/<version>/`.

## Use (Claude Desktop -> Code tab, or the claude CLI)
Start a **new** session (plugins load when a session starts) and type:
```
/niania:create-video A shy robot learns to dance in the rain --duration 30
```
You can also attach reference images and say what you want; the skill picks the look from them.
Output: `./animation_projects/<slug>/final/<Title>.mp4` plus `story.md`, `timeline.json`,
`build/scene.blend`, audio stems, per-shot renders, QC reports and contact sheets.

Re-render one shot after a fix:
```bash
python3 ~/.claude/plugins/cache/niania-plugins/niania/0.2.0/engine/tools/studio.py render <project> --shot s2_catch
python3 ~/.claude/plugins/cache/niania-plugins/niania/0.2.0/engine/tools/studio.py assemble <project>
```

## Share with friends
Send `niania-share.zip` (plugin only; demo renders are excluded). They unzip it, e.g. to `~/niania`, then:
```bash
claude plugin marketplace add ~/niania
claude plugin install niania@niania-plugins
```
(or host the same files in a GitHub repo and use `claude plugin marketplace add <user>/<repo>`).
They need Blender 4.2+ (free) in /Applications or on PATH; on first use niania runs a setup check and
asks before installing the free Kokoro voice + ffmpeg (~1 GB, no API keys).

## Two looks (v0.2)
* **Cel/silhouette** (`style` default): rim-lit characters with faces, street/room/park sets. Demo: `demo/cup_catch`.
* **Clay reconstruction** (`"style": "clay"`): white world, faceless mannequins (subject/ghost/clay),
  seated crowds, aircraft cabin/cockpit cutaway, airport, desert runway, white studio, and broadcast
  graphics (name tags, callouts, titles, stamps, badges). Demo: `demo/cockpit_lockout`.

## Your own assets
Attach images or point to files: they go in `<project>/assets/` and are used as image planes
(screens, backdrops, maps), airliner tail logos, or imported 3D models (glTF/GLB, OBJ, FBX, STL, PLY, USD).
Claude cannot generate images or video; everything is built procedurally or from files you provide.

## Layout
```
plugins/niania/
  .claude-plugin/plugin.json
  commands/create-video.md                /niania:create-video
  skills/animation-studio/SKILL.md        workflow + honesty rules
  skills/animation-studio/reference/      timeline schema, style/storyboard guide, QC + revision
  engine/studio/                          Blender-side engine
    character.py   rig (IK legs/arms, 10 finger bones per hand, face shape keys, springs)
    perform.py     verbs -> balance, steps, look-at, hand specs, grip solver, overlap
    world.py       props, physics on story time (slow-mo), place/topple/catch, grips
    camera.py fx.py sets.py props.py materials.py geom.py tracks.py build.py qc.py
  engine/tools/                           studio.py CLI, audio.py, Blender entry scripts
  templates/                              starter timeline, story template, cup-catch demo
demo/cup_catch/                           first demonstration project
```
