"""Write-agent configuration adapter."""

from __future__ import annotations

import os
from typing import Any

from autor.write_agent.models import WriteAgentConfig


def from_autor_config(cfg: Any) -> WriteAgentConfig:
    raw = getattr(cfg, "write_agent", None)
    if raw is None:
        raw = {}
    elif not isinstance(raw, dict):
        raw = raw.__dict__
    return WriteAgentConfig(
        enabled=bool(raw.get("enabled", True)),
        provider=raw.get("provider", "deepseek"),
        base_url=raw.get("base_url", "https://api.deepseek.com"),
        model=raw.get("model", "deepseek-v4-pro"),
        fast_model=raw.get("fast_model", "deepseek-v4-flash"),
        api_key_env=raw.get("api_key_env", "DEEPSEEK_API_KEY"),
        api_key=raw.get("api_key", "") or (cfg.resolved_api_key() if hasattr(cfg, "resolved_api_key") else ""),
        seed_count=max(1, int(raw.get("seed_count", 9))),
        max_rounds=max(1, int(raw.get("max_rounds", 2))),
        audit_assumption_label=raw.get("audit_assumption_label", "Claude-family LLM-written manuscript"),
        external_critic_model_label=raw.get("external_critic_model_label", "GPT-5.5 thinking high"),
        thinking=bool(raw.get("thinking", True)),
        reasoning_effort=raw.get("reasoning_effort", "high"),
        writer_backend_label=raw.get("writer_backend_label", "DeepSeek write-agent"),
        external_critic_required=bool(raw.get("external_critic_required", True)),
        timeout=max(1, int(raw.get("timeout", 120))),
    )


def resolve_api_key(config: WriteAgentConfig) -> str:
    return os.environ.get(config.api_key_env, "") or os.environ.get("AUTOR_LLM_API_KEY", "") or config.api_key
