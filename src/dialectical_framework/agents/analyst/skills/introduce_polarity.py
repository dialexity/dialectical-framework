"""
IntroducePolarity: Skill for directly introducing a known T-A tension.

When the LLM recognizes a tension in conversation (e.g. "Stay married vs Get divorced"),
this skill introduces both statements into the vocabulary, creates the primary Polarity,
and discovers alternative antitheses for the same thesis.

Flow:
1. Deduplicate thesis and antithesis against vocabulary (reuse or create)
2. Classify thesis + antithesis (get meaning URIs)
3. Run AntithesisClassification to get HS for the primary pair
4. Create primary Polarity node
5. Run AntithesisExtraction to discover alternative antitheses
6. Create additional Polarity nodes for alternatives
7. Return all polarity hashes

Usage:
    skill = IntroducePolarity(thesis="Stay married", antithesis="Get divorced")
    result = await skill.resolve()
    # result.primary_polarity_hash — the tension the LLM identified
    # result.all_polarity_hashes — primary + alternatives
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class IntroducePolarityResult:
    """Result of introducing a polarity."""

    primary_polarity_hash: Optional[str] = None
    all_polarity_hashes: list[str] = field(default_factory=list)
    thesis_hash: Optional[str] = None
    antithesis_hash: Optional[str] = None


class IntroducePolarity(ReasonableConcern[IntroducePolarityResult]):
    """
    Skill for directly introducing a known T-A tension into the graph.

    Deduplicates both statements, classifies them, creates the primary Polarity,
    then discovers alternative antitheses and creates additional Polarities.
    """

    def __init__(self, thesis: str, antithesis: str, text: str = "") -> None:
        self.thesis_text = thesis.strip()
        self.antithesis_text = antithesis.strip()
        self.text = text

    async def resolve(self) -> IntroducePolarityResult:
        """Introduce a T-A tension and discover alternatives."""

        if not self.thesis_text or not self.antithesis_text:
            self._report.ok = False
            self._report.summary = "Both thesis and antithesis text are required"
            return IntroducePolarityResult()

        input_text = await self._get_input_text()
        context = f"{input_text}\n\n{self.text}".strip() if self.text else input_text

        # 1. Create or find thesis Statement
        thesis_stmt = await self._resolve_statement(self.thesis_text, context)

        # 2. Create or find antithesis Statement
        antithesis_stmt = await self._resolve_statement(self.antithesis_text, context)

        # 3. Connect OPPOSITE_OF
        thesis_stmt.oppositions.connect(antithesis_stmt)
        self._report.relationship_created(
            thesis_stmt.oppositions, thesis_stmt, antithesis_stmt
        )

        # 4. Classify the antithesis against the thesis (get HS)
        classifier = AntithesisClassification()
        classification = await classifier.resolve(
            thesis=thesis_stmt,
            antithesis_statement=antithesis_stmt.text,
            text=context,
        )
        self._report = self._report.merge(classifier.report)

        # 5. Create primary Polarity
        pol_repo = PolarityRepository()
        existing_pols = pol_repo.find_by_tension(thesis_stmt, antithesis_stmt)

        if existing_pols:
            primary_polarity = existing_pols[0]
            self._report.artifacts["primary_polarity_source"] = "existing"
        else:
            primary_polarity = Polarity()
            primary_polarity.set_t(thesis_stmt, heuristic_similarity=1.0)
            primary_polarity.set_a(
                antithesis_stmt,
                heuristic_similarity=classification.heuristic_similarity,
            )
            primary_polarity.commit()
            self._report.node_created(primary_polarity)
            self._report.relationship_created(
                primary_polarity.t, thesis_stmt, primary_polarity,
                patch={"heuristic_similarity": 1.0, "alias": "T"},
            )
            self._report.relationship_created(
                primary_polarity.a, antithesis_stmt, primary_polarity,
                patch={"heuristic_similarity": classification.heuristic_similarity, "alias": "A"},
            )
            self._report.artifacts["primary_polarity_source"] = "created"

        all_polarity_hashes = [primary_polarity.hash]

        # 6. Discover alternative antitheses
        vocab = StatementRepository().get_vocabulary_with_rationales()
        not_like_these = [antithesis_stmt.prompt_text]
        not_like_these.extend(c["statement"] for c in vocab)

        extractor = AntithesisExtraction()
        alternatives = await extractor.resolve(
            thesis=thesis_stmt,
            text=context,
            not_like_these=not_like_these,
        )
        self._report = self._report.merge(extractor.report)

        # 7. Deduplicate alternatives against vocabulary
        alt_hashes = [a.component.hash for a in alternatives if a.component.hash]
        if alt_hashes and vocab:
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.resolve(
                extracted_hashes=alt_hashes,
                vocabulary=vocab,
                text=context,
            )
            self._report = self._report.merge(deduplicator.report)

            # Apply replacements
            hash_to_replacement = dedup_result.replacements
            for alt in alternatives:
                if alt.component.hash in hash_to_replacement:
                    alt.component = hash_to_replacement[alt.component.hash]

        # 8. Create Polarity nodes for alternatives
        for alt in alternatives:
            alt_stmt = alt.component

            # Connect OPPOSITE_OF
            thesis_stmt.oppositions.connect(alt_stmt)
            self._report.relationship_created(
                thesis_stmt.oppositions, thesis_stmt, alt_stmt
            )

            # Check if Polarity already exists
            existing = pol_repo.find_by_tension(thesis_stmt, alt_stmt)
            if existing:
                all_polarity_hashes.append(existing[0].hash)
                continue

            alt_polarity = Polarity()
            alt_polarity.set_t(thesis_stmt, heuristic_similarity=1.0)
            alt_polarity.set_a(alt_stmt, heuristic_similarity=alt.heuristic_similarity)
            alt_polarity.commit()
            self._report.node_created(alt_polarity)
            self._report.relationship_created(
                alt_polarity.t, thesis_stmt, alt_polarity,
                patch={"heuristic_similarity": 1.0, "alias": "T"},
            )
            self._report.relationship_created(
                alt_polarity.a, alt_stmt, alt_polarity,
                patch={"heuristic_similarity": alt.heuristic_similarity, "alias": "A"},
            )
            all_polarity_hashes.append(alt_polarity.hash)

        # Build result
        result = IntroducePolarityResult(
            primary_polarity_hash=primary_polarity.hash,
            all_polarity_hashes=all_polarity_hashes,
            thesis_hash=thesis_stmt.hash,
            antithesis_hash=antithesis_stmt.hash,
        )

        self._report.ok = True
        self._report.artifacts["primary_polarity_hash"] = primary_polarity.hash
        self._report.artifacts["all_polarity_hashes"] = all_polarity_hashes
        self._report.artifacts["thesis_hash"] = thesis_stmt.hash
        self._report.artifacts["antithesis_hash"] = antithesis_stmt.hash
        self._report.artifacts["alternative_count"] = len(alternatives)
        self._report.artifacts["polarities"] = [
            {
                "polarity_hash": all_polarity_hashes[0],
                "thesis_text": thesis_stmt.text,
                "antithesis_text": antithesis_stmt.text,
                "is_primary": True,
            }
        ] + [
            {
                "polarity_hash": all_polarity_hashes[i + 1] if (i + 1) < len(all_polarity_hashes) else None,
                "thesis_text": thesis_stmt.text,
                "antithesis_text": alt.component.text,
                "is_primary": False,
            }
            for i, alt in enumerate(alternatives)
        ]
        self._report.summary = (
            f"Introduced polarity: {len(all_polarity_hashes)} total "
            f"(1 primary + {len(alternatives)} alternatives)"
        )

        return result

    async def _resolve_statement(self, text: str, context: str) -> Statement:
        """Classify and commit a Statement. Commit is an upsert — same text reuses existing node."""
        classifier = StatementClassification()
        result = await classifier.resolve(statement=text, text=context)
        self._report = self._report.merge(classifier.report)

        stmt = Statement(text=result.statement, meaning=result.meaning)
        stmt.commit()
        self._report.node_created(stmt)

        classification_label = "SIMPLE" if result.is_simple else "COMPLEX"
        rationale_text = (
            f"Classification: {classification_label}. {result.classification_reasoning}"
        )
        if result.taxonomy_reasoning:
            rationale_text += f" {result.taxonomy_reasoning}"

        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(stmt)
        rationale.commit()
        self._report.node_created(rationale)

        return stmt

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from all inputs in scope."""
        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)


@llm.tool
async def introduce_polarity(
    thesis: Annotated[str, Field(description="The thesis statement text")],
    antithesis: Annotated[str, Field(description="The antithesis statement text")],
    text: Annotated[str, Field(description="Additional context for classification")] = "",
) -> str:
    """Introduce a known thesis-antithesis tension directly as a Polarity. Classifies both statements, creates the Polarity node (T-A pair), and discovers alternative antitheses. Use when the tension is already clear from conversation rather than needing extraction from source material."""
    concern = IntroducePolarity(thesis=thesis, antithesis=antithesis, text=text)
    await concern.resolve()
    return str(concern.report)
