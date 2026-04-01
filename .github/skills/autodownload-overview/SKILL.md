---
name: autodownload-overview
description: Use AutoDownload as a RESTful literature acquisition service for autor. Choose this skill when the user needs PubMed retrieval, PMID resolution, or PDF download to support a autor workspace.
---

# AutoDownload + autor Workflow Overview

When the user expresses any of the following intents, enter this skill first and then decide whether to switch into a more specific workflow:

- expand an existing autor workspace
- build a new workspace from a topic, outline, or claim structure
- batch-find papers from PubMed / PMID / DOI / title inputs and download PDFs
- move external candidate papers into the autor knowledge base for real use

## One-sentence boundary

- **autor**: knowledge base, workspaces, local/global retrieval, evidence organization, writing, and analysis
- **AutoDownload**: PubMed retrieval, PMID resolution, identifier conversion, and PDF acquisition
- **For autor, AutoDownload is an external HTTP service**; do not assume it must be a local module running inside the current Python environment

In one sentence:

**autor manages the knowledge base and workspaces; AutoDownload handles PubMed retrieval and PDF downloads.**

## Service model: REST first

In autor's WSL workflow, AutoDownload usually provides download capability from the Windows side, while autor talks to it as a client over the REST API.

In autor integrations, REST calls remain the default interface. Use CLI commands only for debugging, manual verification, or service-side operations.

## Two hard constraints

### 1. Mark long-running download endpoints explicitly

Treat the following endpoints as long-running operations rather than quick metadata calls:

- `POST /download`
- `POST /search`
- `POST /fetch`

These routes trigger the PDF-acquisition side of AutoDownload (AutoPubmed / Unpaywall / AutoClick). They can involve slow startup, browser-driven retries, and slow writes to disk. Long waits are normal and should not be treated as automatic failure conditions.

By contrast, `GET /health`, `POST /retrieve`, `POST /lookup`, and `POST /resolve` are usually the faster, screening-oriented REST calls and should remain the default first step.

### 2. Database processing must ingest full PDFs; title-only ingest is forbidden

Whether the task is:

- expanding the main autor library
- adding papers to a workspace
- pushing candidates into the database during retrieval

you must **not** use “title-only ingest” as the method, and it should **not** be treated as a fallback path.

The default requirement is always:

- obtain the PDF
- ingest it fully
- run the full downstream autor workflow

That means you must at least complete PDF download and hand the paper into autor's formal processing loop, which inherently requires waiting.

Default conventions:

- base URL: `http://127.0.0.1:8001`
- health check: `GET /health`
- OpenAPI docs: `http://127.0.0.1:8001/docs`
- common startup path: run `./scripts/start.sh` inside the `autor` repository

Before starting any acquisition action, confirm that the service is reachable:

```bash
curl http://127.0.0.1:8001/health
```

If you are not in the default environment, also verify:

- `AUTOR_AUTODOWNLOAD_PORT`
- `AUTOR_AUTODOWNLOAD_WIN_DIR`

## Path rules for `output_dir`

For `POST /download`, `POST /search`, and `POST /fetch`, `output_dir` must be an **absolute Windows path**.

When calling from WSL, convert the path like this:

```bash
INBOX_WIN="$(wslpath -m /mnt/f/autor/data/inbox)"
```

This usually becomes:

```text
F:/autor/data/inbox
```

Do not send a Linux path such as `/mnt/f/autor/data/inbox` directly to the Windows-side AutoDownload service.

## How to choose the REST endpoint

| Endpoint | When to use it | Typical request body | Typical response | Recommendation |
| --- | --- | --- | --- | --- |
| `GET /health` | Check whether the service is available | none | `status`, `version`, `output_dir`, `pdf_count` | Call once before any workflow |
| `POST /retrieve` | You only have a topic and want candidate PMIDs + metadata first, without downloading | `{"topic":"...","max_results":30}` | `pmids`, `metadata`, `mesh_terms`, `query` | Default first choice; ideal when academic screening is required |
| `POST /lookup` | You already have a concrete PubMed Boolean query | `{"query":"...","max_results":40}` | `pmids`, `titles` | Good for section-level, mechanistic, or population-specific searches |
| `POST /resolve` | You already have DOI / title / PMID identifiers and need conversion | `{"identifiers":[...],"target":"pmid"}` | `resolved` or `results` | Good for turning autor, OpenAlex, or user-supplied candidates into PMIDs |
| `POST /download` | You already selected PMIDs and are ready to download PDFs | `{"pmids":[...],"output_dir":"F:/.../data/inbox"}` | download results, failed items, output directory | Commonly paired with `/retrieve`, `/lookup`, or `/resolve`; **long-running by default** |
| `POST /search` | The user accepts a unified “discover + download,” and no pre-screening is needed | `{"topic":"...","max_results":30,"output_dir":"F:/..."}` | retrieval results + download results | Use only when the user explicitly accepts batch auto-download; **long-running batch workflow** |
| `POST /fetch` | You want to hand keywords directly to AutoClick for fallback retrieval | `{"keywords":[...],"output_dir":"F:/..."}` | `total_success`, `remaining_failed` | Fallback only; not the default primary workflow; **long-running** |

Notes:

- `force_online` is still accepted by the API, but it is now mostly a compatibility field and usually does not need to be set explicitly
- `POST /search` skips the “evaluate first, then download” buffer layer, so do not treat it as the default entry point
- For autor, REST is the default integration surface; CLI is mainly for debugging and service operations

## Minimal REST examples

### 1. Find candidates only, without downloading

```bash
curl -X POST http://127.0.0.1:8001/retrieve \
  -H "Content-Type: application/json" \
  -d '{"topic":"CAR-T sequential therapy","max_results":30}'
```

### 2. If you already have a PubMed query, search directly

```bash
curl -X POST http://127.0.0.1:8001/lookup \
  -H "Content-Type: application/json" \
  -d '{"query":"(sequential CAR-T OR CAR-T retreatment) AND (CD19 OR CD22)","max_results":40}'
```

### 3. Resolve DOI / title into PMID

```bash
curl -X POST http://127.0.0.1:8001/resolve \
  -H "Content-Type: application/json" \
  -d '{"identifiers":["10.1038/example","Example paper title"],"target":"pmid"}'
```

### 4. [Long-running] Download selected PMIDs into the autor inbox

```bash
INBOX_WIN="$(wslpath -m /mnt/f/autor/data/inbox)"

curl -X POST http://127.0.0.1:8001/download \
  -H "Content-Type: application/json" \
  -d "{\"pmids\":[\"12345678\",\"23456789\"],\"output_dir\":\"${INBOX_WIN}\"}"
```

Expect this step to take time. The correct behavior is to wait for the acquisition pipeline to finish, then continue into autor ingest.

## Recommended closed loop: reason in autor first, acquire with AutoDownload second

Recommended default order:

1. **Understand the task boundary in autor first**
   - Existing workspace: inspect current coverage and evidence gaps first
   - New topic / new outline: first break it into sections, claims, and comparison dimensions
2. **Use autor's own retrieval tools for the first candidate pass**
   - `usearch`
   - `top-cited`
   - `explore`
   - `search-author`
3. **Then call AutoDownload REST endpoints for PubMed supplementation and PMID resolution**
   - topic-driven question: prefer `/retrieve`
   - existing query: prefer `/lookup`
   - DOI / title list already available: prefer `/resolve`
4. **Screen the papers using three hard criteria**
   - citation impact / representativeness
   - foundational value / historical importance
   - direct support for the current section or claim
5. **Run `/download` only for retained papers**, ideally targeting the autor inbox, and treat that step as long-running
6. **Run the ingest closed loop on the autor side**

```bash
uv run autor pipeline full
```

7. **Relocate the newly ingested papers and add them to the workspace**

```bash
uv run autor usearch "<query>" --top 20
uv run autor ws add <workspace> <paper-id-or-doi...>
```

Note: this “closed loop” means the full PDF-based workflow. It does not accept shortcuts such as “just put the title in the database.”

## When not to download immediately

Do not jump straight to `POST /search` or `POST /download` in the following cases:

- the user wants to “add classic papers,” but you have not yet judged what the current workspace is missing
- the user provides a review topic, but the evidence structure for each section is still unclear
- the user needs to distinguish highly cited reviews, foundational papers, key counterexamples, and recent progress
- the user gives a DOI / title list, but you have not yet confirmed which items are truly worth including

For these tasks, the default should be to stop at `/retrieve`, `/lookup`, or `/resolve` first, make the academic judgment, and only then download.

## Follow-up actions on the autor side

Downloading the PDFs with AutoDownload does not mean the task is finished. The standard closed loop also includes:

1. move the files into `data/inbox/`
2. run `pipeline full` to ingest, enrich, and update indexes
3. search autor again to find the new papers
4. use `ws add` to attach them to the target workspace
5. leave the query matrix, inclusion rationale, and download logs under `workspace/<name>/`

## Two downstream workflows

- **There is already a workspace, and you need to add evidence / classics / recent work / counterexamples**
  - switch to `autodownload-expand`
- **There is no workspace yet, but the user provides a topic / outline / section structure / claim list**
  - switch to `autodownload-outline`

## Output requirements

No matter which downstream workflow you end up using, leave the user with at least these traceable artifacts:

- the query strings or section-level query matrix
- candidate papers with inclusion / exclusion rationale
- which REST endpoints were called and what each step did
- download success / failure lists
- which papers were ingested and which workspace they were added to
