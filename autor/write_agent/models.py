"""Lightweight data models for the write-agent package."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WriteAgentConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    fast_model: str = "deepseek-v4-flash"
    api_key_env: str = "DEEPSEEK_API_KEY"
    api_key: str = ""
    seed_count: int = 9
    max_rounds: int = 2
    audit_assumption_label: str = "Claude-family LLM-written manuscript"
    external_critic_model_label: str = "GPT-5.5 thinking high"
    enabled: bool = True
    thinking: bool = True
    reasoning_effort: str = "high"
    writer_backend_label: str = "DeepSeek write-agent"
    external_critic_required: bool = True
    timeout: int = 120


@dataclass
class SectionKernel:
    section_id: str
    title: str
    controlling_claim: str
    evidence_keys: list[str] = field(default_factory=list)
    contrast: str = ""
    forbidden_overclaim: str = ""
    required_tables: list[str] = field(default_factory=list)
    direct_evidence_keys: list[str] = field(default_factory=list)
    adjacent_evidence_keys: list[str] = field(default_factory=list)
    background_only_keys: list[str] = field(default_factory=list)
    required_figures: list[str] = field(default_factory=list)
    failure_test: str = ""


@dataclass
class SectionWritingContract:
    section_id: str
    target_words: int
    min_words: int
    max_words: int
    required_citekeys: list[str] = field(default_factory=list)
    optional_citekeys: list[str] = field(default_factory=list)
    prohibited_citekeys: list[str] = field(default_factory=list)
    preferred_seed_types: list[str] = field(default_factory=list)
    required_moves: list[str] = field(default_factory=list)
    table_ids: list[str] = field(default_factory=list)
    figure_ids: list[str] = field(default_factory=list)
    prose_allowed_citekeys: list[str] = field(default_factory=list)
    table_only_citekeys: list[str] = field(default_factory=list)
    figure_only_citekeys: list[str] = field(default_factory=list)
    currentness_only_records: list[str] = field(default_factory=list)
    forbidden_claim_patterns: list[str] = field(default_factory=list)
    expansion_objectives: list[str] = field(default_factory=list)
    claim_license_decisions: list[str] = field(default_factory=list)
    evidence_maturity_order: list[str] = field(default_factory=list)
    table_contract: dict[str, Any] = field(default_factory=dict)
    selected_seed_id: str | None = None
    selected_candidate: str | None = None
    selected_score: int | None = None


@dataclass
class CandidateScore:
    evidence_fidelity: int = 0
    section_specificity: int = 0
    claim_courage: int = 0
    boundary_precision: int = 0
    anti_ai_penalty: int = 0
    human_move_score: int = 0
    hard_fail: bool = False
    failure_class: list[str] = field(default_factory=list)


@dataclass
class WriteAgentState:
    workspace: str
    status: str
    failed_stage: str = "none"
    cause_class: str = "none"
    next_action: str = "continue"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(self.details)
        return data
