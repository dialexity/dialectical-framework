"""What the step-2 thesis gate is allowed to see, and what it costs to show it.

`ThesisExtraction` reads a source in two steps: step 1 pulls content items out of
the window, step 2 checks each item, ONE CALL PER ITEM, fanned out over an
isolated copy of step 1's conversation. That copy carries step 1's request, and
step 1's request has the whole window inside `<source_text>` — so a window is
re-sent once per extracted item. Measured on a 120 KB ingest: 207,047 tokens
across 24 calls, 75% of everything the size of the document costs on that path,
plus 184,438 cache-write tokens with 0 reads (concurrent siblings write entries
none of them can read back).

`settings.extraction_step2_carries_source` chooses between two arms, and these
tests pin BOTH along with the property that makes the comparison legitimate:
the two arms must differ in exactly one thing, the presence of the passage.
Everything else — the roles, the count, the turn structure, the gate's own
question — must be byte-identical, or the A/B measures a rewritten prompt.

The default is ON (the behaviour that has always run), and one test pins that
default rather than the behaviour under it: this is a reasoning setting, so the
default may only move on a measurement, and a silent flip would move it on an
edit. **The measurement was run three times and never settled, so the default
stands** (2026-09-17, `tests/e2e/probe_step2_isolate_ab.py`): the OFF arm changed
no keep/drop decision in any run (0 of 216 paired comparisons) and projects
6.7-7.2x cheaper, but the same preregistered endpoints returned don't-take, take
and no-call on three runs, because the blinded judge's tie rate and positional
bias both swing more than the difference it is being asked to detect. Two
confound-free instruments found nothing either way. So OFF is a supported, tested,
opt-in path that has NOT been shown to cost anything and has NOT earned a default
flip — which is exactly why the tests below pin both arms equally.

The rejected third possibility is pinned here too, by absence: dropping step 1's
ANSWER as well was measured and rejected TWICE (`tests/e2e/probe_step2_isolate_ab.py`)
— once because an item that merely restates what the document already established is
not substantive and nothing in the item says so about itself, and once because the
no-history arm also cuts items finer and yielded 18% more candidates. So the OFF arm
must still carry the sibling items, and `test_the_sibling_items_still_travel` is that
guarantee rather than an incidental assertion.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import thesis_extraction as module
from dialectical_framework.concerns.thesis_extraction import (ContentItemDto,
                                                              ThesisExtraction)
from dialectical_framework.settings import Settings


@contextmanager
def _settings(di_container, **overrides):
    current = di_container.settings()
    di_container.settings.override(current.model_copy(update=overrides))
    try:
        yield
    finally:
        di_container.settings.reset_override()
        di_container.settings.override(current)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """DB-free: which conversation step 2 runs in is decided before any write."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


#: Long enough that its presence in a prompt is unmistakable, and phrased so no
#: substring of it can be produced by the prompt scaffolding itself.
_WINDOW = (
    "Centralizing release authority makes the schedule predictable and makes "
    "every delay belong to one team. Distributing it removes the bottleneck and "
    "removes the person who can say the date is wrong."
)


def _message_text(msg) -> str:
    """Text of a Mirascope message, whatever content shape it carries."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(getattr(part, "text", str(part)) for part in content)
    return getattr(content, "text", str(content))


def _roles(conversation: ConversationFacilitator) -> list[str]:
    return [getattr(m, "role", None) for m in conversation._messages]


def _texts(conversation: ConversationFacilitator) -> list[str]:
    return [_message_text(m) for m in conversation._messages]


def _items(*texts: str) -> list[ContentItemDto]:
    return [ContentItemDto(content=t, content_type="claim") for t in texts]


def _prepared() -> tuple[ThesisExtraction, list[ContentItemDto]]:
    """A concern at the state step 2 runs from.

    The private fields are assigned the way `extract_candidates` assigns them and
    step 1's turn is replayed by hand, because the point of interest is what the
    conversation LOOKS like after step 1 — not step 1 itself, which would need a
    provider.
    """
    concern = ThesisExtraction()
    concern._text = _WINDOW
    concern._count = 2
    concern._focus = ""
    concern._not_like_these = []
    concern._conversation.set_system_prompt(module.SYSTEM_PROMPT)

    items = _items(
        "Centralizing release authority makes the schedule predictable",
        "Distributing release authority removes the bottleneck",
    )
    # What `_step1_extract_content` leaves behind: its request, then its answer as
    # the history helper stores it.
    concern._conversation.add_user_message(concern._step1_prompt(concern._text))
    concern._conversation.add_assistant_message(
        str(module.ExtractedContentDto(items=items))
    )
    return concern, items


class TestTheDefaultIsTheBehaviourThatHasAlwaysRun:
    def test_the_field_defaults_to_carrying_the_source(self):
        """Pinned as a DEFAULT, not as a behaviour.

        The arm below it is a reasoning change, so the default may only move on a
        measurement. Without this assertion it could move on an edit, and every
        number recorded against "arm A" would silently start describing the other
        arm. The measurement exists and did not license a flip — the probe's
        `_the_arms_are_the_shipped_code_paths` asserts this same default from the
        other side, so the two cannot drift.
        """
        assert (
            Settings.model_fields["extraction_step2_carries_source"].default is True
        )

    def test_on_is_a_plain_isolate_of_step_1(self, di_container):
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=True):
            conversation = concern._step2_conversation(items)

        assert _texts(conversation) == _texts(concern._conversation)
        assert _WINDOW in _texts(conversation)[1]

    def test_on_does_not_share_the_message_list(self, di_container):
        """The fan-out submits on these concurrently; a shared list is a race."""
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=True):
            first = concern._step2_conversation(items)
            second = concern._step2_conversation(items)

        assert first._messages is not second._messages
        assert first._messages is not concern._conversation._messages


class TestOffCarriesTheReadingAndNotThePassage:
    def test_the_window_is_gone(self, di_container):
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            conversation = concern._step2_conversation(items)

        assert _WINDOW not in "\n".join(_texts(conversation))

    def test_the_turn_structure_is_unchanged(self, di_container):
        """Same three messages in the same roles as the arm it is compared to.

        This is what makes the A/B a one-variable comparison: the model still
        reads "asked to extract, answered, now asked about one item". An arm that
        collapsed the transcript into a single user turn would be a different
        prompt, and any difference it measured would be unattributable.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=True):
            on = concern._step2_conversation(items)
        with _settings(di_container, extraction_step2_carries_source=False):
            off = concern._step2_conversation(items)

        assert _roles(off) == _roles(on) == ["system", "user", "assistant"]

    def test_the_system_prompt_survives(self, di_container):
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            conversation = concern._step2_conversation(items)

        assert _texts(conversation)[0] == module.SYSTEM_PROMPT

    def test_the_step_1_request_is_the_real_one_with_the_passage_replaced(
        self, di_container
    ):
        """Rebuilt through `_step1_prompt`, not edited into shape afterwards.

        `_step1_prompt` takes the source as a PARAMETER for exactly this: string
        surgery on the finished prompt would be a second definition of where the
        source sits inside it, and the two would drift the first time the wording
        of step 1 changed.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            conversation = concern._step2_conversation(items)

        assert _texts(conversation)[1] == concern._step1_prompt(module._SOURCE_ELIDED)

    def test_the_elision_says_the_passage_is_missing(self, di_container):
        """Silence would read as "extract from text that is not there".

        The sentinel is not decoration: a step-1 request with an EMPTY
        `<source_text>` invites the gate to treat every item as unsupported, which
        is a reasoning change dressed as a token saving.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            request = _texts(concern._step2_conversation(items))[1]

        assert module._SOURCE_ELIDED in request
        assert "not repeated here" in module._SOURCE_ELIDED

    def test_the_sibling_items_still_travel(self, di_container):
        """The measured reason this arm keeps step 1's answer.

        Dropping the answer too was rejected: with no context the gate stops
        recognising an item that merely restates what the document established,
        and admits it as substantive. So the OTHER items must be in the prompt.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            answer = _texts(concern._step2_conversation(items))[2]

        for item in items:
            assert item.content in answer

    def test_the_answer_is_step_1_s_own_history_text(self, di_container):
        """Reconstruction, not approximation.

        History stores `_assistant_history_text(result)`, which for a DTO with no
        `message` field is `str(result)` — and `ExtractedContentDto(items=items)`
        is the same model holding the same items. So the rebuilt turn is
        byte-identical to the one the real conversation holds.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            off = concern._step2_conversation(items)

        assert _texts(off)[2] == _texts(concern._conversation)[2]


class TestTheGatesOwnQuestionIsTheSameInBothArms:
    def test_the_prompt_does_not_depend_on_the_arm(self, di_container):
        """`_step2_prompt` reads no setting, and must not start.

        It is what makes the elision surgical: the question names the item and its
        type and asks four things about it, and never refers to the source. If the
        arms ever differed here the comparison would be between two prompts rather
        than between two contexts.
        """
        concern, items = _prepared()
        with _settings(di_container, extraction_step2_carries_source=True):
            on = concern._step2_prompt(items[0].content, items[0].content_type)
        with _settings(di_container, extraction_step2_carries_source=False):
            off = concern._step2_prompt(items[0].content, items[0].content_type)

        assert on == off
        assert _WINDOW not in on

    def test_the_prompt_carries_no_source_reference(self):
        concern, items = _prepared()
        prompt = concern._step2_prompt(items[0].content, items[0].content_type)

        for phrase in ("source", "<source_text>", "the text above", "the document"):
            assert phrase not in prompt.lower()


class TestTheFanOutRunsThroughTheSeam:
    @pytest.mark.asyncio
    async def test_every_item_gets_its_own_conversation_from_the_seam(
        self, di_container, monkeypatch
    ):
        """One call per item, each through `_step2_conversation`.

        Pinned at the fan-out rather than on the seam alone because the whole cost
        argument is the WIDTH of the fan: a caller that built one conversation
        outside the comprehension and reused it would pass every seam test here
        and re-introduce the shared-message-list race `isolate()` exists for.
        """
        concern, items = _prepared()
        built: list[ConversationFacilitator] = []
        real_seam = concern._step2_conversation

        def recording_seam(content_items):
            conversation = real_seam(content_items)
            built.append(conversation)
            return conversation

        monkeypatch.setattr(concern, "_step2_conversation", recording_seam)

        submitted: list[str] = []

        async def fake_submit(self, response_model, user_content, **kwargs):
            submitted.append(user_content)
            return module.CandidateCheckDto(
                is_assertable=True,
                is_substantive=True,
                is_atomic=True,
                atomic_theses=[f"thesis for {len(submitted)}"],
            )

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)

        with _settings(di_container, extraction_step2_carries_source=False):
            candidates = await concern._step2_identify_candidates(items)

        assert len(built) == len(items)
        # Distinct objects, not the same one handed back twice — the race the
        # isolation exists to prevent is invisible to every other assertion here.
        assert len({id(c) for c in built}) == len(items)
        assert len(submitted) == len(items)
        assert submitted == [
            concern._step2_prompt(item.content, item.content_type) for item in items
        ]
        assert candidates == ["thesis for 1", "thesis for 2"]
        # The saving, restated as a test: not one of those calls carried the window.
        assert all(_WINDOW not in "\n".join(_texts(c)) for c in built)

    @pytest.mark.asyncio
    async def test_no_items_asks_nothing(self, di_container):
        """The seam is never reached, so neither arm can crash on an empty read."""
        concern, _ = _prepared()
        with _settings(di_container, extraction_step2_carries_source=False):
            assert await concern._step2_identify_candidates([]) == []


class TestIsolateWithoutHistory:
    """The facilitator-level half, which is why this is not a fresh conversation.

    A bare `ConversationFacilitator()` at the call site would be correct for
    `ThesisExtraction` (it wires no tools) and a trap for the next caller, who
    would lose them silently. These pin what `keep_history=False` promises.
    """

    def test_tools_survive(self):
        def a_tool() -> str:
            """A tool, for the caller this flag is a trap for."""
            return "ok"

        conversation = ConversationFacilitator(tools=[a_tool])
        conversation.set_system_prompt("system")
        conversation.add_user_message("user")

        assert conversation.isolate(keep_history=False)._tools == [a_tool]

    def test_only_the_system_message_is_carried(self):
        conversation = ConversationFacilitator()
        conversation.set_system_prompt("system")
        conversation.add_user_message("user")
        conversation.add_assistant_message("assistant")

        isolated = conversation.isolate(keep_history=False)
        assert _texts(isolated) == ["system"]

    def test_the_default_still_carries_everything(self):
        conversation = ConversationFacilitator()
        conversation.set_system_prompt("system")
        conversation.add_user_message("user")

        assert _texts(conversation.isolate()) == ["system", "user"]

    def test_a_conversation_with_no_system_prompt_yields_nothing(self):
        conversation = ConversationFacilitator()
        conversation.add_user_message("user")

        assert conversation.isolate(keep_history=False)._messages == []

    def test_an_empty_conversation_is_fine(self):
        assert ConversationFacilitator().isolate(keep_history=False)._messages == []

    def test_a_replayed_dict_system_message_is_recognised(self):
        """A caller resuming a serialized conversation hands back plain dicts.

        Both spellings reach `_messages` — Mirascope's own objects carry `.role`,
        a replayed transcript is `{"role": ...}` — so the check that finds the
        system message has to accept both, or resuming a conversation would drop
        the system prompt from every isolated call.
        """
        conversation = ConversationFacilitator()
        conversation._messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ]

        assert conversation.isolate(keep_history=False)._messages == [
            {"role": "system", "content": "system"}
        ]
