---
name: export
description: Export papers from the knowledge base to standard citation formats like BibTeX. Supports exporting all papers, specific papers, or filtered by year/journal. Use when the user needs BibTeX entries, reference files, or citation export.
---

# Export Papers

Export papers from the local library in standard citation formats (BibTeX).

## Execution Logic

**Export all papers to screen:**
```bash
autor export bibtex --all
```

**Export all papers to a file:**
```bash
autor export bibtex --all -o workspace/library.bib
```

**Export specific papers:**
```bash
autor export bibtex "Smith-2023-Turbulence" "Doe-2024-DNS"
```

**Export filtered by year:**
```bash
autor export bibtex --all --year 2020-2024 -o workspace/recent.bib
```

**Export filtered by journal:**
```bash
autor export bibtex --all --journal "Fluid Mechanics" -o workspace/jfm.bib
```

## Examples

User says: "Export all my papers as BibTeX."
→ Run `export bibtex --all`

User says: "Export papers from 2020 onwards to a bib file."
→ Run `export bibtex --all --year 2020- -o workspace/recent.bib`

User says: "Give me the citation for Smith-2023-Turbulence."
→ Run `export bibtex "Smith-2023-Turbulence"`

User says: "Export citations for DNS-related papers."
→ First search with `search "DNS"`, extract directory names from the results, then run `export bibtex <dir1> <dir2> ...`
