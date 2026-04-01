---
name: index
description: Rebuild FTS5 full-text search index or FAISS semantic vector index. Use when the user wants to update or rebuild search indexes after metadata changes.
---

# Rebuild Indexes

Rebuild the FTS5 full-text search index or the FAISS semantic vector index.

## Execution Logic

**Incrementally update the FTS5 full-text index:**
```bash
autor index
```

**Fully rebuild the FTS5 full-text index:**
```bash
autor index --rebuild
```

**Incrementally update the semantic vector index:**
```bash
autor embed
```

**Fully rebuild the semantic vector index:**
```bash
autor embed --rebuild
```

**Update both:**
```bash
autor pipeline reindex
```

## Examples

User says: "Rebuild the index."
→ Run `pipeline reindex`

User says: "Rebuild only the full-text index."
→ Run `index --rebuild`

User says: "Update the vectors."
→ Run `embed`
