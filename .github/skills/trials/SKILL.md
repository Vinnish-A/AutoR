---
name: trials
description: Retrieve structured clinical trial records by disease, intervention, phase, status, location, or a free-text treatment theme, and automatically save the search plan, normalized JSON, and Markdown summary into a workspace. Use when the user wants trial retrieval that stays attached to the current review workflow.
license: MIT
---

# Clinical Trial Retrieval with Workspace Output

Use this skill to retrieve structured clinical trial records and **write the results directly into the current workspace**, rather than leaving them in a temporary directory, example directory, or console output.

It is suitable for requests like:

- “Find clinical trials related to CAR-T sequential therapy.”
- “Find Phase 3 trials of pembrolizumab in NSCLC.”
- “Retrieve PD-1 trials that are recruiting in China.”
- “Organize the clinical trial evidence for trastuzumab in breast cancer; I want to use it later in a review.”

## Where this skill fits in the current workflow

- It is **not** a paper-ingestion tool; it retrieves trial-registry records, not entries for `data/papers/`
- It **is** a workspace-level supporting-evidence tool; by default, all final outputs should be written to `workspace/<name>/trials/`
- If the user later wants to draft a review, create a plan, or build tables, these trial outputs should live in the same workspace and be mapped into `reference-map.json`, `evidence-ledger.md`, and `table-figure-plan.md`

## Prerequisites

- Ideally, the user should specify a **workspace** (`--ws NAME`)
- If the user does not specify one, but is clearly already working within a review/project workflow, prefer reusing the existing workspace
- If there is no suitable workspace, create one first:

```bash
autor ws init <name>
```

- The request should provide at least one of the following, either explicitly or inferable from free text:
  - `condition` / `disease`
  - `intervention` / `drug`
  - `theme`

## Input parameters

Required information (at least one item must be explicit or inferable):

- `condition` / `disease`: disease name, e.g. `non-small cell lung cancer`
- `intervention` / `drug`: intervention / drug, e.g. `PD-1`, `Pembrolizumab`, `CAR-T`
- `theme`: free-text topic, e.g. `CAR-T sequential therapy`

Optional filters:

- `phase`: e.g. `Phase 1`, `Phase 2`, `Phase 3`
- `status`: e.g. `Recruiting`, `Active, not recruiting`, `Completed`
- `location`: e.g. `China`, `United States`, `Global`

## Output-directory convention

By default, write each retrieval run to:

```text
workspace/<name>/trials/<query-slug>/
```

`<query-slug>` should be derived from the theme, disease, intervention, or key filters so that existing results are not overwritten. For example:

- `workspace/immunotherapy-review/trials/cart-sequential/`
- `workspace/nsclc-review/trials/pembrolizumab-nsclc-phase3/`

At minimum, this directory should contain:

- `search-plan.json`: normalized query + provider targets + API request plan
- `trials.json`: normalized trial results in JSON
- `trials-summary.md`: Markdown summary for downstream writing and table-building

If you need to add manual judgment, you may also create:

- `screening-notes.md`: inclusion/exclusion notes, manual remarks, anomaly records

## Workflow

### 1. Bind the workspace first

First determine which workspace should receive the results. Do not leave final outputs in `examples/`, a temporary directory, or the repository root.

If the user did not provide a workspace:

```bash
autor ws list
autor ws init <name>
```

### 2. Normalize the retrieval intent

1. Parse the user's input
2. If the user gives only a free-text theme, infer the disease / intervention whenever possible
3. Convert descriptive treatment modifiers into trial-search semantics, for example:
   - `sequential therapy` -> `sequential`
   - `bridging therapy` -> `bridging`
   - `maintenance therapy` -> `maintenance`
   - `consolidation therapy` -> `consolidation`
4. Generate one or more ClinicalTrials.gov API v2 requests

### 3. Write the search plan to the workspace first

Do not print the search plan only to stdout. Save it to the workspace first:

```bash
mkdir -p workspace/<name>/trials/<query-slug>
python3 tools/build_search_plan.py --theme "sequential CAR-T therapy" \
  > workspace/<name>/trials/<query-slug>/search-plan.json
```

### 4. Run trial retrieval and write normalized JSON into the workspace

Live retrieval:

```bash
python3 tools/retrieve_trials.py \
  --theme "sequential CAR-T therapy" \
  --output workspace/<name>/trials/<query-slug>/trials.json
```

Offline / fixture retrieval:

```bash
python3 tools/retrieve_trials.py \
  --theme "sequential CAR-T therapy" \
  --input-response examples/cart-sequential-api-sample.json \
  --output workspace/<name>/trials/<query-slug>/trials.json
```

### 5. Generate a Markdown summary and write it to the workspace

```bash
python3 tools/render_trial_summary.py \
  workspace/<name>/trials/<query-slug>/trials.json \
  > workspace/<name>/trials/<query-slug>/trials-summary.md
```

By default, `trials-summary.md` should be directly reusable in `/plan`, `/literature-review`, or manual drafting.

### 6. Connect it to the current review workflow

If this retrieval supports a review or planning task, treat the trial results as an auxiliary evidence layer inside the workspace:

- later `/plan` runs can read `workspace/<name>/trials/<query-slug>/trials-summary.md`
- later main-text drafting can use `trials-summary.md` as supporting material for trial design, enrolled populations, primary endpoints, and recruitment status
- when building review tables, fields can be pulled directly from `trials-summary.md` or `trials.json`

If the user also wants to add **related papers** into the same workspace, continue with:

```bash
autor ws search <name> "<condition> <intervention>"
autor ws add <name> <matched-paper-id...>
```

Note: **trial records are not papers**. Trial outputs belong in `workspace/<name>/trials/`, while papers still enter the workspace reference layer through `ws add`.

## Primary data source

The current implementation automatically retrieves from:

- **ClinicalTrials.gov API v2**: `https://clinicaltrials.gov/api/v2/studies`

Current filter support includes:

- `query.cond`
- `query.intr`
- `query.locn`
- `filter.overallStatus`
- `filter.advanced=AREA[Phase]...`
- `query.term` (for modifiers such as `sequential`, `maintenance`, `bridging`, `consolidation`)

## Extended data sources

The skill also records the following registries in the search plan as future expansion targets:

- **CTIS / EU CTR**
- **ChiCTR**
- **WHO ICTRP**

Notes:

- Automatic retrieval currently relies primarily on ClinicalTrials.gov
- For broader coverage, use the provider targets in `search-plan.json` for manual follow-up or future automation

## Output contract

`trials.json` should contain at least:

- `query`
- `normalized_query`
- `provider_targets`
- `api_requests`
- `results`
- `unresolved_questions`

Each result should contain at least:

- `trial_id`
- `title`
- `phase`
- `status`
- `locations`
- `pico.P`
- `pico.I`
- `pico.C`
- `pico.O`
- `evidence`

For the full machine-readable schema, see:

- `resources/output-schema.json`

## Conservative rules

- Do not invent treatment-effect conclusions
- If the source record has no posted results, record the treatment effect as `unknown`
- Do not mistake registry records for full paper-level evidence
- All reusable end-user outputs must be saved under `workspace/`, not left only on stdout

## Resources shipped with this skill

- `tools/clinical_trials_common.py`: shared logic for normalization, API calls, extraction, and scoring
- `tools/build_search_plan.py`: convert a user theme into provider targets and API requests
- `tools/retrieve_trials.py`: retrieve live or fixture JSON and write normalized results
- `tools/render_trial_summary.py`: render normalized results into Markdown tables
- `resources/output-schema.json`: machine-readable output schema
- `resources/live-retrieval-playbook.md`: a practical, workspace-oriented live-retrieval workflow
- `examples/cart-sequential-api-sample.json`: offline test fixture
- `examples/cart-sequential-results.json`: example normalized output

## Example prompts

- “Use `/trials` to retrieve clinical trials on CAR-T sequential therapy and save the results in workspace `my-review`.”
- “Use `/trials` to find recruiting PD-1 trials in China and save the results into the current workspace.”
- “Use `/trials` to list Phase 3 pembrolizumab trials in lung cancer and generate a Markdown table.”
