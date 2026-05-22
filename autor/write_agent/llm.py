"""Single external API boundary for write-agent."""

from __future__ import annotations

import json
from typing import Any

import requests

from autor.write_agent.config import resolve_api_key
from autor.write_agent.models import WriteAgentConfig


class WriteAgentAPIError(RuntimeError):
    """Raised when the write-agent external API call fails."""


def _chat_payload(
    prompt: str,
    config: WriteAgentConfig,
    *,
    system: str | None,
    json_mode: bool,
    model: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "model": model or config.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if config.thinking:
        payload["thinking"] = True
        payload["reasoning_effort"] = config.reasoning_effort
    return payload


def complete_text(
    prompt: str,
    config: WriteAgentConfig,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 2500,
    json_mode: bool = False,
) -> str:
    api_key = resolve_api_key(config)
    if not api_key:
        raise WriteAgentAPIError(
            "WRITE_AGENT_STATUS: WRITE_AGENT_API_FAILED\nFAILED_STAGE: write\nCAUSE_CLASS: api_failure\nMissing API key"
        )
    url = config.base_url.rstrip("/") + "/v1/chat/completions"
    payload = _chat_payload(prompt, config, system=system, json_mode=json_mode, model=model, max_tokens=max_tokens)
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])
    except Exception as e:
        raise WriteAgentAPIError(
            "WRITE_AGENT_STATUS: WRITE_AGENT_API_FAILED\nFAILED_STAGE: write\nCAUSE_CLASS: api_failure\n" + str(e)
        ) from e


def complete_json(
    prompt: str,
    config: WriteAgentConfig,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 2500,
) -> dict[str, Any]:
    json_prompt = prompt.rstrip() + "\n\nReturn valid JSON only."
    text = complete_text(json_prompt, config, system=system, model=model, max_tokens=max_tokens, json_mode=True)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise WriteAgentAPIError(
            "WRITE_AGENT_STATUS: WRITE_AGENT_API_FAILED\nFAILED_STAGE: write\nCAUSE_CLASS: api_failure\nInvalid JSON output"
        ) from e
