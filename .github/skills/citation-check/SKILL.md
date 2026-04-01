---
name: citation-check
description: Verify citations in AI-generated or human-written text against the local knowledge base and external APIs. Catches hallucinated references, wrong metadata, and missing papers. Use when the user wants to check if citations are real and accurate.
---

# Citation Verification

Check whether citations in text are real and accurate — prevents AI-hallucinated references and metadata errors.

**Important context**: Roughly 40% of citations in AI-generated academic text may be hallucinated (fabricated papers, misattributed authorship, assembled metadata). Even human-written text frequently contains year/journal errors. The goal of this skill is to eliminate all citation problems before submission.

## Prerequisites

The user provides text to check (pasted inline, a file path, or a draft file in a workspace).
If a workspace is available, validation is preferentially scoped to it.

## Execution Logic

### 1. Extract Citations

Extract all citations from the text, recognizing these formats:
- `(Author, Year)` / `Author (Year)` — parenthetical citations
- `\cite{key}` / `\citep{key}` / `\citet{key}` — LaTeX citations
- `[N]` — numbered citations (require a reference list)

### 2. Verify Each Citation

Apply a three-layer check to every citation:

**Layer 1 — Local library match**
```bash
autor search-author "<Author>" --top 5
autor usearch "<keywords from title>" --top 5
```
After finding a match in the local library, verify: author names, year, title, and journal are consistent.

**Layer 2 — DOI / metadata cross-check**
If a match exists in the local library, read the DOI and detailed metadata from meta.json for cross-validation.
If no local match is found, flag the citation — it is not in the workspace/knowledge base.

**Layer 3 — Content consistency**
For key citations (those supporting core claims), load L2–L3:
```bash
autor show <dir_name> --level 3
```
Verify: does the text's description of the paper match the paper's actual content? Is there over-interpretation or selective quotation?

### 3. Output Report

Generate a verification report with a status label for every citation:

| Status | Meaning |
|--------|---------|
| **VERIFIED** | Found in local library with consistent metadata |
| **METADATA MISMATCH** | Paper found but author/year/title differs |
| **NOT IN LIBRARY** | Paper not present in the local library |
| **CONTENT MISMATCH** | Paper content does not match the in-text description |
| **SUSPICIOUS** | Cannot be verified; likely a hallucinated citation |

Provide specific correction suggestions for each problematic citation.

## Common Problem Patterns

- **AI hallucination**: an author name and year are combined to produce a non-existent paper — flag as SUSPICIOUS
- **Misattribution**: a real paper is cited but the text describes a different paper — flag as CONTENT MISMATCH
- **Metadata error**: year off by one, journal name misspelled, wrong first author — flag as METADATA MISMATCH and provide the correct value
- **Over-citation**: a single claim backed by 5+ citations that are mostly tangential — suggest trimming

## Examples

User says: "Check whether the citations in this passage are correct."
→ Extract citations, search for each in the local library, output verification report

User says: "Check citations in workspace/my-paper/introduction.md."
→ Read the file, extract citations, verify within workspace scope
