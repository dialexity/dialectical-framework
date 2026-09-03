"""ExpandPolarity carries the anchor's `context` into the graph as grounding.

`anchor(thesis, antithesis, context=...)` documents `context` as "conversational
context that grounds this tension", and until this wiring existed it did not: the
string reached `IntroducePolarity`, informed classification and headlining, and
was then dropped. Nothing about the person's actual situation survived into the
tetrad, whose poles are capped near seven words and deduped against every other
case in the scope.

These tests pin the write path:
  * one extraction per call, reused across the tetrads it produced (the
    particulars describe the situation, not one reading of it);
  * every new tetrad gets its own edge, reported in `artifacts["grounded"]`;
  * no context → no LLM call and no nodes;
  * extraction failure leaves the tetrads intact — grounding is enrichment,
    never a gate.

Grounding runs BEFORE validation on purpose, and `test_grounding_survives_a_
validation_crash` is why: the tetrad is already committed by then, so a
validation blow-up must not cost the case particulars.

Run: poetry run pytest tests/test_expand_polarities_grounding.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.concerns.tetrad_grounding import (GroundingDto,
                                                             TetradGrounding)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.rendering import grounding_line
from dialectical_framework.graph.scope_context import scope

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"
_ASPECT_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence"

CONTEXT = (
    "I hold 55% and he holds 45%. He closed both of our major customers and "
    "he's on every call with them — I've been in three as a plus-one. I raised "
    "it in March, he agreed, nothing changed."
)

PARTICULARS = (
    "Equity 55/45. Cofounder closed both major customers, on every call; "
    "founder attended three as plus-one. Raised in March, agreed, no change."
)


def _make_polarity(sid: str) -> Polarity:
    with scope(sid):
        t = Statement(text="Buy him out", meaning=_T_MEANING)
        t.commit()
        a = Statement(text="Keep the partnership", meaning=_A_MEANING)
        a.commit()

        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        return polarity


def _distinct_aspect_stub(sid: str):
    """Emit distinct aspects per call so `count>1` does not collapse via dedup.

    The mock brain returns identical DTOs every call (CLAUDE.md), which the
    duplicate-discard guard would fold into one perspective.
    """
    call_index = {"n": 0}

    async def _resolve(self, perspective, positions=None, text="", not_like_these=None):
        i = call_index["n"]
        call_index["n"] += 1
        with scope(sid):
            results: list[AspectResult] = []
            for pos, label in (
                (POSITION_T_PLUS, "Decisive ownership"),
                (POSITION_T_MINUS, "Isolated overreach"),
                (POSITION_A_PLUS, "Shared accountability"),
                (POSITION_A_MINUS, "Deadlocked deference"),
            ):
                comp = Statement(text=f"{label} v{i}", meaning=_ASPECT_MEANING)
                comp.commit()
                results.append(
                    AspectResult(
                        component=comp,
                        position=pos,
                        apex_concept="apex",
                        heuristic_similarity=0.8,
                        complementarity_t=0.7,
                        complementarity_a=0.7,
                    )
                )
        return results

    return _resolve, call_index


def _fixed_extraction(monkeypatch, text: str = PARTICULARS) -> dict:
    """Stub the grounding LLM call, counting invocations."""
    calls = {"n": 0, "material": []}

    async def _extract(self, material: str) -> str:
        calls["n"] += 1
        calls["material"].append(material)
        return text

    monkeypatch.setattr(TetradGrounding, "_extract", _extract)
    return calls


@pytest.mark.llm
class TestExpandPolarityGrounding:
    @pytest.mark.asyncio
    async def test_context_is_attached_to_the_new_tetrad(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 1
            assert calls["n"] == 1
            assert CONTEXT in calls["material"][0]

            line = grounding_line(pps[0])
            assert line is not None
            assert "55/45" in line
            assert concern.report.artifacts["grounded"] == [pps[0].short_hash]

    @pytest.mark.asyncio
    async def test_one_extraction_is_reused_across_all_tetrads(self, monkeypatch):
        """N tetrads from one context cost ONE LLM call, not N.

        The particulars describe the situation; each tetrad is a different
        reading OF it. Re-extracting per perspective would spend N calls
        producing the same text from the same material.
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, count=3, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 3
            assert calls["n"] == 1, "grounding re-extracted per perspective"

            for pp in pps:
                line = grounding_line(pp)
                assert line is not None, f"{pp.short_hash} was left ungrounded"
                assert "55/45" in line

            assert set(concern.report.artifacts["grounded"]) == {
                pp.short_hash for pp in pps
            }

    @pytest.mark.asyncio
    async def test_no_context_means_no_call_and_no_grounding(self, monkeypatch):
        """The Analyst path passes no context; it must stay exactly as it was."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert calls["n"] == 0
            assert grounding_line(pps[0]) is None
            assert "grounded" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_blank_context_is_treated_as_absent(self, monkeypatch):
        """`anchor`'s `context` defaults to "" — whitespace must not trigger a call."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context="   \n  "
            )
            pps = await concern.resolve()

            assert calls["n"] == 0
            assert grounding_line(pps[0]) is None

    @pytest.mark.asyncio
    async def test_empty_extraction_grounds_nothing(self, monkeypatch):
        """Material with no particulars must not create an empty Rationale."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            _fixed_extraction(monkeypatch, text="")

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert pps
            assert grounding_line(pps[0]) is None
            assert "grounded" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_extraction_failure_leaves_the_tetrad_intact(self, monkeypatch):
        """Grounding is enrichment: its failure must not fail the expansion."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            async def _boom(self, material: str) -> str:
                raise RuntimeError("provider exploded")

            monkeypatch.setattr(TetradGrounding, "_extract", _boom)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 1
            assert pps[0].is_complete() and pps[0].is_committed
            assert concern.report.ok is True
            assert grounding_line(pps[0]) is None

    @pytest.mark.asyncio
    async def test_grounding_survives_a_validation_crash(self, monkeypatch):
        """Order matters: grounding lands before the validation pass runs.

        Validation is already fail-soft, but it is also the later and more
        elaborate step. Attaching first means a bug there cannot cost the case
        particulars of an already-committed tetrad.
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            _fixed_extraction(monkeypatch)

            async def _boom(self, perspectives, input_text):
                raise RuntimeError("validation exploded")

            monkeypatch.setattr(ExpandPolarity, "_validate_and_flag", _boom)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            with pytest.raises(RuntimeError):
                await concern.resolve()

            # The tetrad committed and was grounded before validation ran.
            pps = polarity.perspectives.all()
            assert pps
            grounded = [
                grounding_line(pp) for pp, _ in pps if grounding_line(pp) is not None
            ]
            assert grounded and "55/45" in grounded[0]


def _identical_aspect_stub(sid: str):
    """Emit the SAME aspects every call, so the second expansion dedups.

    The opposite of `_distinct_aspect_stub`: this reproduces the ordinary live
    case where the model re-anchors a tension already in the graph.
    """

    async def _resolve(self, perspective, positions=None, text="", not_like_these=None):
        with scope(sid):
            results: list[AspectResult] = []
            for pos, label in (
                (POSITION_T_PLUS, "Decisive ownership"),
                (POSITION_T_MINUS, "Isolated overreach"),
                (POSITION_A_PLUS, "Shared accountability"),
                (POSITION_A_MINUS, "Deadlocked deference"),
            ):
                comp = Statement(text=label, meaning=_ASPECT_MEANING)
                comp.commit()
                results.append(
                    AspectResult(
                        component=comp,
                        position=pos,
                        apex_concept="apex",
                        heuristic_similarity=0.8,
                        complementarity_t=0.7,
                        complementarity_a=0.7,
                    )
                )
        return results

    return _resolve


@pytest.mark.llm
class TestGroundingAccretesOnDedup:
    """A duplicate TETRAD does not make the context a duplicate.

    Re-anchoring a tension already in the graph is the ordinary live case: the
    person reveals more, so the model anchors the same opposition again with
    richer material. The generated tetrad collapses onto the existing node — and
    the new particulars used to be discarded with it, silently and with no
    report artifact, because grounding ran over `completed_pps` only.

    Measured in `r13-grounding-attrib`: both `anchor` calls carried `context`
    (195c, then 422c), and the returning session's `# The Person's Case` held
    five near-identical restatements of turn 1 and NOTHING from turn 2 — not the
    60% revenue concentration, not the two anchor CEOs, the facts the whole
    wobble turned on. Accretion is this lane's stated contract
    (`tetrad_grounding.py`: "a person reveals more three turns later"), and
    dedup was where it was skipped.
    """

    @pytest.mark.asyncio
    async def test_a_later_call_grounds_the_tetrad_it_deduped_onto(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            monkeypatch.setattr(
                AspectGeneration, "resolve", _identical_aspect_stub(case_node.sid)
            )

            materials: list[str] = []

            async def _extract(self, material: str) -> str:
                materials.append(material)
                return f"PARTICULARS[{len(materials)}]"

            monkeypatch.setattr(TetradGrounding, "_extract", _extract)

            first = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context="He holds 45%."
            )
            await first.resolve()

            second = ExpandPolarity(
                polarity_hash=polarity.hash,
                grounding_context="60% of revenue sits on two anchor CEOs.",
            )
            pps = await second.resolve()

            # The tetrad was deduped away, so nothing NEW was committed...
            assert second.report.artifacts["duplicates_discarded"]
            # ...yet the surviving node was grounded in the new material.
            assert len(materials) == 2, "the second call's context was never extracted"
            assert "two anchor CEOs" in materials[1]
            assert second.report.artifacts["grounded"]

            line = grounding_line(pps[0])
            assert line is not None
            # BOTH turns are present: accretion, not replacement. A chronology
            # of what was revealed when is the point of appending Rationales.
            assert "PARTICULARS[1]" in line
            assert "PARTICULARS[2]" in line

    @pytest.mark.asyncio
    async def test_no_context_still_means_no_call_on_the_dedup_path(self, monkeypatch):
        """The Analyst path passes no context and must not gain an LLM call
        merely because a tetrad deduped."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            monkeypatch.setattr(
                AspectGeneration, "resolve", _identical_aspect_stub(case_node.sid)
            )
            calls = _fixed_extraction(monkeypatch)

            await ExpandPolarity(polarity_hash=polarity.hash).resolve()
            second = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await second.resolve()

            assert calls["n"] == 0
            assert grounding_line(pps[0]) is None


@pytest.mark.llm
class TestAnchorBranchesGroundAlike:
    """Both `anchor` branches must ground, or the tool has two memories.

    The tests above drive `ExpandPolarity` directly, which is exactly why they
    missed this: `anchor`'s thesis-only branch composes `AnalysisPipeline`
    instead, and that path forwarded nothing. Worse, `context` went in as
    `intent`, which `AnalysisPipeline` reads ONLY on the surface-theses step —
    with `thesis_hashes` supplied it is never read at all, so the person's
    particulars were dropped outright.

    The user-visible symptom was a tool that remembered the case when the model
    happened to name the opposition and forgot it when the model asked the
    framework to find one. Nothing in the report distinguished the two.

    These assert at the seam (which kwargs the callers pass) rather than
    end-to-end: the wiring is what broke, and a full pipeline run here would
    need the whole find-polarities stack stubbed to prove one argument.
    """

    @pytest.mark.asyncio
    async def test_pipeline_forwards_grounding_to_every_expansion(self, monkeypatch):
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        seen: list[str | None] = []

        class _Recorder:
            def __init__(self, polarity_hash: str, **kwargs) -> None:
                seen.append(kwargs.get("grounding_context"))
                self.report = type("R", (), {"ok": True, "summary": ""})()

            async def resolve(self):
                return []

        monkeypatch.setattr(
            "dialectical_framework.agents.analyst.skills.expand_polarities.ExpandPolarity",
            _Recorder,
        )

        pipeline = AnalysisPipeline(thesis_hashes=["h1"], grounding_context=CONTEXT)
        await pipeline._expand_one("polarity-hash")

        assert seen == [CONTEXT]

    def test_pipeline_defaults_to_no_grounding(self):
        """`ingest` must NOT ground: one document holds several tensions, and a
        single extraction stamped onto all of them would cross-contaminate."""
        from dialectical_framework.agents.analyst.analyst import AnalysisPipeline

        assert AnalysisPipeline(text="whatever").grounding_context is None
        assert AnalysisPipeline(thesis_hashes=["h1"]).grounding_context is None
        # Whitespace-only is nothing to ground, not a one-space note.
        assert AnalysisPipeline(thesis_hashes=["h1"], grounding_context="  ").grounding_context is None

    @pytest.mark.asyncio
    async def test_both_poles_anchor_passes_context_as_grounding(self, monkeypatch):
        """The mirror of `test_thesis_only_anchor_passes_context_as_grounding`,
        for the branch nothing covered.

        This class claims to cover "both `anchor` branches" and did not: every
        anchor test in the tree passes `antithesis=None`, so no test had ever
        called `anchor.fn` with both poles. `anchor.py`'s `grounding_context=`
        on that branch could be deleted and the whole suite would stay green —
        the exact regression the comment there records having already shipped
        twice on the other branch.

        Two files DO call it with both poles and neither guards anything:
        `tests/probe_anchor_report.py` contains no `assert` at all, and
        `tests/e2e/probe_anchor_retry_cost.py` asserts only its own timing
        arithmetic. Both are `probe_*`, which pytest does not collect.
        """
        from dialectical_framework.agents.advisor.tools import anchor as anchor_mod

        captured: dict = {}

        class _Report:
            ok = True
            summary = ""

            def __init__(self) -> None:
                self.artifacts: dict = {}

            def merge(self, other):
                return self

        class _FakeIntroduce:
            def __init__(self, **kwargs) -> None:
                self.report = _Report()

            async def resolve(self):
                return type("Res", (), {"primary_polarity_hash": "pol-1"})()

        class _FakeExpand:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)
                self.report = _Report()

            async def resolve(self):
                return []

        monkeypatch.setattr(
            "dialectical_framework.agents.analyst.skills.introduce_polarity.IntroducePolarity",
            _FakeIntroduce,
        )
        monkeypatch.setattr(
            "dialectical_framework.agents.analyst.skills.expand_polarities.ExpandPolarity",
            _FakeExpand,
        )

        await anchor_mod.anchor.fn(
            thesis="Buy out the cofounder now",
            antithesis="Keep the partnership intact",
            context=CONTEXT,
        )

        assert captured.get("grounding_context") == CONTEXT
        # The polarity the tetrad expands must be the one just introduced, not a
        # re-lookup: a stubbed hash proves the value is threaded, so a future
        # refactor cannot satisfy the assertion above while grounding some other
        # polarity's tetrad.
        assert captured.get("polarity_hash") == "pol-1"

    @pytest.mark.asyncio
    async def test_thesis_only_anchor_passes_context_as_grounding(self, monkeypatch):
        """The regression itself: `intent` alone is not grounding."""
        from dialectical_framework.agents.advisor.tools import anchor as anchor_mod

        captured: dict = {}

        class _FakePipeline:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)
                self.report = type("R", (), {"ok": True, "summary": ""})()

            async def resolve(self):
                return type("Res", (), {"perspective_hashes": []})()

        class _FakeAnchorTheses:
            def __init__(self, statements) -> None:
                self.report = type(
                    "R",
                    (),
                    {
                        "ok": True,
                        "summary": "",
                        "artifacts": {"thesis_hashes": ["t1"]},
                        "merge": lambda self, other: self,
                    },
                )()

            async def resolve(self):
                return None

        monkeypatch.setattr(
            "dialectical_framework.agents.analyst.analyst.AnalysisPipeline",
            _FakePipeline,
        )
        monkeypatch.setattr(
            "dialectical_framework.agents.analyst.skills.anchor_theses.AnchorTheses",
            _FakeAnchorTheses,
        )

        # `.fn` is the undecorated coroutine; `execute` wants a tool-call payload.
        await anchor_mod.anchor.fn(thesis="Keep him as cofounder", context=CONTEXT)

        assert captured.get("grounding_context") == CONTEXT


@pytest.mark.llm
class TestGroundingDtoShape:
    def test_particulars_is_the_only_field(self):
        """Flat single-field DTO — the real LLM drops branches the mock fills in."""
        assert list(GroundingDto.model_fields) == ["particulars"]


class TestIntroducePolarityContextOrder:
    """The same particulars must also survive the CLASSIFICATION prompts.

    `IntroducePolarity` hands one string to three consumers, two of which cut it
    from the front: `StatementHeadline` at 1500 chars and both
    `StatementClassification` prompts at 2000 (bare literals in those files, so
    the numbers below are duplicated on purpose — they are what the caps are,
    not a contract this test owns). The other half of the string is case-wide
    `input_context`, which is unbounded: it falls back to full content for any
    Input whose digest is not written yet. Document-first meant one pasted file
    silently deleted the person's particulars from both prompts.
    """

    PARTICULARS = "He wants out by March and the runway is eight months."

    def test_particulars_come_first(self):
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        composed = IntroducePolarity._compose_context(
            self.PARTICULARS, '<Input id="abc">a document</Input>'
        )

        assert composed.startswith(self.PARTICULARS)
        assert "a document" in composed

    def test_particulars_survive_a_document_longer_than_both_caps(self):
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        huge = '<Input id="abc">\n' + ("x" * 50_000) + "\n</Input>"
        composed = IntroducePolarity._compose_context(self.PARTICULARS, huge)

        assert self.PARTICULARS in composed[:1500], "cut by StatementHeadline"
        assert self.PARTICULARS in composed[:2000], "cut by StatementClassification"

    def test_no_particulars_is_just_the_input(self):
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        assert IntroducePolarity._compose_context("", "material") == "material"
        assert IntroducePolarity._compose_context("   ", "material") == "material"

    def test_no_input_is_just_the_particulars(self):
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        assert (
            IntroducePolarity._compose_context(self.PARTICULARS, "")
            == self.PARTICULARS
        )

    def test_neither_is_empty_string(self):
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        assert IntroducePolarity._compose_context("", "") == ""
