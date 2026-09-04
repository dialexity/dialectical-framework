"""
SurfaceTheses: Extracts theses from inputs for AnalystAgent (Phase 1 of polarity-finder).

Extraction-only — does NOT anchor literal concepts (use AnchorTheses for that).

Flow:
1. Get input text (required — returns None if no inputs)
2. Parse intent → extraction parameters (count, focus, domain_hint)
3. Extract fresh theses via ThesisExtraction — one pass with retries on
   different params when the source fits a prompt, a window-by-window SWEEP
   when it does not (`_extraction_sweep`)
4. Semantic dedup against existing vocabulary
5. Create Ideas with final set

Usage:
    skill = SurfaceTheses(intent="extract 3 theses about trust")
    ideas = await skill.resolve()
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository
from dialectical_framework.utils.chunking import chunk_text

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


#: Windows extracted from concurrently when a source is swept. A module constant,
#: not a setting, per "Policy is not config".
#:
#: Deliberately lower than `SourceDigest`'s cap: each window is itself a fan-out
#: (step 2 of `ThesisExtraction` issues one call per content item, up to
#: `count + 2`), so the calls actually in flight are roughly this times six. Same
#: underlying reason for having a cap at all — the width comes from the size of a
#: file somebody pasted, not from graph structure the framework produced.
MAX_CONCURRENT_WINDOW_SWEEPS = 3


# --- System Prompt ---

SYSTEM_PROMPT = """You are an extraction agent for dialectical analysis.

Your task is to parse extraction instructions into structured parameters for thesis extraction from inputs.

When parsing intent:
- Extract count, focus, constraints, domain hints
- The intent describes WHAT to extract from the available inputs
- Do not treat the intent itself as a thesis — it is extraction guidance"""


# --- DTOs for LLM structured outputs ---


class ParsedIntentDto(BaseModel):
    """Result of parsing the extraction intent."""

    count: int = Field(default=3, description="Number of theses to extract (1-10)")
    constraints: list[str] = Field(
        default_factory=list,
        description="Things to avoid (e.g., 'not about security', 'exclude X')",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Preferences (e.g., 'prefer existing', 'focus on Y')",
    )
    domain_hint: str = Field(
        default="",
        description="Contextual domain hint derived from intent/inputs (e.g., 'software architecture', 'interpersonal relationships', 'organizational dynamics')",
    )
    focus: str = Field(
        default="",
        description="Topic focus for extraction",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of how intent was interpreted",
    )


# --- Main Agent ---


class SurfaceTheses(ReasonableConcern[Optional[Ideas]]):
    """
    Extracts theses from inputs for AnalystAgent.

    Requires inputs in scope — returns None if no inputs available.
    For anchoring literal concepts, use AnchorTheses instead.

    Flow:
    1. Gets input text (required)
    2. Parses extraction intent (count, focus, domain_hint, constraints)
    3. Extracts fresh theses via ThesisExtraction (retries on a source that
       fits one prompt; a sweep over overlapping windows on one that does not)
    4. Deduplicates against existing vocabulary (prefers DB versions)
    5. Creates Ideas node with final component set
    """

    def __init__(self, intent: str, input_hashes: list[str] | None = None) -> None:
        self.intent = intent
        self.input_hashes = input_hashes
        self._conversation: Optional[ConversationFacilitator] = None

    async def resolve(self) -> Optional[Ideas]:
        """Extract theses from inputs. Returns Ideas container or None if no inputs."""
        # 1. Get input text — required for extraction
        input_text = await self._get_input_text()
        if not input_text:
            # Two different situations, and conflating them is what made the
            # `find_by_hashes` prefix bug invisible for so long. An empty scope
            # is a legitimate no-op the caller should shrug at; being handed
            # hashes that resolve to nothing is a failure, and reporting it as
            # `ok=True` let `AnalysisPipeline` go on to tell the model "no
            # tensions extracted — anchor a position instead of ingesting",
            # i.e. to blame the material and stop using the tool.
            self._report.artifacts["thesis_hashes"] = []
            if self.input_hashes:
                self._report.ok = False
                self._report.summary = (
                    f"None of the {len(self.input_hashes)} requested input hash(es) "
                    f"resolved to an input in scope: {', '.join(self.input_hashes)}"
                )
            else:
                self._report.ok = True
                self._report.summary = "No inputs in scope for extraction"
            return None

        # 2. Parse extraction intent
        self._conversation = ConversationFacilitator()
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        parsed = await self._parse_intent()

        # 3. Get existing vocabulary for dedup
        comp_repo = StatementRepository()
        vocab = comp_repo.get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        # 4. Extraction — one pass if the source fits a prompt, a sweep if not
        windows = chunk_text(input_text)
        self._report.artifacts["source_windows"] = len(windows)
        if len(windows) > 1:
            extracted_components, extraction_reports = await self._extraction_sweep(
                windows=windows,
                parsed=parsed,
                target_count=parsed.count,
                not_like_these=not_like_these,
            )
        else:
            extracted_components, extraction_reports = await self._extraction_loop(
                input_text=input_text,
                parsed=parsed,
                target_count=parsed.count,
                not_like_these=not_like_these,
            )
        for r in extraction_reports:
            self._report = self._report.merge(r)

        if not extracted_components:
            self._report.ok = True
            self._report.summary = "No theses extracted"
            self._report.artifacts["thesis_hashes"] = []
            return None

        # 5. Semantic dedup
        deduped: list[Statement] = []
        deleted_count = 0

        if vocab and extracted_components:
            extracted_hashes = [c.hash for c in extracted_components]
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.resolve(
                extracted_hashes=extracted_hashes,
                vocabulary=vocab,
                text=input_text,
            )
            self._report = self._report.merge(deduplicator.report)
            deleted_count = dedup_result.deleted_count
            deduped = dedup_result.components
        else:
            deduped = extracted_components

        # 6. Create Ideas
        ideas = self._create_ideas(deduped, parsed)

        # 7. Build final artifacts
        self._report.artifacts["thesis_hashes"] = [c.hash for c in deduped]
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["extracted_theses_count"] = len(extracted_components)
        self._report.artifacts["duplicates_found_and_deleted"] = deleted_count
        self._report.artifacts["theses"] = [
            {"hash": c.hash, "text": c.text} for c in deduped
        ]
        self._report.summary = f"Extracted {len(deduped)} thesis(es)"

        return ideas

    # --- Intent Parsing ---

    def _parse_intent_prompt(self, input_preview: str) -> str:
        """Build user prompt for parsing extraction intent."""
        return f"""Parse this extraction intent into structured parameters.

**Intent:** {self.intent}

**Available inputs preview:** {input_preview}

Determine:

1. **count**: Number of theses to extract.
   - If a number is specified in intent (e.g., "3 theses" → count: 3), use it
   - Otherwise default to 3
2. **constraints**: What to avoid or exclude
3. **preferences**: What to prefer (e.g., "prefer existing", "focus on X")
4. **domain_hint**: Derive a contextual domain hint from intent and inputs
5. **focus**: Topic/theme to focus extraction on"""

    async def _parse_intent(self) -> ParsedIntentDto:
        """Parse unstructured intent into structured parameters."""
        input_previews = await self._get_input_previews()

        result = await self._conversation.submit(
            response_model=ParsedIntentDto,
            user_content=self._parse_intent_prompt(input_previews),
        )

        result.count = max(1, min(result.count, 10))
        return result

    # --- Extraction Loop ---

    async def _extraction_loop(
        self,
        input_text: str,
        parsed: ParsedIntentDto,
        target_count: int,
        not_like_these: list[str],
    ) -> tuple[list[Statement], list[ExecutionReport]]:
        """
        Extract theses with retries on different parameters.

        Args:
            input_text: Text to extract from
            parsed: Parsed intent (for focus, domain_hint)
            target_count: Number of theses to extract (accounts for direct theses already added)
            not_like_these: Statements to avoid

        Returns tuple of (extracted components, reports).
        """
        extracted_components: list[Statement] = []
        reports: list[ExecutionReport] = []
        max_attempts = 4

        # Build parameter variations to try
        param_variations = self._build_param_variations(parsed)

        for attempt, params in enumerate(param_variations[:max_attempts]):
            if len(extracted_components) >= target_count:
                break

            # How many more do we need?
            remaining = target_count - len(extracted_components)

            service = ThesisExtraction()
            new_components = await service.resolve(
                text=input_text,
                count=remaining,
                focus=params.get("focus", ""),
                domain_hint=params.get("domain_hint", ""),
                not_like_these=not_like_these + [c.text for c in extracted_components],
            )
            reports.append(service.report)

            extracted_components.extend(new_components)

            # Update not_like_these for next iteration
            for comp in new_components:
                if comp.text not in not_like_these:
                    not_like_these.append(comp.text)

        return extracted_components[:target_count], reports

    async def _extraction_sweep(
        self,
        windows: list[str],
        parsed: ParsedIntentDto,
        target_count: int,
        not_like_these: list[str],
    ) -> tuple[list[Statement], list[ExecutionReport]]:
        """Extract from a source too long for one prompt: sweep, merge, classify.

        `_extraction_loop` hands the WHOLE concatenated source to
        `ThesisExtraction` up to four times. That is the last of the three
        unbounded raw-content paths and by far the worst, because the cost is
        multiplied twice over: `_step2_identify_candidates` fans out one call per
        content item through `self._conversation.isolate()`, which COPIES the
        message history — and that history is step 1's prompt, i.e. the entire
        source. So one `ThesisExtraction` is ~7 full-source sends, and four
        attempts plus the deduplication pass is ~29. At 1.2 MB (~300k tokens)
        that is millions of tokens, or a context-limit failure before any of it.

        Why a sweep and not retrieval: extraction has NO query. The theses are
        the thing being looked for, so selecting top-k against the intent string
        would return what the intent already anticipated and miss the tensions
        nobody thought to ask about — which is the framework's whole job. Every
        window must therefore be read.

        Candidates only, in one pass over the windows: `extract_candidates`
        writes nothing, so the merge happens on strings and only the survivors
        become Statements. Sweeping with the full `resolve()` instead would
        commit a Statement plus a Rationale per candidate per window and rely on
        deduplication to delete most of them again.
        """
        reports: list[ExecutionReport] = []

        candidates = await self._sweep_windows(
            windows=windows,
            focus=parsed.focus,
            target_count=target_count,
            not_like_these=not_like_these,
            reports=reports,
        )

        # A sweep with a focus has already looked everywhere, so under-delivery
        # means the material does not hold what was asked for — re-sweeping
        # under `_build_param_variations` would re-read the whole document up to
        # three more times to reconsider material the first pass saw and
        # declined. The ZERO case is different: it is the shape of a focus that
        # excluded everything, or of the step-2 gate over-rejecting, so it earns
        # exactly one broader sweep with no focus at all.
        if not candidates and parsed.focus:
            self._report.artifacts["sweep_retried_without_focus"] = True
            candidates = await self._sweep_windows(
                windows=windows,
                focus="",
                target_count=target_count,
                not_like_these=not_like_these,
                reports=reports,
            )

        self._report.artifacts["swept_candidate_count"] = len(candidates)
        if not candidates:
            return [], reports

        # Classify only the survivors, each against the window it came from.
        selected = candidates[:target_count]
        classifier = ThesisExtraction()
        components = await classifier.classify_candidates(
            selected, domain_hint=parsed.domain_hint
        )
        reports.append(classifier.report)

        return components, reports

    async def _sweep_windows(
        self,
        windows: list[str],
        focus: str,
        target_count: int,
        not_like_these: list[str],
        reports: list[ExecutionReport],
    ) -> list[tuple[str, str]]:
        """One `extract_candidates` per window, merged into `(candidate, window)`.

        Windows run concurrently and therefore cannot see each other's results,
        so `not_like_these` cannot grow across them the way it does across the
        sequential attempts in `_extraction_loop`. Two windows restating the same
        claim is expected rather than avoided, and is what the merge below plus
        `StatementDeduplication` are for — the alternative, sweeping windows
        serially to thread the exclusion list, would make a 30-window source 30
        round-trips deep.
        """
        # Bounded for the same reason `SourceDigest`'s fan-out is: the width here
        # is the size of a file somebody pasted. Lower than the digest's cap
        # because each window is itself a fan-out — step 2 issues one call per
        # content item — so the real in-flight count is a multiple of this.
        slots = asyncio.Semaphore(MAX_CONCURRENT_WINDOW_SWEEPS)

        async def _sweep_one(window: str) -> tuple[list[str], ExecutionReport]:
            async with slots:
                service = ThesisExtraction()
                found = await service.extract_candidates(
                    text=window,
                    count=target_count,
                    focus=focus,
                    not_like_these=not_like_these,
                )
                return found, service.report

        results = await asyncio.gather(*[_sweep_one(w) for w in windows])

        # Merged in document order — `gather` preserves argument order — and
        # deduplicated on normalised text, so the same claim surfacing in two
        # overlapping windows costs one classification rather than two. Exact
        # matching only; semantic near-duplicates are `StatementDeduplication`'s
        # job and it runs later with the vocabulary to compare against.
        merged: list[tuple[str, str]] = []
        seen: set[str] = set()
        for window, (found, report) in zip(windows, results):
            reports.append(report)
            for candidate in found:
                key = " ".join(candidate.lower().split())
                if key and key not in seen:
                    seen.add(key)
                    merged.append((candidate, window))

        return merged

    def _build_param_variations(self, parsed: ParsedIntentDto) -> list[dict]:
        """Build list of parameter variations to try."""
        variations = []

        # First: use parsed parameters
        variations.append(
            {
                "domain_hint": parsed.domain_hint,
                "focus": parsed.focus,
            }
        )

        # Second: try without focus (broader extraction)
        if parsed.focus:
            variations.append(
                {
                    "domain_hint": parsed.domain_hint,
                    "focus": "",
                }
            )

        # Third: try without domain hint
        if parsed.domain_hint:
            variations.append(
                {
                    "domain_hint": "",
                    "focus": parsed.focus,
                }
            )

        # Fourth: no hints at all (broadest)
        variations.append(
            {
                "domain_hint": "",
                "focus": "",
            }
        )

        return variations

    def _get_statement_by_hash(self, hash: str) -> str:
        """Get statement text for a component by hash."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if comp and isinstance(comp, Statement):
                return comp.text
        except ValueError:
            pass
        return ""

    # --- Helpers ---

    def _get_inputs(self) -> list:
        """Get inputs: filtered by input_hashes if provided, otherwise all in scope.

        A partial miss is recorded rather than raised: extracting from the two
        inputs that resolved beats refusing because a third went away. The
        TOTAL miss is handled in `resolve()`, where it fails the report.

        `inputs_read` is recorded because "no material was there" and "the
        material yielded no tensions" call for opposite advice, and only this
        method can tell them apart.
        """
        if self.input_hashes:
            from dialectical_framework.graph.nodes.input import Input

            repo = NodeRepository()
            inputs = repo.find_by_hashes(self.input_hashes, node_type=Input)
            unresolved = len(self.input_hashes) - len(inputs)
            if inputs and unresolved > 0:
                self._report.artifacts["unresolved_input_hashes"] = unresolved
        else:
            inputs = InputRepository().get_all()

        self._report.artifacts["inputs_read"] = len(inputs)
        return inputs

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from inputs (filtered by input_hashes if provided)."""
        inputs = self._get_inputs()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)

    @inject
    async def _get_input_previews(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get preview of each input (uses digest if available, else first 500 chars)."""
        inputs = self._get_inputs()

        if not inputs:
            return "No inputs"

        previews = []
        for i, input_node in enumerate(inputs, 1):
            if input_node.digest:
                previews.append(f"[Input {i}]\n{input_node.digest}")
            else:
                resolved = await input_resolver.resolve(input_node)
                preview = resolved[:500] + "..." if len(resolved) > 500 else resolved
                previews.append(f"[Input {i}]\n{preview}")

        return "\n\n".join(previews)

    def _resolve_component(self, hash: str) -> Optional[Statement]:
        """Resolve hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if isinstance(comp, Statement):
                return comp
        except ValueError:
            pass
        return None

    def _resolve_components(self, hashes: list[str]) -> list[Statement]:
        """Resolve list of hashes to components."""
        return [c for h in hashes if (c := self._resolve_component(h))]

    def _create_ideas(
        self,
        components: list[Statement],
        parsed: ParsedIntentDto,
    ) -> Optional[Ideas]:
        """Create Ideas node and wire to components and inputs. Records effects in self._report."""
        if not components:
            return None

        ideas = Ideas(intent=self.intent)
        ideas.save()
        self._report.node_created(ideas)

        # Connect to inputs (filtered or all)
        for input_node in self._get_inputs():
            ideas.inputs.connect(input_node)
            self._report.relationship_created(ideas.inputs, ideas, input_node)

        # Connect to components
        for comp in components:
            ideas.statements.connect(comp)
            self._report.relationship_created(ideas.statements, ideas, comp)

        ideas.commit()
        self._report.node_committed(ideas)

        # Attach rationale explaining how intent was interpreted
        if parsed.reasoning:
            rationale = Rationale(text=parsed.reasoning)
            rationale.set_explanation_target(ideas)
            rationale.commit()
            self._report.node_created(rationale)
            self._report.relationship_created(
                rationale.explains,
                rationale,
                ideas,
            )

        return ideas


@llm.tool
async def surface_theses(
    intent: Annotated[
        str,
        Field(
            description="Extraction instructions — e.g. 'extract 3 theses about trust', 'find themes in the inputs', 'surface theses about security'"
        ),
    ],
    input_hashes: Annotated[
        list[str] | None,
        Field(
            description="Optional list of input hashes to process selectively. If None, processes all inputs in scope."
        ),
    ] = None,
) -> str:
    """Extract theses from inputs. Requires inputs in scope — returns empty if none.
    For anchoring named concepts directly, use anchor_theses instead.

    Examples: 'extract 5 theses about trust and integrity',
    'find theses from inputs, prefer existing ones if suitable',
    'surface 3 new theses about security, avoid anything about performance'
    """
    concern = SurfaceTheses(intent=intent, input_hashes=input_hashes)
    await concern.resolve()
    return str(concern.report)
