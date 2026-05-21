# Academic Writing

AutoR includes several agent skills to assist with academic writing. These work best through Claude Code's natural language interface.

## Available Writing Skills

### Literature Review (`/literature-review`)

Generates a structured literature review from papers in a workspace. Organizes by topic, builds narrative, identifies gaps, and exports BibTeX.

### Paper Writing (`/paper-writing`)

Assists with drafting specific paper sections: Introduction, Related Work, Method, Results, Discussion, Conclusion. Uses workspace papers for citations.

### Writing Polish (`/writing-polish`)

Polishes academic prose — removes AI-generated patterns, improves clarity, adapts to a target journal style. Supports English and Chinese.

### Review Response (`/review-response`)

Drafts point-by-point responses to peer reviewer comments, locating evidence from workspace papers and the manuscript.

### Research Gap (`/research-gap`)

Identifies unexplored areas and open questions by analyzing literature in a workspace through topic clustering, citation analysis, and cross-paper comparison.

### Citation Check (`/citation-check`)

Verifies citations in AI-generated or human-written text against the knowledge base. Catches hallucinated references and wrong metadata.

## Workflow

1. Create a workspace: use `/workspace` to organize relevant papers
2. Check evidence readiness before planning:

```bash
autor ws status <name> --papers
autor ws export-evidence <name> -o workspace/<name>/evidence.json
autor enrich-l3 --workspace <name> --only-missing
```

3. Optionally screen the workspace before writing:

```bash
autor ws screen <name> --criteria "topic boundary and exclusion rules" --target 150 -o workspace/<name>/screening.json
```

Add `--apply` only after inspecting the screening report.

4. Generate the canonical planning skeleton:

```bash
autor ws plan-package <name> --title "Review title" --criteria "topic boundary"
```

This creates `references.bib`, `reference-map.json`, `review-plan.md`, `evidence-ledger.md`, and `table-figure-plan.md`. The files are a stable handoff scaffold, not a substitute for scholarly section planning.

During planning, set `citation_policy` in `reference-map.json` for each retained paper: `must_cite`, `cite_if_relevant`, `background_only`, or `do_not_cite`.
For figure planning, reserve 7-8 figures for a full review and 4-5 figures for a mini/focused review. Every planned figure should require PlotEnhance before generation and must be generated through `autor plot` / `autor.plot.generate_plot()` rather than manual drawing scripts.

5. Use writing skills via Claude Code: `/<skill-name>`
6. Before final export, check that required citation keys entered the manuscript:

```bash
autor ws citation-coverage <name> --manuscript workspace/<name>/write.md --require must_cite --fail-if-missing
autor ws figure-status <name> --fail-if-missing
```

Use `--require retained` without `--fail-if-missing` when you want an audit of retained-but-unused literature.

7. Output files are saved in `workspace/<name>/`
