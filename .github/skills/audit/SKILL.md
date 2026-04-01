---
name: audit
description: Audit paper data quality in the knowledge base. Checks for missing fields, filename issues, DOI duplicates, title mismatches, and more. Supports LLM-based deep diagnosis for title mismatches and automated repair. Use when the user wants to check data quality, find problems, or fix metadata issues.
---

# Paper Audit

Check the data quality of papers already in the knowledge base. Runs in stages: rule-based checks (automatic) → LLM deep diagnosis (on suspicious items) → automated repair.

## Stage 1: Rule-Based Checks

```bash
autor audit [--severity error|warning|info]
```

Issues are classified by severity:
- **Error**: missing title, missing MD file, JSON parse failure, duplicate DOI
- **Warning**: missing DOI / abstract / year / authors / journal, MD too short, title mismatch, filename year mismatch
- **Info**: filename does not follow the standard format

## Stage 2: LLM Deep Diagnosis (title_mismatch items)

For each `title_mismatch` paper, use the Read tool to load meta.json and the first 80 lines of paper.md, then determine:
- Whether the actual subject/title in the MD body is consistent with the JSON metadata
- Whether it is harmless (a MinerU H1 recognition issue) vs. a genuine content mismatch

## Stage 3: Repair

For confirmed mismatches, use the `repair` command:

```bash
# Preview with dry-run first
autor repair "<paper-id>" --title "Correct Title" [--author "First Author"] [--year YYYY] [--doi "10.xxx/..."] --dry-run

# Apply after confirmation
autor repair "<paper-id>" --title "Correct Title" [--author "First Author"] [--year YYYY] [--doi "10.xxx/..."]

# Rebuild the index after repair
autor pipeline reindex
```

## Check Rules

| Rule | Level | Description |
|------|-------|-------------|
| `missing_title` | error | Title is absent |
| `missing_md` | error | No MD file corresponding to the JSON |
| `duplicate_doi` | error | Duplicate DOI |
| `missing_doi` | warning | DOI is absent |
| `missing_abstract` | warning | Abstract is absent |
| `title_mismatch` | warning | JSON title does not match MD H1 |
| `nonstandard_filename` | info | Filename does not follow the standard format |

## Examples

User says: "Check whether there are any problems in my paper library."
→ Run Stage 1 rule-based check

User says: "Run a deep check."
→ Run Stage 1 + Stage 2 (LLM diagnosis on each title_mismatch paper)

User says: "Fix the mismatched papers."
→ Run Stage 3
