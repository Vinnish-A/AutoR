---
name: metrics
description: View LLM token usage, API call timing, and runtime metrics. Use when the user asks about token consumption, API costs, or performance statistics.
---

# View Usage Metrics

View LLM token usage, API call timing, and other runtime metrics.

## Execution Logic

**View recent LLM call details:**
```bash
autor metrics --last 20
```

**View aggregate statistics:**
```bash
autor metrics --summary
```

**View a specific time period:**
```bash
autor metrics --since 2026-03-01
```

**View other event categories:**
```bash
autor metrics --category api --last 50
```

## Examples

User says: "How many tokens have I used?"
→ Run `metrics --summary`

User says: "Show me the recent LLM calls."
→ Run `metrics --last 10`
