"""Tests for GPT Image 2 plot generation helpers and CLI glue."""

from __future__ import annotations

import base64
import json
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from autor import cli, plot
from autor.config import _build_config

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0xUAAAAASUVORK5CYII="
)


@pytest.fixture()
def mock_plot_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            self.server.requests.append(  # type: ignore[attr-defined]
                {
                    "path": self.path,
                    "json": body,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            if self.path == "/v1/draw/completions":
                self._send_json({"code": 0, "msg": "success", "data": {"id": "job-123"}})
                return
            if self.path == "/v1/draw/result":
                port = self.server.server_address[1]  # type: ignore[attr-defined]
                self._send_json(
                    {
                        "code": 0,
                        "msg": "success",
                        "data": {
                            "id": body["id"],
                            "results": [
                                {
                                    "url": f"http://127.0.0.1:{port}/mock.png",
                                    "content": "Mock biomedical figure",
                                }
                            ],
                            "progress": 100,
                            "status": "succeeded",
                            "failure_reason": "",
                            "error": "",
                        },
                    }
                )
                return
            self._send_json({"code": -1, "msg": "not found"}, status=404)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/mock.png":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(_PNG_1X1)))
            self.end_headers()
            self.wfile.write(_PNG_1X1)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server.requests  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class TestGeneratePlot:
    def test_generate_plot_downloads_image_and_writes_metadata(self, tmp_path, mock_plot_server):
        base_url, requests_seen = mock_plot_server
        cfg = _build_config({"plot": {"host": base_url, "api_key": "plot-key"}}, tmp_path)
        cfg.ensure_dirs()

        summary = plot.generate_plot(
            "English biomedical overview figure",
            cfg=cfg,
            workspace="car-glioma",
            name="overview",
        )

        image_path = Path(summary["files"][0])
        meta_path = Path(summary["meta_file"])
        assert image_path.exists()
        assert meta_path.exists()
        assert image_path.parent == tmp_path / "workspace" / "car-glioma" / "figure"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["request"]["model"] == "gpt-image-2"
        assert meta["request"]["aspectRatio"] == "auto"
        assert requests_seen[0]["authorization"] == "Bearer plot-key"
        assert requests_seen[0]["json"]["webHook"] == "-1"
        assert "imageSize" not in requests_seen[0]["json"]

    def test_generate_plot_requires_api_key(self, tmp_path):
        cfg = _build_config({}, tmp_path)
        with pytest.raises(plot.PlotError, match="API key"):
            plot.generate_plot("English prompt", cfg=cfg)


class TestCmdPlot:
    def test_cmd_plot_reads_prompt_file(self, tmp_path, monkeypatch):
        cfg = _build_config({}, tmp_path)
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("English figure prompt", encoding="utf-8")

        captured: dict[str, str] = {}

        def fake_generate_plot(prompt: str, **kwargs):
            captured["prompt"] = prompt
            return {
                "id": "job-1",
                "files": [str(tmp_path / "workspace" / "car-glioma" / "figure" / "overview.png")],
                "meta_file": str(tmp_path / "workspace" / "car-glioma" / "figure" / "overview.json"),
            }

        monkeypatch.setattr(plot, "generate_plot", fake_generate_plot)
        messages: list[str] = []
        monkeypatch.setattr(cli, "ui", messages.append)

        args = Namespace(
            prompt=[],
            prompt_file=str(prompt_file),
            workspace="car-glioma",
            output_dir=None,
            name="overview",
            ref_url=None,
            host=None,
            api_key=None,
            model=None,
            aspect_ratio=None,
            timeout=None,
            poll_interval=None,
        )

        cli.cmd_plot(args, cfg)

        assert captured["prompt"] == "English figure prompt"
        assert any("已生成 1 张图片" in message for message in messages)
