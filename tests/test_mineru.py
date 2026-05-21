from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

from autor.ingest.mineru import (
    ConvertOptions,
    ConvertResult,
    MinerUCloudRateLimitError,
    _convert_long_pdf_cloud,
    _download_cloud_result,
    _flatten_assets,
    _resolve_cloud_model_version,
    convert_pdfs_cloud_batch,
    convert_pdfs_mixed_batch,
    strip_markdown_images,
)


def test_strip_markdown_images_removes_markdown_and_html_refs():
    text = "A\n![](images/a.png)\nB ![alt](x.jpg) C <img src=\"y.png\">"

    cleaned = strip_markdown_images(text)

    assert "![" not in cleaned
    assert "<img" not in cleaned.lower()
    assert "A" in cleaned
    assert "B" in cleaned
    assert "C" in cleaned


def test_download_cloud_result_discards_image_assets(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("paper.md", "Text\n\n![](images/a.png)\n\n<img src=\"images/b.jpg\">")
        zf.writestr("images/a.png", b"png")
        zf.writestr("images/b.jpg", b"jpg")
        zf.writestr("layout.json", "{}")

    class Response:
        status_code = 200
        content = buf.getvalue()

    monkeypatch.setattr("autor.ingest.mineru.requests.get", lambda *args, **kwargs: Response())

    md = _download_cloud_result({"full_zip_url": "https://example.test/result.zip"}, tmp_path)

    assert md is not None
    assert "![" not in md
    assert "<img" not in md.lower()
    assert (tmp_path / "layout.json").exists()
    assert not (tmp_path / "images").exists()


def test_flatten_assets_discards_images(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    images = src / "images"
    images.mkdir()
    (images / "a.png").write_bytes(b"png")
    (src / "layout.json").write_text("{}", encoding="utf-8")

    _flatten_assets(src, tmp_path, "paper")

    assert (tmp_path / "paper_layout.json").exists()
    assert not (tmp_path / "paper_images").exists()
    assert not src.exists()


def test_convert_long_pdf_cloud_preserves_cloud_model_version(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    chunk_pdf = tmp_path / "chunk-1.pdf"
    chunk_pdf.write_bytes(b"%PDF-1.4")

    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "autor.ingest.mineru._split_pdf",
        lambda _pdf_path, chunk_size, output_dir: [chunk_pdf],
    )

    def fake_convert_pdfs_cloud_batch(
        pdf_paths: list[Path],
        opts: ConvertOptions,
        *,
        api_key: str,
        cloud_url: str,
    ) -> list[ConvertResult]:
        captured["cloud_model_version"] = opts.cloud_model_version
        return [ConvertResult(pdf_path=pdf_paths[0], md_path=output_dir / "chunk-1.md", success=True)]

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_merge_chunk_results(chunk_results, original_pdf_path, out_dir):
        assert chunk_results[0].success is True
        assert original_pdf_path == pdf_path
        return ConvertResult(pdf_path=original_pdf_path, md_path=out_dir / "paper.md", success=True)

    monkeypatch.setattr("autor.ingest.mineru.convert_pdfs_cloud_batch", fake_convert_pdfs_cloud_batch)
    monkeypatch.setattr("autor.ingest.mineru._merge_chunk_results", fake_merge_chunk_results)

    opts = ConvertOptions(
        output_dir=output_dir,
        backend="pipeline",
        cloud_model_version="MinerU-HTML",
        lang="en",
    )

    result = _convert_long_pdf_cloud(
        pdf_path,
        opts,
        api_key="test-key",
        cloud_url="https://mineru.example",
    )

    assert result.success is True
    assert captured["cloud_model_version"] == "MinerU-HTML"


def test_resolve_cloud_model_version_falls_back_to_backend_when_unset():
    opts = ConvertOptions(backend="vlm-auto-engine", cloud_model_version="")
    assert _resolve_cloud_model_version(opts) == "vlm"


def test_resolve_cloud_model_version_uses_backend_mapping_by_default():
    opts = ConvertOptions(backend="vlm-auto-engine")
    assert _resolve_cloud_model_version(opts) == "vlm"


def test_convert_pdfs_cloud_batch_uses_one_worker_per_token(tmp_path, monkeypatch):
    pdf_paths = []
    for idx in range(4):
        pdf_path = tmp_path / f"paper-{idx}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        pdf_paths.append(pdf_path)

    calls: list[tuple[str, list[str]]] = []

    def fake_convert_chunk_cloud(pdf_paths, opts, *, api_key, cloud_url, token_id, query_limiter, poll_interval_seconds):
        calls.append((token_id, [p.name for p in pdf_paths]))
        return [
            ConvertResult(pdf_path=pdf_path, md_path=tmp_path / f"{pdf_path.stem}.md", success=True)
            for pdf_path in pdf_paths
        ]

    monkeypatch.setattr("autor.ingest.mineru._convert_chunk_cloud", fake_convert_chunk_cloud)

    results = convert_pdfs_cloud_batch(
        pdf_paths,
        ConvertOptions(output_dir=tmp_path),
        api_keys=["token-1", "token-2"],
        cloud_url="https://mineru.example",
        batch_size=1,
    )

    assert all(result.success for result in results)
    assert {token_id for token_id, _ in calls} == {"mineru_token_1", "mineru_token_2"}


def test_convert_pdfs_cloud_batch_requeues_one_token_429(tmp_path, monkeypatch):
    pdf_paths = []
    for idx in range(2):
        pdf_path = tmp_path / f"paper-429-{idx}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        pdf_paths.append(pdf_path)

    calls: list[str] = []
    raised = False

    def fake_convert_chunk_cloud(pdf_paths, opts, *, api_key, cloud_url, token_id, query_limiter, poll_interval_seconds):
        nonlocal raised
        calls.append(token_id)
        if token_id == "mineru_token_1" and not raised:
            raised = True
            raise MinerUCloudRateLimitError("rate limited")
        return [
            ConvertResult(pdf_path=pdf_path, md_path=tmp_path / f"{pdf_path.stem}.md", success=True)
            for pdf_path in pdf_paths
        ]

    monkeypatch.setattr("autor.ingest.mineru._convert_chunk_cloud", fake_convert_chunk_cloud)

    results = convert_pdfs_cloud_batch(
        pdf_paths,
        ConvertOptions(output_dir=tmp_path),
        api_keys=["token-1", "token-2"],
        cloud_url="https://mineru.example",
        batch_size=1,
        backoff_on_429_seconds=1,
    )

    assert all(result.success for result in results)
    assert "mineru_token_1" in calls
    assert "mineru_token_2" in calls


def test_convert_pdfs_mixed_batch_runs_local_and_each_token_source(tmp_path, monkeypatch):
    pdf_paths = []
    for idx in range(6):
        pdf_path = tmp_path / f"mixed-{idx}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        pdf_paths.append(pdf_path)

    local_calls: list[str] = []
    cloud_calls: list[tuple[str, list[str]]] = []

    def fake_convert_pdf(pdf_path, opts):
        local_calls.append(pdf_path.name)
        time.sleep(0.02)
        return ConvertResult(pdf_path=pdf_path, md_path=tmp_path / f"{pdf_path.stem}.md", success=True)

    def fake_convert_chunk_cloud(pdf_paths, opts, *, api_key, cloud_url, token_id, query_limiter, poll_interval_seconds):
        cloud_calls.append((token_id, [p.name for p in pdf_paths]))
        time.sleep(0.02)
        return [
            ConvertResult(pdf_path=pdf_path, md_path=tmp_path / f"{pdf_path.stem}.md", success=True)
            for pdf_path in pdf_paths
        ]

    monkeypatch.setattr("autor.ingest.mineru.convert_pdf", fake_convert_pdf)
    monkeypatch.setattr("autor.ingest.mineru._convert_chunk_cloud", fake_convert_chunk_cloud)

    results = convert_pdfs_mixed_batch(
        pdf_paths,
        ConvertOptions(output_dir=tmp_path),
        use_local=True,
        api_keys=["token-1", "token-2"],
        cloud_url="https://mineru.example",
        batch_size=1,
    )

    assert all(result.success for result in results)
    assert local_calls
    assert {token_id for token_id, _ in cloud_calls} == {"mineru_token_1", "mineru_token_2"}
