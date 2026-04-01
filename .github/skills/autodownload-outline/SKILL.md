---
name: autodownload-outline
description: Build a new autor workspace from a topic or outline, using AutoDownload over REST for PubMed retrieval, identifier resolution, and PDF download before ingesting the new papers into autor.
---

# Build a Workspace from a Topic or Outline

Use this skill for tasks like the following:

**The user does not yet have a autor workspace, but provides a topic, article title, section outline, or several core claims; the agent must turn that input into a real, usable workspace and use the AutoDownload REST service to complete the PDF-acquisition step.**

## Goal

Turn “a topic / an outline” into:

- a workspace with clear research boundaries
- a section-level query matrix
- a candidate-paper list with selection rationale
- papers that have already been downloaded and ingested
- a workspace that can move directly into autor writing workflows such as `plan`, `write`, and `literature-review`

## Start with structure, not downloads

After receiving a topic or outline, break it down into three layers first:

1. **Overall topic layer**: What is the main question this review or report is actually trying to answer?
2. **Section layer**: What kind of evidence does each heading require?
3. **Comparison-dimension layer**: Under each heading, what needs to be compared, demonstrated, or challenged?

If the user's headings are not well designed, you may revise them, but you must explain:

- why the change is needed
- which evidence gap the change addresses
- how the revision improves retrieval and evidence organization

## Every section needs its own query matrix

Do not rely on one global query by default. For each section, specify at least:

- `section`
- `research_question`
- `core_terms`
- `synonyms_or_abbr`
- `target_terms`
- `mechanism_terms`
- `outcome_terms`
- `exclude_terms`
- `paper_types_needed`
- `preferred_endpoint`

Default choices for `preferred_endpoint`:

- only a broad topic -> `/retrieve`
- already have a concrete PubMed query -> `/lookup`
- already have DOI / title candidates -> `/resolve`

Do not make `/download` the default section-level endpoint. Download belongs after screening, not before it.

## Recommended workflow

### 1. Define the workspace name and research boundary first

At minimum, clarify:

- the workspace name
- the overall topic
- which headings may be revised
- whether the final output is a review, a project report, or a chapter draft

Then create the workspace:

```bash
uv run autor ws init <workspace>
```

### 2. Check autor's local capabilities for seed papers first

```bash
uv run autor usearch "<query>" --top 20
uv run autor top-cited --top 20
```

If the local library is still not enough, supplement with `explore`:

```bash
uv run autor explore fetch --keyword "<query>" --name <slug>
uv run autor explore search --name <slug> "<query>" --top 20
```

### 3. Then use the AutoDownload REST service for PubMed retrieval and PDFs

Keep the integration REST-first. For candidate formation, prefer `GET /health`, `POST /retrieve`, `POST /lookup`, and `POST /resolve`. The following download-stage endpoints are long-running and should be marked as such in your workflow notes:

- `POST /download`
- `POST /search`
- `POST /fetch`

Check the service first:

```bash
curl http://127.0.0.1:8001/health
```

#### If you only have a section topic, use `/retrieve`

```bash
curl -X POST http://127.0.0.1:8001/retrieve \
  -H "Content-Type: application/json" \
  -d '{"topic":"sequential CAR-T therapy in relapsed lymphoma","max_results":30}'
```

#### If you already have a section-level PubMed query, use `/lookup`

```bash
curl -X POST http://127.0.0.1:8001/lookup \
  -H "Content-Type: application/json" \
  -d '{"query":"(sequential CAR-T OR retreatment) AND (CD19 OR CD22) AND (relapse OR antigen escape)","max_results":40}'
```

#### If you already have DOI / title candidates, use `/resolve`

```bash
curl -X POST http://127.0.0.1:8001/resolve \
  -H "Content-Type: application/json" \
  -d '{"identifiers":["10.1038/example","Example paper title"],"target":"pmid"}'
```

### 4. Perform academic screening on section-level candidates

Do not just collect “related papers.” Each section should have its own evidence structure. As far as possible, cover:

- background or concept-defining papers
- key mechanistic or methodological papers
- representative clinical / experimental data papers
- high-quality reviews
- necessary counterexamples or controversy papers

Screening should consider all three of the following at once:

1. **Citation impact / representativeness**
2. **Foundational value / originality / historical importance**
3. **Ability to support the current section or comparison dimension**

### 5. [Long-running] Download the retained PMIDs into the autor inbox

In WSL, convert the path first:

```bash
INBOX_WIN="$(wslpath -m /mnt/f/autor/data/inbox)"
```

Then call:

```bash
curl -X POST http://127.0.0.1:8001/download \
  -H "Content-Type: application/json" \
  -d "{\"pmids\":[\"12345678\",\"23456789\"],\"output_dir\":\"${INBOX_WIN}\"}"
```

This is a long-running step. Expect slower PDF acquisition and disk writes than the metadata-oriented REST calls above.

### 6. Continue the autor closed loop

```bash
uv run autor pipeline full
uv run autor usearch "<query>" --top 20
uv run autor ws add <workspace> <paper-id-or-doi...>
```

## When is `/search` appropriate?

`POST /search` is a long-running convenience endpoint and is only a good fit when:

- the user explicitly accepts a unified “discover + download” workflow
- the topic boundary is already clear and does not require careful pre-screening
- you want to build an initial batch of seed papers for a specific subtopic quickly

Otherwise, the default should still be:

`/retrieve` or `/lookup` -> academic screening -> `/download`

## Example: a review on sequential CAR-T therapy

If the user gives the title:

**“Concepts and research progress in sequential CAR-T therapy”**

and includes these sections:

- Concepts and theoretical foundations
- Same-target sequential therapy
- Different-target sequential therapy
- Sequential strategies combining CAR-T with other immunotherapies or radiotherapy
- Comparison between sequential therapy and other multi-target strategies

then the query matrix should cover at least these dimensions:

- `sequential CAR-T`
- `CAR-T retreatment`
- `CAR-T reinfusion`
- `salvage CAR-T`
- `CD19 CAR-T`
- `CD22 CAR-T`
- `CD19/CD22 sequential`
- `antigen escape`
- `target loss`
- `relapse after CAR-T`
- `ORR`, `CR`, `PFS`, `OS`, `CRS`, `ICANS`
- `dual-target` vs `sequential` vs `cocktail` vs `bispecific`
- `radiotherapy`, `checkpoint inhibitor`, `bridging`, `combination immunotherapy`

And every subsection should answer:

- Why was this sequential combination chosen?
- What is the indication?
- What do the clinical data show?
- What resistance or antigen-escape mechanism is involved?
- Where does the advantage of the sequential strategy lie?
- How does it differ from dual-target parallel treatment?
- What is the safety profile?

## Suggested artifacts

Leave at least the following files under `workspace/<name>/`:

- `seed-outline.md`
- `section-query-matrix.md`
- `candidate-papers.md`
- `download-log.md`
- `workspace-build-log.md`

If the next step is formal review writing, switch to autor's `plan`, `write`, or `literature-review` workflow.
