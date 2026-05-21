# Search & Browse

AutoR search is now non-vector and auditable. `autor index` builds a
node-level SQLite FTS5 index from metadata plus full-text `paper.md` chunks.
Search results keep evidence snippets and source paths; `autor research`
writes a bounded evidence bundle with machine-readable trace/verify files.

## Search Modes

### Auditable Search

```bash
autor search "turbulent boundary layer"
autor search "Reynolds stress modeling"
```

`search` uses the deterministic node-level FTS5 path and aggregates evidence
nodes back to paper-level results.

### Evidence Bundle

```bash
autor research "What evidence supports Reynolds stress modeling?" \
  --run-dir workspace/runs/reynolds-stress
```

This writes:

- `bundle.roundNN.md`
- `bundle.md`
- `bundle.json`
- `trace.roundNN.json`
- `verify.roundNN.json`
- append-only `trace.jsonl`

Answer from the bundle, preserve the references section, and rerun with a
revised query if `verify.roundNN.json` reports insufficient evidence.

### Author Search

```bash
autor search-author "Smith"
```

## Viewing Papers

```bash
autor show <paper-id> --layer 1  # metadata
autor show <paper-id> --layer 2  # + abstract
autor show <paper-id> --layer 3  # + conclusion
autor show <paper-id> --layer 4  # full text
```

## Filtering

Search commands support filters:

```bash
autor search "turbulence" --year 2020-2024 --journal "JFM" --type review
```

## Top-Cited Papers

```bash
autor top-cited --top 20 --year 2020-
```
