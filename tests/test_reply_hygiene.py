"""
Hash citations never reach the person — the one leak shape the framework can
strip deterministically on both entry points (`agents/advisor/reply_hygiene.py`).

Pinned at two levels: the pure functions (the streaming filter must equal the
regex over EVERY chunking, or `ResponseComplete.streamed` lies), and the
Advisor's two entry points (the filter is wired where the person reads, and
only where the machinery is hidden — the Navigator's advisory register
discloses hashes on purpose).
"""

from __future__ import annotations

import random

import pytest

from dialectical_framework.agents.advisor.reply_hygiene import (
    HashCitationFilter, strip_hash_citations)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


CORPUS = [
    "That is the reflection piece: [[69961e3]] Re+ is \"Notice logged contributions\".",
    "the price [[abc1234]] you named",
    "[[abc1234]] leads",
    "ends with [[abc1234]]",
    "two [[abc1234]] then [[deadbeef]] here",
    "full [[" + "a" * 64 + "]] hash",
    "too long [[" + "a" * 65 + "]] stays",
    "not hex [[hello12]] stays",
    "too short [[abc12]] stays",
    "unclosed [[abc1234 stays",
    "nested [[[abc1234]]] odd",
    "brackets [x] and [[ and ]] alone",
    "space before [ then [[abc1234]] gone",
    "no space[[abc1234]]tight",
    "trailing space ",
    "trailing bracket [",
    "trailing two [[",
    "T1+ [[abc1234]]: \"Buy out cofounder\" (HS=0.85)",
    "",
    "[[",
    "]]",
    "a [[abc1234]] b [[zz]] c [[abcdef]] d",
]


def _every_split(text: str, seed: int, samples: int = 12) -> list[list[str]]:
    rng = random.Random(seed)
    splits: list[list[str]] = [[text], list(text)]
    for _ in range(samples):
        cuts = sorted(rng.sample(range(1, len(text)), min(len(text) - 1, rng.randint(1, 6)))) if len(text) > 1 else []
        chunks, last = [], 0
        for c in cuts:
            chunks.append(text[last:c])
            last = c
        chunks.append(text[last:])
        splits.append(chunks)
    return splits


class TestTheRegex:
    def test_addresses_go_and_their_leading_space_with_them(self):
        assert strip_hash_citations("the price [[abc1234]] you") == "the price you"
        assert strip_hash_citations("[[abc1234]] leads") == " leads"

    def test_what_is_not_an_address_stays(self):
        for text in ("[[hello12]]", "[[abc12]]", "[[" + "a" * 65 + "]]", "[[abc1234", "[x]"):
            assert strip_hash_citations(text) == text


class TestTheStreamEqualsTheRegex:
    @pytest.mark.parametrize("text", CORPUS)
    def test_every_chunking_of_the_corpus(self, text):
        expected = strip_hash_citations(text)
        for seed, chunks in enumerate(_every_split(text, seed=len(text))):
            f = HashCitationFilter()
            got = "".join(f.feed(c) for c in chunks) + f.flush()
            assert got == expected, (chunks, got, expected)

    def test_random_hash_soup(self):
        rng = random.Random(7)
        alphabet = ["[", "]", " ", "a", "f", "z", "1", "[[", "]]", "[[abc1234]]", "[[" + "b" * 64 + "]]"]
        for _ in range(300):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
            expected = strip_hash_citations(text)
            for chunks in _every_split(text, seed=rng.randint(0, 10**6), samples=4):
                f = HashCitationFilter()
                got = "".join(f.feed(c) for c in chunks) + f.flush()
                assert got == expected, (text, chunks)

    def test_holding_back_is_bounded(self):
        f = HashCitationFilter()
        f.feed("x" * 1000 + " [[" + "a" * 64)
        assert len(f._pending) <= 1 + 2 + 64
        f.feed("b")  # 65th char: cannot be an address any more
        assert f._pending == "" or len(f._pending) <= 2


class TestTheAdvisorFiltersWhereTheMachineryIsHidden:
    """The filter is a property of the HEAD, decided at construction from the
    composed preamble: hidden machinery filters, a disclosed register does not."""

    def test_the_hidden_heads_filter_and_the_disclosed_register_does_not(self, di_container):
        from dialectical_framework.agents.advisor.advisor import Advisor
        from dialectical_framework.agents.app_spec import AppSpec
        from dialectical_framework.agents.apps import (
            NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER)

        spec = AppSpec(advisor_persona="## Persona\nYou are calm.", voicing="## V\nx")
        assert Advisor(app=spec)._hides_hashes is True
        assert Advisor()._hides_hashes is True
        assert Advisor(app_preamble="## Persona\nplain")._hides_hashes is True
        # The Navigator's advisory register grants disclosure — hashes are the
        # person's own addresses there.
        assert Advisor(app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER)._hides_hashes is False

    @pytest.mark.asyncio
    async def test_chat_returns_the_clean_reply(self, di_container, monkeypatch):
        from dialectical_framework.agents.advisor.advisor import Advisor, ChatResponse
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.scope_context import scope

        advisor = Advisor(app_preamble="## Persona\nplain")
        raw = "The price [[abc1234]] is real."

        async def fake_submit(model, text):
            advisor._conversation.last_submit_seconds = 0.1
            return ChatResponse(message=raw)

        async def nothing(*a, **k):
            return None

        monkeypatch.setattr(advisor._conversation, "submit", fake_submit)
        monkeypatch.setattr(advisor, "_repair_unrecorded_decision", nothing)
        monkeypatch.setattr(advisor, "_refresh_context", lambda: _zero())
        monkeypatch.setattr(advisor, "_settle_deferred_work", lambda: _zero())
        case = Case()
        case.commit()
        with scope(case.sid):
            reply = await advisor.chat("hi")
        assert reply == "The price is real."

    @pytest.mark.asyncio
    async def test_chat_stream_filters_the_deltas_and_the_final_message_alike(self, di_container, monkeypatch):
        from dialectical_framework.agents.advisor.advisor import Advisor, ChatResponse
        from dialectical_framework.agents.stream_events import (
            ResponseComplete, TextDelta)
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.scope_context import scope

        advisor = Advisor(app_preamble="## Persona\nplain")
        pieces = ["The pri", "ce [[ab", "c1234]] is", " real."]

        async def fake_stream(model, text):
            for p in pieces:
                yield TextDelta(text=p)
            advisor._conversation.last_submit_seconds = 0.1
            advisor._conversation.last_submit_first_delta_s = 0.05
            yield ResponseComplete(result=ChatResponse(message="".join(pieces)), streamed=True)

        async def nothing(*a, **k):
            return None

        monkeypatch.setattr(advisor._conversation, "submit_stream", fake_stream)
        monkeypatch.setattr(advisor, "_repair_unrecorded_decision", nothing)
        monkeypatch.setattr(advisor, "_refresh_context", lambda: _zero())
        monkeypatch.setattr(advisor, "_settle_deferred_work", lambda: _zero())

        case = Case()
        case.commit()
        with scope(case.sid):
            events = []
            async for e in advisor.chat_stream("hi"):
                events.append(e)
        deltas = "".join(e.text for e in events if isinstance(e, TextDelta))
        final = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert deltas == "The price is real."
        assert final.message == deltas, "streamed=True means message IS the deltas"
        assert final.streamed is True


async def _zero() -> float:
    return 0.0
