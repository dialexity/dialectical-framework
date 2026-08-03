"""
RecordDecision: persist a user-confirmed decision as a Decision node.

The recording ceremony (propose, read back, confirm) happens in
conversation BEFORE this concern runs — parameters arrive as literal
confirmed wording, never as instructions to interpret. The concern:

1. Resolves ground hashes (refuses on unknown/uncommitted/non-assessable —
   fail-closed for grounds, since a dangling or reader-invisible ground
   would break the record's value)
2. Commits the Decision (question rides intent, stance frozen in hash)
3. Attaches the distilled why as a Rationale with agent="human"
4. Connects GROUNDED_IN edges with their roles
5. Runs DecisionCoherenceCheck and flags the verdict (fail-soft: a failed
   or errored check NEVER blocks the record — soft gate)

Replacing/retracting a decision is NOT this concern's job — that is the
standard Discard concern (reason like "superseded by [[new_hash]]").
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern


class GroundLink(BaseModel):
    """One grounding reference for a decision."""

    hash: str = Field(
        description="Hash (or unique prefix) of a committed node this "
        "decision rests on — a perspective, statement, wheel, or pathway."
    )
    role: str | None = Field(
        default=None,
        description="Optional semantic role. Seed vocabulary: "
        "'accepted_cost' = the unchosen side's constructive contribution "
        "the person confronted and accepted; 'adopted_pathway' = the "
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
            grounds=[GroundLink(hash="abc123", role="accepted_cost")],
        )
    """

    async def resolve(
        self,
        question: str,
        stance: str,
        rationale: str,
        grounds: list[GroundLink] | None = None,
    ) -> str | None:
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
            # The distilled why: a human-provenance Rationale.
            why = Rationale(text=rationale)
            why.agent = "human"  # overwrite the auto-filled model identifier
            why.set_explanation_target(decision)
            why.commit()  # auto-connects EXPLAINS
            self._report.node_created(why, patch={"agent": "human"})
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
        # describe the record as it exists in the graph, not as proposed.
        try:
            checker = DecisionCoherenceCheck()
            verdict = await checker.resolve(
                decision=decision, grounds=attached, rationale=rationale
            )
        except Exception:
            verdict = None
        if verdict is not None:
            decision.validation = (
                "passed" if verdict.passed else f"failed: {'; '.join(verdict.reasons)}"
            )
            decision.save()
            self._report.node_updated(decision, patch={"validation": decision.validation})
            self._report.artifacts["coherence"] = {
                "passed": verdict.passed,
                "reasons": verdict.reasons,
                "conflicting_decision_hashes": verdict.conflicting_decision_hashes,
            }

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
