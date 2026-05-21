# autor Practical Workflow Guide

> Migration note (2026-05-19): AutoR has removed vector/RAG storage. Any older
> mentions of `autor embed`, `vsearch`, FAISS, semantic vectors, or hybrid
> keyword+vector retrieval should be read as historical. Current search uses
> node-level SQLite FTS5 and `autor research` evidence bundles.

This guide is for anyone who has cloned autor locally and plans to use it long term. It focuses on four practical questions:

1. How to start the local services
2. How to batch-convert PDFs in the inbox to Markdown and update the fast FTS5 search index
3. How to add papers on a specific topic to a workspace
4. How to organize writing inside a workspace

The final section distills the design intent implied by the README and suggests improvements that would better serve that intent.

---

## 0. Understanding How autor Runs

autor is not a single web service. It has three composable local runtime modes:

- **CLI**: The most direct mode—ideal for manual ingest, search, workspace management, and export.
- **MCP server**: Exposes autor as a tool server for agents such as Claude Desktop, Cursor, Claude Code, and Copilot.
- **MinerU service**: Handles PDF-to-Markdown conversion. It can run through a local MinerU API or fall back to the cloud API.

In everyday use, the typical local setup is:

1. Activate the Python virtual environment.
2. Start the local MinerU API if needed.
3. Start the autor MCP server, or use the CLI directly.

---

## 1. How to Start My Local autor Services

### 1.1 Activate the Project Environment

```bash
cd /mnt/f/autor
source .venv/bin/activate
```

It is a good idea to run an environment diagnostic once first:

```bash
autor setup check
```

This step checks:

- whether the Python environment is healthy
- whether the config files exist
- whether MinerU is reachable
- whether an LLM key is configured
- whether the data and workspace directories are present

### 1.2 Start the autor MCP Server

If you want to expose autor as a local knowledge service for an agent, use:

```bash
cd /mnt/f/autor
source .venv/bin/activate
AUTOR_ROOT=/mnt/f/autor autor-mcp
```

Or:

```bash
cd /mnt/f/autor
source .venv/bin/activate
AUTOR_ROOT=/mnt/f/autor python -m autor.mcp_server
```

Use this when:

- you want Claude Desktop, Cursor, Copilot Chat, and similar tools to call autor through MCP
- you want to search, show, add to a workspace, or run pipeline ingest directly from the conversation instead of typing every CLI command yourself

### 1.3 Start the Local MinerU Service

If you want PDF-to-Markdown conversion to happen locally instead of through the MinerU cloud API, start local MinerU:

```bash
cd /mnt/f/autor
source .venv/bin/activate
MINERU_MODEL_SOURCE=modelscope mineru-api --host 127.0.0.1 --port 8000
```

By default, autor will try to connect to:

```text
http://localhost:8000
```

In the default `hybrid` mode, a running local MinerU endpoint and all configured cloud tokens work as parallel sources during batch PDF conversion. If local MinerU is not running, but `ingest.mineru_api_keys` is configured in `config.local.yaml` or `MINERU_API_KEYS` is set in the environment, autor falls back to cloud-only conversion.

### 1.4 When You Do Not Need to Start a "Server"

If you are just running commands yourself in a terminal, you do not need the MCP server. As long as the virtual environment works, commands like these are enough:

```bash
autor search "CAR glioma"
autor pipeline ingest
autor ws show car-glioma
```

In other words:

- if an agent needs access, start `autor-mcp`
- if you need PDF conversion, start `mineru-api` or configure a cloud key
- if you are operating manually, the CLI is sufficient

---

## 2. How to Batch-Convert Inbox PDFs into Markdown and a Searchable Database

### 2.0 Recommended Flow for Importing a Specific Zotero Collection from Local SQLite

If your Zotero database lives on Windows:

```text
C:\Users\Administrator\Zotero\zotero.sqlite
```

Then inside WSL it should be written as:

```bash
/mnt/c/Users/Administrator/Zotero/zotero.sqlite
```

One important point often causes confusion:

- the built-in `import-zotero` flow is **not** “import into inbox first, then run ingest”
- instead, it **imports directly into `data/papers/`, then automatically handles PDF → Markdown conversion, TOC extraction, L3 generation, and FTS5 indexing**

So if you use the built-in Zotero import command, you usually **do not** need to manually shuttle files into `data/inbox/`.

#### Step 1: List Available Collections in Local Zotero

```bash
cd /mnt/f/autor
source .venv/bin/activate

autor import-zotero \
  --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite \
  --list-collections
```

The output shows:

- the collection `Key`
- the number of items
- the collection name

When you later import a specific collection, you must use its `Key`, not the display name.

#### Step 2: Import One Collection

```bash
autor import-zotero \
  --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite \
  --collection <COLLECTION_KEY>
```

By default this command runs the full workflow:

1. Parse items from the chosen collection in local Zotero SQLite.
2. Match and copy PDFs.
3. Write entries directly into `data/papers/`.
4. Batch-convert PDFs into `paper.md`.
5. Backfill abstracts.
6. Extract TOC.
7. Generate L3 paper-level conclusion cards.
8. Update the FTS5 search index.

In other words, if you do not add `--no-convert`, this single step already covers “import + Markdown conversion + TOC/L3 generation + FTS5 indexing.” Semantic vectors are intentionally not built by default; run `autor embed` only when you need semantic/vector search or topics.

#### Step 3: If You Only Want to Import First and Convert Later

You can explicitly disable conversion:

```bash
autor import-zotero \
  --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite \
  --collection <COLLECTION_KEY> \
  --no-convert
```

After that:

- entries are placed into `data/papers/`
- PDFs are copied into the corresponding paper directories
- but `paper.md` is not generated yet
- and TOC/L3 are not generated automatically

If you later want to complete the conversion in one batch, the recommended approach is to run the built-in Python batch job:

```bash
cd /mnt/f/autor
source .venv/bin/activate

python - <<'PY'
from autor.config import load_config
from autor.ingest.pipeline import batch_convert_pdfs

cfg = load_config()
stats = batch_convert_pdfs(cfg, enrich=True)
print(stats)
PY
```

The `enrich=True` flag is important. It means:

- convert `paper.md`
- automatically extract `TOC`
- automatically generate `L3`
- then update the FTS5 full-text index

#### Step 4: If You Insist on Using “Inbox First, Then Ingest”

The current project does **not** provide a built-in flow like:

```text
Zotero collection -> data/inbox/
```

The built-in path is:

```text
Zotero collection -> data/papers/ -> automatic conversion / enrichment / indexing
```

So from the perspective of native project support, the recommended path is to use `import-zotero --local --collection ...` directly rather than adding your own extra inbox hop.

If you truly want to do the transfer manually, the only workable option is:

1. Copy PDFs yourself from the Zotero attachment directory into `data/inbox/`.
2. Then run:

```bash
autor pipeline full
```

That will give you:

- `ingest`
- `TOC`
- `L3`

But this is **not** the standard built-in flow for local Zotero import.

#### The Most Recommended Command Chain in Practice

```bash
cd /mnt/f/autor
source .venv/bin/activate

# 1. Inspect collections
autor import-zotero \
  --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite \
  --list-collections

# 2. Import one collection; by default this also does PDF->MD + TOC + L3 + indexing
autor import-zotero \
  --local /mnt/c/Users/Administrator/Zotero/zotero.sqlite \
  --collection <COLLECTION_KEY>
```

#### How to Confirm That TOC and L3 Were Generated After Import

You can check a paper with:

```bash
autor show "<paper-id>" --layer 3
```

If you want to force TOC and L3 generation for all ingested papers:

```bash
autor pipeline enrich --force
```

### 2.1 Put Files in the Right Directory First

autor has three entry directories:

- `data/inbox/`: regular papers
- `data/inbox-thesis/`: theses
- `data/inbox-doc/`: technical reports, lecture notes, draft reviews, and other nonstandard paper-like documents

Recommended rules:

- put formal papers in `data/inbox/` whenever possible
- if there is no DOI and the item is really a report or explanatory document, put it in `data/inbox-doc/`
- put theses in `data/inbox-thesis/`

### 2.2 Which Command Should You Use for Ingest?

The most common command is:

```bash
autor pipeline ingest
```

This preset runs:

- `mineru`: PDF → Markdown
- `extract`: metadata extraction
- `dedup`: DOI-based deduplication
- `ingest`: write into `data/papers/`
- `l3`: generate the L3 paper-level conclusion card
- `index`: update the FTS5 search database

It does not build semantic vectors by default. This saves time during ordinary ingest. If you later need semantic/vector search or topic modeling, run:

```bash
autor embed
```

If you also want an explicit TOC saved before/alongside L3 generation, use:

```bash
autor pipeline full
```

Compared with `ingest`, `full` adds:

- `toc`

### 2.3 Recommended Batch Processing Routine

```bash
cd /mnt/f/autor
source .venv/bin/activate

# 1. Dry-run first to see which files will be processed
autor pipeline ingest --dry-run --inspect

# 2. Run the actual ingest
autor pipeline ingest

# 3. If you want richer content enhancement
autor pipeline full
```

### 2.3.1 Batch Ingest Straight into a Workspace

Previously, a large PDF batch had to be ingested first and then searched or filtered again before it could be gathered into a project workspace.

Now you can attach a workspace name directly to the pipeline command and lock the newly ingested batch into that project box in one step:

```bash
autor pipeline ingest --workspace my_research_project
```

The workspace is created automatically when it does not exist. Only papers that actually receive a UUID and are written into `data/papers/` during the current run are added. Items diverted to pending because they lack a DOI, along with duplicates skipped by deduplication, are excluded automatically.

### 2.4 What Happens After Ingest Finishes?

After processing, a paper or document is stored under:

```text
data/papers/<Author-Year-Title>/
```

That directory usually contains:

- `meta.json`
- `paper.md`
- `images/`

At the same time, the following search layers are updated:

- the FTS5 index in `data/index.db`
- the vector-search tables in the same database
- if `embed` was run, the corresponding FAISS/vector data also becomes available

### 2.5 How to Confirm That the Paper Really Entered the Database

The safest check is to search immediately after ingest:

```bash
autor usearch "your topic keywords" --top 10
```

Or directly test whether the paper can be shown:

```bash
autor show "directory name or DOI"
```

If you suspect the index is inconsistent, run:

```bash
autor pipeline reindex
```

### 2.5.1 How to Extract TOC and Generate L3 When Re-Ingesting or Repairing `paper.md`

There are three different cases here.

#### Case A: You Just Finished a Normal Ingest and Want Explicit TOC Backfill

The best follow-up is:

```bash
autor pipeline enrich
```

This adds or refreshes the following for already ingested papers:

- `toc`
- `l3`
- `index`

To force re-extraction:

```bash
autor pipeline enrich --force
```

#### Case B: You Are Repairing a Single Paper and Already Obtained a Fresh `paper.md`

Run the single-paper commands directly:

```bash
autor enrich-toc <paper-id>
autor enrich-l3 <paper-id>
```

To force re-extraction:

```bash
autor enrich-toc <paper-id> --force
autor enrich-l3 <paper-id> --force
```

#### Case C: You Are Repairing an Already-Ingested Record That Has a PDF but Is Missing `paper.md`

The safest option is the built-in batch repair logic `batch_convert_pdfs(cfg, enrich=True)`.

The companion script [repair_missing_md_entries.py](/mnt/f/autor/repair_missing_md_entries.py) already uses that default flow:

- reconvert the existing PDF into `paper.md`
- backfill `abstract`
- extract `TOC`
- generate `L3`
- rebuild the FTS5 index

Run it directly with:

```bash
cd /mnt/f/autor
source .venv/bin/activate
python repair_missing_md_entries.py
```

If you do **not** want TOC and L3 generated during the repair, disable enrichment explicitly:

```bash
python repair_missing_md_entries.py --no-enrich
```

Here `L3` means “level-3 content loading,” not a model name:

- `L1`: metadata
- `L2`: abstract
- `L3`: paper-level conclusion card
- `L4`: full Markdown text

So “generate L3” means writing a structured paper-level takeaway to `meta.json`. It uses an explicit conclusion/summary section when present, otherwise it can synthesize from abstract, results, discussion, figure captions, and table captions. The structured field records mode, source spans, key findings, quantitative signals, limitations, and warnings when available.

### 2.6 Minimal Python Usage If You Only Want to Call the API Programmatically

```python
from autor.config import load_config
from autor.index import unified_search

cfg = load_config()
results = unified_search("glioblastoma CAR", cfg.index_db, top_k=10, cfg=cfg)
```

If this fails in Python while the CLI works, the first things to suspect are:

- the current Python interpreter is not the project `.venv`
- you used a new index from an old interpreter session
- the interpreter was not restarted after ingest

### 2.7 How to Requeue Items from `pending` After You Edit Them

One important clarification first:

`data/pending/` is **not** an automatic retry queue in the current version. It is a **manual review area**.

In other words, autor moves things into `pending/` when:

- they have no DOI and were not recognized as a thesis
- their DOI duplicates an existing paper in the library

Each pending item directory usually contains:

- `paper.md`
- the original PDF
- `pending.json`
- `images/` and other MinerU assets

`pending.json` is only a marker/explanation file. The current pipeline will not automatically reconsume it.

The correct procedure is:

#### Case A: It Was a No-DOI Item and You Have Manually Fixed It

If you have added the title, year, authors, DOI, or determined that it should really be treated as a document:

1. Take the original PDF or `paper.md` out of `data/pending/<item>/`.
2. Put it back into the appropriate inbox based on the real item type:
   - regular papers go to `data/inbox/`
   - theses go to `data/inbox-thesis/`
   - technical reports / explanatory documents go to `data/inbox-doc/`
3. Run:

```bash
autor pipeline ingest
```

If you edited the Markdown directly, you can also put only `paper.md` back into `data/inbox/` and rerun `pipeline ingest`.

#### Case B: It Was Marked as a Duplicate, but You Want to Keep the New Version and Replace the Old One

The current version does not provide a “confirm overwrite” command. The practical flow is:

1. Inspect `data/pending/<item>/pending.json`.
2. Find:
   - `issue: duplicate`
   - `duplicate_of`
3. Manually decide which directory to keep.
4. If you want the new version, handle the old directory yourself first, then put the new PDF/Markdown back into the inbox and rerun `pipeline ingest`.

In short, the current `pending` return path is:

```text
manual fix in pending -> move back to inbox / inbox-thesis / inbox-doc -> rerun pipeline ingest
```

If you only edit `pending.json` but do not move the PDF/Markdown back into an inbox, the pipeline will not pick it up again automatically.

### 2.8 How the System Deduplicates Entries

autor currently has two layers of deduplication, but they operate at different times.

#### First layer: Automatic DOI deduplication during ingest

This is built in and enabled by default.

When you run:

```bash
autor pipeline ingest
```

The flow will:

- extract metadata
- call Crossref / Semantic Scholar / OpenAlex to fill in a DOI
- compare that DOI against the existing library

If the DOI already exists:

- the system will not ingest a second copy directly
- it will move the new item into `data/pending/`
- and mark `pending.json` with `duplicate`

This means:

- the software can automatically block duplicate papers **at ingest time**
- the current strategy is **block duplicate ingest**, not **automatically merge the two records**

#### Second layer: Duplicate checks over the already ingested library

If duplicates have already made it into `data/papers/`, run:

```bash
autor audit
```

It will report issues such as:

- `duplicate_doi`

That is, DOI duplication among already ingested papers.

#### Important boundary to keep in mind

In the current version:

- automatic DOI deduplication exists
- duplicate detection for already ingested records exists
- there is **no** one-click command to automatically delete duplicate directories or merge duplicate metadata

So the most accurate summary of the current capability is:

- **automatically block most new duplicate ingests**
- **automatically detect existing DOI duplicates**
- **still require a human decision about which copy to keep**

### 2.9 Recommended Handling Flow for Duplicates Already in the Library

```bash
# 1. Find duplicate DOIs first
autor audit

# 2. If the problem is just bad metadata, repair metadata first
autor repair "<paper-dir>" --title "Correct title" --doi "10.xxxx/..."

# 3. If the two entries are confirmed duplicates, manually delete the directory you do not want to keep

# 4. Then rebuild the index
autor pipeline reindex
```

The more reliable manual criteria are:

- which item has the more complete `paper.md`
- which item has the more accurate abstract / authors / year
- which item is already referenced by multiple workspaces
- which item has the cleaner normalized directory name

If you often batch-import external libraries, make this a fixed routine:

```bash
autor pipeline ingest
autor audit
autor pipeline reindex
```

Only add `autor embed` to this routine when you explicitly need semantic/vector search or topic modeling.

---

## 3. How to Add Papers on a Specific Topic into a Workspace

A workspace is a “project-specific paper subset.” It does not duplicate full texts; it references papers in the main library by UUID.

### 3.1 Initialize a Workspace

```bash
autor ws init car-glioma
```

This creates:

```text
workspace/car-glioma/
```

And generates:

```text
workspace/car-glioma/papers.json
```

### 3.2 Search the Topic First, Then Add Papers to the Workspace

The recommended routine is:

```bash
autor usearch "glioblastoma CAR" --top 10
autor usearch "glioma CAR" --top 10
autor usearch "CAR glioma" --top 10
```

Then add the papers you want into the workspace:

```bash
autor ws add car-glioma <paper UUID or directory name or DOI>
```

For example:

```bash
autor ws add car-glioma Begley-2025-CAR-T-cell-therapy-for-glioblastoma-A-review-of-the-first-decade-of-clinical-trials
```

### 3.3 View Workspace Contents

```bash
autor ws show car-glioma
```

### 3.4 Search Within the Workspace Scope

```bash
autor ws search car-glioma "glioblastoma CAR"
```

This matters a lot, because it narrows the search scope to the current project instead of letting unrelated CAR-T papers from the whole library interfere with ranking.

### 3.5 Use a Workspace as the Query Scope from Python

```python
from pathlib import Path
from autor.config import load_config
from autor.index import unified_search
from autor.workspace import read_paper_ids

cfg = load_config()
ws_dir = Path("/mnt/f/autor/workspace/car-glioma")
pids = read_paper_ids(ws_dir)

results = unified_search(
    "glioblastoma CAR",
    cfg.index_db,
    top_k=10,
    cfg=cfg,
    paper_ids=pids,
)
```

### 3.6 A Reliable Topic Workflow

```bash
autor ws init car-glioma
autor usearch "glioblastoma CAR" --top 10
autor usearch "glioma CAR" --top 10
autor ws add car-glioma <selected papers...>
autor ws show car-glioma
autor ws search car-glioma "IL13Ra2 CAR"
```

---

## 4. How to Write Inside a Workspace

The README's real design intent is not “just do retrieval.” It treats `workspace/` as a project workbench. In other words:

- the paper library lives in `data/papers/`
- your project outputs live in `workspace/<name>/`

### 4.1 What Should Go Inside a Workspace?

A good rule is to put the following into `workspace/<name>/`:

- literature-review drafts
- per-section drafts such as Introduction, Related Work, or Discussion
- Python analysis scripts
- comparison tables
- exported citation files such as `references.bib`
- research logs and question lists

### 4.2 The Most Practical Writing Rhythm

#### Stage A: Survey the Workspace First

```bash
autor ws show car-glioma
autor ws search car-glioma "review"
autor ws search car-glioma "phase 1 trial"
```

Then read key papers layer by layer:

```bash
autor show "directory-name" --layer 2
autor show "directory-name" --layer 3
autor show "directory-name" --layer 4
```

#### Stage B: Build the Writing Skeleton First

For example, create these files under `workspace/car-glioma/`:

- `00-outline.md`
- `01-background.md`
- `02-related-work.md`
- `03-clinical-trials.md`
- `04-research-gap.md`
- `references.bib`

#### Stage C: Search While You Write

The recommended approach is **not** “read every paper first and only then start writing.” Instead:

1. write a 5–10 line skeleton first
2. use `ws search` to fill in evidence
3. use `show --layer 2/3/4` to add context
4. make each paragraph solve one clear claim

#### Stage D: Export Citations

```bash
autor ws export car-glioma -o workspace/car-glioma/references.bib
```

### 4.3 Best Practices When Writing with an Agent

If you are writing through Claude Code, Copilot, Cursor, or another agent, the most reliable pattern is:

1. first collect the topic papers into a clearly scoped workspace
2. explicitly tell the agent to place outputs under `workspace/<name>/`
3. have the agent start with `ws show` and `ws search`
4. only use `show --layer 4` for the core papers

This gives two benefits:

- the citation scope stays constrained, which reduces hallucinated references
- writing outputs and the paper subset live in the same directory, which makes later maintenance much easier

### 4.4 An End-to-End Writing Example

```bash
# 1. Create the workspace
autor ws init car-glioma

# 2. Add papers
autor ws add car-glioma <several papers>

# 3. Search inside the workspace
autor ws search car-glioma "glioblastoma CAR"

# 4. Export citations
autor ws export car-glioma -o workspace/car-glioma/references.bib
```

Then continue writing under `workspace/car-glioma/`:

- `literature-review.md`
- `related-work.md`
- `notes.md`
- `outline.md`

---

## 5. Inferring the Author's Intent from the README

The README is very explicit: the core goal of this project is **not** “build a traditional paper manager,” but rather something else.

### 5.1 Intent One: The Primary User Is an Agent, Not a Pure GUI User

The author repeatedly emphasizes:

- one terminal, one agent
- agent-agnostic
- a three-part combination of MCP server + skills + CLI

That tells us the main entry point is not a webpage, but rather:

- conversational agents
- CLI automation
- MCP tool calls

### 5.2 Intent Two: The Knowledge Base Is Infrastructure, Not the Final Product

The README keeps emphasizing:

- structured Markdown
- searchable indexes
- verifiable citations
- outputs that feed writing

In other words, `data/papers/` is only the foundation. The real goal is to support:

- literature discovery
- paper reproduction
- result cross-validation
- literature reviews and paper writing

### 5.3 Intent Three: A Workspace Is the Unit of a Research Project

From the skill design and directory conventions, it is clear that the author wants users to work around `workspace/<name>/` as a full research loop, rather than repeatedly searching the full library in the raw.

### 5.4 Intent Four: Progressive Information Loading to Reduce Noise

The L1–L4 loading model shows that the author does **not** want an agent to swallow the whole paper immediately. The intended order is metadata first, then abstract, then L3 paper-level takeaway, and only finally the full text. That is designed to:

- reduce token and cognitive load
- preserve efficiency from retrieval through writing

---

## 6. The Parts of This Workflow Most Worth Improving

The optimizations below all serve the original intent expressed in the README.

### 6.1 Improvement One: Unify Service Startup Behind One Command

Current pain points:

- the MCP server must be started separately
- the local MinerU API must be started separately
- users can easily get confused about the relationship among CLI, MCP, and MinerU

Suggested improvement:

add an aggregate command such as:

```bash
autor up
```

Ideal behavior:

- check `.venv`
- check the config files
- check whether local MinerU is alive
- automatically launch the MCP server when needed
- print a one-page health summary

Result:

- new users no longer have to memorize several startup commands
- the idea of a “local service stack” becomes much clearer

### 6.2 Improvement Two: Give `inbox-doc` a More Explicit Entry Point

Current pain points:

- `data/inbox-doc/` exists, but users often assume it needs a separate command
- in reality it is handled implicitly by `pipeline ingest`

Suggested improvement:

- add `autor ingest-doc`
- or explicitly print the meaning of all three inboxes in `pipeline --help`

Result:

- less confusion about “I dropped a PDF into the folder; what do I run next?”
- lower risk that users accidentally send technical reports through the normal paper pipeline

### 6.3 Improvement Three: Add “Search and Add to Workspace” in One Step

Current pain points:

- users usually have to search first, copy UUIDs, and then run `ws add`
- that flow is agent-friendly, but not very short for human terminal users

Suggested improvement:

add a command like:

```bash
autor ws add-query car-glioma "glioblastoma CAR" --top 10
```

Ideal behavior:

- run `usearch` first
- show candidates
- allow interactive selection or automatic add of the top N

Result:

- the workspace becomes the main entry point for topical organization rather than a post-processing container
- it matches the project-based research flow described in the README more closely

### 6.4 Improvement Four: Make the Writing Workflow a First-Class Product Surface

Current pain points:

- the README explicitly emphasizes writing capability
- but at the CLI layer the emphasis is still mainly search, show, workspace, and export
- new users do not easily understand how writing is supposed to happen inside a workspace

Suggested improvement:

- add `autor ws scaffold <name>`
- automatically generate:
  - `outline.md`
  - `literature-review.md`
  - `notes.md`
  - `references.bib`

Result:

- the “knowledge base” flows more smoothly into a “writing workbench”
- it fits the README's positioning of autor as an AI-native research terminal

### 6.5 Improvement Five: Print the Next Recommended Steps After Ingest

Current pain points:

- after `pipeline ingest` succeeds, the user still has to decide on their own whether the next step should be search, workspace creation, or export

Suggested improvement:

after the ingest summary, automatically print something like:

```text
Recommended next steps:
1. autor usearch "<possible topic keywords>"
2. autor ws init <workspace>
3. autor ws add <workspace> <paper_refs>
```

Result:

- the product becomes a guided research terminal rather than just a bag of tools
- new users are more likely to reach the workspace and writing phases

### 6.6 Improvement Six: Provide a Higher-Level Python API for Workspace Search

Current pain points:

- in Python, you currently need to call `read_paper_ids()` first and then pass the result into `unified_search(..., paper_ids=...)`
- that interface is fine for people who know the internals, but slightly heavy for ordinary researchers

Suggested improvement:

provide a higher-level helper like:

```python
workspace_search("car-glioma", "glioblastoma CAR", cfg)
```

Result:

- Python usage becomes closer to task semantics
- notebook and script integration becomes easier

---

## 7. The Shortest Daily Path I Recommend

If your main goal is topic-level literature management and writing, I suggest standardizing on this daily routine:

```bash
cd /mnt/f/autor
source .venv/bin/activate

# Start local MinerU if PDF conversion is needed
MINERU_MODEL_SOURCE=modelscope mineru-api --host 127.0.0.1 --port 8000

# Ingest
autor pipeline ingest

# Search the topic
autor usearch "glioblastoma CAR" --top 10

# Create a workspace and add candidate papers
autor ws init car-glioma
autor ws add car-glioma <paper_refs>

# Continue searching and writing inside the workspace
autor ws search car-glioma "IL13Ra2"
autor ws export car-glioma -o workspace/car-glioma/references.bib
```

In one sentence:

First ingest the papers into the library, then gather the topic into a workspace, and finally write and export citations from inside that workspace.
