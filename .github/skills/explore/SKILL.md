---
name: explore
description: Explore literature by fetching papers from OpenAlex with multi-dimensional filters (ISSN, concept, author, institution, keyword, etc.), building local embeddings, running BERTopic clustering, and multi-mode search (semantic/keyword/unified). Data is isolated in data/explore/<name>/. Use when the user wants to survey a journal, explore a research field, analyze an author's output, or do landscape analysis.
---

# Multi-Dimensional Literature Exploration

Fetch literature from OpenAlex (with multi-dimensional filters), build local embeddings + BERTopic clustering + multi-mode search, for literature surveying. Data is fully isolated from the main library.

## Execution Logic

### Fetch Papers

Supports multiple filter dimensions in any combination:

```bash
# By journal ISSN
autor explore fetch --issn <ISSN> --name <name> [--year-range <start-end>]

# By research concept
autor explore fetch --concept <OpenAlex-concept-ID> --name <name>

# By author
autor explore fetch --author <OpenAlex-author-ID> --name <name>

# By institution
autor explore fetch --institution <OpenAlex-institution-ID> --name <name>

# By keyword
autor explore fetch --keyword "acoustic metamaterial" --name <name>

# Multi-dimensional with citation filter
autor explore fetch --institution I123 --year-range 2020-2025 --min-citations 50 --name <name>

# Incremental update (append new papers, DOI-deduplicated)
autor explore fetch --issn 0022-1120 --name jfm --incremental
```

All filter parameters:
- `--issn` — journal ISSN
- `--concept` — OpenAlex concept ID
- `--topic-id` — OpenAlex topic ID
- `--author` — OpenAlex author ID
- `--institution` — OpenAlex institution ID
- `--keyword` — title/abstract keyword search
- `--source-type` — source type (journal/conference/repository)
- `--oa-type` — paper type (article/review, etc.)
- `--min-citations` — minimum citation count
- `--year-range` — year filter (e.g. 2020-2025)
- `--name` — explore library name (derived from filters by default)
- `--incremental` — incremental update mode

Common journal ISSNs:
- JFM (Journal of Fluid Mechanics): 0022-1120
- PoF (Physics of Fluids): 1070-6631
- JCP (Journal of Computational Physics): 0021-9991
- IJMF (Int J Multiphase Flow): 0301-9322

### Build Embeddings

```bash
autor explore embed --name <name> [--rebuild]
```

### Topic Clustering

```bash
autor explore topics --name <name> --build
autor explore topics --name <name> --rebuild --nr-topics <N>
autor explore topics --name <name>
autor explore topics --name <name> --topic <ID> [--top N]
```

### Search (Three Modes)

```bash
# Semantic search (default)
autor explore search --name <name> "<query>" [--top N]

# Keyword search (FTS5)
autor explore search --name <name> "<query>" --mode keyword

# Unified search (semantic + keyword, RRF ranking)
autor explore search --name <name> "<query>" --mode unified
```

### Generate Visualizations

```bash
autor explore viz --name <name>
```

### View Explore Library Info

```bash
autor explore info
autor explore info --name <name>
```

For a brand-new explore library, the full workflow is: fetch → embed → topics --build → viz

## Examples

User says: "Fetch all papers from JFM."
→ Run `explore fetch --issn 0022-1120 --name jfm`

User says: "Show me the research landscape on acoustic metamaterials."
→ Run `explore fetch --keyword "acoustic metamaterial" --name acoustic-metamaterial`

User says: "Fetch highly cited papers from an institution in the past 5 years."
→ Run `explore fetch --institution I123 --year-range 2020-2025 --min-citations 50 --name inst-highcite`

User says: "Search JFM for drag reduction."
→ Run `explore search --name jfm "drag reduction"`

User says: "Keyword search for turbulence in JFM."
→ Run `explore search --name jfm "turbulence" --mode keyword`

User says: "Update the JFM explore library."
→ Run `explore fetch --issn 0022-1120 --name jfm --incremental`

User says: "What explore libraries do I have?"
→ Run `explore info`
