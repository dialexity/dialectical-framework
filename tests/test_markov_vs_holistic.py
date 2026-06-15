"""
Empirical comparison: Markov (pairwise composition) vs holistic cycle causality estimation.

This test scores atomic directed links (A→B) and composes them into cycle scores,
then compares against the existing holistic estimator that assesses each cycle as a whole.

Purpose: determine if we can save exponential LLM calls by scoring only N*(N-1) directed
pairs instead of all cycles at every layer.

FINDINGS (2026-06-15, Haiku 4.5 via Bedrock):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Markov composition does NOT preserve holistic cycle rankings.

  Spearman ρ (product):  0.000
  Spearman ρ (geomean):  0.250
  Top-cycle agreement:   ✗ (different top cycle for both methods)

Why it fails:
  - Holistic scores cluster tightly (0.75–0.78) — the LLM sees the circular system
    as a self-reinforcing whole, not a chain of independent steps.
  - Markov scores vary widely (0.25–0.64) — asymmetric pairwise links
    (e.g., A→B=0.85 but B→A=0.35) get amplified by multiplication.
  - A weak individual link can still participate in a strong circular system;
    holistic assessment captures this, pairwise composition does not.

Conclusion: keep holistic per-cycle estimation. The LLM calls are not redundant —
each cycle layer assesses a genuinely different circular dynamic.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run with: poetry run pytest tests/test_markov_vs_holistic.py --real-llm -v -s
"""

from __future__ import annotations

import asyncio
from itertools import combinations, permutations

import pytest
from conftest import traced
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.concerns.causality.causality_estimator_balanced import (
    CausalityEstimatorBalanced,
)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.use_brain import use_brain

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.skip(reason="Research test — findings documented above. Re-run manually to re-validate."),
]

SITUATION_TEXT = """
Our company is growing from 50 to 200 people in the next year. The founders built
the culture through daily interaction — everyone knew everyone, decisions were fast,
context was shared implicitly. Now we're hiring aggressively and new people don't
have that shared context. The veterans feel like the culture is diluting. The new
hires feel excluded from an implicit old-guard network. We need to scale but we
can't lose what made us great.
"""


class DirectedLinkAssessmentDto(BaseModel):
    probability: float = Field(
        description="Probability (0-1) of the causal link from source to target."
    )
    reasoning: str = Field(
        default="", description="Brief explanation of why this link is plausible or not."
    )


async def estimate_directed_link(
    source: Statement, target: Statement, source_text: str
) -> float:
    """Estimate probability of a single directed causal link: source → target."""

    @use_brain(format=DirectedLinkAssessmentDto)
    async def _call() -> list:
        tpl: list = []
        if source_text:
            tpl.extend([
                llm.messages.user(
                    f"Consider the following text as the initial context:\n\n"
                    f"<context>{source_text}</context>"
                ),
                llm.messages.assistant("OK, let's start.", model_id=None, provider_id=None),
            ])
        tpl.append(llm.messages.user(
            f"Assess the plausibility of the following ONE-WAY causal link:\n\n"
            f'"{source.prompt_text}" --> "{target.prompt_text}"\n\n'
            f"This is NOT a circular sequence. Assess ONLY the one-directional relationship:\n"
            f'"How plausible is it that the first concept leads to / causes / enables the second?"\n\n'
            f"<instructions>\n"
            f"1) Estimate probability (0 to 1) considering realism, desirability, and feasibility\n"
            f"2) Briefly explain why this causal direction is or isn't plausible\n"
            f"</instructions>"
        ))
        return tpl

    result: DirectedLinkAssessmentDto = await _call()
    return result.probability


def markov_product(link_scores: list[float]) -> float:
    result = 1.0
    for s in link_scores:
        result *= s
    return result


def markov_geometric_mean(link_scores: list[float]) -> float:
    product = markov_product(link_scores)
    return product ** (1.0 / len(link_scores)) if link_scores else 0.0


def spearman_rank_correlation(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation without scipy."""
    n = len(x)
    if n < 3:
        return float("nan")

    def _rank(values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda t: t[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rank_x = _rank(x)
    rank_y = _rank(y)
    d_sq = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
    return 1 - (6 * d_sq) / (n * (n**2 - 1))


def extract_directed_links(cycle: Cycle) -> list[tuple[str, str]]:
    """Extract directed (source_hash, target_hash) pairs from a cycle's PP order."""
    hashes = cycle.perspective_hashes
    n = len(hashes)
    return [(hashes[i], hashes[(i + 1) % n]) for i in range(n)]


class TestMarkovVsHolistic:

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    @traced
    async def test_markov_approximation_quality(self):
        """Compare Markov pairwise composition vs holistic cycle scoring."""
        case = Case()
        case.commit()

        with scope(case.sid):
            # Step 1: Get real Perspectives
            analyst = AnalysisPipeline(
                text=SITUATION_TEXT,
                intent="find 3 distinct tensions about scaling company culture",
            )
            analysis = await analyst.resolve()

            if len(analysis.perspective_hashes) < 3:
                pytest.skip(
                    f"Need 3+ perspectives, got {len(analysis.perspective_hashes)}"
                )

            repo = NodeRepository()

            # Filter out near-duplicate theses (same prompt_text)
            seen_texts: set[str] = set()
            unique_hashes: list[str] = []
            for h in analysis.perspective_hashes:
                pp = repo.find_by_hash(h, node_type=Perspective)
                if pp:
                    t_result = pp.t.get()
                    if t_result:
                        text = t_result[0].prompt_text
                        if text not in seen_texts:
                            seen_texts.add(text)
                            unique_hashes.append(h)
            if len(unique_hashes) < 3:
                pytest.skip(
                    f"Need 3+ unique perspectives, got {len(unique_hashes)}"
                )
            perspectives: list[Perspective] = []
            for h in unique_hashes[:3]:
                pp = repo.find_by_hash(h, node_type=Perspective)
                assert pp is not None
                perspectives.append(pp)

            # Get T (thesis) statements for directed link scoring
            t_statements: dict[str, Statement] = {}
            for pp in perspectives:
                t_result = pp.t.get()
                assert t_result, f"PP {pp.short_hash} has no thesis"
                t_statements[pp.hash] = t_result[0]

            print("\n" + "=" * 70)
            print("MARKOV vs HOLISTIC COMPARISON")
            print("=" * 70)
            print(f"\nPerspectives ({len(perspectives)}):")
            for pp in perspectives:
                t = t_statements[pp.hash]
                print(f"  [{pp.short_hash}] T: {t.prompt_text[:80]}...")

            # Step 2: Score all directed links in parallel
            print(f"\n--- Directed Link Estimation ({len(perspectives) * (len(perspectives) - 1)} links) ---")

            link_tasks = []
            link_keys = []
            for src_pp in perspectives:
                for tgt_pp in perspectives:
                    if src_pp.hash != tgt_pp.hash:
                        link_keys.append((src_pp.hash, tgt_pp.hash))
                        link_tasks.append(
                            estimate_directed_link(
                                t_statements[src_pp.hash],
                                t_statements[tgt_pp.hash],
                                SITUATION_TEXT,
                            )
                        )

            link_results = await asyncio.gather(*link_tasks)
            directed_scores: dict[tuple[str, str], float] = dict(
                zip(link_keys, link_results)
            )

            for (src_h, tgt_h), score in directed_scores.items():
                src_pp = next(p for p in perspectives if p.hash == src_h)
                tgt_pp = next(p for p in perspectives if p.hash == tgt_h)
                print(f"  {src_pp.short_hash} → {tgt_pp.short_hash}: {score:.3f}")

            # Step 3: Build cycles
            cycles: list[Cycle] = []

            # 2-PP cycles: one per pair (first-element-fixed = 1 permutation)
            for pp_a, pp_b in combinations(perspectives, 2):
                cycle = Cycle(intent="preset:balanced")
                cycle.set_perspectives([pp_a, pp_b])
                cycle.commit()
                cycles.append(cycle)

            # 3-PP cycles: (3-1)! = 2 permutations (first fixed, permute rest)
            first_pp = perspectives[0]
            for perm in permutations(perspectives[1:]):
                cycle = Cycle(intent="preset:balanced")
                cycle.set_perspectives([first_pp, *perm])
                cycle.commit()
                cycles.append(cycle)

            # Step 4: Holistic estimation
            print(f"\n--- Holistic Estimation ({len(cycles)} cycles) ---")
            estimator = CausalityEstimatorBalanced()
            holistic_results = await estimator.estimate(cycles)

            # Step 5: Compute Markov scores and compare
            print("\n--- Comparison ---")
            print(f"{'Cycle':<25} {'Holistic':>10} {'Product':>10} {'GeoMean':>10}")
            print("-" * 60)

            holistic_scores = []
            product_scores = []
            geomean_scores = []

            for cycle in cycles:
                pp_labels = [
                    next(p for p in perspectives if p.hash == h).short_hash
                    for h in cycle.perspective_hashes
                ]
                label = "→".join(pp_labels) + "→" + pp_labels[0]

                links = extract_directed_links(cycle)
                link_vals = [directed_scores[link] for link in links]

                h_score = holistic_results[cycle.hash].probability if cycle.hash in holistic_results else 0.0
                p_score = markov_product(link_vals)
                g_score = markov_geometric_mean(link_vals)

                holistic_scores.append(h_score)
                product_scores.append(p_score)
                geomean_scores.append(g_score)

                print(f"  {label:<23} {h_score:>10.4f} {p_score:>10.4f} {g_score:>10.4f}")

            # Step 6: Correlation analysis
            print("\n--- Rank Correlation (Spearman) ---")
            rho_product = spearman_rank_correlation(holistic_scores, product_scores)
            rho_geomean = spearman_rank_correlation(holistic_scores, geomean_scores)
            print(f"  Holistic vs Product:       ρ = {rho_product:.3f}")
            print(f"  Holistic vs GeoMean:       ρ = {rho_geomean:.3f}")

            # Absolute differences
            print("\n--- Absolute Differences ---")
            for method, scores in [("Product", product_scores), ("GeoMean", geomean_scores)]:
                diffs = [abs(h - m) for h, m in zip(holistic_scores, scores)]
                print(f"  {method}: max={max(diffs):.4f}, mean={sum(diffs)/len(diffs):.4f}")

            # Top-cycle agreement
            print("\n--- Top Cycle Agreement ---")
            holistic_top = cycles[holistic_scores.index(max(holistic_scores))]
            product_top = cycles[product_scores.index(max(product_scores))]
            geomean_top = cycles[geomean_scores.index(max(geomean_scores))]

            h_label = "→".join(
                next(p for p in perspectives if p.hash == h).short_hash
                for h in holistic_top.perspective_hashes
            )
            p_label = "→".join(
                next(p for p in perspectives if p.hash == h).short_hash
                for h in product_top.perspective_hashes
            )
            g_label = "→".join(
                next(p for p in perspectives if p.hash == h).short_hash
                for h in geomean_top.perspective_hashes
            )
            print(f"  Holistic top: {h_label}")
            print(f"  Product top:  {p_label} {'✓' if product_top.hash == holistic_top.hash else '✗'}")
            print(f"  GeoMean top:  {g_label} {'✓' if geomean_top.hash == holistic_top.hash else '✗'}")

            print("\n" + "=" * 70)
            print("INTERPRETATION:")
            if rho_product > 0.8 or rho_geomean > 0.8:
                print("  HIGH correlation — Markov composition is viable for navigation.")
                print("  Could switch to pairwise scoring and save LLM calls.")
            elif rho_product > 0.5 or rho_geomean > 0.5:
                print("  MODERATE correlation — Markov roughly preserves ranking.")
                print("  Might work for coarse filtering but not precise ordering.")
            else:
                print("  LOW correlation — holistic assessment captures emergent dynamics")
                print("  that pairwise composition misses. Keep holistic scoring.")
            print("=" * 70)
