"""The system prompt's cache breakpoint must sit BEFORE the mutable graph dump.

Mirascope emits the system prompt as one text block with `cache_control` at its
end. The Advisor's prompt ends with the Current Understanding dump, so the
breakpoint sat after content that changes on every graph write and the cached
prefix missed whenever it moved — the whole ~15.6k-token engine re-prefilled at
full rate to deliver a few hundred changed tokens.

`split_system_for_cache` splits at the seam. These tests pin the two things that
make that legal and the several ways it must decline, because both halves are
invisible at runtime: a wrong split still produces a valid request that merely
caches nothing, and nothing else in the tree would notice.
"""

from __future__ import annotations

from dialectical_framework.agents.advisor.system_prompts import (
    DEFAULT_TOOL_NAMES, system_prompt)
from dialectical_framework.utils.bedrock_provider import (
    CACHE_SPLIT_SENTINEL, _MIN_CACHEABLE_HEAD_CHARS, _fix_cache_breakpoints,
    _normalize_tool_breakpoints, split_system_for_cache)


def _block(text: str) -> list[dict]:
    """A system prompt shaped the way Mirascope's encoder emits it."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class TestTheSeamTheSplitDependsOn:
    """The prompt-side invariants. If either breaks, the split silently stops
    working — it would return the input unchanged and caching would quietly
    revert, with no test failing and no error anywhere."""

    def test_the_dump_is_the_last_thing_in_the_prompt(self):
        """`_CONTEXT_SLOT` last is what makes the dump a strict byte-suffix.

        Move it, or append any section after it, and the stable/mutable seam stops
        being a single point — the split would then leave stable text uncached, or
        worse, put mutable text in the cached head.
        """
        assert system_prompt().endswith("{dialectical_context}")
        assert system_prompt(scoped_nexus_hash="abc123").endswith(
            "{dialectical_context}"
        )

    def test_the_sentinel_appears_exactly_once_in_every_render(self):
        """Across tool sets and both modes. The sentinel is the seam's only
        marker, so a second occurrence would make the split position ambiguous."""
        for scoped in (None, "abc123"):
            for names in ([], ["anchor"], list(DEFAULT_TOOL_NAMES)):
                rendered = system_prompt(tool_names=names, scoped_nexus_hash=scoped)
                assert rendered.count(CACHE_SPLIT_SENTINEL) == 1, (
                    f"scoped={scoped} tools={len(names)}"
                )

    def test_the_stable_head_is_long_enough_to_be_cacheable(self):
        """The smallest realistic Advisor head must still clear the provider's
        minimum cacheable prefix, or the split would move the only breakpoint
        below the threshold and buy nothing."""
        smallest = system_prompt(tool_names=[], scoped_nexus_hash="abc123")
        head = smallest[: smallest.find(CACHE_SPLIT_SENTINEL)]
        assert len(head) > _MIN_CACHEABLE_HEAD_CHARS, len(head)

    def test_no_app_preamble_carries_the_sentinel(self):
        """The preamble is prepended BEFORE the engine (`advisor.py`), so a persona
        containing this heading would move the seam ahead of the engine and leave
        most of the stable prompt in the uncached tail. `find` keeps that a smaller
        win rather than a wrong answer, but there is no reason to accept it."""
        from dialectical_framework.agents import apps

        offenders = [
            name for name in dir(apps)
            if name.isupper()
            and isinstance(getattr(apps, name), str)
            and CACHE_SPLIT_SENTINEL in getattr(apps, name)
        ]
        assert not offenders, offenders


class TestTheSplit:
    def test_it_breaks_at_the_seam_and_loses_nothing(self):
        full = system_prompt().replace("{dialectical_context}", "T+: something\n")
        head, tail = split_system_for_cache(_block(full))

        assert head["text"] + tail["text"] == full, "the split changed the prompt"
        assert head["text"].endswith(CACHE_SPLIT_SENTINEL)
        assert tail["text"] == "T+: something\n"

    def test_only_the_stable_head_carries_the_breakpoint(self):
        full = system_prompt().replace("{dialectical_context}", "T+: something\n")
        head, tail = split_system_for_cache(_block(full))

        assert head["cache_control"] == {"type": "ephemeral"}
        # ABSENT, not None: the SDK serializes an explicit None as JSON `null`,
        # and "no breakpoint" should look like no key.
        assert "cache_control" not in tail

    def test_the_breakpoint_count_is_unchanged(self):
        """The fix RELOCATES a breakpoint. Adding one would risk the provider's
        limit of four, which the request already spends on the last tool and the
        last message of a multi-turn conversation."""
        full = system_prompt().replace("{dialectical_context}", "T+: something\n")
        before = _block(full)
        after = split_system_for_cache(before)

        assert sum(1 for b in before if b.get("cache_control")) == 1
        assert sum(1 for b in after if b.get("cache_control")) == 1

    def test_a_changed_dump_leaves_the_head_byte_identical(self):
        """The point of the whole change, stated as an assertion."""
        template = system_prompt()
        first = split_system_for_cache(_block(template.replace(
            "{dialectical_context}", "T+: one reading\n")))
        second = split_system_for_cache(_block(template.replace(
            "{dialectical_context}", "T+: a totally different reading\n" * 50)))

        assert first[0]["text"] == second[0]["text"]
        assert first[1]["text"] != second[1]["text"]


class TestWhenItMustDecline:
    """Every passthrough is load-bearing: this helper runs on EVERY request through
    three provider entry points, most of which are not the Advisor."""

    def test_other_agents_prompts_are_untouched(self):
        """No sentinel means no split. The Advisor is the only agent in the tree
        that puts mutable state in a system prompt."""
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT as ANALYST

        assert CACHE_SPLIT_SENTINEL not in ANALYST
        block = _block(ANALYST)
        assert split_system_for_cache(block) is block

    def test_a_head_too_short_to_cache_is_left_alone(self):
        """Below the provider's minimum cacheable prefix, splitting would move the
        only breakpoint below the threshold. On a single-turn request there is no
        message-level breakpoint to fall back on, so the result would be strictly
        less caching than before — a latency fix making latency worse."""
        short = f"You are helpful.{CACHE_SPLIT_SENTINEL}T+: something"
        block = _block(short)
        assert split_system_for_cache(block) is block

    def test_an_empty_dump_is_left_alone(self):
        """The provider rejects empty text blocks, and there is nothing to gain:
        with no tail the single block's own breakpoint already sits on stable
        text."""
        block = _block("x" * 20_000 + CACHE_SPLIT_SENTINEL)
        assert split_system_for_cache(block) is block

    def test_shapes_it_does_not_recognise_pass_through(self):
        assert split_system_for_cache(None) is None
        assert split_system_for_cache([]) == []
        assert split_system_for_cache("a plain string") == "a plain string"
        # Already split — re-splitting would move the breakpoint a second time.
        already = [{"type": "text", "text": "a" * 20_000}, {"type": "text", "text": "b"}]
        assert split_system_for_cache(already) is already
        not_text = [{"type": "image", "source": {}}]
        assert split_system_for_cache(not_text) is not_text


class TestTheLeakedToolBreakpoints:
    """Mirascope stamps the last tool but builds tool params through an
    `@lru_cache`d converter that returns a SHARED dict, so the stamp survives for
    the process and leaks onto later requests where that tool is not last. Four
    breakpoints is the provider's hard limit and a fifth is a 400, so this is a
    liveness defect, not a cost one."""

    def _tool(self, name: str, *, stamped: bool) -> dict:
        tool: dict = {"name": name, "input_schema": {"type": "object"}}
        if stamped:
            tool["cache_control"] = {"type": "ephemeral"}
        return tool

    def test_a_leaked_breakpoint_on_an_earlier_tool_is_removed(self):
        kwargs = {"tools": [
            self._tool("discard", stamped=True),      # leaked from a prior request
            self._tool("get_schema", stamped=True),   # this request's real last tool
        ]}
        _normalize_tool_breakpoints(kwargs)
        assert "cache_control" not in kwargs["tools"][0]
        assert kwargs["tools"][1]["cache_control"] == {"type": "ephemeral"}

    def test_the_shared_dict_is_not_mutated(self):
        """The leaked dict is the `lru_cache`'s own entry, aliased into the tools
        list of every in-flight request that also uses that tool. Popping from it
        would strip a breakpoint from a request already on its way — swapping a loud
        failure for a silent loss of caching."""
        leaked = self._tool("discard", stamped=True)
        kwargs = {"tools": [leaked, self._tool("get_schema", stamped=True)]}
        _normalize_tool_breakpoints(kwargs)
        assert leaked["cache_control"] == {"type": "ephemeral"}
        assert kwargs["tools"][0] is not leaked

    def test_a_correctly_stamped_request_is_left_exactly_as_is(self):
        tools = [self._tool("a", stamped=False), self._tool("b", stamped=True)]
        kwargs = {"tools": tools}
        _normalize_tool_breakpoints(kwargs)
        assert kwargs["tools"][0] is tools[0]
        assert kwargs["tools"][1] is tools[1]

    def test_shapes_it_leaves_alone(self):
        for tools in (None, [], [{"name": "only"}]):
            kwargs = {"tools": tools}
            _normalize_tool_breakpoints(kwargs)
            assert kwargs["tools"] == tools
        no_tools: dict = {"model": "m"}
        _normalize_tool_breakpoints(no_tools)
        assert "tools" not in no_tools


class TestTheProviderApplication:
    def test_a_request_without_a_system_prompt_does_not_grow_one(self):
        """Two call sites in the tree send no system prompt. Using `.get()` here
        would hand the provider `system=None` on every one of them."""
        kwargs: dict = {"model": "m", "messages": []}
        _fix_cache_breakpoints(kwargs)
        assert "system" not in kwargs

    def test_it_rewrites_the_system_prompt_in_place(self):
        full = system_prompt().replace("{dialectical_context}", "T+: something\n")
        kwargs: dict = {"model": "m", "system": _block(full)}
        _fix_cache_breakpoints(kwargs)
        assert len(kwargs["system"]) == 2

    def test_the_whole_request_stays_within_the_providers_four(self):
        """The number that decides whether the request is accepted at all: one tool,
        one system head, and the encoder's rolling breakpoint on the last message."""
        full = system_prompt().replace("{dialectical_context}", "T+: something\n")
        kwargs: dict = {
            "model": "m",
            "system": _block(full),
            "tools": [
                {"name": "discard", "cache_control": {"type": "ephemeral"}},
                {"name": "get_schema", "cache_control": {"type": "ephemeral"}},
            ],
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": "hi",
                     "cache_control": {"type": "ephemeral"}}
                ]}
            ],
        }
        _fix_cache_breakpoints(kwargs)

        breakpoints = sum(
            1 for t in kwargs["tools"] if t.get("cache_control")
        ) + sum(
            1 for b in kwargs["system"] if b.get("cache_control")
        ) + sum(
            1 for m in kwargs["messages"] for b in m["content"]
            if b.get("cache_control")
        )
        assert breakpoints == 3, breakpoints
