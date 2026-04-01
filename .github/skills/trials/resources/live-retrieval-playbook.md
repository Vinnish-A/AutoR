# Workspace-First Live Retrieval Playbook

Follow this workflow when the environment can access ClinicalTrials.gov. The key is not just “get results,” but to write them reliably into the current workspace.

## Step 0: Bind the workspace first

If the user is already inside a review or project workflow, prefer reusing that workspace. Otherwise, create one first:

```bash
autor ws init <name>
mkdir -p workspace/<name>/trials/<query-slug>
```

Write all later trial outputs to:

```text
workspace/<name>/trials/<query-slug>/
```

## Step 1: Generate and save the search plan

```bash
python3 tools/build_search_plan.py --theme "sequential CAR-T therapy" \
  > workspace/<name>/trials/<query-slug>/search-plan.json
```

This step saves:

- inferred `condition` / `intervention`
- normalized `phase`, `status`, and `location`
- expansion of modifiers such as `sequential`, `maintenance`, `bridging`, and `consolidation`
- provider targets for ClinicalTrials.gov, CTIS/EU CTR, ChiCTR, and WHO ICTRP

## Step 2: Run the ClinicalTrials.gov retrieval

```bash
python3 tools/retrieve_trials.py \
  --theme "sequential CAR-T therapy" \
  --output workspace/<name>/trials/<query-slug>/trials.json
```

The live retriever will:

1. generate one or more API v2 request variants
2. paginate with `nextPageToken`
3. deduplicate by NCT ID
4. apply local filters for phase, status, location, and theme modifiers

## Step 3: Extract PICO conservatively

Each trial should retain at least:

- `P`: conditions, enrollment, age/sex restrictions, eligibility excerpt
- `I`: interventions and arms
- `C`: control description or single-arm note
- `O`: primary endpoints and posted effect summary (if available)

If no posted results exist, keep the treatment effect as `unknown`.

## Step 4: Generate a Markdown summary and save it to the workspace

```bash
python3 tools/render_trial_summary.py \
  workspace/<name>/trials/<query-slug>/trials.json \
  > workspace/<name>/trials/<query-slug>/trials-summary.md
```

Recommended columns:

- NCT ID
- title
- P
- I
- C
- O
- phase
- status
- location

## Step 5: Extend to other registries if needed

ClinicalTrials.gov is currently the primary source with automated retrieval. If broader coverage is needed, continue from the provider targets recorded in `search-plan.json`:

- CTIS / EU CTR: public portal + legacy EUCTR portal
- ChiCTR: public English search page
- WHO ICTRP: public portal or on-demand web service access

## Step 6: Connect it to the review workflow

If the trial retrieval supports a review or planning task:

- keep `trials-summary.md` as an auxiliary evidence file inside the workspace
- later `/plan` or `/literature-review` runs can read it directly
- if related papers are also needed, continue with:

```bash
autor ws search <name> "<condition> <intervention>"
autor ws add <name> <matched-paper-id...>
```

## Offline testing

If the current environment cannot access the network, use the fixture—but **still write the outputs into the workspace**:

```bash
python3 tools/retrieve_trials.py \
  --theme "sequential CAR-T therapy" \
  --input-response examples/cart-sequential-api-sample.json \
  --output workspace/<name>/trials/<query-slug>/trials.json

python3 tools/render_trial_summary.py \
  workspace/<name>/trials/<query-slug>/trials.json \
  > workspace/<name>/trials/<query-slug>/trials-summary.md
```
