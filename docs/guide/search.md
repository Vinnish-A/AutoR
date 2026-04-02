# Search & Browse

AutoR provides multiple search modes to find papers in your knowledge base.

## Search Modes

### Keyword Search (FTS5)

```bash
autor search "turbulent boundary layer"
```

Searches title, abstract, and conclusion using SQLite FTS5 full-text search.

### Semantic Search

```bash
autor vsearch "methods for predicting flow separation"
```

Uses Qwen3 embeddings + FAISS for meaning-based retrieval.

### Unified Search (Fusion)

```bash
autor usearch "Reynolds stress modeling"
```

Combines keyword and semantic results using Reciprocal Rank Fusion (RRF).

### Author Search

```bash
autor search-author "Smith"
```

## Viewing Papers

Load paper content at different detail levels:

```bash
autor show <paper-id> --layer 1  # metadata
autor show <paper-id> --layer 2  # + abstract
autor show <paper-id> --layer 3  # + conclusion
autor show <paper-id> --layer 4  # full text
```

## Filtering

All search commands support filters:

```bash
autor search "turbulence" --year 2020-2024 --journal "JFM" --type review
```

## Top-Cited Papers

```bash
autor top-cited --top 20 --year 2020-
```
