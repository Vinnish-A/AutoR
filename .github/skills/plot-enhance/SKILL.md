---
name: plot-enhance
description: Enhance biomedical figure prompts before image generation. Read the source manuscript, infer missing molecules, cells, tissues, and anatomical relationships, and output a long, scientifically constrained English prompt in a BioRender × Nature Reviews style for downstream plotting.
version: 1.3.0
author: Vinnish-A/AutoR
license: MIT
tags: ["biomedical", "figure", "prompt-enhancement", "nature-reviews", "biorender"]
---

# plot-enhance

Use this skill **immediately before** `autor plot` / `autor.plot.generate_plot()` for biology, medicine, anatomy, immunology, neuroscience, oncology, or translational figures.

## Goal

Do **not** draw first, and do not create manual PIL/SVG/HTML drawing scripts as substitutes. First reconstruct the real biological scene from domain knowledge, fill in the missing structures that must exist, constrain their locations and interactions, and only then write the final prompt for `autor plot`.

The priority order is:

1. **Scientific correctness**
2. **Structural completeness**
3. **Clarity for review-style communication**
4. **Visual polish**

If a detail is uncertain, simplify it instead of inventing a speculative structure.

## Default figure set for review-style requests

When the user asks for a figure set from a manuscript, review draft, or `final.md`, default to extracting and designing the following figure types unless the user explicitly narrows the scope:

**Comparison images**
   - Organize each figure around one high-value contrast theme only.
   - Typical themes include conceptual landscapes, target-antigen comparisons, platform comparisons, main obstacles versus solution strategies, and clinical-trial progress comparisons.
   - Keep them synthesis-heavy and detail-light: enough to show the difference, not enough to become a dense catalog.

When generating multiple figures, keep overlap low. The overview figure should explain the manuscript architecture, the conceptual-landscape figure should crystallize the strongest viewpoint, and the comparison figures should separate different contrast themes instead of repeating the same logic with minor relabeling.

## Mandatory reading + subagent workflow

When the user provides a manuscript, workspace, `final.md`, section draft, or any substantial review text:

1. **Do not rely on a short one-pass summary.**
2. **Launch a dedicated subagent using GPT-5.4** to read the source text.
3. The subagent must extract the strongest visualizable comparative, qualitative, mechanistic, and conceptual content.
4. The subagent must think through biological structure, layout, and label hierarchy before writing the final prompt.
5. The final prompt should be materially **longer and more specific** than a short image-model instruction.

Preferred source priority:

- `workspace/<name>/final.md`
- review draft markdown provided by the user
- `table-figure-plan.md`, `evidence-ledger.md`, and `reference-map.json` if they help figure design

If a full manuscript is available, do not skip reading it. The figure prompt must be grounded in the manuscript's actual argument structure, not only in the figure title.

When the manuscript is a review or synthesis piece, the subagent must also identify:

- the one best candidate for the overview image,
- the one best candidate for the most valuable conceptual landscape,
- the 2-3 strongest comparison-worthy themes that can be expressed visually rather than textually.

## Prompt length and richness requirements

The final English prompt must be **substantive**, not minimalist.

Target characteristics:

- usually **400-800 words** for a single complex review figure
- includes explicit compartments, cell types, molecules, and directional processes
- includes panel structure when the figure is multi-panel
- includes label priorities and visual hierarchy
- includes stylistic constraints and negative constraints
- includes what to simplify and what to emphasize

Avoid shallow prompts such as:

- "Draw CAR-T cells killing glioma cells in the brain."
- "Create a comparison table of antigens."

Instead, specify:

- which anatomical compartments are shown
- which cells occupy each compartment
- which targets are membrane-bound and on which cells
- which suppressive mechanisms are extracellular versus cell-bound
- which arrows represent trafficking, killing, exhaustion, inhibition, or escape
- which dimensions define rows and columns in a table-like figure
- which parts deserve enlarged emphasis versus background treatment

## Mandatory style target

Every enhanced prompt must enforce the following visual style:

- **BioRender-like and Nature Reviews-like**
- High-end editorial scientific illustration
- Clean 2D vector schematic
- Flat, vectorized, clean editorial composition
- Flat shapes with minimal shading
- White or light neutral background
- Restrained color palette, low texture or no texture
- Restrained low-saturation palette
- Crisp compartment boundaries and readable labels
- Consistent stroke width
- Consistent icon style
- Consistent arrow style
- Grid-based alignment with generous whitespace
- Clear 3-level visual hierarchy: primary mechanism, supporting modules, concise labels
- Academic review figure layout, not concept art
- No photorealism, no sci-fi lighting, no cinematic effects

The aesthetic target is a polished review-article mechanism diagram that looks like a top-tier review journal figure: elegant, restrained, print-friendly, professional, and clearly designed by a biomedical illustrator. It must not be flashy, cinematic, decorative, glossy, or poster-like.

## Mandatory biological completion

Before writing the final prompt, infer and complete all biologically necessary objects and their spatial relationships.

You must identify and place, when relevant:

- **Molecules**
  - membrane proteins
  - intracellular proteins
  - soluble cytokines / chemokines / ligands
  - extracellular-matrix components
- **Cells**
  - tumor cells
  - immune cells
  - stromal cells
  - endothelial / epithelial / glial / neuronal cells when required by the topic
- **Tissues / anatomical structures**
  - vessel lumen and endothelium
  - basement membrane / extracellular matrix
  - parenchyma / stroma
  - organ-specific barriers and spaces, such as blood-brain barrier, meninges, ventricles, synapse-adjacent space, marrow niche, lymphoid structure, and so on

For every object, decide:

- what it is
- where it belongs
- what it touches or separates from
- whether it should be enlarged, simplified, cross-sectioned, or abstracted

## Scientific constraints

The enhanced prompt must obey all of the following:

- Membrane proteins stay on membranes
- Secreted factors stay extracellular unless receptor binding or uptake is explicitly shown
- Intracellular signaling nodes stay inside the correct cell
- Cell morphologies and size ratios remain biologically plausible
- Tissue layers and barriers follow real anatomy
- Arrows represent real processes only: migration, secretion, trafficking, activation, inhibition, killing, differentiation, antigen presentation, clonal expansion, exhaustion, barrier penetration, and similar
- Mechanistic logic must match established biology
- Cross-talk must connect the correct source and target compartments
- If a mechanism requires an intermediate structure, include it

## Negative constraints

The enhanced prompt must explicitly forbid:

- nonexistent biological structures
- extra membranes, cavities, ducts, or channels that do not belong there
- lava, coral, crystal, fractal, or other decorative textures
- glowing energy fields, lasers, holograms, sci-fi beams
- mechanical, robotic, cyberpunk, or metallic components unless the user explicitly asks for a device
- alien-looking cells or absurd size ratios
- glossy 3D rendering
- plastic texture
- lens flare
- neon glow
- sci-fi biotech style
- poster-like composition
- excessive gradients
- cluttered annotations
- too many arrows
- redundant icons
- AI-art look
- clip-art look

## Figure design rules

When the requested figure is a review figure:

- prefer a central mechanism axis in the middle
- place upstream regulators on the left and/or top
- place downstream effects on the right and/or bottom
- arrange supporting modules symmetrically but not rigidly
- keep the total module count to 6 or fewer unless the user explicitly needs more
- keep one clear topic per panel
- minimize repeated labels
- prefer left-to-right or top-to-bottom causal flow
- use comparison grids when the content is comparative
- use compartment bands or layered backgrounds when the mechanism is anatomical
- show only the key entities needed for interpretation
- make the panel division explicit when more than one mechanism is shown
- use concise labels only
- prioritize clarity over completeness
- keep labels normalized and publication-like, not chatty
- if the paper argues a hierarchy of barriers or strategies, reflect that hierarchy directly in the visual structure

### Special rules for overview images

- compress the paper into one dominant structural idea
- emphasize argument architecture rather than exhaustive mechanism listing
- keep the number of major modules limited and editorially clean
- make the main through-line visible at first glance
- use only the minimum labels needed to orient the reader
- avoid turning the overview into a crowded mini-atlas

### Special rules for conceptual-landscape images

- choose the manuscript's most important conceptual synthesis, not just its easiest mechanism
- make spatial organization carry the message before labels do
- keep the composition balanced, with well-proportioned objects and modules
- avoid label-heavy or caption-dependent expression
- use shape, distance, grouping, enclosure, and directional emphasis to show the key viewpoint

### Special rules for comparison images

- each comparison image must revolve around one comparison question only
- try diverse layouts across figures: opposed halves, mirrored modules, radial contrasts, stacked trajectories, lane-based progressions, spatial gradients, or matrix-style synthesis panels
- use visual structure first: grouping, spacing, icons, process arrows, module shape, hierarchy, and spatial separation should explain the contrast before labels do
- keep text sparse and normalized; readers should first understand the difference, then read a small number of labels
- do not rely on large paragraphs, dense callouts, or high-density cell text to carry the meaning
- if the content can only be understood by reading many words or scanning many cells, it should become a table instead of a diagram
- for clinical-trial progress comparisons, show stage progression, attrition, modality grouping, or translational bottlenecks through layout rather than through text blocks

When the requested figure is table-like:

- do not render a literal spreadsheet screenshot
- turn it into a clean vector comparison matrix
- define explicit row and column dimensions
- keep wording short, normalized, and parallel
- use color sparingly for category coding or emphasis only
- ensure every row and column encodes a meaningful analytical comparison
- prefer synthesis over raw transcription from the manuscript
- if a caption-level takeaway exists, encode it in the layout and emphasis

When deciding between a diagram and a table:

- use a **diagram** when the main value is contrast, hierarchy, flow, grouping, spatial relation, or strategy structure
- use a **table** when the main value depends on precise text, many attributes, or cell-by-cell reading
- never force a text-dominant comparison into a pseudo-diagram

## Required workflow

For every request, follow this sequence:

1. Identify the biological question and figure type.
2. Read the source text deeply; if a manuscript is available, use a GPT-5.4 subagent to read and reason over it.
3. Extract the manuscript's strongest figure-worthy comparisons, mechanisms, and conceptual claims.
4. Decide whether each candidate should be an overview image, conceptual-landscape image, comparison image, or table.
5. Infer the real molecules, cells, tissues, and anatomical compartments that must exist.
6. Resolve spatial hierarchy, panel logic, causal direction, and comparison logic.
7. Remove speculative or biologically unjustified elements.
8. Convert the result into a long, production-ready **English** image-generation prompt that explicitly encodes the editorial style, composition hierarchy, spacing discipline, and print-friendly restraint above.
9. Add a compact negative-prompt block.

## Required output format

Return exactly these sections:

### Figure intent

One sentence describing what the figure should explain.

### Biological structure model

List the key compartments, cells, molecules, and required spatial relations.

### Layout plan

Describe panel logic, reading direction, label hierarchy, module count, and where the central mechanism axis, upstream regulators, downstream effects, and supporting modules will sit.

### Final English prompt

Write one long, production-ready English prompt for the image model. It must explicitly request a polished review-article mechanism diagram that is sharp, legible, balanced, and visually calm.

### Negative constraints

Write one compact English negative block that explicitly excludes glossy 3D, plastic surfaces, neon or cinematic effects, poster-like layouts, clutter, redundant icons, excessive arrows, AI-art appearance, and clip-art appearance.

### Suggested filename

Provide a short snake-case or kebab-case stem.

## Example use

If the user asks for a glioma CAR-T overview figure, do not jump straight to “draw CAR-T cells attacking glioma”.

First infer whether the figure needs:

- glioma cells in brain parenchyma
- CAR-T cells in vessel / perivascular / tumor regions
- endothelial barrier if trafficking is shown
- immunosuppressive microenvironment components such as macrophages / microglia / TGF-beta / PD-L1 when they are central to the message
- antigen localization on tumor-cell membrane
- cytokine directionality in extracellular space

Then write the final English prompt under those constraints.

If the user asks for a **set of review figures from `final.md`**, the skill should:

1. use a GPT-5.4 subagent to read the manuscript,
2. identify 1 overview figure, 1 most valuable conceptual-landscape figure, plus the 2-3 most synthesis-rich comparison figures,
3. generate long English prompts for each figure,
4. keep overlap low between figures,
5. make the overview figure logic-driven, the conceptual-landscape figure viewpoint-driven, and the comparison figures contrast-driven,
6. convert text-dominant comparisons into tables rather than forcing them into diagrams.
