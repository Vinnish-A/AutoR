# Configuration

AutoR uses two config files:

| File | Tracked | Purpose |
|------|---------|---------|
| `config.yaml` | Yes | Default settings |
| `config.local.yaml` | No (git-ignored) | API keys and local overrides |

## API Keys

LLM API key lookup order:

1. `config.local.yaml` → `llm.api_key`
2. Environment variable `AUTOR_LLM_API_KEY`
3. Environment variable `DEEPSEEK_API_KEY`
4. Environment variable `OPENAI_API_KEY`

### Example `config.local.yaml`

```yaml
llm:
  api_key: "sk-your-key-here"

ingest:
  mineru_api_keys:
    - "your-mineru-key"
    - "your-second-mineru-key"
```

## Key Settings

### LLM Backend

Default: DeepSeek (`deepseek-chat`) via OpenAI-compatible protocol.

```yaml
llm:
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
```

### Metadata Extraction

```yaml
ingest:
  extractor: robust  # regex + LLM (default)
  # Other options: auto, regex, llm
```

### Search

```yaml
search:
  top_k: 20  # default paper-level results for node-level FTS5 search
```
