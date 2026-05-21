---
name: autodownload
description: Use the Records-backed AutoDownload service as autor's external literature acquisition service. Choose this skill when the user needs PubMed retrieval, PMID resolution, or PDF download to support an autor workspace.
---

# Records Service + autor Workflow Overview

When the user expresses any of the following intents, enter this skill first and then decide whether to switch into a more specific workflow:

- expand an existing autor workspace
- build a new workspace from a topic, outline, or claim structure
- batch-find papers from PubMed / PMID / DOI / title inputs and download PDFs
- move external candidate papers into the autor knowledge base for real use

## One-sentence boundary

- **autor**: knowledge base, workspaces, local/global retrieval, evidence organization, writing, and analysis
- **Records service**: PubMed retrieval, PMID resolution, identifier conversion, and PDF acquisition
- **For autor, the Records service is an external HTTP service**; do not assume it must be a local module running inside the current Python environment
- The service usually runs from the `/mnt/f/Records` (`F:\Records`) checkout, even though the Python package / Windows service may still be named `autodownload`

In one sentence:

**autor manages the knowledge base and workspaces; the Records service handles PubMed retrieval and PDF downloads.**

## Service model: REST first

In autor's WSL workflow, the Records service usually provides download capability from the Windows side, while autor talks to it as a client over the REST API.

In autor integrations, REST calls remain the default interface. Use CLI commands only for debugging, manual verification, or service-side operations.

## Three hard constraints

### 1. PDF acquisition is inherently slow

The Records service's PDF pipeline involves multi-layer source resolution (S3 cache, Unpaywall, OA Sources, Sci-Hub, browser-driven AutoClick). Each stage can take seconds to minutes per paper. A batch of 10–50 papers can easily take 1–10 minutes.

**Treat all download-class operations as long-running.** Slow responses are normal and should not be treated as automatic failure conditions.

By contrast, `GET /health`, `POST /retrieve`, `POST /lookup`, and `POST /resolve` are quick metadata calls and should remain the default first step.

### 2. Use the task-based API for long-running downloads (recommended)

Starting from v0.3.0, the Records-backed AutoDownload service provides an async task API that decouples submission from completion. This is the **recommended interface** for all download operations from autor:

- **Submit**: `POST /tasks/` → returns a `task_id` immediately
- **Monitor**: `GET /tasks/{id}` (poll) or `GET /tasks/{id}/events` (SSE real-time stream)
- **Download**: `GET /tasks/{id}/artifact` → zip of all PDFs (only available after `completed`)

The task API eliminates:
- the need for `output_dir` / Windows path conversion
- blocking HTTP connections during long downloads
- unobservable "is it stuck or still working?" states

Task states: `queued` → `executing` → `partial_done` → `completed` / `failed` / `cancelled`

### 3. Database processing must ingest full PDFs; title-only ingest is forbidden

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

## Service conventions

Default conventions:

- base URL: `http://127.0.0.1:8001`
- health check: `GET /health`
- OpenAPI docs: `http://127.0.0.1:8001/docs`
- default service repo: `F:\Records` on Windows (`/mnt/f/Records` from WSL)
- common startup path: run `./scripts/start.sh` inside the `autor` repository

Before starting any acquisition action, confirm that the service is reachable:

```bash
curl http://127.0.0.1:8001/health
```

If you are not in the default environment, also verify:

- `AUTOR_AUTODOWNLOAD_PORT`
- `AUTOR_AUTODOWNLOAD_WIN_DIR`

## How to choose the REST endpoint

### Quick metadata endpoints (fast, seconds)

| Endpoint | When to use it | Typical request body | Typical response |
| --- | --- | --- | --- |
| `GET /health` | Check whether the service is available | none | `status`, `version`, `pdf_count` |
| `POST /retrieve` | You only have a topic and want candidate PMIDs + metadata first, without downloading | `{"topic":"...","max_results":30}` | `pmids`, `metadata`, `mesh_terms`, `query` |
| `POST /lookup` | You already have a concrete PubMed Boolean query | `{"query":"...","max_results":40}` | `pmids`, `titles` |
| `POST /resolve` | You already have DOI / title / PMID identifiers and need conversion | `{"identifiers":[...],"target":"pmid"}` | `resolved` or `results` |

### Task-based download endpoints (async, minutes — recommended)

| Endpoint | Method | Purpose | Notes |
| --- | --- | --- | --- |
| `/tasks/` | POST | Submit a download/search/fetch task | Returns `task_id` immediately |
| `/tasks/` | GET | List all tasks (filter by `?state=`) | |
| `/tasks/{id}` | GET | Get task details + per-item progress + PDF count | |
| `/tasks/{id}/events` | GET | SSE real-time event stream | Streams stage progression |
| `/tasks/{id}/artifact` | GET | Download zip of completed PDFs | Only available when state=completed |
| `/tasks/{id}/cancel` | POST | Cancel a running task | |
| `/tasks/{id}/retry` | POST | Retry a failed task | Creates a new linked task |

Task types for `POST /tasks/`:

| Type | Required params | What it does |
| --- | --- | --- |
| `download` | `pmids: [...]` | Download PDFs for specific PMIDs |
| `search` | `topic: "..."` | Full pipeline: retrieve + download |
| `fetch` | `keywords: [...]` | Send keywords to AutoClick |

### Legacy synchronous download endpoints (blocking, still supported)

| Endpoint | When to use it | Typical request body | Notes |
| --- | --- | --- | --- |
| `POST /download` | Download PDFs by PMIDs | `{"pmids":[...],"output_dir":"F:/.../data/inbox"}` | Requires `output_dir` (Windows path); **blocking** |
| `POST /search` | Unified discover + download | `{"topic":"...","max_results":30,"output_dir":"F:/..."}` | Requires `output_dir`; **blocking** |
| `POST /fetch` | Keywords to AutoClick | `{"keywords":[...],"output_dir":"F:/..."}` | Fallback only; **blocking** |

Notes:

- The task API (`/tasks/`) is the recommended approach for all download operations; it returns immediately and lets you monitor progress
- Legacy endpoints (`/download`, `/search`, `/fetch`) still work but block the HTTP connection and require `output_dir`
- `force_online` is still accepted by the API but is mostly a compatibility field
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

### 4. [Recommended] Submit a download task (returns immediately)

```bash
curl -X POST http://127.0.0.1:8001/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"type":"download","pmids":["12345678","23456789"]}'
```

Response: `{"task_id": "a1b2c3d4e5f6", "state": "queued"}`

### 5. Monitor progress (poll or SSE)

```bash
# Poll
curl http://127.0.0.1:8001/tasks/a1b2c3d4e5f6

# Or stream events in real time
curl -N http://127.0.0.1:8001/tasks/a1b2c3d4e5f6/events
```

### 6. Download the artifact when completed

```bash
curl -o papers.zip http://127.0.0.1:8001/tasks/a1b2c3d4e5f6/artifact
```

Unzip into the autor inbox and continue the ingest loop.

## Recommended closed loop: reason in autor first, acquire with the Records service second

Recommended default order:

1. **Understand the task boundary in autor first**
   - Existing workspace: inspect current coverage and evidence gaps first
   - New topic / new outline: first break it into sections, claims, and comparison dimensions
2. **Use autor's own retrieval tools for the first candidate pass**
   - `search`
   - `top-cited`
   - `explore`
   - `search-author`
3. **Then call the Records service REST endpoints for PubMed supplementation and PMID resolution**
   - topic-driven question: prefer `/retrieve`
   - existing query: prefer `/lookup`
   - DOI / title list already available: prefer `/resolve`
4. **Screen the papers using three hard criteria**
   - citation impact / representativeness
   - foundational value / historical importance
   - direct support for the current section or claim
5. **Submit a download task** for retained papers via `POST /tasks/` and monitor until completed
6. **Download the artifact** (zip of PDFs) and unzip into the autor inbox
7. **Run the ingest closed loop on the autor side**

```bash
unzip papers.zip -d /mnt/f/AutoR/data/inbox/
uv run autor pipeline ingest
```

8. **Relocate the newly ingested papers and add them to the workspace**

```bash
uv run autor search "<query>" --top 20
uv run autor ws add <workspace> <paper-id-or-doi...>
```

Note: this “closed loop” means the full PDF-based workflow. It does not accept shortcuts such as “just put the title in the database.”

## Coverage-first acquisition mode for full reviews

When the user asks for a `full review`, `large review`, or `comprehensive review`, acquisition must be **coverage-first**, not “core-papers-first”.

### Hard rules

1. Build a **universe corpus** from external metadata before aggressively filtering.
2. Do not exclude a directly relevant paper merely because it looks low-impact, narrow, or not central enough before the universe corpus exists.
3. In the first acquisition pass, exclude only:
   - duplicates
   - retractions
   - clearly off-scope records
   - records that remain unusable after identifier normalization
4. Only after the universe corpus is visible may you derive:
   - a `working corpus` for ingestion and section mapping
   - a `core analytical corpus` for the later main argument

### Recommended landscape-first sequence

If literature-landscape MCP tools are available in the current environment, use them before download:

- `estimate_subfield_scope`
- `analyze_topic_trends`
- `measure_review_saturation`
- `rank_seminal_papers`
- `retrieve_topic_literature`
- `resolve_literature_identifiers`
- `get_citation_neighborhood`

This step is not the final search. It is for calibrating how broad the field is and which branches must be covered.

### Query-matrix rule

For a full review, do not rely on a single topic string. Build a query matrix across at least:

1. **Platform terms**
   - `CAR-T`, `CAAR-T`, `CAR-Treg`, `engineered Treg`, `CAR-NK`, `CAR-M`, `in vivo CAR`, `allogeneic`, `iPSC`
2. **Disease terms**
   - the major autoimmune diseases genuinely relevant to the review
3. **Translational terms**
   - `toxicity`, `manufacturing`, `conditioning`, `persistence`, `relapse`, `immune reset`, `organ remodeling`
4. **Adjacent comparator terms**
   - non-autoimmune CAR literature only when needed to explain platform logic or translational constraints

Run metadata retrieval in batches by branch, not only by one umbrella query. Keep the branch label for every candidate record.

### Required artifacts in full-review mode

Leave coverage traces in the current canonical planning package:

- `acquisition-log.md`: query matrix, branch objectives, candidate counts, download failures, no-full-text records, and ingest status
- `reference-map.json`: each retained or unresolved candidate's citation key, identifiers, corpus layer, section mapping, and full-text status
- `evidence-ledger.md`: final retained/excluded/unresolved evidence roles by citation key
- `sidecars/`: raw Records responses, task payloads, artifact manifests, or large candidate ledgers

Legacy files such as `query-matrix.md`, `download-report.md`, or `corpus-ledger.md` may be generated only as derived compatibility exports. The canonical trace of coverage is `acquisition-log.md` plus `reference-map.json`.

## When not to download immediately

Do not jump straight to `POST /tasks/` with type=download in the following cases:

- the user wants to “add classic papers,” but you have not yet judged what the current workspace is missing
- the user provides a review topic, but the evidence structure for each section is still unclear
- the user needs to distinguish highly cited reviews, foundational papers, key counterexamples, and recent progress
- the user gives a DOI / title list, but you have not yet confirmed which items are truly worth including

For these tasks, the default should be to stop at `/retrieve`, `/lookup`, or `/resolve` first, make the academic judgment, and only then download.

## Follow-up actions on the autor side

Downloading the PDFs with the Records service does not mean the task is finished. The standard closed loop also includes:

1. unzip artifact into `data/inbox/`
2. run `pipeline ingest` to ingest, enrich, and update indexes
3. search autor again to find the new papers
4. use `ws add` to attach them to the target workspace
5. leave the query matrix, inclusion rationale, and download logs under `workspace/<name>/`

## Output requirements

No matter which downstream workflow you end up using, leave the user with at least these traceable artifacts:

- the query strings or section-level query matrix
- candidate papers with inclusion / exclusion rationale
- which REST endpoints were called and what each step did
- download success / failure lists
- which papers were ingested and which workspace they were added to
