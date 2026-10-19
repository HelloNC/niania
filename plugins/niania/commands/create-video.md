---
description: Turn one premise into a finished animated MP4 (script, storyboard, characters, animation, narration, sound, export)
argument-hint: <premise> [--duration 30] [--size 1920x1080]
---

Create a complete animated video from this premise:

$ARGUMENTS

Use the **animation-studio** skill of the niania plugin (load it now) and follow its steps end to end without asking
for approval per scene:

0. If the user attached reference images or models, look at them first, decide the style (cel
   silhouette vs clay reconstruction), and copy any files you will use into the project's `assets/`.
1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/engine/tools/studio.py doctor`. If something is missing, explain it and ask before installing anything.
2. Create the project at `./animation_projects/<short-slug>/` (in the current working folder) with
   `studio.py new` using the duration/size from the arguments (default 30 s, 1920×1080).
3. Write `story.md`: beat sheet, narration script, storyboard, blocking. Then write `timeline.json`.
   Keep one cast spec per character for consistency.
4. Iterate `lines → build → qc → preview` and **look at the preview sheet** until QC is clean and the
   acting reads.
5. `mix → render (background) → assemble → check`. Read the final contact sheet.
6. Reply with the MP4 path, the editable sources, the QC summary, and any known limitations.
   Intermediate work stays in the project, so single shots can be re-rendered with
   `studio.py render <project> --shot <name>` followed by `studio.py assemble <project>`.
