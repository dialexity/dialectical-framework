"""A source too long for one prompt is SWEPT window by window.

The third and worst of the three unbounded raw-content paths. `_extraction_loop`
hands the whole concatenated source to `ThesisExtraction` up to four times, and
each of those is itself ~7 full-source sends because `_step2_identify_candidates`
fans out through `isolate()`, which copies the history holding step 1's prompt.
~29 sends of a 1.2 MB document is millions of tokens, or a context-limit failure
before any of them.

What these tests pin is the guarantee, not the mechanism: every window is looked
at (extraction has no query to retrieve against — the theses ARE what is being
looked for), the whole document never goes out in one prompt, candidates merge in
document order, each survivor is classified against the window it came from, and
the fan-out's width — which comes from the size of a file somebody pasted rather
than from graph structure — is capped.
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.analyst.skills import \
    surface_theses as surface_theses_module
from dialectical_framework.agents.analyst.skills.surface_theses import (
    MAX_CONCURRENT_WINDOW_SWEEPS, ParsedIntentDto, SurfaceTheses)
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.utils.chunking import CHUNK_SIZE, chunk_text


@pytest.fixture
def cleanup_graph_db():
    """DB-free: nothing here reaches the graph."""
    yield


@pytest.fixture
def cleanup_test_graph_data():
    yield


# --- Fakes -------------------------------------------------------------------


class _FakeExtraction:
    """Stands in for `ThesisExtraction`, recording what each half was asked."""

    #: Every instance ever built, in construction order.
    instances: list[_FakeExtraction] = []
    #: `(kind, payload)` per call, across all instances.
    calls: list[tuple[str, object]] = []
    #: Candidates to return per window text; missing window → one derived name.
    candidates: dict[str, list[str]] = {}
    #: Windows whose extraction returns nothing at all.
    barren: set[str] = set()
    #: Live `extract_candidates` bodies, and the high-water mark.
    live = 0
    peak = 0
    #: How long every sweep dawdles, so overlap is observable.
    dwell = 0.0
    #: Per-window dwell, so completion order can be made to differ from
    #: document order.
    delays: dict[str, float] = {}

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.calls = []
        cls.candidates = {}
        cls.barren = set()
        cls.live = 0
        cls.peak = 0
        cls.dwell = 0.0
        cls.delays = {}

    def __init__(self) -> None:
        _FakeExtraction.instances.append(self)
        self.report = ExecutionReport(tool="ThesisExtraction")
        self.report.artifacts["instance"] = len(_FakeExtraction.instances)

    async def extract_candidates(
        self,
        text: str,
        count: int = 4,
        focus: str = "",
        not_like_these: list[str] | None = None,
    ) -> list[str]:
        _FakeExtraction.calls.append(
            (
                "extract",
                {
                    "text": text,
                    "count": count,
                    "focus": focus,
                    "not_like_these": list(not_like_these or []),
                },
            )
        )
        _FakeExtraction.live += 1
        _FakeExtraction.peak = max(_FakeExtraction.peak, _FakeExtraction.live)
        try:
            wait = _FakeExtraction.delays.get(text, _FakeExtraction.dwell)
            if wait:
                await asyncio.sleep(wait)
            else:
                await asyncio.sleep(0)
        finally:
            _FakeExtraction.live -= 1

        if text in _FakeExtraction.barren:
            return []
        if text in _FakeExtraction.candidates:
            return list(_FakeExtraction.candidates[text])
        return [f"claim-from-{text[:12]}"]

    async def classify_candidates(
        self,
        candidates: list[tuple[str, str]],
        domain_hint: str = "",
    ) -> list[object]:
        _FakeExtraction.calls.append(
            ("classify", {"candidates": list(candidates), "domain_hint": domain_hint})
        )
        return [_FakeStatement(text) for text, _ in candidates]

    async def resolve(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "the sweep must use extract_candidates/classify_candidates; "
            "resolve() writes a Statement and a Rationale per candidate per window"
        )


class _FakeStatement:
    def __init__(self, text: str) -> None:
        self.text = text
        self.hash = f"h-{abs(hash(text)) % 10**7:07d}"


@pytest.fixture
def extraction(monkeypatch):
    _FakeExtraction.reset()
    monkeypatch.setattr(
        surface_theses_module, "ThesisExtraction", _FakeExtraction
    )
    yield _FakeExtraction
    _FakeExtraction.reset()


# --- Helpers -----------------------------------------------------------------


def _document(chars: int) -> str:
    """A document of roughly `chars`, with paragraph breaks to cut on."""
    paragraph = (
        "Governance concentrates decisions where the information is thinnest. "
        "Distributing them multiplies the coordination cost instead.\n\n"
    )
    out = []
    size = 0
    index = 0
    while size < chars:
        piece = f"[p{index}] {paragraph}"
        out.append(piece)
        size += len(piece)
        index += 1
    return "".join(out)[:chars]


def _skill() -> SurfaceTheses:
    return SurfaceTheses(intent="surface the tensions")


def _parsed(**kwargs) -> ParsedIntentDto:
    return ParsedIntentDto(**kwargs)


def _extract_texts(extraction) -> list[str]:
    return [payload["text"] for kind, payload in extraction.calls if kind == "extract"]


def _classify_payloads(extraction) -> list[dict]:
    return [payload for kind, payload in extraction.calls if kind == "classify"]


# --- Tests -------------------------------------------------------------------


class TestEveryWindowIsSwept:
    """Coverage, not best effort. A thesis set drawn from the first few pages
    while presenting itself as the theses of the source is a lie nothing
    downstream can detect."""

    @pytest.mark.asyncio
    async def test_one_extraction_per_window_carrying_that_window(self, extraction):
        text = _document(CHUNK_SIZE * 3)
        windows = chunk_text(text)
        assert len(windows) > 2

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        assert _extract_texts(extraction) == windows

    @pytest.mark.asyncio
    async def test_the_whole_document_never_goes_out_in_one_prompt(self, extraction):
        text = _document(CHUNK_SIZE * 3)
        windows = chunk_text(text)

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        for sent in _extract_texts(extraction):
            assert len(sent) <= CHUNK_SIZE
            assert text not in sent

    @pytest.mark.asyncio
    async def test_every_window_gets_its_own_extraction_instance(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        # One per window plus the single classifier that writes the survivors.
        assert len(extraction.instances) == len(windows) + 1

    @pytest.mark.asyncio
    async def test_the_window_count_is_reported(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        assert skill.report.artifacts["swept_candidate_count"] >= 1

    @pytest.mark.asyncio
    async def test_every_window_report_is_merged(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))

        skill = _skill()
        _, reports = await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        # One report per window plus the classifier's.
        assert len(reports) == len(windows) + 1


class TestNothingIsWrittenWhileSweeping:
    """`extract_candidates` writes nothing, which is the entire reason the
    concern was split. Sweeping with `resolve()` would commit a Statement plus a
    Rationale per candidate per window and lean on deduplication to delete most
    of them again."""

    @pytest.mark.asyncio
    async def test_resolve_is_never_called_on_the_extraction_concern(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        kinds = {kind for kind, _ in extraction.calls}
        assert kinds == {"extract", "classify"}


class TestCandidatesMergeInDocumentOrder:
    @pytest.mark.asyncio
    async def test_order_follows_the_document_not_completion(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        extraction.candidates = {
            windows[0]: ["first claim"],
            windows[-1]: ["last claim"],
        }
        for w in windows[1:-1]:
            extraction.barren.add(w)
        # The FIRST window dawdles, so it finishes last. Merging on completion
        # order would hand the classifier the document backwards — the same trap
        # the digest's reduce avoids, and the reason `gather`'s argument-order
        # guarantee is load-bearing rather than incidental.
        extraction.delays = {windows[0]: 0.05}

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        classified = _classify_payloads(extraction)[0]["candidates"]
        assert [text for text, _ in classified] == ["first claim", "last claim"]

    @pytest.mark.asyncio
    async def test_the_same_claim_in_two_windows_is_classified_once(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        for w in windows:
            extraction.candidates[w] = ["  Centralization   erodes TRUST "]

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        classified = _classify_payloads(extraction)[0]["candidates"]
        assert len(classified) == 1
        assert skill.report.artifacts["swept_candidate_count"] == 1

    @pytest.mark.asyncio
    async def test_only_the_requested_count_is_classified(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        for index, w in enumerate(windows):
            extraction.candidates[w] = [f"claim {index}a", f"claim {index}b"]

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=2),
            target_count=2,
            not_like_these=[],
        )

        classified = _classify_payloads(extraction)[0]["candidates"]
        assert len(classified) == 2
        # But the count reported is what the sweep actually found.
        assert skill.report.artifacts["swept_candidate_count"] == 2 * len(windows)


class TestEachCandidateIsClassifiedAgainstItsOwnWindow:
    """`StatementClassification` truncates its source context to 2000 chars, so
    handing it the head of a 400 KB concatenation would ask it to place a claim
    from page 300 using page 1."""

    @pytest.mark.asyncio
    async def test_the_pair_carries_the_window_the_candidate_came_from(
        self, extraction
    ):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        extraction.candidates = {w: [f"claim {i}"] for i, w in enumerate(windows)}

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=len(windows)),
            target_count=len(windows),
            not_like_these=[],
        )

        classified = _classify_payloads(extraction)[0]["candidates"]
        for index, (text, context) in enumerate(classified):
            assert text == f"claim {index}"
            assert context == windows[index]

    @pytest.mark.asyncio
    async def test_the_domain_hint_still_reaches_classification(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=2, domain_hint="organizational dynamics"),
            target_count=2,
            not_like_these=[],
        )

        assert (
            _classify_payloads(extraction)[0]["domain_hint"]
            == "organizational dynamics"
        )


class TestTheFanOutIsBounded:
    """The width here is the size of a file somebody pasted, not graph structure
    the framework produced — past the provider's ceiling a wider gather finishes
    LATER for the same tokens, on the throttle ladder."""

    @pytest.mark.asyncio
    async def test_never_more_windows_in_flight_than_the_cap(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 8))
        assert len(windows) > MAX_CONCURRENT_WINDOW_SWEEPS
        extraction.dwell = 0.01

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        assert extraction.peak <= MAX_CONCURRENT_WINDOW_SWEEPS
        # And it is a cap, not a serialization.
        assert extraction.peak > 1


class TestUnderDeliveryDoesNotResweep:
    """A sweep with a focus has already looked everywhere. Re-running
    `_build_param_variations` would re-read the whole document up to three more
    times to reconsider material the first pass saw and declined."""

    @pytest.mark.asyncio
    async def test_fewer_candidates_than_asked_for_is_accepted(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        extraction.candidates = {windows[0]: ["the only claim"]}
        for w in windows[1:]:
            extraction.barren.add(w)

        skill = _skill()
        await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3, focus="governance"),
            target_count=3,
            not_like_these=[],
        )

        assert len(_extract_texts(extraction)) == len(windows)
        assert "sweep_retried_without_focus" not in skill.report.artifacts

    @pytest.mark.asyncio
    async def test_zero_candidates_under_a_focus_earns_one_broader_sweep(
        self, extraction
    ):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        for w in windows:
            extraction.barren.add(w)

        skill = _skill()
        components, _ = await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3, focus="governance"),
            target_count=3,
            not_like_these=[],
        )

        assert skill.report.artifacts["sweep_retried_without_focus"] is True
        # Exactly twice over the windows — one focused, one broad.
        assert len(_extract_texts(extraction)) == 2 * len(windows)
        focuses = {
            payload["focus"]
            for kind, payload in extraction.calls
            if kind == "extract"
        }
        assert focuses == {"governance", ""}
        assert components == []

    @pytest.mark.asyncio
    async def test_zero_candidates_without_a_focus_does_not_retry(self, extraction):
        windows = chunk_text(_document(CHUNK_SIZE * 3))
        for w in windows:
            extraction.barren.add(w)

        skill = _skill()
        components, _ = await skill._extraction_sweep(
            windows=windows,
            parsed=_parsed(count=3),
            target_count=3,
            not_like_these=[],
        )

        assert len(_extract_texts(extraction)) == len(windows)
        assert "sweep_retried_without_focus" not in skill.report.artifacts
        assert components == []
        # No classifier is built for nothing.
        assert _classify_payloads(extraction) == []


class TestASourceThatFitsIsNotSwept:
    """`chunk_text` returns a single chunk holding the text unchanged, so the
    existing single-pass path stays byte-for-byte."""

    @pytest.mark.asyncio
    async def test_short_input_takes_the_loop(self, monkeypatch, extraction):
        skill = _skill()
        taken: list[str] = []

        async def fake_loop(**kwargs):
            taken.append("loop")
            assert kwargs["input_text"] == "a short source"
            return [], []

        async def fake_sweep(**kwargs):  # pragma: no cover - must not run
            taken.append("sweep")
            return [], []

        _stub_resolve_surroundings(monkeypatch, skill, "a short source")
        monkeypatch.setattr(skill, "_extraction_loop", fake_loop)
        monkeypatch.setattr(skill, "_extraction_sweep", fake_sweep)

        await skill.resolve()

        assert taken == ["loop"]
        assert skill.report.artifacts["source_windows"] == 1

    @pytest.mark.asyncio
    async def test_long_input_takes_the_sweep(self, monkeypatch, extraction):
        text = _document(CHUNK_SIZE * 3)
        skill = _skill()
        taken: list[str] = []

        async def fake_loop(**kwargs):  # pragma: no cover - must not run
            taken.append("loop")
            return [], []

        async def fake_sweep(**kwargs):
            taken.append("sweep")
            assert kwargs["windows"] == chunk_text(text)
            return [], []

        _stub_resolve_surroundings(monkeypatch, skill, text)
        monkeypatch.setattr(skill, "_extraction_loop", fake_loop)
        monkeypatch.setattr(skill, "_extraction_sweep", fake_sweep)

        await skill.resolve()

        assert taken == ["sweep"]
        assert skill.report.artifacts["source_windows"] == len(chunk_text(text))


def _stub_resolve_surroundings(monkeypatch, skill: SurfaceTheses, text: str) -> None:
    """Everything `resolve()` needs around the extraction branch, stubbed.

    The branch under test is one `if`; the graph and provider work on either
    side of it is covered elsewhere.
    """

    async def fake_input_text():
        return text

    async def fake_parse_intent():
        return _parsed(count=3)

    class _FakeVocabRepo:
        def get_vocabulary_with_rationales(self):
            return []

    monkeypatch.setattr(skill, "_get_input_text", fake_input_text)
    monkeypatch.setattr(skill, "_parse_intent", fake_parse_intent)
    monkeypatch.setattr(
        surface_theses_module, "StatementRepository", _FakeVocabRepo
    )
    monkeypatch.setattr(
        surface_theses_module, "ConversationFacilitator", lambda: _NullConversation()
    )


class _NullConversation:
    def set_system_prompt(self, prompt: str) -> None:
        pass
