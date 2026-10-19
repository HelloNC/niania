# Character specs (from reference sheets or prompts)

A character is a front-facing 2D cel "bust" drawn from a JSON spec. The style is flat colour, one
shadow tone, and dark linework. The same spec renders identically in every shot.

```json
"doc": {
  "voice": "am_michael",
  "skin": "#f6dabd", "skin_shade": "#e8bf9c", "line": "#1b2236", "lips": "#a0524a",
  "hair": {"style": "messy", "color": "#273348", "highlight": "#3e4d72", "seed": 7, "part": "left"},
  "brows": "#273348",
  "eyes": {"iris": "#4f6886", "shape": "tired", "lashes": false},
  "glasses": {"style": "rect", "color": "#1d2540"},
  "facial_hair": "stubble",
  "top": {"style": "vneck", "color": "#6aa79e", "tie": "#7a1f2b"},
  "outer": {"style": "labcoat", "color": "#f4f2ec"},
  "accessories": ["stethoscope", "pen_pocket", "badge"],
  "stethoscope_color": "#d9463c", "mug_color": "#e05a48", "badge_color": "#2d6fd6",
  "expression": "neutral"
}
```

| key | options |
|---|---|
| hair.style | `messy` (spiky crown + swept fringe), `short`, `long` (curtains to the shoulders), `bun`, `curly`, `bald` |
| hair.part | `left` / `right`; `seed` changes the messy spikes and strands |
| eyes.shape | `normal`, `tired` (heavier lids), `round`, `sharp` |
| glasses.style | `rect`, `round`, `none` |
| facial_hair | `none`, `stubble`, `beard` |
| top.style | `vneck` (scrubs), `tshirt`, `hoodie`, `shirt_tie` (`tie` colour) |
| outer.style | `labcoat`, `jacket`, `blazer`, `none` |
| accessories | `stethoscope`, `pen_pocket`, `badge`; a mug appears with the `hold_mug` gesture |

## Workflow with a reference sheet
1. Read the sheet. Note the hair silhouette, glasses, eye shape, outfit layers, props and default
   expression.
2. `studio2d.py palette assets/sheet.png x,y x,y ...` and sample the hair (dark and highlight), skin
   (lit and shade), each clothing layer and each prop. Copy the hex values in.
3. `studio2d.py sheet <project> <id>`, then compare the result with the reference side by side. Adjust
   colours, style choices and seed. If something essential is missing (a hat, a ponytail, a scarf),
   add it to `engine/puppet.py` as a new option rather than leaving it out.
4. Expressions in the reference (smile, worried, surprised, exhausted…) map to `expr` presets of
   the same name.

## Without references
Build the spec from the prompt (age, role, outfit, colours). Give each character one strong
clothing colour so silhouettes stay distinct in two-shots, then check with `sheet` the same way.
