# WriteAgent Pattern Library

This directory contains curated writing-pattern policy data used by `autor/write_agent`.
It stores source metadata, movement annotations, short excerpts where allowed, and reusable pattern rules.
It does not store full copyrighted articles or raw retrieval dumps.

## Files

- `sources.yaml`: source metadata used by positive and negative corpora.
- `license-audit.tsv`: source-level reuse policy and storage limits.
- `human-moves.json`: positive human writing moves required by section contracts.
- `negative-patterns.json`: reusable anti-patterns used by deterministic gates.
- `positive-passages.jsonl`: annotated positive writing patterns.
- `failure-cases.jsonl`: real and empirical negative cases.
- `table-patterns.jsonl`: table design patterns that adjudicate evidence.
- `lexical-ai-markers.jsonl`: lexical/style markers with severity and source trace.
- `rewrite-recipes.jsonl`: pattern-specific rewrite actions.

## Storage Policy

Open-license sources may have bounded excerpts only when license metadata is recorded.
Non-open or unclear-license sources store metadata, move annotations, and short excerpts only.
Raw retrieval caches belong under `workspace/_pattern_research_cache/`, not in this package.
