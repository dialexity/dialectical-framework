"""
RecordDecision: persist a user-confirmed decision as a Decision node.

The recording ceremony (propose, read back, confirm) happens in
conversation BEFORE this concern runs — parameters arrive as literal
confirmed wording, never as instructions to interpret. The concern:

1. Resolves ground hashes (refuses on unknown/uncommitted/non-assessable —
   fail-closed for grounds, since a dangling or reader-invisible ground
   would break the record's value)
2. Commits the Decision (question rides intent, stance frozen in hash)
3. Attaches the distilled why as a Rationale carrying the confirming
   principal's provenance (agent="human" only when a person confirmed;
   delegated drivers pass their own identity — see resolve())
4. Connects GROUNDED_IN edges with their roles
5. Runs DecisionCoherenceCheck and flags the verdict (fail-soft: a failed
   or errored check NEVER blocks the record — soft gate)

Replacing/retracting a decision is NOT this concern's job — that is the
standard Discard concern (reason like "superseded by [[new_hash]]").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import \
        AssessableEntity

#: The two positions a price can occupy: (display label, Perspective accessor,
#: edge type). A cost is a MINUS — `GroundedInRelationship` owns why, with the
#: measurement that forced the correction. Owned here because three consumers
#: read it and a hand-typed fourth copy would drift: the omission recovery
#: (`_unpriced_aspects`), the misplacement guard (`_accepted_cost_misplacement`),
#: and that guard's repair suggestion.
COST_POSITIONS: tuple[tuple[str, str, str], ...] = (
    ("T-", "t_minus", "T_MINUS"),
    ("A-", "a_minus", "A_MINUS"),
)


class GroundLink(BaseModel):
    """One grounding reference for a decision."""

    hash: str = Field(
        description="Hash (or unique prefix) of a committed node this "
        "decision rests on — a perspective, statement, wheel, or pathway."
    )
    role: str | None = Field(
        default=None,
        description="Optional semantic role. Seed vocabulary: "
        "'accepted_cost' = the risk the person confronted and accepted — the "
        "CHOSEN side's overdevelopment aspect (T- if they chose the thesis, "
        "A- if the antithesis), never a plus (a plus is a goal or an "
        "obligation, not a price); 'adopted_pathway' = the "
        "transformation adopted as the ongoing management recipe. "
        "Omit for a plain ground.",
    )


class RecordDecision(ReasonableConcern[str | None]):
    """
    Record a confirmed decision with its grounds and human rationale.

    Programmatic usage:
        concern = RecordDecision()
        decision_hash = await concern.resolve(
            question="Which job offer to take?",
            stance="Accept the startup offer",
            rationale="Growth outweighs stability for me right now...",
            # abc123 is the chosen side's minus — the risk being accepted.
            grounds=[GroundLink(hash="abc123", role="accepted_cost")],
        )
    """

    async def resolve(
        self,
        question: str,
        stance: str,
        rationale: str,
        grounds: list[GroundLink] | None = None,
        principal: str = "human",
    ) -> str | None:
        """
        `principal` is the provenance stamped on the decision's Rationale —
        WHO confirmed the recording ceremony. "human" (default) is the
        sentinel meaning an actual person confirmed the wording; a delegated
        driver (agent-to-agent runs) must pass its own identity (e.g.
        "agent:<name>" or a <provider>/<model> string) — the ledger and
        inspect_node render only human-confirmed rationales as the person's
        own "why", so a false "human" here corrupts the record's authority
        semantics unfixably. Attested by the HOST at agent construction
        (Advisor(principal=...)), never by the LLM.
        """
        from dialectical_framework.concerns.decision_coherence_check import \
            DecisionCoherenceCheck
        from dialectical_framework.graph.nodes.assessable_entity import \
            AssessableEntity
        from dialectical_framework.graph.nodes.decision import Decision
        from dialectical_framework.graph.nodes.rationale import Rationale
        from dialectical_framework.graph.relationships.grounded_in_relationship import \
            GroundedInRelationship
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        # 0a. Validate the speech act itself. Refusals must stay in-band
        # (report, not exception): Mirascope re-raises tool exceptions,
        # which would kill the whole agent turn.
        question = (question or "").strip()
        stance = (stance or "").strip()
        if not question or not stance:
            missing = "question" if not question else "stance"
            self._report.ok = False
            self._report.summary = (
                f"Cannot record: {missing} is empty — a decision needs both "
                "the question decided and the confirmed stance."
            )
            return None

        # 0b. Normalize grounds — callers at the tool boundary hand raw
        # dicts (Mirascope passes json.loads'd kwargs without coercion) —
        # and dedup: GROUNDED_IN is directed, so repeated connect() calls
        # would create duplicate edges.
        try:
            normalized = [
                g if isinstance(g, GroundLink) else GroundLink.model_validate(g)
                for g in grounds or []
            ]
        except Exception as e:
            self._report.ok = False
            self._report.summary = f"Cannot record: malformed grounds entry — {e}"
            return None
        seen: set[tuple[str, str | None]] = set()
        grounds = []
        for g in normalized:
            key = (g.hash, g.role)
            if key not in seen:
                seen.add(key)
                grounds.append(g)

        # 1. Resolve grounds BEFORE creating anything — refuse cleanly on
        # unknown/uncommitted/wrong-type hashes rather than leaving a
        # half-built record.
        repo = NodeRepository()
        resolved: list[tuple[AssessableEntity, str | None]] = []
        for g in grounds:
            try:
                node = repo.find_by_hash(g.hash)
            except Exception as e:
                self._report.ok = False
                self._report.summary = f"Cannot record: ground hash '{g.hash}' — {e}"
                return None
            if node is None:
                self._report.ok = False
                self._report.summary = (
                    f"Cannot record: no node found for ground hash '{g.hash}'."
                )
                return None
            if not isinstance(node, AssessableEntity):
                # The grounds relationship targets AssessableEntity — an edge
                # to anything else (Input, Rationale, ...) would be created
                # but filtered out by every reader (grounds.all() matches
                # Assessable labels), silently diverging from the report.
                self._report.ok = False
                self._report.summary = (
                    f"Cannot record: [[{g.hash}]] is a "
                    f"{node.__class__.__name__} — a decision can rest on "
                    "perspectives, statements, arrangements, or pathways, "
                    "not on this node type."
                )
                return None
            if not node.is_committed:
                # Unreachable via find_by_hash (it matches on hash), kept as
                # belt-and-braces for future resolution paths.
                self._report.ok = False
                self._report.summary = (
                    f"Cannot record: ground [[{g.hash}]] is not committed — "
                    "a decision can only rest on committed nodes."
                )
                return None
            if g.role == "accepted_cost":
                # A price the reader cannot read is worse than no price at all
                # (see _accepted_cost_misplacement). Refused HERE, in step 1,
                # so nothing is half-built and the retry is clean.
                misplacement = self._accepted_cost_misplacement(node)
                if misplacement:
                    self._report.ok = False
                    self._report.summary = f"Cannot record: {misplacement}"
                    return None
            resolved.append((node, g.role))

        # Grounding on an already-discarded node is allowed (the ledger will
        # flag it), but silent acceptance would surprise the agent — warn.
        discarded_grounds = [
            node.short_hash for node, _ in resolved
            if getattr(node, "discarded", None)
        ]

        # 2. The decision itself (atomic commit; committed_at = decided-at).
        decision = Decision(intent=question, stance=stance)
        decision.commit()
        self._report.node_created(decision, patch={"stance": stance, "intent": question})

        # 3+4. Rationale + grounds. The decision is already committed (each
        # GQLAlchemy write autocommits — no transaction to roll back), so a
        # transient failure here must not swallow the report: the LLM needs
        # the decision_hash to repair the record (re-record or discard), not
        # a raw exception hiding that a Decision now exists.
        attach_failures: list[str] = []
        try:
            # The distilled why: a Rationale carrying the confirming
            # principal's provenance (see resolve() docstring).
            why = Rationale(text=rationale)
            why.agent = principal  # overwrite the auto-filled model identifier
            why.set_explanation_target(decision)
            why.commit()  # auto-connects EXPLAINS
            self._report.node_created(why, patch={"agent": principal})
            self._report.relationship_created(why.explains, why, decision)
        except Exception as e:
            attach_failures.append(f"rationale not attached ({e})")

        attached: list[tuple[AssessableEntity, str | None]] = []
        for node, role in resolved:
            try:
                decision.grounds.connect(
                    node, relationship=GroundedInRelationship(role=role)
                )
                self._report.relationship_created(
                    decision.grounds, decision, node,
                    patch={"role": role} if role else None,
                )
                attached.append((node, role))
            except Exception as e:
                attach_failures.append(
                    f"ground [[{node.short_hash}]] not attached ({e})"
                )

        # 5. Coherence review — non-blocking flag (PerspectiveValidation pattern).
        # Guarded here too: no failure mode of the check may block the record.
        # Judged against ATTACHED grounds only — the persisted verdict must
        # describe the record as it exists in the graph, not as proposed —
        # plus the prices those grounds carried and the record did NOT cite,
        # which the attached list cannot express (see _unpriced_aspects).
        try:
            checker = DecisionCoherenceCheck()
            verdict = await checker.resolve(
                decision=decision,
                grounds=attached,
                rationale=rationale,
                unpriced=self._unpriced_aspects(attached),
            )
        except Exception:
            verdict = None
        if verdict is not None:
            # The verdict is worth reporting even if PERSISTING it fails: the
            # decision is already committed, and this `save()` is the one write
            # in the method that runs after an `await` — so a DB fault here
            # would otherwise take the whole record's report down with it and
            # leave the caller believing nothing was written. `claim2-weak-r11`
            # lost a decision to a bare `GQLAlchemyError` on this path with no
            # message recorded; whatever its cause, the annotation is metadata
            # and must never outrank the record.
            self._report.artifacts["coherence"] = {
                "passed": verdict.passed,
                "reasons": verdict.reasons,
                "conflicting_decision_hashes": verdict.conflicting_decision_hashes,
            }
            decision.validation = (
                "passed" if verdict.passed else f"failed: {'; '.join(verdict.reasons)}"
            )
            try:
                decision.save()
                self._report.node_updated(
                    decision, patch={"validation": decision.validation}
                )
            except Exception as e:
                attach_failures.append(f"coherence verdict not persisted ({e})")

        self._report.ok = True
        self._report.summary = f"Recorded decision [[{decision.short_hash}]]: {decision}"
        if discarded_grounds:
            refs = ", ".join(f"[[{h}]]" for h in discarded_grounds)
            self._report.summary += (
                f" — note: ground(s) {refs} are already discarded and will "
                "render flagged in the ledger."
            )
        if attach_failures:
            self._report.summary += (
                " — INCOMPLETE: " + "; ".join(attach_failures) +
                ". The decision node exists; repair or discard it."
            )
            self._report.artifacts["attach_failures"] = attach_failures
        self._report.artifacts["decision_hash"] = decision.short_hash
        if attached:
            # Authoritative final state: only grounds that actually connected.
            self._report.artifacts["grounds"] = [
                {"hash": node.short_hash, "role": role} for node, role in attached
            ]
        return decision.hash

    @classmethod
    def _accepted_cost_misplacement(cls, node: AssessableEntity) -> str | None:
        """Why `node` cannot be an `accepted_cost`, or None if it can be.

        The role has been documented as "the CHOSEN side's minus" in five places
        (`GroundedInRelationship`, `GroundLink.role`, `GRAPH_SCHEMA`,
        `_TOOL_DOCS["record_decision"]`, `_DECISION_READINESS`) and enforced in
        none, so the concern attached whatever hash the model handed it. Twice
        measured: one bench round recorded EVERY `accepted_cost` on the
        Perspective — the tension rather than its price, which is why
        `claim2-weak-r5` rendered no condition clauses — and another put one on a
        Statement sitting at `T/T-`. Only the framework-derived path
        (`Advisor._accepted_cost_ground`) ever got the position right.

        **Structural half only.** A cost is a minus (Rule 3.1's dialogical
        reading: T− is the risk of what is said, a plus is a goal or an
        obligation), and *that* is decidable by walking the graph. WHICH minus —
        the chosen side's, not the one the choice avoided — needs the stance read
        against the poles, so it stays with `DecisionCoherenceCheck`. This guard
        deliberately accepts either minus rather than reaching for a semantic
        call it cannot make reliably.

        **Refuse, not downgrade.** Attaching the ground with `role=None` was the
        obvious alternative and is wrong: archive-wide, decisions with no
        `accepted_cost` passed 17 of 19 against 68 of 120 with one, so quietly
        dropping the role turns a mis-citation into the cheapest way to clear the
        audit. Refusal costs a turn and keeps the price; the message names the
        candidate hashes so the retry is a substitution, not a re-derivation.
        The ceremony already happened in conversation, so the wording survives
        the refusal — nothing is asked of the person again.

        Fail-OPEN on a repository fault: a confirmed decision must not be lost to
        a lookup that could not run. The audit still sees the ground.
        """
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        cost_edges = {edge for _label, _accessor, edge in COST_POSITIONS}
        try:
            if isinstance(node, Statement):
                found = PerspectiveRepository().find_by_statement(node)
                if any(edge in cost_edges for _pp, edge in found):
                    return None
                held = sorted({edge for _pp, edge in found})
                was = (
                    f"sits at {'/'.join(held)}, not at a price position"
                    if held
                    else "sits at no position in any tension"
                )
                candidates = cls._cost_candidates([pp for pp, _edge in found])
            elif isinstance(node, Perspective):
                was = "is the tension itself, not the price of resolving it"
                candidates = cls._cost_candidates([node])
            else:
                was = f"is a {node.__class__.__name__}, which names no price"
                candidates = []
        except Exception:  # noqa: BLE001 - never lose a confirmed decision to this
            return None

        message = (
            f"ground [[{node.short_hash}]] is marked accepted_cost but {was}. "
            "The accepted cost is the chosen side's overdevelopment — the risk "
            "that side's one-sidedness carries (T- or A-), never a plus and "
            "never the tension as a whole."
        )
        if candidates:
            message += f" Available here: {', '.join(candidates)}."
        message += (
            " Re-record with the risk actually confronted; this node can still "
            "be a plain ground (omit the role)."
        )
        return message

    @staticmethod
    def _cost_candidates(perspectives: list) -> list[str]:
        """`T- [[hash]]` references for the minus aspects of `perspectives`.

        Turns a refusal into a substitution: the model is told which hashes WOULD
        be prices, from the very node it mis-cited. Deduplicated by hash —
        sibling perspectives share most minus aspects (7 of 10, measured live).
        """
        out: list[str] = []
        seen: set[str] = set()
        for pp in perspectives:
            for label, accessor, _edge in COST_POSITIONS:
                try:
                    aspects = getattr(pp, accessor).all()
                except Exception:  # noqa: BLE001 - a hint, never a blocker
                    continue
                for aspect, _rel in aspects:
                    if not aspect.is_committed or aspect.hash in seen:
                        continue
                    seen.add(aspect.hash)
                    out.append(f"{label} [[{aspect.short_hash}]]")
        return out

    @staticmethod
    def _unpriced_aspects(
        attached: list[tuple[AssessableEntity, str | None]],
    ) -> list[tuple[str, str]]:
        """Overdevelopment aspects the cited tensions carry and the record did not.

        `DecisionCoherenceCheck` sees only what was ATTACHED, so a record that
        argues a risk away is caught (check 3) while one merely SILENT about it
        is not — check 2 has no cost to cohere against and skips. Measured
        archive-wide: decisions with no accepted_cost passed 17 of 19 against 68
        of 120 with one, so omitting the price was the reliable way to clear the
        audit. This recovers the prices that WERE available, so check 5 can ask
        why none was paid.

        Reach is deliberately limited to minus aspects hanging off a cited
        Perspective — the only ones the record itself points at. Of 19 priceless
        decisions in the archive, 5 cite a tension (reachable here), 5 cite only
        a pathway, and 9 cite nothing at all; the last 9 are check 2's
        documented exemption and stay exempt. Resolving from scope instead of
        from the citation would reach them and would also fire on decisions
        about an unrelated question, which is the false-positive direction an
        auditor cannot afford (`tests/e2e/probe_rationale_integrity.py`
        --omission reach table).

        Returns (position label, aspect text) pairs, deduplicated by hash —
        sibling perspectives on one polarity share most minus aspects.
        """
        from dialectical_framework.graph.nodes.perspective import Perspective

        # A record that priced its choice at all is not check 5's business, and
        # the guard is structural rather than a negative condition in the
        # prompt: the leftover here would otherwise be the OTHER side's minus —
        # what the choice avoids — and offering it to an auditor invites exactly
        # the category error the `accepted_cost` role was corrected for (asking
        # for the wrong position got remedies recorded as costs in 4 of 6 runs).
        if any(role == "accepted_cost" for _node, role in attached):
            return []

        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for node, _role in attached:
            if not isinstance(node, Perspective):
                continue
            for label, accessor, _edge in COST_POSITIONS:
                try:
                    aspects = getattr(node, accessor).all()
                except Exception:  # noqa: BLE001 - an audit input, never a blocker
                    continue
                # RelationshipManager.all() yields (node, relationship) pairs.
                for aspect, _rel in aspects:
                    if aspect.hash in seen:
                        continue
                    seen.add(aspect.hash)
                    out.append((label, str(aspect)))
        return out
