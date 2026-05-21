---
name: index
description: Rebuild the node-level SQLite FTS5 evidence index. Use when the user asks to rebuild search, refresh search after metadata/full-text changes, or repair missing search results.
---

# Rebuild Index

AutoR no longer builds FAISS or embedding storage. `autor index` builds:

- paper-level metadata/registry tables
- citation graph tables
- `paper_nodes`
- `paper_node_fts` for auditable evidence retrieval

## Execution Logic

**Incrementally update the evidence index:**
```bash
autor index
```

**Fully rebuild the evidence index:**
```bash
autor index --rebuild
```

Full rebuilds use a temporary SQLite database by default, then replace
`data/index.db` after a successful build. This avoids long WAL writes on
Windows-mounted WSL paths. Use `--direct` only for diagnosis.

**Check index health without rebuilding:**
```bash
autor index --status
```

**Queue a rebuild in the background:**
```bash
autor index --rebuild --background
```

**Pipeline preset:**
```bash
autor pipeline reindex
```

## Examples

User says: "Rebuild the index."
→ Run `autor index --rebuild`

User says: "Search results look stale after editing paper.md."
→ Run `autor index --rebuild`

User says: "Update the vectors."
→ Explain vector storage has been removed, then run `autor index --rebuild` if they meant search refresh.
