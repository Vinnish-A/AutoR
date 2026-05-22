from __future__ import annotations

from autor.write_agent.integrate import create_skeleton, replace_section
from autor.write_agent.models import SectionKernel
from autor.write_agent.revise import revise_from_tickets
from autor.write_agent.workspace_io import write_critic_context, write_jsonl


class TestWriteAgentWorkspaceIO:
    def test_anchor_replacement_updates_only_target_section(self, tmp_path):
        ws_dir = tmp_path / "workspace" / "anchor-ws"
        kernels = [
            SectionKernel("S1", "First", "First claim."),
            SectionKernel("S2", "Second", "Second claim."),
        ]
        create_skeleton(ws_dir, kernels)

        replace_section(ws_dir, "S2", "Second", "Jones shows the replacement [@Jones2023].")
        text = (ws_dir / "write.md").read_text(encoding="utf-8")

        assert "## First\n\n_Draft pending._" in text
        assert "Jones shows the replacement" in text

    def test_critic_ticket_revises_affected_section_only(self, tmp_path):
        ws_dir = tmp_path / "workspace" / "revise-ws"
        kernels = [
            SectionKernel("S1", "First", "First claim."),
            SectionKernel("S2", "Second", "Second claim."),
        ]
        create_skeleton(ws_dir, kernels)
        replace_section(ws_dir, "S1", "First", "Smith shows first [@Smith2024].")
        replace_section(ws_dir, "S2", "Second", "Jones shows old second [@Jones2023].")
        write_jsonl(ws_dir / "sidecars" / "section-kernels.jsonl", kernels)
        ticket = ws_dir / "qa" / "round-1" / "critic-ticket.md"
        ticket.parent.mkdir(parents=True)
        ticket.write_text(
            "<!-- AUTOR:REPLACEMENT S2 START -->\nJones shows revised second [@Jones2023].\n<!-- AUTOR:REPLACEMENT S2 END -->\n",
            encoding="utf-8",
        )

        state = revise_from_tickets(ws_dir, [ticket])
        text = (ws_dir / "write.md").read_text(encoding="utf-8")

        assert state["status"] == "WRITE_READY_FOR_EXTERNAL_CRITIC"
        assert "Smith shows first" in text
        assert "Jones shows revised second" in text
        assert "Jones shows old second" not in text

    def test_critic_context_is_written(self, tmp_path):
        ws_dir = tmp_path / "workspace" / "ctx-ws"
        path = write_critic_context(ws_dir, 2, "Claude-family LLM-written manuscript", "GPT-5.5 thinking high")

        text = path.read_text(encoding="utf-8")
        assert "workspace/ctx-ws/write.md" in text
        assert "round-2/critic-ticket.md" in text
