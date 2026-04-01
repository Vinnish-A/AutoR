---
name: topics
description: Explore topic distribution in the paper library using BERTopic clustering. Build/rebuild topic models, view topic overview, list papers in a topic, merge similar topics, and generate HTML visualizations. Use when the user asks about research themes, topic distribution, or wants to discover cross-domain connections.
---

# Topic Exploration

Explore the topic distribution of the paper library and discover cross-domain connections. Powered by BERTopic clustering.

## Execution Logic

1. Determine user intent:
   - "Build model" / "rebuild topics" → build or rebuild
   - "Merge topics" / "reduce to N topics" → intelligent merge
   - "Visualize" / "plot" → generate HTML
   - View details of a specific topic → topic query
   - View outliers → topic -1
   - Default: show topic overview

2. Run the command:

**Build / rebuild the topic model:**
```bash
autor topics --build
autor topics --rebuild [--min-topic-size N]
```

**Manually merge specified topics (format: comma-separated IDs in the same group, + to separate groups):**
```bash
autor topics --merge "1,6,14+3,5"
```

**Algorithmically reduce to N topics:**
```bash
autor topics --reduce <N>
```

**View topic overview:**
```bash
autor topics
```

**View papers in a specific topic:**
```bash
autor topics --topic <ID> [--top N]
```

**Generate HTML visualizations (6 charts):**
```bash
autor topics --viz
```

3. **Intelligent merge workflow** (when the user requests merging or consolidation):
   a. First run `topics` to get an overview of all topics
   b. Analyze the keywords of each topic and identify which ones belong to the same research direction academically
   c. Generate a merge plan
   d. Execute the merge with `--merge`

## Examples

User says: "Show me the topic distribution of my library."
→ Run `topics`

User says: "What papers are in topic 2?"
→ Run `topics --topic 2`

User says: "Merge similar topics."
→ First run `topics` to view the overview, analyze keywords, then run `topics --merge "1,6,14+3,5"`

User says: "Plot a topic distribution chart."
→ Run `topics --viz`
