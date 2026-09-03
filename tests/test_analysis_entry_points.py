"""
How `AnalysisPipeline` decides there is something to analyze.

Both entry tools document processing material already in scope — `ingest`'s
"omit to process pre-loaded inputs", `analyze`'s "If None, processes all inputs
in scope" — but the pipeline required `text` or `intent` before it would look,
so the documented calls were refused with "No text or thesis_hashes provided",
a message that never mentions inputs. Whether there is material to read is
`SurfaceTheses`' question; these tests pin that it gets asked, and that its
three different answers stay three different answers.

Also pins the idempotence that lets `ingest` and `AnalysisPipeline` BOTH call
`AddInput` on the same text: `ingest` needs the hash (for `SourceDigest` and
`input_hashes`), the pipeline needs the capture to happen for callers that
hand it raw text and nothing else. Neither can drop its call, so the second
one must be a no-op.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.concerns.add_input import AddInput
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.scope_context import scope


def _new_case() -> Case:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case


class TestNothingToAnalyze:
    """No LLM involved: `SurfaceTheses` answers before it opens a conversation."""

    @pytest.mark.asyncio
    async def test_bare_call_on_empty_scope_says_the_scope_is_empty(self):
        """Not "no tensions in this material" — there was no material."""
        case = _new_case()
        with scope(case.sid):
            pipeline = AnalysisPipeline()
            await pipeline.resolve()

        assert pipeline.report.ok is True
        assert "No input material in scope" in pipeline.report.summary
        # The old guard's wording, which named neither inputs nor scope.
        assert "No text or thesis_hashes provided" not in pipeline.report.summary

    @pytest.mark.asyncio
    async def test_unresolvable_hashes_without_text_still_fail_loudly(self):
        """The guard used to swallow this into its own generic refusal."""
        case = _new_case()
        with scope(case.sid):
            pipeline = AnalysisPipeline(input_hashes=["ffffffffffffffff"])
            await pipeline.resolve()

        assert pipeline.report.ok is False
        assert "resolved to an input in scope" in pipeline.report.summary
        assert "ffffffffffffffff" in pipeline.report.summary


class TestSurfaceThesesInputsRead:
    """`inputs_read` is what separates "nothing there" from "nothing found"."""

    @pytest.mark.asyncio
    async def test_counts_inputs_in_scope(self):
        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses

        case = _new_case()
        with scope(case.sid):
            for text in ("First source.", "Second source."):
                node = Input(content=text)
                node.commit()
                case.inputs.connect(node)

            surface = SurfaceTheses(intent="extract")
            assert len(surface._get_inputs()) == 2
            assert surface.report.artifacts["inputs_read"] == 2

    @pytest.mark.asyncio
    async def test_counts_zero_on_empty_scope(self):
        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses

        case = _new_case()
        with scope(case.sid):
            surface = SurfaceTheses(intent="extract")
            await surface.resolve()

        assert surface.report.ok is True
        assert surface.report.artifacts["inputs_read"] == 0


class TestAddInputIsIdempotent:
    """Two captures of the same text are one Input and one HAS_INPUT edge."""

    @pytest.mark.asyncio
    async def test_second_capture_reuses_the_node(self):
        case = _new_case()
        text = "The cofounder wants out and the runway is eight months."
        with scope(case.sid):
            first = await AddInput().resolve(content=text)

            second_concern = AddInput()
            second = await second_concern.resolve(content=text)

            assert second.hash == first.hash
            assert "already exists" in second_concern.report.summary
            assert [i.hash for i in InputRepository().get_all()] == [first.hash]

            edges = [n for n, _ in case.inputs.all() if n.hash == first.hash]
            assert len(edges) == 1, "the second capture duplicated the HAS_INPUT edge"

    @pytest.mark.asyncio
    async def test_creation_reports_the_full_hash(self):
        """`ingest` passes this straight into `input_hashes`."""
        case = _new_case()
        with scope(case.sid):
            concern = AddInput()
            node = await concern.resolve(content="Fresh material.")

            assert concern.report.artifacts["input_hash"] == node.hash
            assert len(node.hash) == 64
