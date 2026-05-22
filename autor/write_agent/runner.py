"""Top-level write-agent runner functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autor.write_agent.config import from_autor_config
from autor.write_agent.draft import generate_section_candidates, load_seed_bank
from autor.write_agent.gates import evaluate_candidate
from autor.write_agent.integrate import create_skeleton, replace_section
from autor.write_agent.kernels import build_kernels
from autor.write_agent.models import SectionKernel, WriteAgentState
from autor.write_agent.patterns import build_pattern_sidecars, evaluate_pattern_contract, load_section_contracts
from autor.write_agent.polish import run_polish
from autor.write_agent.preflight import run_preflight
from autor.write_agent.revise import revise_from_tickets
from autor.write_agent.seeds import build_seed_bank
from autor.write_agent.workspace_io import (
    read_jsonl,
    read_state,
    read_text,
    update_state,
    workspace_dir,
    write_critic_context,
)


def _ensure_cfg(cfg: Any | None) -> Any:
    if cfg is not None:
        return cfg
    from autor.config import load_config

    return load_config()


def _root(cfg: Any) -> Path:
    return getattr(cfg, "_root", Path.cwd())


def preflight(workspace: str, cfg: Any | None = None) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    return run_preflight(_root(cfg), workspace)


def build(workspace: str, cfg: Any | None = None) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    state = preflight(workspace, cfg)
    if state.status != "PREFLIGHT_PASSED":
        return state
    ws_dir = workspace_dir(_root(cfg), workspace)
    wa_cfg = from_autor_config(cfg)
    kernels = build_kernels(ws_dir)
    build_pattern_sidecars(ws_dir, kernels)
    build_seed_bank(ws_dir, kernels, wa_cfg.seed_count)
    if not (ws_dir / "write.md").exists():
        create_skeleton(ws_dir, kernels)
    state = WriteAgentState(
        workspace=workspace,
        status="SEEDS_GENERATED",
        details={"section_count": len(kernels), "seed_count": len(kernels) * wa_cfg.seed_count},
    )
    update_state(ws_dir, **state.to_dict())
    return state


def _load_kernels(ws_dir: Path) -> list[SectionKernel]:
    kernels: list[SectionKernel] = []
    for row in read_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl"):
        kernels.append(SectionKernel(**row))
    return kernels


def run(
    workspace: str,
    cfg: Any | None = None,
    sections: list[str] | None = None,
    round_no: int = 1,
) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    ws_dir = workspace_dir(_root(cfg), workspace)
    if not (ws_dir / "sidecars" / "section-kernels.jsonl").exists():
        built = build(workspace, cfg)
        if built.status not in {"SEEDS_GENERATED", "INTEGRATED_WRITE_UPDATED"}:
            return built
    wa_cfg = from_autor_config(cfg)
    kernels = _load_kernels(ws_dir)
    selected = set(sections or [])
    seeds = load_seed_bank(ws_dir)
    updated: list[str] = []
    for kernel in kernels:
        if selected and kernel.section_id not in selected:
            continue
        try:
            candidate_paths = generate_section_candidates(ws_dir, kernel, wa_cfg, seeds)
        except Exception as e:
            state = WriteAgentState(
                workspace=workspace,
                status="WRITE_AGENT_API_FAILED",
                failed_stage="write",
                cause_class="api_failure",
                next_action="stop",
                details={"error": str(e), "section_id": kernel.section_id},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        contracts = load_section_contracts(ws_dir)
        passing: list[tuple[int, Path]] = []
        pattern_failed = False
        for path in candidate_paths:
            decision = evaluate_candidate(read_text(path), ws_dir, kernel)
            if decision.hard_fail:
                continue
            contract = contracts.get(kernel.section_id)
            if contract:
                pattern_result = evaluate_pattern_contract(read_text(path), contract, wa_cfg)
                if pattern_result.hard_fail:
                    pattern_failed = True
                    continue
                pattern_bonus = sum(pattern_result.scores.values()) - pattern_result.scores.get("anti_ai_penalty", 0)
            else:
                pattern_bonus = 0
            passing.append((decision.score.claim_courage + decision.score.human_move_score + pattern_bonus, path))
        if not passing:
            state = WriteAgentState(
                workspace=workspace,
                status="REWRITE_REQUIRED_STYLE" if pattern_failed else "REWRITE_REQUIRED_COWARDICE",
                failed_stage="write",
                cause_class="pattern_gate_failed" if pattern_failed else "style",
                next_action="rerun_write",
                details={"section_id": kernel.section_id},
            )
            update_state(ws_dir, **state.to_dict())
            return state
        passing.sort(reverse=True, key=lambda item: item[0])
        replace_section(ws_dir, kernel.section_id, kernel.title, read_text(passing[0][1]))
        updated.append(kernel.section_id)
    state = WriteAgentState(
        workspace=workspace,
        status="WRITE_READY_FOR_EXTERNAL_CRITIC",
        details={"updated_sections": updated, "round": round_no},
    )
    update_state(ws_dir, **state.to_dict())
    return state


def write(
    workspace: str,
    cfg: Any | None = None,
    sections: list[str] | None = None,
    round_no: int = 1,
) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    result = build(workspace, cfg)
    if result.status != "SEEDS_GENERATED":
        return result
    result = run(workspace, cfg, sections=sections, round_no=round_no)
    if result.status != "WRITE_READY_FOR_EXTERNAL_CRITIC":
        return result
    ws_dir = workspace_dir(_root(cfg), workspace)
    state = WriteAgentState(
        workspace=workspace,
        status="DRAFT_READY_FOR_POLISH",
        failed_stage="none",
        cause_class="none",
        next_action="run_polish",
        details={"updated_sections": result.details.get("updated_sections", []), "round": round_no},
    )
    update_state(ws_dir, **state.to_dict())
    return state


def polish(
    workspace: str,
    cfg: Any | None = None,
    sections: list[str] | None = None,
    round_no: int = 1,
    in_place: bool = True,
) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    return run_polish(workspace, cfg, sections=sections, round_no=round_no, in_place=in_place)


def revise(workspace: str, cfg: Any | None = None, ticket_paths: list[str] | None = None) -> WriteAgentState:
    cfg = _ensure_cfg(cfg)
    ticket_paths = ticket_paths or []
    ws_dir = workspace_dir(_root(cfg), workspace)
    state = revise_from_tickets(ws_dir, [Path(p) for p in ticket_paths])
    return WriteAgentState(
        workspace=workspace,
        status=state.get("status", "REWRITE_REQUIRED_STYLE"),
        failed_stage=state.get("failed_stage", "revise"),
        cause_class=state.get("cause_class", "none"),
        details=state,
    )


def status(workspace: str, cfg: Any | None = None) -> dict[str, Any]:
    cfg = _ensure_cfg(cfg)
    ws_dir = workspace_dir(_root(cfg), workspace)
    return read_state(ws_dir)


def critic_context(workspace: str, cfg: Any | None = None, round_no: int = 1) -> dict[str, Any]:
    cfg = _ensure_cfg(cfg)
    ws_dir = workspace_dir(_root(cfg), workspace)
    wa_cfg = from_autor_config(cfg)
    path = write_critic_context(
        ws_dir,
        round_no,
        wa_cfg.audit_assumption_label,
        wa_cfg.external_critic_model_label,
    )
    state = update_state(ws_dir, status="WRITE_READY_FOR_EXTERNAL_CRITIC", critic_context=str(path), round=round_no)
    return state
