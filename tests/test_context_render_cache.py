"""
The Advisor's render cache: re-read the graph only when it moved.

`consultant-latency` measured `context_render_s` at 3.21s a turn on the
Consultant over a 5-6 perspective graph, a fifth of that surface's reply path,
for a render that came out byte-identical to the previous turn's on 12 of 16
turns. `Advisor._refresh_context` now gates the render on
`CaseRepository.scope_fingerprint()`, two aggregate queries over the `Node(sid)`
index.

The cache is only as safe as the fingerprint is complete, so most of this file
is about the fingerprint MOVING for every kind of change a render can see:
every addition (nodes and edges) and every mutable field — the ones excluded
from hashes precisely so they can change after commit, which a count and a
timestamp cannot see. `TestTheFingerprintKnowsEveryMutableField` holds the
query's list to the node classes, because the failure mode of a missing field
is a stale prompt on exactly the turns that changed it, and nothing else in the
suite would notice.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.case_repository import \
    CaseRepository
from dialectical_framework.graph.scope_context import scope

# Shared by importing the sibling module directly (`tests/` is on sys.path).
from test_dialectical_context import _create_perspective_with_aspects

SUBSTANTIVE_MESSAGE = (
    "I want to push my team hard toward the deadline, but I worry that the "
    "pressure is burning people out and quality is starting to slip."
)


def _new_case() -> Case:
    case = Case()
    case.commit()
    return case


def _fingerprint() -> tuple:
    fp = CaseRepository().scope_fingerprint()
    assert fp is not None
    return fp


def _annotations(cls: type) -> dict[str, object]:
    """Declared fields across the MRO (GQLAlchemy nodes are not Pydantic v2
    models, so `model_fields` is not there); ClassVar relationship descriptors
    excluded."""
    found: dict[str, object] = {}
    for klass in reversed(cls.__mro__):
        for name, ann in getattr(klass, "__annotations__", {}).items():
            if "ClassVar" in str(ann):
                continue
            found[name] = ann
    return found


class TestTheFingerprintMovesOnEveryKindOfChange:
    """Each test is one way the graph changes without any other changing."""

    def test_no_scope_means_cannot_tell(self):
        assert CaseRepository().scope_fingerprint() is None

    def test_a_pure_read_does_not_move_it(self):
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            before = _fingerprint()
            CaseRepository().find_by_sid()
            assert _fingerprint() == before

    def test_a_committed_node_moves_it(self):
        case = _new_case()
        with scope(case.sid):
            before = _fingerprint()
            Statement(text="Ship weekly", meaning="test").commit()
            assert _fingerprint() != before

    def test_a_discard_moves_it(self):
        """In-place on a committed node: no new node, no new commit. The
        fingerprint folds in the discard reason's length, so it moves."""
        case = _new_case()
        with scope(case.sid):
            stmt = Statement(text="Ship weekly", meaning="test")
            stmt.commit()
            before = _fingerprint()
            stmt.discarded = "not what they meant"
            stmt.save()
            assert _fingerprint() != before

    def test_a_validation_verdict_moves_it(self):
        case = _new_case()
        with scope(case.sid):
            pp = _create_perspective_with_aspects()
            before = _fingerprint()
            pp.validation = "failed: T+ does not balance A"
            pp.save()
            assert _fingerprint() != before

    def test_a_changed_verdict_of_the_same_length_class_moves_it(self):
        """Length, not presence: "passed" -> "failed: ..." is a different
        string, and a count of set fields would not see a re-validation."""
        case = _new_case()
        with scope(case.sid):
            pp = _create_perspective_with_aspects()
            pp.validation = "passed"
            pp.save()
            before = _fingerprint()
            pp.validation = "failed: reasons"
            pp.save()
            assert _fingerprint() != before

    def test_a_digest_moves_it(self):
        case = _new_case()
        with scope(case.sid):
            src = Input(content="A long source about shipping cadence.")
            src.commit()
            before = _fingerprint()
            src.digest = "The source argues for a weekly cadence."
            src.save()
            assert _fingerprint() != before

    def test_a_display_text_override_moves_it(self):
        """Cosmetic, hash-excluded, and rendered in every dump line that names
        the statement (`concerns/display_text_edit.py`)."""
        case = _new_case()
        with scope(case.sid):
            stmt = Statement(text="Ship weekly", meaning="test")
            stmt.commit()
            before = _fingerprint()
            stmt.display_text = "Weekly releases"
            stmt.save()
            assert _fingerprint() != before

    def test_an_edge_on_a_committed_node_moves_it(self):
        """`GROUNDED_IN` and `BELONGS_TO_NEXUS` attach to nodes that are already
        committed, so no node changes at all — only the edge count can see it."""
        case = _new_case()
        with scope(case.sid):
            pp = _create_perspective_with_aspects()
            nexus = Nexus(intent="cache test")
            nexus.save()
            before = _fingerprint()
            pp.nexus.connect(nexus)
            assert _fingerprint() != before

    def test_an_estimation_upsert_moves_it(self):
        """Delete-and-recreate: the count comes back equal, and the new node's
        later commit is what the fingerprint sees."""
        from dialectical_framework.graph.estimation_manager import \
            EstimationManager
        from dialectical_framework.graph.nodes.estimation import ModeEstimation

        case = _new_case()
        with scope(case.sid):
            stmt = Statement(text="Ship weekly", meaning="test")
            stmt.commit()
            EstimationManager().upsert_estimation(stmt, ModeEstimation, 0.4)
            before = _fingerprint()
            EstimationManager().upsert_estimation(stmt, ModeEstimation, 0.7)
            assert _fingerprint() != before


class TestTheFingerprintKnowsEveryMutableField:
    """The query names the mutable fields by hand; this holds the hand to the
    node classes. A mutable field is one a node declares as `Optional[str]`
    metadata that its hash excludes — the framework has no registry of them, so
    the pin is the list itself, checked both ways: every field the query folds
    in exists on some node, and every known mutable field is in the query.
    """

    KNOWN_MUTABLE = {
        "discarded",
        "validation",
        "digest",
        "display_text",
        "instruction",
        "summary",
        "haiku",
    }

    def _query_source(self) -> str:
        import inspect

        return inspect.getsource(CaseRepository.scope_fingerprint)

    def test_every_known_mutable_field_is_in_the_query(self):
        source = self._query_source()
        missing = {f for f in self.KNOWN_MUTABLE if f"n.{f}" not in source}
        assert not missing, (
            f"mutable field(s) {sorted(missing)} are not in scope_fingerprint — "
            "the render cache would serve a stale prompt on the turns that "
            "change them"
        )

    def test_every_field_in_the_query_exists_on_a_node(self):
        from dialectical_framework.graph.nodes.decision import Decision
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.nodes.transition import Transition

        declared: set[str] = set()
        for cls in (Statement, Perspective, Decision, Input, Transition):
            declared |= set(_annotations(cls))
        unknown = self.KNOWN_MUTABLE - declared
        assert not unknown, f"query folds in fields no node declares: {unknown}"

    def test_the_node_classes_declare_no_other_optional_str_metadata(self):
        """The closest thing to a registry: the Optional[str] fields on the
        node classes, minus the ones that participate in hashes, must be exactly
        the known mutable set. A new `Optional[str]` field on a node lands here
        first, and whoever adds it decides whether it is hash-excluded (then it
        goes into the query) or not (then it goes into `HASHED` below)."""
        from dialectical_framework.graph.nodes.decision import Decision
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.nodes.transition import Transition

        # Optional[str] fields that ARE part of a node's identity (in its hash)
        # or of its lifecycle, so they cannot change after commit — or are the
        # lifecycle stamps the fingerprint already reads directly.
        HASHED = {"text", "intent", "meaning", "content", "hash", "sid", "rationale",
                  "stance", "nonce", "saved_at", "committed_at", "resolution",
                  "source", "type", "agent"}

        optional_str: set[str] = set()
        for cls in (Statement, Perspective, Decision, Input, Transition):
            for name, ann in _annotations(cls).items():
                if name.startswith("_"):
                    continue  # private caches (Transition's endpoint hashes), never persisted
                text = str(ann).replace(" ", "")
                if text in {"Optional[str]", "str|None", "None|str", "typing.Optional[str]"}:
                    optional_str.add(name)
        unclassified = optional_str - HASHED - self.KNOWN_MUTABLE
        assert not unclassified, (
            f"Optional[str] field(s) {sorted(unclassified)} are neither known "
            "mutable nor known hashed — classify them (see this test's docstring)"
        )


@pytest.mark.llm
class TestTheAdvisorSkipsTheRenderWhenNothingMoved:
    def _counting_render(self, monkeypatch) -> list[int]:
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        renders: list[int] = []
        real = DialecticalContext.resolve

        async def counting(self):
            renders.append(1)
            return await real(self)

        monkeypatch.setattr(DialecticalContext, "resolve", counting)
        return renders

    async def test_two_quiet_turns_render_once(self, monkeypatch):
        renders = self._counting_render(monkeypatch)
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            advisor = Advisor()
            await advisor._refresh_context()
            await advisor._refresh_context()
        assert renders == [1]

    async def test_a_write_between_turns_renders_again(self, monkeypatch):
        renders = self._counting_render(monkeypatch)
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            advisor = Advisor()
            await advisor._refresh_context()
            Statement(text="Ship monthly", meaning="test").commit()
            await advisor._refresh_context()
        assert renders == [1, 1]

    async def test_a_seeded_context_still_reads_on_turn_one(self, monkeypatch):
        """The seed was rendered by someone else at some earlier moment; the
        cache trusts only a fingerprint this instance took."""
        renders = self._counting_render(monkeypatch)
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            advisor = Advisor(dialectical_context="# a seed from before")
            await advisor._refresh_context()
        assert renders == [1]

    async def test_cannot_tell_falls_through_to_the_render(self, monkeypatch):
        """A failing fingerprint query must cost a render, never a stale prompt."""
        renders = self._counting_render(monkeypatch)

        def broken(self, *args, **kwargs):
            raise RuntimeError("index missing")

        monkeypatch.setattr(CaseRepository, "scope_fingerprint", broken)
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            advisor = Advisor()
            await advisor._refresh_context()
            await advisor._refresh_context()
        assert renders == [1, 1]

    async def test_the_fingerprint_is_taken_before_the_render(self, monkeypatch):
        """A write that lands DURING a render must show up on the next turn.

        Simulated by writing from inside the (patched) render: the fingerprint
        the cache records must predate that write, so the next refresh sees a
        difference and renders again.
        """
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        renders: list[int] = []
        real = DialecticalContext.resolve

        async def render_and_write(self):
            renders.append(1)
            if len(renders) == 1:
                Statement(text="written mid-render", meaning="test").commit()
            return await real(self)

        monkeypatch.setattr(DialecticalContext, "resolve", render_and_write)
        case = _new_case()
        with scope(case.sid):
            Statement(text="Ship weekly", meaning="test").commit()
            advisor = Advisor()
            await advisor._refresh_context()
            await advisor._refresh_context()
        assert renders == [1, 1]
