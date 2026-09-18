"""A tension the advisory head just planted must be visible to it next turn.

Advisory mode pins the Advisor to one exploration, and `anchor` — which it keeps
in that mode on purpose — plants a STANDALONE perspective: `explore` is what
weaves one into the exploration afterwards, and `explore` fires 2 times in 6.
So until it fires, the tension the head anchored in this conversation, out of the
person's own words, lived entirely outside what `_resolve_scoped` rendered. On
the next turn it was one digit in

    3 other tension(s) exist outside this exploration (not shown).

indistinguishable from a tension belonging to some other exploration of the same
case. The head could only act on its own anchor by remembering the hash out of an
earlier turn's tool result.

The dump was enforcing a STRICTER pin than the tools it serves.
`tools/scoped.py::_outside_scope_refusal` already states the real rule — "the pin
protects explorations (deliverables), not standalone garbage: member of another
nexus → refused; member of no nexus → allowed (e.g. a framing this head anchored
during the conversation and the user rejected)" — and `explore`'s own tool doc
says to call it "when a newly anchored tension should join the exploration". The
context dump is now on that same line.

What this file pins, in the three halves that can break separately:
1. an unattached tension is rendered in advisory mode, with its particulars
   hoisted, and it is not also counted away as "outside";
2. the fence that remains is real — another exploration's perspectives, their
   particulars, and any cross-reference line that would name their contents;
3. the bound is the quality floor and nothing else, exactly as unscoped: a weak
   anchor is suppressed with a count line, a discarded one is gone, and the
   unscoped dump is unchanged.
"""

from __future__ import annotations

from test_dialectical_context import (_create_perspective_with_aspects, _ground,
                                      _new_sid)

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.scope_context import scope

#: The wording the pinned head reads for another exploration's tensions. Kept in
#: one place because two tests assert its presence and two its absence.
OTHER_EXPLORATION_LINE = "belong to other exploration(s)"

#: A taxonomy branch both sides of a correspondence must share. Same shape as
#: `TestDialecticalContextMultiNexus` uses: the branch is the third component.
BRANCH_URI = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"


def _exploration(intent: str, *perspectives) -> Nexus:
    nexus = Nexus(intent=intent)
    nexus.save()
    nexus.commit()
    for pp in perspectives:
        pp.nexus.connect(nexus)
    return nexus


class TestTheHeadSeesItsOwnAnchor:
    async def test_a_freshly_anchored_tension_is_rendered_not_counted(self):
        """The whole defect in one assertion."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(
                thesis_text="Take the investment", antithesis_text="Stay bootstrapped"
            )
            pinned = _exploration("whether to take the investment", member)
            anchored = _create_perspective_with_aspects(
                thesis_text="Hire the operator",
                antithesis_text="Keep running it myself",
            )

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Hire the operator" in dump, (
            "the tension this head anchored in this conversation was invisible "
            "to it on the next turn"
        )
        assert "Keep running it myself" in dump
        assert anchored.short_hash in dump, (
            "without the hash the head cannot weave it in with `explore`, "
            "discard it, or inspect it — it can only re-anchor it"
        )
        assert "# Unexplored Tensions" in dump

    async def test_its_particulars_come_with_it(self):
        """`anchor`'s `context` is the only place the person's numbers survive."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(thesis_text="Take the investment")
            pinned = _exploration("whether to take the investment", member)
            anchored = _create_perspective_with_aspects(thesis_text="Hire the operator")
            _ground(anchored, "The operator wants 8% and a two-year vest.")

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "- The operator wants 8% and a two-year vest." in dump

    async def test_it_is_not_also_counted_as_outside(self):
        """Shown AND counted away would tell the head two opposite things."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(thesis_text="Take the investment")
            pinned = _exploration("whether to take the investment", member)
            _create_perspective_with_aspects(thesis_text="Hire the operator")

            concern = DialecticalContext(nexus_hash=pinned.short_hash)
            dump = await concern.resolve()

        assert OTHER_EXPLORATION_LINE not in dump
        assert "1 unexplored" in concern.report.summary

    async def test_a_correspondence_with_the_exploration_is_stated(self):
        """The payoff `_build_cross_nexus_refs` documented and could not reach.

        Its docstring already promised "a fresh unexplored anchor echoing an
        already-explored tension" — unreachable from advisory mode, because the
        anchor was not in the dump to carry a line.
        """
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(
                thesis_text="Take the investment",
                antithesis_text="Stay bootstrapped",
                thesis_meaning=BRANCH_URI,
            )
            pinned = _exploration("whether to take the investment", member)
            _create_perspective_with_aspects(
                thesis_text="Hire the operator",
                antithesis_text="Keep running it myself",
                thesis_meaning=BRANCH_URI,
            )

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Same opposition family (Integrity)" in dump


class TestTheFenceThatRemains:
    """Another exploration is another deliverable. That half does not move."""

    @staticmethod
    def _two_explorations() -> Nexus:
        mine = _create_perspective_with_aspects(thesis_text="Take the investment")
        theirs = _create_perspective_with_aspects(
            thesis_text="Move the family abroad",
            antithesis_text="Keep the children in school here",
        )
        _ground(theirs, "The school year ends in June.")
        pinned = _exploration("whether to take the investment", mine)
        _exploration("whether to move abroad", theirs)
        return pinned

    async def test_another_explorations_perspectives_are_not_rendered(self):
        with scope(_new_sid()):
            pinned = self._two_explorations()
            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Move the family abroad" not in dump
        assert "Keep the children in school here" not in dump
        assert f"1 tension(s) {OTHER_EXPLORATION_LINE}" in dump

    async def test_another_explorations_particulars_do_not_leak(self):
        with scope(_new_sid()):
            pinned = self._two_explorations()
            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "school year ends in June" not in dump

    async def test_no_cross_reference_names_another_explorations_contents(self):
        """Cross-refs are built over the PINNED nexus only.

        A line reading "Same opposition family as perspective 1 in [[other]]"
        would walk straight around the count line above, naming both the other
        exploration and what is in it.

        All three tensions share a branch, and one of them is unattached — so a
        correspondence IS built here (it is the previous class's payoff) and the
        only question is which groups may appear in it. Without the unattached
        one there would be no correspondence to leak through, which is a way to
        pass this test rather than to satisfy it.
        """
        with scope(_new_sid()):
            mine = _create_perspective_with_aspects(
                thesis_text="Take the investment",
                thesis_meaning=BRANCH_URI,
            )
            theirs = _create_perspective_with_aspects(
                thesis_text="Move the family abroad",
                thesis_meaning=BRANCH_URI,
            )
            _create_perspective_with_aspects(
                thesis_text="Hire the operator",
                thesis_meaning=BRANCH_URI,
            )
            pinned = _exploration("whether to take the investment", mine)
            other = _exploration("whether to move abroad", theirs)

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Same opposition family (Integrity)" in dump, (
            "fixture is inert: no correspondence was built, so nothing could "
            "have leaked through one"
        )
        assert other.short_hash not in dump
        assert f"in [[{other.short_hash}]]" not in dump
        assert "Move the family abroad" not in dump


class TestTheBoundIsTheQualityFloorAndNothingElse:
    async def test_a_weak_anchor_is_suppressed_with_a_count(self):
        """Same floor, same reason as unscoped: a weak tetrad given full counsel
        choreography is confident bad advice. Inventing a second quality policy
        for advisory mode is not this change's job."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(thesis_text="Take the investment")
            pinned = _exploration("whether to take the investment", member)
            weak = _create_perspective_with_aspects(thesis_text="Hire the operator")
            weak.validation = "failed: the poles are the same claim restated"
            weak.save()

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Hire the operator" not in dump
        assert "1 unexplored tension(s) suppressed for low quality" in dump
        assert "reachable via inspect_node" in dump

    async def test_a_discarded_anchor_is_gone(self):
        """`discard` on a standalone perspective is allowed from advisory mode, so
        a rejected framing must actually leave the dump."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(thesis_text="Take the investment")
            pinned = _exploration("whether to take the investment", member)
            rejected = _create_perspective_with_aspects(thesis_text="Hire the operator")
            rejected.discarded = "the user rejected this framing"
            rejected.save()

            dump = await DialecticalContext(nexus_hash=pinned.short_hash).resolve()

        assert "Hire the operator" not in dump
        assert "# Unexplored Tensions" not in dump
        assert OTHER_EXPLORATION_LINE not in dump

    async def test_the_unscoped_dump_is_unchanged(self):
        """It always showed both, and it still shows both under one heading."""
        with scope(_new_sid()):
            member = _create_perspective_with_aspects(thesis_text="Take the investment")
            _exploration("whether to take the investment", member)
            _create_perspective_with_aspects(thesis_text="Hire the operator")

            dump = await DialecticalContext().resolve()

        assert "Take the investment" in dump
        assert "Hire the operator" in dump
        assert "# Unexplored Tensions" in dump
        assert OTHER_EXPLORATION_LINE not in dump
