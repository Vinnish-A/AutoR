---
name: autodownload-expand
description: Expand an existing autor workspace by discovering missing papers, using AutoDownload over REST for PubMed retrieval and PDF download, ingesting the results into autor, and attaching the new papers to the current workspace.
---

# Expand an Existing Workspace

Use this skill for tasks like the following:

**The user already has a autor workspace and now needs to backfill classic papers, recent developments, counterexamples, or key evidence missing from a section; AutoDownload participates in the loop only as an external REST download service.**

## Goal

The goal is not to “download another batch of PDFs,” but to expand the library in a targeted way around evidence gaps in the current workspace:

- missed foundational papers
- important updates from the past 3–5 years
- direct evidence missing from a specific subsection
- counterexamples that conflict with the mainstream narrative
- missing population, target, mechanism, outcome, or safety data for a comparison dimension

## Two hard constraints

### 1. The download service is slow by default

AutoDownload's download service depends on the host machine and a virtual display, so it is inherently slow. For this skill, all of the following should be treated as normal expectations:

- slow API responses
- slow page interactions
- slow PDF writes to disk
- long waits across the full workspace-expansion workflow

Mark these endpoints explicitly as long-running download stages:

- `POST /download`
- `POST /search`
- `POST /fetch`

Do not treat “this is taking a long time” as an automatic failure, and do not skip PDF acquisition just to shorten the wait.

### 2. Never expand the library by ingesting titles only

Whether you are adding classic papers, recent updates, counterexamples, or missing evidence for a section, you must not use “title-only ingest” as the method, or even as a fallback.

The default requirement for expansion must always be:

- download the PDF
- ingest it fully into autor
- run the full downstream processing workflow

In other words, expansion is slow, but it must still go through the complete PDF-based loop.

## Principle: inspect the workspace before designing API calls

Do not start with AutoDownload by default. First inspect the existing workspace in autor:

```bash
uv run autor ws show <workspace>
uv run autor ws search <workspace> "<topic>"
uv run autor show <paper-id> --layer 2
uv run autor show <paper-id> --layer 3
```

If needed, supplement with:

```bash
uv run autor top-cited --top 20
uv run autor explore fetch --keyword "<query>" --name <slug>
uv run autor explore search --name <slug> "<query>" --top 20
```

Answer these four questions before moving on:

1. Which topics and populations are already covered in the current workspace?
2. Is the gap foundational, recent, mechanistic, clinical, or controversy-focused?
3. Which section / claim / comparison dimension most urgently needs support?
4. Which candidates already have DOI, title, or author clues, and which still require a fresh PubMed query?

## Build the query matrix around the gap

Create a gap-driven matrix before calling AutoDownload. Each row should contain at least:

- `section_or_claim`
- `gap_type`
- `core_terms`
- `synonyms`
- `mesh_candidates`
- `must_have`
- `exclude_terms`
- `preferred_endpoint`
- `why_needed`

Here `preferred_endpoint` defines the API strategy:

- existing DOI / title list -> `/resolve`
- already have a concrete PubMed query -> `/lookup`
- only a topic or problem statement -> `/retrieve`

## REST call strategy

Keep autor on the REST-first path: use `GET /health`, `POST /resolve`, `POST /lookup`, and `POST /retrieve` to form the candidate set, then treat the download-stage endpoints below as long-running operations.

### 1. Run a health check first

```bash
curl http://127.0.0.1:8001/health
```

### 2. If you already have DOI or title candidates, prefer `/resolve`

```bash
curl -X POST http://127.0.0.1:8001/resolve \
  -H "Content-Type: application/json" \
  -d '{"identifiers":["10.1038/example","Example paper title"],"target":"pmid"}'
```

### 3. If you already wrote a PubMed query, prefer `/lookup`

```bash
curl -X POST http://127.0.0.1:8001/lookup \
  -H "Content-Type: application/json" \
  -d '{"query":"(sequential CAR-T OR retreatment) AND (CD19 OR CD22) AND (ORR OR PFS OR OS)","max_results":40}'
```

### 4. If you only know the topic direction, start with `/retrieve` and do not download immediately

```bash
curl -X POST http://127.0.0.1:8001/retrieve \
  -H "Content-Type: application/json" \
  -d '{"topic":"CAR-T sequential therapy after relapse","max_results":30}'
```

### 5. [Long-running] Only run `/download` on papers you decided to keep

In WSL, prepare the output directory like this:

```bash
INBOX_WIN="$(wslpath -m /mnt/f/autor/data/inbox)"
```

Then download:

```bash
curl -X POST http://127.0.0.1:8001/download \
  -H "Content-Type: application/json" \
  -d "{\"pmids\":[\"12345678\",\"23456789\"],\"output_dir\":\"${INBOX_WIN}\"}"
```

This step is expected to take time. Wait for the acquisition pipeline to finish before moving on to autor ingest.

## Three hard screening criteria for candidate papers

For every candidate, answer these three questions:

1. **Citation impact / representativeness**: Is it a frequently cited review, pivotal trial, or representative study for this direction?
2. **Foundational value / historical importance**: Even if it is not the most cited, did it define the concept, validate the mechanism first, establish the treatment route first, or shift the field's narrative?
3. **Fitness for purpose**: Does it directly support the section, comparison dimension, or counterexample requirement that is currently missing in the workspace?

Additional guidance:

- Do not include a paper just because it is highly cited if it is only weakly related to the current question
- Keep low-cited papers if they uniquely support an edge case or counterexample
- If major contradictions exist, actively retain evidence on both sides

## Close the loop after download

A completed AutoDownload job is only an intermediate step, not the end of the task.

Standard closed loop:

```bash
uv run autor pipeline full
uv run autor usearch "<query>" --top 20
uv run autor ws add <workspace> <paper-id-or-doi...>
```

If you want the smallest viable ingest first and enrichment later, you can start with `pipeline ingest`, but `pipeline full` remains the default recommendation.

Here, `pipeline ingest` still refers to autor processing after full PDF ingestion. It does **not** mean “ingest the title only.”

## Discouraged practices

The following are not recommended by default:

- skipping the current workspace and sending a broad topic directly to `/search`
- downloading every PMID returned by `/retrieve` without academic screening
- using `/fetch` as the main workflow; it is better suited for backfilling after `/download` fails
- treating a long wait on `/download`, `/search`, or `/fetch` as an automatic failure without checking whether the acquisition pipeline is still progressing
- sending a Linux path such as `/mnt/f/...` directly as `output_dir`
- saving only titles or a small amount of bibliographic metadata to the database just to save time

## Suggested artifacts

Leave at least the following files under `workspace/<name>/`:

- `expansion-gap-map.md`
- `expansion-query-matrix.md`
- `expansion-candidates.md`
- `expansion-download-log.md`
- `expansion-ingest-log.md`

For each retained paper, record:

- why it was included
- which section or claim it supports
- whether it is a foundational paper, recent advance, key mechanistic study, clinical evidence item, or counterexample
- which AutoDownload endpoint was used for it

## When to stop the current expansion round

You can stop this round when any of the following becomes true:

- each core section already has enough primary evidence
- newly found papers mostly repeat conclusions already covered
- the newly added papers already cover the important updates in the current time window
- the remaining gaps are mainly due to unavailable PDFs or genuinely scarce evidence, not insufficient retrieval
