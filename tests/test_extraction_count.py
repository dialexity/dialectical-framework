"""How many theses an extraction places is a PARAMETER, and placement covers the
whole source (2026-10-04).

Before: the number was read out of the free-text `intent` by an LLM call
(`_parse_intent`) — a tool argument that was both a literal and an instruction —
defaulting to 3; the pipeline substituted "extract key theses from the input" so
that call fired on every ingest with nothing to parse; and on a source too long
for one prompt the sweep read every window, merged candidates in document order
and placed `candidates[:count]` — page one's first three, nothing from the rest.

Run: poetry run pytest tests/test_extraction_count.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.skills import surface_theses as st
from dialectical_framework.agents.analyst.skills.surface_theses import (
    DEFAULT_THESIS_COUNT, MAX_THESIS_COUNT, CandidateSelectionDto,
    ParsedIntentDto, SurfaceTheses, clamp_thesis_count)


class TestTheCountIsAParameter:
    def test_default_and_clamp(self):
        assert DEFAULT_THESIS_COUNT == 3
        assert clamp_thesis_count(None) == 3
        assert clamp_thesis_count(0) == 1
        assert clamp_thesis_count(99) == MAX_THESIS_COUNT
        assert SurfaceTheses().count == 3
        assert SurfaceTheses(count=7).count == 7

    def test_the_intent_parser_no_longer_carries_a_number(self):
        assert "count" not in ParsedIntentDto.model_fields
        prompt = SurfaceTheses(intent="themes about trust")._parse_intent_prompt("preview")
        assert "count" not in prompt.lower().replace("not yours to decide", "")  # the one mention says it is not parsed
        assert "default to 3" not in prompt

    def test_the_tools_expose_count(self):
        import inspect

        from dialectical_framework.agents.advisor.tools.ingest import ingest
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline, analyze

        assert "count" in inspect.signature(st.surface_theses.fn).parameters
        assert "count" in inspect.signature(ingest.fn).parameters
        assert "count" in inspect.signature(analyze.fn).parameters
        assert AnalysisPipeline(text="x", count=5).count == 5

    def test_prompts_say_it_is_incremental(self):
        from dialectical_framework.agents.advisor.system_prompts import SYSTEM_PROMPT
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT as ANALYST

        idx = SYSTEM_PROMPT.find("- `ingest`")
        assert "INCREMENTAL" in SYSTEM_PROMPT[idx: idx + 900]
        assert "`count`" in ANALYST


@pytest.mark.llm
class TestNoIntentMeansNoParseCall:
    @pytest.mark.asyncio
    async def test_resolve_skips_the_parser_without_an_intent(self, monkeypatch):
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.scope_context import scope

        calls = {"parse": 0}
        original = SurfaceTheses._parse_intent

        async def counting(self):
            calls["parse"] += 1
            return await original(self)

        monkeypatch.setattr(SurfaceTheses, "_parse_intent", counting)
        case = Case()
        case.commit()
        with scope(case.sid):
            Input(content="Remote work is killing our culture, and the office is where it was built.").commit()
            await SurfaceTheses().resolve()
            assert calls["parse"] == 0, "nothing to parse, no call"
            await SurfaceTheses(intent="themes about culture").resolve()
            assert calls["parse"] == 1

    @pytest.mark.asyncio
    async def test_the_pipeline_passes_intent_through_as_none(self, monkeypatch):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.scope_context import scope

        seen: dict = {}

        class _Fake:
            def __init__(self, **kwargs) -> None:
                seen.update(kwargs)
                self.report = type("R", (), {"ok": True, "summary": "", "artifacts": {"thesis_hashes": []}})()

            async def resolve(self):
                return None

        monkeypatch.setattr("dialectical_framework.agents.analyst.skills.surface_theses.SurfaceTheses", _Fake)
        case = Case()
        case.commit()
        with scope(case.sid):
            await AnalysisPipeline(text="some material", count=4).resolve()
        assert seen["intent"] is None, "no substituted 'extract key theses' string"
        assert seen["count"] == 4


@pytest.mark.llm
class TestSelectionCoversTheWholeSource:
    """The sweep's positional cut is gone: the top of a ranking across windows is
    placed, and the rest is reported as seen."""

    @pytest.mark.asyncio
    async def test_ranked_selection_reaches_past_the_first_window(self, monkeypatch):
        skill = SurfaceTheses(count=2)
        skill._conversation = st.ConversationFacilitator()
        candidates = [(f"claim {i}", f"window {i // 2}") for i in range(6)]  # 3 windows x 2
        pool_numbering: dict = {}

        class _Iso:
            async def submit(self, response_model, user_content):
                # the prompt numbers a SHUFFLED order; pick the two candidates
                # from the LAST window by their text, whatever their numbers
                lines = [l for l in user_content.splitlines() if l[:1].isdigit()]
                by_text = {l.split(". ", 1)[1]: int(l.split(".")[0]) for l in lines}
                pool_numbering.update(by_text)
                return CandidateSelectionDto(ranking=[by_text["claim 5"], by_text["claim 4"]] + [n for t, n in by_text.items() if t not in ("claim 5", "claim 4")])

        monkeypatch.setattr(skill._conversation, "isolate", lambda: _Iso())
        selected = await skill._select_candidates(candidates, 2, ParsedIntentDto())
        assert [c[0] for c in selected] == ["claim 5", "claim 4"]
        assert skill._report.artifacts["candidate_selection"] == "ranked"
        assert len(pool_numbering) == 6, "every candidate was offered"

    @pytest.mark.asyncio
    async def test_a_failed_ranking_degrades_to_the_positional_cut(self, monkeypatch):
        skill = SurfaceTheses(count=2)
        skill._conversation = st.ConversationFacilitator()

        class _Boom:
            async def submit(self, response_model, user_content):
                raise RuntimeError("provider down")

        monkeypatch.setattr(skill._conversation, "isolate", lambda: _Boom())
        candidates = [(f"claim {i}", "w") for i in range(5)]
        selected = await skill._select_candidates(candidates, 2, ParsedIntentDto())
        assert [c[0] for c in selected] == ["claim 0", "claim 1"]
        assert skill._report.artifacts["candidate_selection"] == "positional"

    @pytest.mark.asyncio
    async def test_a_pool_no_larger_than_the_count_costs_no_call(self, monkeypatch):
        skill = SurfaceTheses(count=3)
        skill._conversation = st.ConversationFacilitator()
        monkeypatch.setattr(skill._conversation, "isolate", lambda: (_ for _ in ()).throw(AssertionError("no call")))
        candidates = [("a", "w"), ("b", "w")]
        assert await skill._select_candidates(candidates, 3, ParsedIntentDto()) == candidates

    @pytest.mark.asyncio
    async def test_unplaced_candidates_are_reported(self, monkeypatch):
        """The model learns incrementality from the artifact: the summary says
        how many more were seen, the same shape as the pipeline's deferral line."""
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.scope_context import scope

        async def fake_input_text(self):
            return "x" * 90_000  # three windows

        async def fake_sweep(self, windows, focus, target_count, not_like_these, reports, broader=False):
            return [(f"claim {i}", windows[0]) for i in range(7)]

        async def fake_select(self, candidates, target_count, parsed):
            return candidates[:target_count]

        async def fake_classify(self, pairs, domain_hint=""):
            out = []
            for text, _w in pairs:
                s = Statement(text=text, meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion")
                s.commit()
                out.append(s)
            return out

        monkeypatch.setattr(SurfaceTheses, "_get_input_text", fake_input_text)
        monkeypatch.setattr(SurfaceTheses, "_sweep_windows", fake_sweep)
        monkeypatch.setattr(SurfaceTheses, "_select_candidates", fake_select)
        monkeypatch.setattr(st.ThesisExtraction, "classify_candidates", fake_classify)
        case = Case()
        case.commit()
        with scope(case.sid):
            skill = SurfaceTheses(count=3)
            await skill.resolve()
        assert skill.report.artifacts["unplaced_candidates"] == 4
        assert "4 more candidate tension(s) seen" in skill.report.summary
        assert "call again" in skill.report.summary
