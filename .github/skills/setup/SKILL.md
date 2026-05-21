---
name: setup
description: Initialize and diagnose the autor environment. Run interactive setup wizard (bilingual EN/ZH) to install dependencies, create config files, and configure API keys. Run status check to see what's installed and what's missing. Use when the user wants to set up, install, configure, or troubleshoot autor.
---

# Setup / Environment Configuration

When the user needs to configure, install, or initialize autor, follow this workflow:

## 1. Diagnose the Current State

```bash
autor setup check --lang zh
```

Read the output to see which components are ready and which are missing.

## 2. Guide the User Based on What's Missing

### Missing dependencies
- Tell the user which dependencies are absent and explain what each group is used for:
  - `import`: Endnote / Zotero import
  - `full`: all features
- Run `pip install -e ".[full]"` or install selectively

### Missing config.yaml
- Run `autor setup` to launch the interactive wizard and create it automatically
- Or create it directly for the user (the default config is sufficient)

### API key not configured
- **LLM key** (DeepSeek / OpenAI): ask whether the user has one. Without it, the system still works, but metadata extraction falls back to pure regex and enrichment is unavailable.
- **MinerU key**: ask whether the user needs to process PDFs. If not, skip this step (only `.md` files will be ingested).
- Write the key(s) to `config.local.yaml` (not tracked by git)

### Directories not found
- After running `autor setup check`, any missing directories will be created automatically the next time any `autor` command is run (`ensure_dirs()`)

## 3. Verify

After configuration, run `autor setup check` again to confirm all items show [OK].

## Notes

- The user can also run `autor setup` directly to enter the interactive wizard (bilingual EN/ZH)
- `config.local.yaml` stores sensitive information (API keys) and is not tracked by git
- AutoR no longer downloads embedding models or builds FAISS/vector storage
