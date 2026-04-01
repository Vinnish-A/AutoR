---
name: rename
description: Rename paper directories to standardized Author-Year-Title format based on JSON metadata. Use when the user wants to normalize filenames after metadata corrections.
---

# Rename Paper Files

Normalize paper directory names (to the `Author-Year-Title` format) based on JSON metadata.

## Execution Logic

1. Determine user intent:
   - Rename a single paper: specify a paper_id
   - Rename all papers: use `--all`
   - Preview before applying: use `--dry-run`

2. Run the command:

**Preview all renames:**
```bash
autor rename --all --dry-run
```

**Apply all renames:**
```bash
autor rename --all
```

**Rename a single paper:**
```bash
autor rename <paper-id>
```

3. After renaming, it is recommended to rebuild the index:
```bash
autor pipeline reindex
```

## Examples

User says: "Clean up my paper filenames."
→ First run `rename --all --dry-run` to preview, then apply with `rename --all` after confirmation
