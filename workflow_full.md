# Full Report on autor and Its Command Workflows

## 1. Overall Positioning of the Project

autor is not merely a "paper manager," but a piece of research knowledge infrastructure designed for AI agents. The core problem it solves is this: organizing scattered PDFs, Markdown files, metadata, citation relationships, semantic vectors, and topic structures into a local knowledge base that is searchable, traceable, writable, and callable by agents.

From the code structure, this repository mainly covers six things:

1. Turning PDFs or Markdown into structured paper records.
2. Completing metadata, abstracts, tables of contents, conclusions, citation counts, and other fields.
3. Building multiple retrieval capabilities, including keyword search, semantic search, and hybrid search.
4. Building citation graphs and topic models to support horizontal comparison and knowledge discovery.
5. Providing a workspace mechanism that regroups papers from the main library by project for writing and export.
6. Exposing these capabilities to humans or AI agents through three entry points: CLI, MCP, and Agent Skills.

Its core idea is not "read one paper and then move to the next," but to turn the entire literature collection into a research operating system that can be continuously refined.

## 2. System Architecture and Data Flow

### 2.1 Main Data Flow

A typical data flow looks like this:

1. PDFs enter `data/inbox/`, `data/inbox-thesis/`, or `data/inbox-doc/`.
2. `pipeline` calls MinerU to convert PDFs into Markdown.
3. `extract` / API completion writes the title, authors, year, DOI, journal, abstract, and so on into `meta.json`.
4. After DOI deduplication, the paper enters `data/papers/<Author-Year-Title>/`.
5. `index` builds the FTS5 full-text index.
6. `embed` builds the vector index.
7. `topics` builds a BERTopic topic model based on vectors and metadata.
8. Commands such as `search` / `vsearch` / `usearch` / `refs` / `citing` / `shared-refs` / `ws` / `export` operate on the data structures above.

### 2.2 Responsibilities of Data Directories

`data/papers/`
Stores papers or documents that have been formally ingested into the library, one directory per item. Each directory usually contains at least `meta.json` and `paper.md`.

`data/inbox/`
The entry point for regular papers. By default, these are assumed to be academic papers that should have a DOI.

`data/inbox-thesis/`
The entry point for theses. It skips DOI deduplication logic and is handled directly as thesis material.

`data/inbox-doc/`
The entry point for general documents. It is meant for non-paper materials such as technical reports, lecture notes, and standards.

`data/pending/`
Entries awaiting manual confirmation, such as materials without a DOI that are not theses, or duplicates waiting to be resolved.

`data/explore/`
An exploratory external corpus. The data here comes from OpenAlex and is kept separate from the main library, making it suitable for workflows like "fetch an entire field first, then analyze it."

`workspace/`
The user workspace. This is not source code space, but research process space. It is used to store paper subset indexes, review drafts, analysis notes, exported BibTeX files, and so on.

### 2.3 The Four-Layer Reading Model

autor uses L1-L4 to load paper content in layers:

1. L1: metadata, suitable for fast filtering.
2. L2: abstract, suitable for initial topic scoping.
3. L3: conclusion, suitable for quickly judging the paper's contributions and takeaways.
4. L4: full Markdown text, suitable for in-depth analysis, method reproduction, and extraction of figures and formulas.

This layered design runs through the entire project and is the key abstraction behind both the CLI and agent workflows.

## 3. Entry Points

The project has three main entry points:

1. CLI: `autor ...`
2. MCP: `autor-mcp`
3. Agent Skills / Instructions: for automatic use by coding agents such as Claude, Copilot, and Codex

This report focuses on the CLI, because the CLI is the lowest-level composable interface behind all capabilities.

## 4. Complete CLI Command Reference

The current top-level CLI has 29 subcommands:

1. `index`
2. `search`
3. `search-author`
4. `show`
5. `embed`
6. `vsearch`
7. `usearch`
8. `enrich-toc`
9. `pipeline`
10. `refetch`
11. `top-cited`
12. `refs`
13. `citing`
14. `shared-refs`
15. `topics`
16. `backfill-abstract`
17. `rename`
18. `audit`
19. `repair`
20. `explore`
21. `export`
22. `ws`
23. `import-endnote`
24. `import-zotero`
25. `attach-pdf`
26. `setup`
27. `migrate-dirs`
28. `metrics`
29. `enrich-l3`

The sections below explain them by responsibility.

---

## 5. Environment and Maintenance Commands

### 5.1 `setup`

Purpose: environment checking and initialization wizard.

Submodes:

1. `autor setup`
2. `autor setup check --lang zh|en`

It checks:

1. Whether the Python version reaches 3.10+.
2. Whether core dependencies are installed.
3. Whether optional dependencies such as `embed`, `topics`, and `import` are installed.
4. Whether `config.yaml` exists.
5. Whether an LLM API key is configured.
6. Whether MinerU is available, either as a local service or through a cloud API key.
7. Whether directories such as `data/papers`, `data/inbox`, `data/pending`, and `workspace` exist.
8. How many formal entries are currently in the paper library.

Applicable scenarios:

1. Installing the project for the first time.
2. When you are not sure why a command will not run.
3. Environment health checks after another team member takes over the project.

Relationship to other commands:

1. Any command that depends on LLMs, MinerU, vectors, or topic modeling should go through `setup check` first.
2. If dependencies for `embed`, `topics`, or `import` are missing, the corresponding commands will fail.

Typical usage:

```bash
autor setup check --lang zh
autor setup
```

### 5.2 `metrics`

Purpose: view call statistics for LLM / API / pipeline steps.

Parameters:

1. `--summary`: view the summary.
2. `--last N`: view the most recent N records.
3. `--category llm|api|step`: filter by category.
4. `--since YYYY-MM-DD`: view data after a given date.

Applicable scenarios:

1. You want to know how many tokens the LLM has consumed over a period of time.
2. You want to confirm which enrichment or API calls recently failed.
3. You want to estimate the cost and runtime of a workflow.

Typical usage:

```bash
autor metrics --summary
autor metrics --category llm --last 50
autor metrics --category api --since 2026-03-01
```

### 5.3 `migrate-dirs`

Purpose: migrate the old flat `data/papers/` layout into the new "one directory per paper" structure.

Parameters:

1. By default it is a dry run.
2. Only `--execute` performs the migration for real.

Applicable scenarios:

1. Upgrading from an older version of autor.
2. When historical data directories have inconsistent structures.

Relationship to other commands:

1. After migration, you usually need to rerun `pipeline reindex` or at least `embed` and `index`.

Typical usage:

```bash
autor migrate-dirs
autor migrate-dirs --execute
autor pipeline reindex
```

---

## 6. Ingest and Metadata Processing Commands

### 6.1 `pipeline`

Purpose: the most important orchestration command in the entire project. It chains PDF/Markdown processing, deduplication, ingest, content enrichment, vectorization, and indexing into a pipeline.

It supports three scopes:

1. Inbox-level: process files waiting to be ingested one by one.
2. Paper-level: process already ingested papers one by one.
3. Global-level: perform a one-time global operation, such as rebuilding indexes.

Built-in presets:

1. `full = mineru, extract, dedup, ingest, toc, l3, embed, index`
2. `ingest = mineru, extract, dedup, ingest, embed, index`
3. `enrich = toc, l3, embed, index`
4. `reindex = embed, index`

Parameters:

1. `pipeline <preset>`: run a preset.
2. `--steps a,b,c`: use custom steps.
3. `--list`: list steps and presets.
4. `--dry-run`: preview only.
5. `--no-api`: skip external academic APIs.
6. `--force`: force reprocessing of steps such as `toc` and `l3`.
7. `--inspect`: print more detailed processing information.
8. `--max-retries N`: control the retry count for `l3` extraction.
9. `--rebuild`: used for index steps; forces a rebuild.
10. `--inbox`, `--papers`: override default directories.

Applicable scenarios:

1. Ingesting new papers.
2. Batch-filling TOC/L3 for papers already in the library.
3. Rebuilding vectors and indexes.
4. Batch-processing the three inboxes in a unified way.

Internally it actually processes three entry points:

1. `data/inbox/`: regular papers.
2. `data/inbox-thesis/`: theses.
3. `data/inbox-doc/`: non-paper documents.

This is the master switch for the project's entire production pipeline.

Typical usage:

```bash
autor pipeline --list
autor pipeline ingest
autor pipeline full
autor pipeline enrich --force
autor pipeline reindex --rebuild
autor pipeline --steps toc,l3,embed,index
```

### 6.2 `enrich-toc`

Purpose: extract the paper's table-of-contents structure from `paper.md` and write it into `meta.json`.

Parameters:

1. `paper_id` or `--all`.
2. `--force`: overwrite an existing TOC.
3. `--inspect`: display extraction details.

Applicable scenarios:

1. You want the agent to understand the section structure.
2. You want to prepare for later conclusion extraction, section localization, or full-text reading.

Relationship to other commands:

1. Often used together with `enrich-l3` and `show --layer 4`.
2. Often triggered automatically by `pipeline full` or `pipeline enrich`.

### 6.3 `enrich-l3`

Purpose: extract the conclusion section from the full text and write it into the L3 field of `meta.json`.

Parameters:

1. `paper_id` or `--all`.
2. `--force`: overwrite existing results.
3. `--inspect`: output the extraction process.
4. `--max-retries`: number of LLM retries.

Applicable scenarios:

1. You want to read conclusions quickly without reading the full text.
2. You want the agent to load only the most critical conclusions when writing a review or screening papers quickly.

Relationship with `show`:

1. `show --layer 3` depends on its output.

### 6.4 `refetch`

Purpose: call Crossref / Semantic Scholar / OpenAlex and similar interfaces again to complete citation counts and some bibliographic metadata.

Parameters:

1. `paper_id` or `--all`.
2. `--force`: refetch even if data already exists.
3. `--jobs`: concurrency.

Characteristics of its internal logic:

1. If you use `--all` without `--force`, it preferentially filters out entries that are already relatively complete and only processes papers missing citation data or fields such as volume/publisher.
2. It runs concurrently to improve batch update speed.

Applicable scenarios:

1. You want to update citation rankings.
2. You imported papers offline before and now want to complete the metadata.
3. Results from `refs` or `top-cited` are incomplete.

### 6.5 `backfill-abstract`

Purpose: fill in missing abstracts.

Parameters:

1. `--dry-run`: preview only.
2. `--doi-fetch`: fetch abstracts from the DOI landing page and overwrite existing content when necessary.

Applicable scenarios:

1. Historical entries are missing abstracts.
2. Semantic search quality is poor because vector construction depends heavily on title + abstract.

Relationship to other commands:

1. After filling in abstracts, it is recommended to rerun `embed`.

### 6.6 `rename`

Purpose: normalize paper directory names based on `meta.json`.

Parameters:

1. `paper_id` or `--all`.
2. `--dry-run`.

Applicable scenarios:

1. Metadata has been fixed manually, but the directory name has not been synchronized yet.
2. Imported source formats are messy and directory naming is inconsistent.

Relationship to other commands:

1. After renaming, the registry / index should ideally be rebuilt or at least checked for freshness.
2. Workspaces are maintained by UUID, so `rename` does not break the workspace itself, but the displayed `dir_name` will refresh in `ws show`.

### 6.7 `audit`

Purpose: inspect the data quality of papers already ingested into the library.

Parameters:

1. `--severity error|warning|info`

The issues it usually focuses on include:

1. Missing metadata.
2. Duplicate DOIs.
3. Title mismatches or irregular structure.
4. File naming problems.
5. Data problems that may affect retrieval and enrichment.

Applicable scenarios:

1. Running a quality inspection after large batch imports.
2. Making sure the library is reasonably clean before writing or exporting.

### 6.8 `repair`

Purpose: manually repair the key metadata of a paper without reparsing the Markdown.

Parameters:

1. Required: `paper_id`, `--title`.
2. Optional: `--doi`, `--author`, `--year`.
3. `--no-api`: use only manually provided information.
4. `--dry-run`: preview the result.

Its logic is:

1. Keep the original UUID.
2. Use the title, DOI, author, and year you provide to construct new metadata.
3. If `--no-api` is not set, continue calling external APIs to fill in the remaining fields.
4. Write the result back to `meta.json`.
5. Regenerate the normalized name based on the new metadata.

Applicable scenarios:

1. Poor OCR caused the title to be extracted incorrectly.
2. The paper's DOI was not recognized.
3. You want to correct the author or year and then let the API continue the completion work.

### 6.9 `attach-pdf`

Purpose: add a PDF to an already ingested entry that lacks `paper.md`, then automatically generate Markdown, abstracts, vectors, and indexes.

Parameters:

1. `paper_id`
2. `pdf_path`

Internal actions:

1. Copy the PDF into the corresponding paper directory.
2. Call MinerU to convert it into Markdown.
3. Normalize the output as `paper.md`.
4. Clean up redundant intermediate files while keeping `images/`.
5. If metadata lacks an abstract, try to extract one from the Markdown.
6. Trigger incremental `embed` and `index`.

Applicable scenarios:

1. You imported metadata first and obtained the PDF later.
2. You imported metadata from Zotero / Endnote before doing full-text conversion.

### 6.10 `import-endnote`

Purpose: import paper metadata from Endnote XML or RIS, and optionally bring matched PDFs into the main library as well.

Parameters:

1. One or more `.xml` / `.ris` files.
2. `--no-api`: trust only the source file metadata.
3. `--dry-run`: preview.
4. `--no-convert`: do not convert PDFs into `paper.md` immediately after import.

Applicable scenarios:

1. The user already has an old library managed in Endnote.
2. They want to migrate it into autor as a whole.

Relationship to other commands:

1. By default, it enters the formal library through `import_external`.
2. If `--no-convert` is not used, PDF-to-Markdown conversion will run later in batch.

### 6.11 `import-zotero`

Purpose: import metadata and PDFs from Zotero, supporting both local SQLite mode and Web API mode.

Parameter highlights:

1. `--local SQLITE_PATH`: import from a local database.
2. `--api-key`, `--library-id`, `--library-type`: import through the Zotero API.
3. `--collection`: limit to a collection.
4. `--item-type`: limit to an item type.
5. `--list-collections`: list collections first.
6. `--no-pdf`: import metadata only, without processing PDFs.
7. `--no-api`: skip academic APIs.
8. `--dry-run`: preview.
9. `--no-convert`: do not convert to Markdown yet.
10. `--import-collections`: map Zotero collections into autor workspaces.

Applicable scenarios:

1. Full migration from Zotero.
2. Importing only a specific collection.
3. Preserving Zotero's organizational structure as workspaces.

This command is very important because it solves the real-world problem of "how to migrate an existing personal literature library in."

---

## 7. Retrieval and Reading Commands

### 7.1 `index`

Purpose: build the FTS5 full-text index.

Parameters:

1. `--rebuild`: clear and rebuild.

Applicable scenarios:

1. You want to do keyword search after new papers have been ingested.
2. You have batch-modified metadata or full text and need to synchronize the index.

Relationship to other commands:

1. `search`, `search-author`, `usearch`, `top-cited`, `refs`, `citing`, `shared-refs`, and `ws search` all depend on `index.db`.

### 7.2 `embed`

Purpose: generate semantic vectors and write them into `index.db`.

Parameters:

1. `--rebuild`: rebuild everything.

Applicable scenarios:

1. You want to enable semantic search.
2. You just filled in abstracts or corrected titles and want the vectors to reflect the new content.

Dependencies:

1. It requires embed dependencies such as `sentence-transformers`, `faiss`, and `numpy`.

### 7.3 `search`

Purpose: keyword search, implemented on top of FTS5.

Parameters:

1. `query`
2. `--top`
3. `--year`
4. `--journal`
5. `--type`

Applicable scenarios:

1. You know exactly which term you want to find.
2. You want interpretable literal matching.

Advantages:

1. Controllable.
2. Fast.
3. More reliable for precise terminology queries.

Limitations:

1. Synonyms, paraphrases, and implicit semantics may not be recalled.

### 7.4 `search-author`

Purpose: fuzzy search by author name.

Its parameters and filters are basically the same as `search`.

Applicable scenarios:

1. Quickly checking which papers by a given author are in your library.
2. Following up with `top-cited` and `show` to trace the author's research line.

### 7.5 `vsearch`

Purpose: semantic vector search.

Its parameters are similar to `search`, but the default for `--top` is read from `embed.top_k`.

Applicable scenarios:

1. The user describes a concept in natural language rather than with standard terminology.
2. You want to find papers that are thematically close but use different wording.

Prerequisite:

1. `embed` must already have been run.

### 7.6 `usearch`

Purpose: hybrid search that combines keyword search and semantic search, using RRF-style fusion ranking.

Applicable scenarios:

1. This is the default recommended search mode.
2. Use it when you want both precise terminology matching and semantic recall.

Common `match` markers in the output:

1. `both`: matched by both keyword and semantic search.
2. `fts`: matched only by keyword search.
3. `vec`: matched only by vector search.

If you remember only one retrieval command, this should be the one.

### 7.7 `show`

Purpose: view a paper's L1-L4 content.

Parameters:

1. `paper_id`
2. `--layer 1|2|3|4`

Output logic:

1. It always prints the L1 header first.
2. `--layer 2` then prints the abstract.
3. `--layer 3` prints the conclusion, provided `enrich-l3` has already been run.
4. `--layer 4` prints the full Markdown text.

Applicable scenarios:

1. Reading more deeply after finding a result.
2. Quickly browsing the abstract or conclusion.
3. The basic entry point when an agent performs close reading paper by paper.

### 7.8 `top-cited`

Purpose: output papers ranked by citation count.

Parameters:

1. `--top`
2. `--year`
3. `--journal`
4. `--type`

Applicable scenarios:

1. Quickly identifying classic papers in a field.
2. Selecting representative papers for a workspace.
3. Finding high-impact anchor papers before writing a review.

Prerequisite:

1. If the library does not yet have citation data, run `refetch --all` first.

---

## 8. Citation Graph Commands

### 8.1 `refs`

Purpose: view which references a paper cites.

Parameters:

1. `paper_id`
2. `--ws`: restrict overlap statistics within a given workspace

The output is divided into two categories:

1. In-library references: the cited paper is also in your main library.
2. Out-of-library references: only the DOI exists, with no local entry.

Applicable scenarios:

1. You want to trace backward to the knowledge sources of a paper.
2. You want to discover important works it cites that you have not ingested yet.

### 8.2 `citing`

Purpose: see which local papers cite the specified paper.

Parameters:

1. `paper_id`
2. `--ws`

Applicable scenarios:

1. Forward citation tracking.
2. Seeing how a paper is continued, responded to, or extended within your own library.

### 8.3 `shared-refs`

Purpose: perform shared-reference analysis across multiple papers.

Parameters:

1. At least two `paper_id`
2. `--min`: the minimum number of papers that must share a citation, default 2.
3. `--ws`

Applicable scenarios:

1. Comparing whether two research lines share a common theoretical foundation.
2. Finding foundational literature jointly relied upon within a topic.
3. Looking for common source material when grouping a review.

---

## 9. Topic Modeling and Exploration Commands

### 9.1 `topics`

Purpose: perform BERTopic topic modeling and browsing on the main library.

Parameters:

1. `--build`: build the model.
2. `--rebuild`: rebuild the model.
3. `--reduce N`: quickly merge topics.
4. `--merge "1,6,14+3,5"`: manually merge topic groups.
5. `--topic ID`: inspect a specific topic.
6. `--top`: limit the number of papers shown for a topic.
7. `--min-topic-size`
8. `--nr-topics`
9. `--viz`: export 6 HTML visualizations.

Output modes:

1. Without extra parameters, it outputs a topic overview.
2. With `--topic`, it outputs the papers under that topic.
3. With `--viz`, it writes visualization HTML files.

Applicable scenarios:

1. You want to understand which topic clusters exist across the whole literature library.
2. You want to elevate your work from reading single papers to analyzing at the topic level.
3. You want structure for reviews, research gaps, or related-work writing.

Dependencies:

1. It requires topics dependencies.
2. In practice it also depends on the baseline data quality provided by vectors and indexes.

### 9.2 `explore`

Purpose: fetch an external exploratory corpus outside the main library, then vectorize it, search it, topic-model it, and visualize it.

This is an important feature that sets autor apart from a "local reference manager." It does not only search your existing library; it lets you first build a temporary external research corpus.

It has five subcommands.

#### 9.2.1 `explore fetch`

Purpose: fetch papers from OpenAlex into `data/explore/<name>/papers.jsonl`.

The filters are very rich:

1. `--issn`
2. `--concept`
3. `--topic-id`
4. `--author`
5. `--institution`
6. `--keyword`
7. `--source-type`
8. `--oa-type`
9. `--min-citations`
10. `--year-range`
11. `--incremental`

Applicable scenarios:

1. Fetching the full corpus of a journal.
2. Fetching papers from recent years for a concept or author.
3. Building a field-analysis corpus and then topic-modeling it.

#### 9.2.2 `explore embed`

Purpose: generate semantic vectors for the exploratory corpus.

Parameters:

1. `--name`
2. `--rebuild`

#### 9.2.3 `explore topics`

Purpose: perform topic modeling on the exploratory corpus.

Parameters:

1. `--name`
2. `--build`
3. `--rebuild`
4. `--topic`
5. `--top`
6. `--min-topic-size`
7. `--nr-topics`

#### 9.2.4 `explore search`

Purpose: search within the exploratory corpus.

Parameters:

1. `--name`
2. `query`
3. `--top`
4. `--mode semantic|keyword|unified`

#### 9.2.5 `explore viz`

Purpose: output topic-visualization HTML files for the exploratory corpus.

#### 9.2.6 `explore info`

Purpose: view exploratory-corpus metadata; if `--name` is omitted, list all exploratory corpora.

Summary of applicable scenarios:

1. The main library solves "how to manage the literature I already have."
2. `explore` solves "how to scan a field before I have formally added it to the library."

---

## 10. Export and Organization Commands

### 10.1 `export bibtex`

Purpose: export papers as BibTeX.

Parameters:

1. Specify several `paper_ids`, or use `--all`.
2. `--year`
3. `--journal`
4. `-o / --output`

Applicable scenarios:

1. Preparing references for LaTeX/Word writing.
2. Exporting citation files for a batch of papers.

### 10.2 `ws`

Purpose: workspace subset management. Its core idea is not copying papers, but referencing papers from the main library by UUID.

This means:

1. Workspaces are very lightweight.
2. `rename` does not destroy a workspace, because the workspace is bound to UUIDs.
3. One paper can belong to multiple workspaces at the same time.

Its subcommands are as follows.

#### 10.2.1 `ws init <name>`

Create the workspace directory and an empty `papers.json`.

#### 10.2.2 `ws add <name> <paper_refs...>`

Add papers to the workspace. UUIDs, directory names, and DOIs are supported.

#### 10.2.3 `ws remove <name> <paper_refs...>`

Remove papers from the workspace.

#### 10.2.4 `ws list`

List all workspaces.

#### 10.2.5 `ws show <name>`

List papers in the workspace and refresh stale `dir_name` values.

#### 10.2.6 `ws search <name> <query>`

Run hybrid search inside the workspace, supporting `--top`, `--year`, `--journal`, and `--type`.

#### 10.2.7 `ws export <name>`

Export the workspace's BibTeX.

Applicable scenarios:

1. Maintaining a subset of literature for a project, a paper, or a review.
2. Narrowing the scope of writing and search to avoid noise from the full library.

---

## 11. Dependency Relationships Between Commands

If you treat these commands as a system rather than as isolated subcommands, their dependencies are roughly as follows:

1. `setup` is the prerequisite check for all workflows.
2. `pipeline` / `import-*` / `attach-pdf` are responsible for "putting things into the library."
3. `index` and `embed` are responsible for "making the library searchable."
4. `search` / `vsearch` / `usearch` / `show` are responsible for "reading and finding."
5. `refetch` / `backfill-abstract` / `enrich-toc` / `enrich-l3` / `repair` / `rename` / `audit` are responsible for "keeping the library healthy."
6. `refs` / `citing` / `shared-refs` / `topics` / `explore` are responsible for "understanding literature groups through relationships and structure."
7. `ws` / `export` are responsible for "organizing the literature you have understood for output."
8. `metrics` is responsible for "looking back at system cost and efficiency."

In other words, autor's CLI is a closed loop that goes from acquisition to processing to analysis and writing.

## 12. How to Combine Commands into Workflows

What follows is not a simple list of commands, but recommended combinations based on real research workflows.

### Workflow A: Install and Validate the Environment for the First Time

Goal: confirm that the project can run normally.

Steps:

1. `autor setup check --lang zh`
2. Install missing dependencies according to the check results.
3. Run `autor setup` to fill in API keys and basic configuration.
4. Run `autor setup check --lang zh` once again to verify.

Applicable users:

1. First-time users.
2. New-machine deployments.

### Workflow B: Batch-Ingest New PDFs

Goal: turn new papers from PDFs into searchable entries.

Steps:

1. Put regular papers into `data/inbox/`.
2. Put theses into `data/inbox-thesis/`.
3. Put technical reports or lecture notes into `data/inbox-doc/`.
4. Run `autor pipeline ingest`.
5. If you also want TOC and conclusions to be filled automatically, run `autor pipeline full`, or simply start with `full` from the beginning.

Outputs:

1. Formal entries go into `data/papers/`.
2. Suspicious entries go into `data/pending/`.
3. Vectors and indexes are updated in sync.

When to use `ingest` versus `full`:

1. `ingest`: you only want papers to enter the library and become searchable first.
2. `full`: you already know this batch is worth deeper downstream use and want TOC/L3 filled in one shot.

### Workflow C: Migrate an Existing Literature Library from an External Reference Manager

Goal: move an Endnote / Zotero library into autor.

Endnote approach:

1. `autor import-endnote mylib.xml`
2. Or use `--dry-run` first to see the effect.
3. If you do not want PDF-to-Markdown conversion immediately, add `--no-convert`.

Zotero approach:

1. If you do not know the collection yet, first run `autor import-zotero --list-collections ...`
2. Then import by collection.
3. If you want collections to be mapped automatically into workspaces, add `--import-collections`.

Standard remediation steps after migration:

1. `autor audit`
2. `autor refetch --all`
3. `autor backfill-abstract`
4. `autor pipeline reindex`

This is the recommended order for "cleaning up an old library."

### Workflow D: Fix Dirty Data and Improve Retrieval Quality

Goal: solve problems such as messy metadata after import, missing abstracts, and poor retrieval quality.

Recommended order:

1. `autor audit`
2. For clearly incorrect entries, run `autor repair <paper_id> --title ... --doi ...` one by one
3. `autor refetch --all`
4. `autor backfill-abstract`
5. `autor rename --all`
6. `autor pipeline reindex`

Why this order:

1. Start with `audit` to find the problems.
2. Fix the key metadata first, so API completion and abstract backfilling can work on correct information.
3. Rebuild indexes and vectors in a unified way at the end.

### Workflow E: Do Everyday Retrieval and Layered Reading

Goal: quickly find relevant papers for a topic and go deeper layer by layer.

Recommended order:

1. Start with `autor usearch "your question"`
2. If the results are too narrow, run `autor vsearch "your question"`
3. If you only want exact terminology matching, run `autor search "term"`
4. For hits, run `autor show <paper_id> --layer 2`
5. If a paper is worth reading further, run `autor show <paper_id> --layer 3`
6. Finally, only a small number of key papers should go to `--layer 4`

This workflow reflects autor's core value: recall broadly first, then reduce reading cost through layered narrowing.

### Workflow F: Do Citation Tracing Around a Paper

Goal: see both its sources and its impact.

Steps:

1. `autor show <paper_id> --layer 2`
2. `autor refs <paper_id>` to see what it cites.
3. `autor citing <paper_id>` to see which local papers cite it.
4. If you also want to compare the shared foundation of two or three representative papers, run `autor shared-refs <id1> <id2> <id3>`.

Applicable scenarios:

1. Finding foundational papers when writing related work.
2. Tracing the evolution chain of a method.

### Workflow G: Do Topic Modeling to Build a Structural Map of a Field

Goal: shift from the perspective of single papers to the perspective of topic groups.

Steps:

1. Make sure the library has enough papers and has already been vectorized.
2. `autor topics --build`
3. View the overview: `autor topics`
4. View a topic: `autor topics --topic 3 --top 20`
5. If topics are too fragmented: `autor topics --reduce 20`
6. If manual cleanup is needed: `autor topics --merge "1,6,14+3,5"`
7. Export visualizations: `autor topics --viz`

Applicable scenarios:

1. Looking at the natural topic clusters in your library before writing a review.
2. Finding outlier papers or cross-disciplinary papers.

### Workflow H: Do a "Field Sweep" Instead of Using Only the Existing Main Library

Goal: when your main library is still incomplete, use an external exploratory corpus to quickly build a panoramic view of the field.

Steps:

1. Fetch: `autor explore fetch --keyword "amyloid beta" --year-range 2020-2026 --name abeta`
2. Vectorize: `autor explore embed --name abeta`
3. Cluster: `autor explore topics --name abeta --build`
4. Search: `autor explore search --name abeta "microglia therapy" --mode unified`
5. Visualize: `autor explore viz --name abeta`

This workflow is especially suitable for:

1. Doing landscape analysis when you first enter a new direction.
2. Preliminary analysis before deciding which papers are worth formally importing into the main library.

### Workflow I: Build a Writing Workspace

Goal: carve out a writing subset from the large library.

Steps:

1. `autor ws init drag-review`
2. Use `usearch` to find papers.
3. `autor ws add drag-review <paper_ids...>`
4. `autor ws show drag-review`
5. `autor ws search drag-review "boundary layer"`
6. `autor ws export drag-review -o workspace/drag-review/references.bib`

Why the workspace is so important:

1. It narrows the writing context.
2. You can repeatedly search and export against one paper subset instead of filtering the whole main library every time.

### Workflow J: Write a Review or Related-Work Section Around a Workspace

Goal: move from the workspace into writing.

Recommended order:

1. `autor ws show <ws>`
2. `autor ws search <ws> "topic"`
3. Use `autor topics` to view the global topic structure and, when needed, assist grouping
4. For core papers in the workspace, run `show --layer 2` and `show --layer 3` in sequence
5. Use `refs` / `citing` / `shared-refs` on key papers to strengthen relationship coverage
6. `autor ws export <ws> -o workspace/<ws>/references.bib`

If you use an agent for automatic writing, this is exactly the combination of underlying commands corresponding to `.github/skills/literature-review`.

### Workflow K: Metadata First, PDF Later

Goal: get entries into the library first, then add full text later.

Steps:

1. First ensure the metadata exists through Endnote/Zotero import or manual `repair`.
2. After obtaining the PDF, run: `autor attach-pdf <paper_id> /path/to/file.pdf`
3. The system automatically generates `paper.md`, fills in the abstract, and updates `embed` and `index`.

Applicable scenarios:

1. Metadata arrives before the full text.
2. In the early stage of migrating an old library, only record-level information was available.

### Workflow L: From Zotero to PDF2MD to the Local Database and Then to Agent-Augmented Writing

Goal: use Zotero as the upstream bibliographic source and autor as the local knowledge base plus agent workbench, forming a complete closed loop from acquisition to writing.

It is recommended to split the whole chain into four layers rather than mixing them together:

1. Zotero layer: maintain raw bibliographic information, collections, and PDF attachments.
2. PDF2MD layer: materialize only the PDFs that truly need deep processing into Markdown.
3. autor local database layer: maintain `meta.json`, `paper.md`, `index.db`, vectors, topic models, and workspaces.
4. Agent layer: perform retrieval, comparison, and writing enhancement on the main library or workspaces.

The complete recommended workflow is as follows.

#### Stage 1: Identify Which Objects from Zotero Should Enter autor

There are two modes:

1. One-time migration:
`autor import-zotero --local /path/to/zotero.sqlite --collection <KEY>`
2. Long-term coexistence:
Adopt a Git-style `status/pull/materialize` synchronization approach and treat Zotero as the upstream source.

If your goal is to use both Zotero and autor over the long term, the second option is more recommended than repeatedly doing full `import-zotero` runs.

#### Stage 2: Decide Which PDFs Are Worth Running Through PDF2MD

Do not assume by default that all PDFs in the entire Zotero library should be copied and converted to Markdown. A more reasonable strategy is:

1. By default, sync only metadata and attachment references.
2. Only run PDF2MD for papers that truly need to enter the knowledge-processing pipeline.
3. For entries that do not need full-text analysis in the short term, metadata alone is enough.

The core criterion at this step is not "does Zotero have a PDF for it," but "is this paper worth entering autor's full-text processing pipeline?"

#### Stage 3: Materialize the PDF as a autor Knowledge Object

For papers that need deeper processing, execute:

1. Prepare the PDF.
2. Generate `paper.md` through `pipeline` or `attach-pdf`.
3. Then perform enrichment for TOC/L3/abstract/citations.

If you use the standard autor path:

```bash
autor pipeline full
```

If the metadata is already in the library and you are only adding the PDF:

```bash
autor attach-pdf <paper_id> /path/to/file.pdf
```

The true core outputs of this layer are not the PDF itself, but:

1. `meta.json`
2. `paper.md`
3. `images/`
4. FTS, registry, and citations in `index.db`
5. `paper_vectors`
6. Inputs for the `topics` model

#### Stage 4: Enter the Local Database and Knowledge-Processing Layer

Once an entry has been turned into Markdown and enriched with metadata, it is no longer just a "Zotero item," but a computable object in autor's local knowledge base.

Typical commands you can run at this point are:

```bash
autor usearch "glioblastoma evolution under therapy"
autor show <paper-id> --layer 2
autor show <paper-id> --layer 3
autor refs <paper-id>
autor citing <paper-id>
autor topics --build
```

Here, the "local database" is not just the single file `index.db`, but the combination of three parts:

1. File-based primary data: `data/papers/<dir>/meta.json + paper.md`
2. Retrieval / relationship database: `index.db`
3. Derived analytical artifacts: vectors, topic models, workspace subsets

#### Stage 5: Use an Agent for Augmented Reading and Writing

Once papers enter the local knowledge layer above, the Agent can finally amplify their value. The recommended usage is:

1. Use `usearch` and `show --layer 2/3` to screen papers quickly.
2. Use `refs`, `citing`, and `shared-refs` to understand relationship structure.
3. Use `topics` or `explore` to identify topic groups and research gaps.
4. Use `ws` to narrow candidate papers into a writing workspace.
5. Carry out agent-assisted writing for reviews, related work, method comparison, review responses, and so on within the workspace.

Example of a full command chain:

```bash
autor ws init gbm-review
autor ws add gbm-review <paper-id-1> <paper-id-2> <paper-id-3>
autor ws search gbm-review "therapy resistance"
autor ws export gbm-review -o workspace/gbm-review/references.bib
```

Together with Agent Skills:

1. `search`: retrieve candidate papers.
2. `show`: read abstracts, conclusions, and full text layer by layer.
3. `literature-review`: generate a review draft from a workspace.
4. `paper-writing`: write sections such as the introduction, related work, and discussion.
5. `citation-check`: verify whether citations in the writing are real and match the local library.

The real division of labor in this chain is:

1. Zotero is responsible for collection and organization.
2. autor is responsible for structured processing and computable retrieval.
3. The Agent is responsible for understanding, comparison, and writing enhancement on top of that foundation.

### Workflow M: Use Git-Style Synchronization Instead of Repeatedly Importing Zotero Attachments

Goal: avoid repeatedly importing large PDFs and attachments from Zotero, while retaining autor's local derived-layer capabilities.

The recommended strategy is:

1. Zotero as the bibliographic upstream.
2. autor as the local materialized cache.
3. By default, do not copy PDFs from Zotero `storage/`; only record references and hashes.
4. Only when full-text processing is needed should you `materialize` an individual entry.

The suggested command model is as follows:

```bash
autor zotero init --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite --storage /mnt/c/Users/Administrator/Zotero/storage --mode reference
autor zotero status
autor zotero pull --collection EV6N9LWE
autor zotero materialize --item KQF9CVWF --mode symlink
```

The corresponding data flow should be:

1. `status`: only scan differences, without importing large files.
2. `pull`: write Zotero entries and attachment references into a manifest without copying PDFs.
3. `materialize`: create a symlink or copy for a small number of entries.
4. `attach-pdf` or a dedicated derive command: generate `paper.md` for materialized PDFs.
5. `embed/index/topics/ws`: continue along autor's existing pipeline.

Compared with repeatedly doing full `import-zotero` migrations, this approach has the following advantages:

1. It avoids repeatedly copying large attachments.
2. It does not disrupt Zotero's role as the primary bibliography manager.
3. It is maximally compatible with autor's current architecture.
4. It is convenient for later incremental synchronization, difference auditing, and controlled write-back.

The real sample from your current local Zotero library has already shown that this pattern is feasible:

1. item key: `KQF9CVWF`
2. attachment key: `SLRJQNAB`
3. PDF path: `/mnt/c/Users/Administrator/Zotero/storage/SLRJQNAB/Interpretation.pdf`
4. The local manifest can record only the `reference`; there is no need to copy the PDF

## 13. Suggested Command Usage Strategy

From the perspective of "which command should I use," I would summarize it this way:

1. If you want to put materials into the library: think first of `pipeline`, `import-endnote`, `import-zotero`, and `attach-pdf`; if Zotero is the upstream and long-term coexistence is needed, Git-style `pull/materialize` is more recommended than repeated full imports.
2. If you want to clean up the library: think first of `audit`, `repair`, `refetch`, `backfill-abstract`, and `rename`.
3. If you want to find things in the library: think first of `usearch`, then `search` / `vsearch` / `search-author` / `top-cited`.
4. If you want to read papers: think first of `show --layer 2/3/4`.
5. If you want to understand relationships between papers: think first of `refs`, `citing`, `shared-refs`, and `topics`.
6. If you want to narrow the literature within the scope of a project: think first of `ws`.
7. If you want to scan an external field: think first of `explore`.
8. If you want to export to writing tools: think first of `export bibtex` or `ws export`.

## 14. What This Repository Really Accomplishes

If summarized in one sentence:

autor fully connects paper files, metadata, citation relationships, semantic indexes, topic structures, project subsets, and writing export into a single local research pipeline.

If stated more concretely, it delivers five layers of capability:

1. Storage layer: normalize papers and documents into `data/papers/`, or materialize them from upstream systems such as Zotero into local sidecars and derived knowledge objects.
2. Processing layer: use LLMs, APIs, MinerU, abstract backfilling, and conclusion extraction to turn raw PDFs into actionable research objects.
3. Retrieval layer: provide keyword, semantic, and hybrid search plus filtering.
4. Structure layer: provide citation graphs and topic modeling so users can understand the literature through group structure.
5. Output layer: provide workspaces and BibTeX export so analytical results can flow directly into writing and research production.

The most important point is that it is not "yet another GUI reference manager," but an "agent-first research terminal backend." The CLI is the foundational primitive, while skills and MCP are higher-level automation shells.

## 15. A Most Practical Minimal Command Set

If you only want to master the most important small set of commands first, I recommend remembering these 10 above all:

1. `autor setup check`
2. `autor pipeline ingest`
3. `autor pipeline full`
4. `autor usearch "..."`
5. `autor show <paper_id> --layer 2`
6. `autor show <paper_id> --layer 3`
7. `autor ws init <name>`
8. `autor ws add <name> <paper_ids...>`
9. `autor ws export <name> -o workspace/<name>/references.bib`
10. `autor audit`

These 10 commands already cover seven core actions: installation, ingest, retrieval, reading, organization, export, and quality control.

## 16. Recommended Learning Path

For a new user, the most reasonable learning path is not "memorize all 29 commands first," but to follow this sequence:

1. Learn `setup` first.
2. Then learn `pipeline`.
3. Then learn `usearch` and `show`.
4. Then learn `ws` and `export`.
5. After that, add `audit`, `repair`, and `refetch`.
6. Finally, learn `topics` and `explore`.

The reason is simple:

1. The first four steps solve 80% of everyday research needs.
2. The last two solve advanced knowledge discovery and library maintenance problems.

---

## 17. Conclusion

The design of autor's commands is not "feature piling," but something organized around one clear goal:

Turn papers from raw files into knowledge objects usable by agents, and bring those objects into a complete research loop that supports retrieval, comparison, synthesis, export, and writing.

Therefore, the best way to understand this repository is not to memorize commands one by one, but to remember its main line:

1. Bring materials into the library.
2. Process the library well.
3. Retrieve and read within the library.
4. Use relationships and topics to understand the entire field.
5. Use the workspace to converge analysis into writable output.

As long as you use it along this main line, the 29 commands will not feel scattered at all; they will instead feel very natural.
