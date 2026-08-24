"""
BuildStatus: one typed read of how far a Case got, for host apps.

Everything here is DERIVED on read — the same rule as `wheel_completeness` and
`polarity_completeness`, whose results this aggregates. Nothing is stored, so a
reopened session gets its status for free and there is no progress counter to
drift from the graph.

Why this exists next to `DialecticalContext`: that concern performs the same
traversal but returns LLM prose, which a UI cannot render and a caller cannot
branch on. This returns dataclasses. Same graph, two consumers:

    status = await BuildStatus().resolve()
    for wheel in status.wheels:
        render(wheel.short_hash, wheel.fraction, wheel.state)
    if status.resume_hint:
        await run_deepen(status.resume_hint)   # tops up exactly the gap

The reads are LLM-free and sid-scoped (call inside `with scope(case.sid)`), and
fail-soft per node: a wheel or polarity whose reads blow up lands in
`unreadable_hashes` rather than taking down the whole status pass — and rather
than vanishing, which would report a broken graph as a finished one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.wheel import Wheel

#: Wheel states. The split that matters is `shallow` vs `interrupted`: both are
#: short of 6N, but a shallow wheel was never developed BY DESIGN (`explore`
#: deepens one arrangement per call — EXPLORE_DEEP_WHEELS) while an interrupted
#: one is work the user lost. Only the second is something to offer to resume.
WHEEL_COMPLETE = "complete"
WHEEL_INTERRUPTED = "interrupted"
WHEEL_SHALLOW = "shallow"
#: Nothing can be built here yet — this wheel's edge pairs have unfinished
#: segments, so a `deepen` would spend nothing and add nothing.
WHEEL_BLOCKED = "blocked"


@dataclass(frozen=True)
class PolarityStatus:
    """How far one tension got. `state` is a `POLARITY_*` value from `rendering`."""

    hash: str
    short_hash: str
    state: str
    heuristic_similarity: Optional[float] = None
    thesis: Optional[str] = None
    antithesis: Optional[str] = None


@dataclass(frozen=True)
class SynthesisStatus:
    """A wheel's S+/S- pair and what it was derived from.

    `is_stale` means the stamp no longer matches the wheel: the synthesis was
    computed from a fragment and the wheel has since been topped up. S+ emerges
    from ALL Transformations at once, so a stale synthesis is worth regenerating
    — same rule `inspect_node` renders.
    """

    hash: str
    short_hash: str
    completeness: Optional[str] = None
    is_stale: bool = False


@dataclass(frozen=True)
class WheelStatus:
    """One causal arrangement: how much of its 6N pathway budget exists."""

    hash: str
    short_hash: str
    nexus_hash: str
    cycle_hash: str
    #: Perspectives in the parent cycle — the wheel's layer.
    layer: int
    done: int
    expected: int
    #: Edge labels a `deepen` would top up, and ones it cannot help.
    incomplete_edges: tuple[str, ...] = ()
    blocked_edges: tuple[str, ...] = ()
    syntheses: tuple[SynthesisStatus, ...] = ()

    @property
    def fraction(self) -> str:
        """`"4/6"` — the same form `Synthesis.completeness` stores."""
        return f"{self.done}/{self.expected}"

    @property
    def is_complete(self) -> bool:
        return self.expected > 0 and self.done >= self.expected

    @property
    def is_resumable(self) -> bool:
        """Whether a `deepen` on this wheel would actually build something."""
        return not self.is_complete and bool(self.incomplete_edges)

    @property
    def state(self) -> str:
        if self.is_complete:
            return WHEEL_COMPLETE
        if not self.incomplete_edges:
            # No edge can take a Transformation right now. Reported as blocked
            # even at 0/6, so a host never offers a deepen that cannot help.
            return WHEEL_BLOCKED
        return WHEEL_INTERRUPTED if self.done else WHEEL_SHALLOW

    @property
    def has_stale_synthesis(self) -> bool:
        return any(s.is_stale for s in self.syntheses)


@dataclass(frozen=True)
class CaseStatus:
    """The whole picture for one Case, in one read."""

    sid: Optional[str] = None
    polarities: tuple[PolarityStatus, ...] = ()
    wheels: tuple[WheelStatus, ...] = ()
    #: Every nexus in the case, including ones with no wheels built yet — an
    #: exploration whose structure was never built is status, not absence.
    nexus_hashes: tuple[str, ...] = ()
    #: Nodes whose status could not be read. Named rather than dropped.
    unreadable_hashes: tuple[str, ...] = ()

    def polarities_by_state(self) -> dict[str, list[str]]:
        """`POLARITY_*` → hashes, for a per-state count or listing."""
        grouped: dict[str, list[str]] = {}
        for polarity in self.polarities:
            grouped.setdefault(polarity.state, []).append(polarity.hash)
        return grouped

    def wheels_by_state(self) -> dict[str, list[str]]:
        """`WHEEL_*` → hashes. Full hashes: `deepen` resolves by hash."""
        grouped: dict[str, list[str]] = {}
        for wheel in self.wheels:
            grouped.setdefault(wheel.state, []).append(wheel.hash)
        return grouped

    @property
    def interrupted_wheels(self) -> tuple[WheelStatus, ...]:
        return tuple(w for w in self.wheels if w.state == WHEEL_INTERRUPTED)

    @property
    def shallow_wheel_hashes(self) -> tuple[str, ...]:
        """Built and ranked but never deepened — the `explore` budget's leftovers."""
        return tuple(w.hash for w in self.wheels if w.state == WHEEL_SHALLOW)

    @property
    def stale_synthesis_wheel_hashes(self) -> tuple[str, ...]:
        return tuple(w.hash for w in self.wheels if w.has_stale_synthesis)

    @property
    def resume_hint(self) -> Optional[str]:
        """Which wheel a `deepen` should finish, or None if nothing is owed.

        Interrupted wheels only. A shallow wheel is also short of 6N, but
        deepening it is ordinary work the user chooses by which arrangement
        their reality matches — offering it as a "resume" would present the
        argmax path as unfinished business and quietly overrule that choice.

        Closest to finishing wins (least work to whole), hash as tiebreak so two
        reads of the same graph never disagree.
        """
        candidates = [w for w in self.interrupted_wheels if w.is_resumable]
        if not candidates:
            return None
        return max(candidates, key=lambda w: (w.done, w.hash)).hash

    @property
    def is_complete(self) -> bool:
        """Nothing outstanding: no interrupted wheel, no half-built tension.

        Shallow wheels and set-aside polarities don't count against it — the
        first is a budget working as designed, the second is the HS gate working
        as designed. An unreadable node does: its status is unknown, and
        "unknown" must not be laundered into "finished" — that is the very
        substitution this whole status pass exists to prevent.
        """
        from dialectical_framework.graph.rendering import POLARITY_PARTIAL

        return (
            not self.resume_hint
            and not self.unreadable_hashes
            and not any(p.state == POLARITY_PARTIAL for p in self.polarities)
        )


class BuildStatus(ReasonableConcern[CaseStatus]):
    """
    Derived build status for the current Case (sid), as data rather than prose.

    Programmatic usage:
        with scope(case.sid):
            status = await BuildStatus().resolve()
    """

    @inject
    async def resolve(self, sid: Optional[str] = Provide[DI.sid]) -> CaseStatus:
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository
        from dialectical_framework.graph.repositories.polarity_repository import \
            PolarityRepository

        unreadable: list[str] = []

        polarities: list[PolarityStatus] = []
        for polarity in PolarityRepository().find_all():
            polarity_status = self._polarity_status(polarity, unreadable)
            if polarity_status is not None:
                polarities.append(polarity_status)

        # Committed only, like every other listing: a nexus still being built
        # has no stable identity to report against.
        nexuses = [n for n in NexusRepository().find_all() if n.hash]
        wheels: list[WheelStatus] = []
        # A cycle qualifies for every nexus whose perspective set contains it,
        # so a wheel under a shared arrangement can come back more than once.
        # First occurrence wins — a host counting wheels must not double-count
        # one arrangement because two explorations overlap.
        seen: set[str] = set()
        for nexus in nexuses:
            for wheel_status in self._nexus_wheels(nexus, unreadable):
                if wheel_status.hash in seen:
                    continue
                seen.add(wheel_status.hash)
                wheels.append(wheel_status)

        status = CaseStatus(
            sid=sid,
            polarities=tuple(polarities),
            wheels=tuple(wheels),
            nexus_hashes=tuple(n.hash for n in nexuses if n.hash),
            unreadable_hashes=tuple(unreadable),
        )

        summary = (
            f"{len(status.wheels)} wheel(s), {len(status.polarities)} tension(s)"
        )
        if status.resume_hint:
            summary += f" — resume {status.resume_hint[:7]}"
        elif status.is_complete:
            summary += " — nothing outstanding"
        self._report.ok = True
        self._report.summary = summary
        return status

    def _polarity_status(
        self, polarity: Polarity, unreadable: list[str]
    ) -> Optional[PolarityStatus]:
        from dialectical_framework.agents.analyst.analyst import HS_THRESHOLD
        from dialectical_framework.graph.rendering import polarity_completeness

        if not polarity.hash:
            return None
        try:
            state = polarity_completeness(polarity, hs_threshold=HS_THRESHOLD)
            t = polarity.get_t_component()
            a = polarity.get_a_component()
            return PolarityStatus(
                hash=polarity.hash,
                short_hash=polarity.short_hash,
                state=state,
                heuristic_similarity=polarity.heuristic_similarity,
                thesis=t.text if t else None,
                antithesis=a.text if a else None,
            )
        except Exception:  # noqa: BLE001 - one bad node must not sink the read
            # Broad on purpose: the classification reads relationships from the
            # DB, so the failure modes include driver errors that are neither
            # ValueError nor RuntimeError. Named, not dropped.
            unreadable.append(polarity.hash)
            return None

    def _nexus_wheels(
        self, nexus: Nexus, unreadable: list[str]
    ) -> list[WheelStatus]:
        from dialectical_framework.graph.repositories.wheel_repository import \
            WheelRepository

        try:
            pairs = WheelRepository().find_by_nexus(nexus)
        except Exception:  # noqa: BLE001 - see _polarity_status
            if nexus.hash:
                unreadable.append(nexus.hash)
            return []

        statuses: list[WheelStatus] = []
        for cycle, wheel in pairs:
            status = self._wheel_status(nexus, cycle, wheel, unreadable)
            if status is not None:
                statuses.append(status)
        return statuses

    def _wheel_status(
        self,
        nexus: Nexus,
        cycle: Cycle,
        wheel: Wheel,
        unreadable: list[str],
    ) -> Optional[WheelStatus]:
        from dialectical_framework.graph.rendering import (build_pp_index,
                                                           wheel_completeness)

        if not wheel.hash:
            return None
        try:
            # pp_index is passed explicitly so the edge labels read as
            # T1- → A2+ (the same indices every other surface uses) instead of
            # hashes, and so `wheel_completeness` doesn't re-find the nexus it
            # was just handed.
            completeness = wheel_completeness(wheel, build_pp_index(nexus))
            return WheelStatus(
                hash=wheel.hash,
                short_hash=wheel.short_hash,
                nexus_hash=nexus.hash or "",
                cycle_hash=cycle.hash or "",
                layer=len(cycle.perspective_hashes or []),
                done=completeness.done,
                expected=completeness.expected,
                incomplete_edges=tuple(completeness.incomplete_edges),
                blocked_edges=tuple(completeness.blocked_edges),
                syntheses=self._syntheses(wheel, completeness.fraction),
            )
        except Exception:  # noqa: BLE001 - see _polarity_status
            unreadable.append(wheel.hash)
            return None

    @staticmethod
    def _syntheses(
        wheel: Wheel, current_fraction: str
    ) -> tuple[SynthesisStatus, ...]:
        out: list[SynthesisStatus] = []
        for synth, _ in wheel.synthesis.all():
            if not synth.hash:
                continue
            stamp = synth.completeness
            out.append(
                SynthesisStatus(
                    hash=synth.hash,
                    short_hash=synth.short_hash,
                    completeness=stamp,
                    # Unstamped syntheses predate the stamp; calling those stale
                    # would flag every old graph as needing regeneration.
                    is_stale=bool(stamp) and stamp != current_fraction,
                )
            )
        return tuple(out)
