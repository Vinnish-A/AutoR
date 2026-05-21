"""
plot.py -- GPT Image 2 generation client
========================================

Submit image-generation jobs to a GPT Image 2-compatible relay service,
poll for completion, and persist downloaded images into ``workspace/``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from autor.ingest.metadata import _sanitize_for_filename

_log = logging.getLogger(__name__)

_DRAW_PATH = "/v1/draw/completions"
_RESULT_PATH = "/v1/draw/result"
_VALID_MODELS = {
    "gpt-image-2",
}
_VALID_ASPECT_RATIOS = {
    "auto",
    "1:1",
    "3:2",
    "2:3",
    "16:9",
    "9:16",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "21:9",
    "9:21",
    "1:3",
    "3:1",
    "2:1",
    "1:2",
}
_EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


class PlotError(RuntimeError):
    """Raised when a plot request cannot be completed."""


def build_payload(
    prompt: str,
    cfg,
    *,
    model: str | None = None,
    aspect_ratio: str | None = None,
    urls: list[str] | None = None,
) -> dict[str, Any]:
    """Build and validate a GPT Image 2 request payload.

    Args:
        prompt: Image-generation prompt.
        cfg: Loaded autor config object.
        model: Optional model override.
        aspect_ratio: Optional aspect-ratio override.
        urls: Optional reference image URLs.

    Returns:
        Validated JSON payload ready for API submission.

    Raises:
        PlotError: If any parameter is invalid.
    """
    text = (prompt or "").strip()
    if not text:
        raise PlotError("prompt 不能为空")

    resolved_model = (model or cfg.plot.model).strip()
    if resolved_model not in _VALID_MODELS:
        raise PlotError(f"不支持的模型: {resolved_model}")

    resolved_ratio = (aspect_ratio or cfg.plot.aspect_ratio).strip()
    if resolved_ratio not in _VALID_ASPECT_RATIOS:
        raise PlotError(f"不支持的 aspectRatio: {resolved_ratio}")

    clean_urls = [u.strip() for u in (urls or []) if u and u.strip()]
    payload: dict[str, Any] = {
        "model": resolved_model,
        "prompt": text,
        "aspectRatio": resolved_ratio,
        "webHook": "-1",
        "shutProgress": True,
    }
    if clean_urls:
        payload["urls"] = clean_urls
    return payload


def default_output_dir(cfg, workspace: str | None = None, output_dir: Path | None = None) -> Path:
    """Return the directory where generated figures should be written."""
    if output_dir is not None:
        return output_dir
    if workspace:
        return cfg._root / "workspace" / workspace / "figure"
    return cfg._root / "workspace" / "figure"


def generate_plot(
    prompt: str,
    *,
    cfg,
    workspace: str | None = None,
    output_dir: Path | None = None,
    name: str | None = None,
    urls: list[str] | None = None,
    host: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
    timeout: int | None = None,
    poll_interval: int | None = None,
) -> dict[str, Any]:
    """Generate image(s), download them, and persist metadata.

    Args:
        prompt: Image-generation prompt.
        cfg: Loaded autor config.
        workspace: Optional workspace name; outputs go to ``workspace/<name>/figure``.
        output_dir: Optional explicit output directory.
        name: Optional filename stem override.
        urls: Optional reference image URLs.
        host: Optional API host override.
        api_key: Optional API key override.
        model: Optional model override.
        aspect_ratio: Optional aspect ratio override.
        timeout: Optional total timeout override in seconds.
        poll_interval: Optional polling interval override in seconds.

    Returns:
        Summary with downloaded files and response metadata locations.

    Raises:
        PlotError: If the request fails or the API returns an error.
    """
    key = (api_key or cfg.resolved_plot_api_key()).strip()
    if not key:
        raise PlotError("未配置绘图 API key（plot.api_key 或 AUTOR_PLOT_API_KEY）")

    base_url = (host or cfg.plot.host).rstrip("/")
    total_timeout = max(1, int(timeout or cfg.plot.timeout))
    interval_s = max(1, int(poll_interval or cfg.plot.poll_interval))
    payload = build_payload(
        prompt,
        cfg,
        model=model,
        aspect_ratio=aspect_ratio,
        urls=urls,
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    submit_data = _post_json(
        f"{base_url}{_DRAW_PATH}",
        payload,
        headers=headers,
        timeout=min(total_timeout, 60),
    )
    result_data = _extract_result_data(submit_data)
    if result_data is None:
        job_id = _extract_job_id(submit_data)
        result_data = _poll_result(
            base_url,
            job_id,
            headers=headers,
            timeout=total_timeout,
            poll_interval=interval_s,
        )

    output_root = default_output_dir(cfg, workspace=workspace, output_dir=output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stem = _ensure_unique_stem(output_root, name or _derive_stem(prompt))
    files = _download_results(result_data, output_root, stem, timeout=min(total_timeout, 120))

    meta = {
        "id": result_data.get("id"),
        "status": result_data.get("status"),
        "progress": result_data.get("progress"),
        "request": payload,
        "results": result_data.get("results") or [],
        "files": [str(p) for p in files],
    }
    meta_path = output_root / f"{stem}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "id": result_data.get("id"),
        "status": result_data.get("status"),
        "files": [str(p) for p in files],
        "meta_file": str(meta_path),
        "output_dir": str(output_root),
        "prompt": payload["prompt"],
        "model": payload["model"],
        "aspect_ratio": payload["aspectRatio"],
    }


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        raise PlotError(f"{data.get('msg') or '绘图接口返回错误'}")
    return data


def _extract_job_id(data: dict[str, Any]) -> str:
    job_id = ""
    if isinstance(data.get("data"), dict):
        job_id = str(data["data"].get("id") or "").strip()
    if not job_id:
        job_id = str(data.get("id") or "").strip()
    if not job_id:
        raise PlotError("绘图接口未返回任务 ID")
    return job_id


def _extract_result_data(data: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(data.get("data"), dict) and data["data"].get("status"):
        return data["data"]
    if data.get("status"):
        return data
    return None


def _poll_result(
    base_url: str,
    job_id: str,
    *,
    headers: dict[str, str],
    timeout: int,
    poll_interval: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        data = _post_json(
            f"{base_url}{_RESULT_PATH}",
            {"id": job_id},
            headers=headers,
            timeout=min(timeout, 60),
        )
        result = _extract_result_data(data)
        if result is None:
            raise PlotError("查询结果接口返回结构异常")
        status = str(result.get("status") or "").strip().lower()
        if status == "succeeded":
            return result
        if status == "failed":
            reason = result.get("failure_reason") or "error"
            detail = result.get("error") or ""
            raise PlotError(f"任务失败: {reason}{f' ({detail})' if detail else ''}")
        time.sleep(poll_interval)
    raise PlotError(f"任务超时（{timeout}s）: {job_id}")


def _download_results(result: dict[str, Any], output_dir: Path, stem: str, *, timeout: int) -> list[Path]:
    items = result.get("results") or []
    if not items:
        raise PlotError("绘图任务成功但未返回图片结果")
    paths: list[Path] = []
    for idx, item in enumerate(items, start=1):
        url = str(item.get("url") or "").strip()
        if not url:
            raise PlotError("绘图结果缺少图片 URL")
        suffix = "" if len(items) == 1 else f"-{idx}"
        paths.append(_download_one(url, output_dir, f"{stem}{suffix}", timeout=timeout))
    return paths


def _download_one(url: str, output_dir: Path, stem: str, *, timeout: int) -> Path:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            # Some result CDNs fail through local HTTPS proxies with EOF errors.
            resp = requests.get(url, timeout=timeout, proxies={"http": None, "https": None})
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(2 * attempt)
    else:
        raise PlotError(f"图片下载失败: {last_error}")
    ext = _guess_extension(url, resp.headers.get("Content-Type"))
    path = output_dir / f"{stem}{ext}"
    path.write_bytes(resp.content)
    return path


def _guess_extension(url: str, content_type: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[mime]
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix
    if ext:
        return ext
    guessed, _ = mimetypes.guess_type(url)
    if guessed and guessed in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[guessed]
    return ".png"


def _derive_stem(prompt: str) -> str:
    text = _sanitize_for_filename((prompt or "").strip()[:80], max_bytes=80)
    return text or "plot"


def _ensure_unique_stem(output_dir: Path, stem: str) -> str:
    base = _sanitize_for_filename(stem.strip(), max_bytes=80) or "plot"
    candidate = base
    index = 2
    while any((output_dir / f"{candidate}{suffix}").exists() for suffix in (".png", ".jpg", ".webp", ".json")):
        candidate = f"{base}-{index}"
        index += 1
    return candidate
