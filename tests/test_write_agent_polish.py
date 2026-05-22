from __future__ import annotations

from types import SimpleNamespace

from autor.write_agent.integrate import create_skeleton, replace_section
from autor.write_agent.models import SectionKernel
from autor.write_agent.polish import run_polish
from autor.write_agent.workspace_io import write_jsonl


def _cfg(tmp_path):
    return SimpleNamespace(
        _root=tmp_path,
        write_agent={
            "model": "deepseek-v4-pro",
            "fast_model": "deepseek-v4-flash",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
    )


def _workspace(tmp_path):
    ws_dir = tmp_path / "workspace" / "polish-ws"
    kernel = SectionKernel(
        section_id="S1",
        title="Evidence section",
        controlling_claim="Direct evidence constrains the endpoint claim.",
        evidence_keys=["Smith2024"],
    )
    create_skeleton(ws_dir, [kernel])
    source = (
        "## Evidence section\n\n"
        "This section discusses the workspace draft. Direct evidence tiers show endpoint uncertainty "
        "and unresolved assay proof [@Smith2024]."
    )
    replace_section(ws_dir, "S1", "Evidence section", source)
    write_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl", [kernel])
    write_jsonl(
        ws_dir / "sidecars" / "section-pattern-contracts.jsonl",
        [
            {
                "section_id": "S1",
                "section_kind": "evidence",
                "required_moves": ["evidence_tiering", "precise_uncertainty"],
                "preferred_moves": ["verbs_carry_judgment"],
                "forbidden_patterns": ["generic_validation_ending"],
            }
        ],
    )
    return ws_dir


def test_missing_write_md_returns_blocked(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "workspace" / "missing").mkdir(parents=True)

    result = run_polish("missing", cfg)

    assert result.status == "BLOCKED_BY_MISSING_INPUT"
    assert result.failed_stage == "polish"


def test_polish_preserves_citekeys_and_updates_anchor(tmp_path, monkeypatch):
    ws_dir = _workspace(tmp_path)
    cfg = _cfg(tmp_path)

    def fake_complete(*_args, **_kwargs):
        return "## Evidence section\n\nDirect evidence tiers show endpoint uncertainty and unresolved assay proof [@Smith2024]."

    monkeypatch.setattr("autor.write_agent.llm.complete_text", fake_complete)
    result = run_polish("polish-ws", cfg, round_no=1)

    text = (ws_dir / "write.md").read_text(encoding="utf-8")
    assert result.status == "WRITE_READY_FOR_EXTERNAL_CRITIC"
    assert "workspace draft" not in text
    assert "[@Smith2024]" in text
    assert (ws_dir / "qa" / "round-1" / "S1.polished.md").exists()


def test_added_citekey_fails(tmp_path, monkeypatch):
    _workspace(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "autor.write_agent.llm.complete_text",
        lambda *_args, **_kwargs: "Direct evidence tiers show endpoint uncertainty [@Smith2024; @Jones2023].",
    )

    result = run_polish("polish-ws", cfg)

    assert result.status == "REWRITE_REQUIRED_STYLE"
    assert result.cause_class == "citation_drift"
    assert result.details["added_citekeys"] == ["Jones2023"]


def test_removed_citekey_fails(tmp_path, monkeypatch):
    _workspace(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "autor.write_agent.llm.complete_text",
        lambda *_args, **_kwargs: "Direct evidence tiers show endpoint uncertainty and unresolved assay proof.",
    )

    result = run_polish("polish-ws", cfg)

    assert result.status == "REWRITE_REQUIRED_STYLE"
    assert result.cause_class == "citation_drift"
    assert result.details["removed_citekeys"] == ["Smith2024"]


def test_process_trace_removed_or_hard_failed(tmp_path, monkeypatch):
    _workspace(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "autor.write_agent.llm.complete_text",
        lambda *_args, **_kwargs: "Direct evidence tiers show endpoint uncertainty and unresolved assay proof [@Smith2024].",
    )

    result = run_polish("polish-ws", cfg)

    assert result.status == "WRITE_READY_FOR_EXTERNAL_CRITIC"


def test_citation_placeholder_returns_rewrite_required(tmp_path):
    ws_dir = _workspace(tmp_path)
    text = ws_dir / "write.md"
    text.write_text(text.read_text(encoding="utf-8").replace("[@Smith2024]", "[citation needed]"), encoding="utf-8")

    result = run_polish("polish-ws", _cfg(tmp_path))

    assert result.status == "REWRITE_REQUIRED_STYLE"
    assert result.cause_class == "needs_rewrite_not_polish"
