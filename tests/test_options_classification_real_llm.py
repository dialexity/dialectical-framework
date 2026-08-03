"""Real-LLM behavioral check: named options classify COMPLEX.

Decision-shaped conversations route option statements ("Take the startup
offer") straight at the SIMPLE/COMPLEX boundary — CLAUDE.md calls it the most
leverage-dense prompt in the extraction pipeline. A SIMPLE misclassification
poisons everything downstream for the decision use case: degenerate
dx://taxonomy/Simple meaning, no real apexes, no taxonomy anchoring for the
tetrad. This drives the real classifier over a set of options phrased as
imperatives and noun phrases (plus SIMPLE controls) and asserts the verdicts.

Run: poetry run pytest tests/test_options_classification_real_llm.py -s --real-llm
(Skipped in the default suite — needs a real provider.)
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

from conftest import traced

from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

# (statement, expect_simple)
CASES = [
    # Named options / courses of action — must be COMPLEX
    ("Take the startup offer", False),
    ("Stay at BigCo", False),                 # bare noun-phrase option
    ("Migrate to microservices", False),
    ("Move to Berlin for the new role", False),
    # SIMPLE controls — the fix must not drag bare facts into COMPLEX
    ("The sky is blue", True),
    ("The repository has 3 branches", True),
]


class TestOptionsClassifyComplex:
    @pytest.mark.asyncio
    @traced
    async def test_options_classify_complex_facts_stay_simple(self):
        case_node = Case()
        case_node.commit()

        failures: list[str] = []
        with scope(case_node.sid):
            for statement, expect_simple in CASES:
                concern = StatementClassification()
                result = await concern.resolve(statement=statement)
                print(
                    f"{statement!r}: is_simple={result.is_simple} "
                    f"meaning={result.meaning}"
                )
                if result.is_simple != expect_simple:
                    failures.append(
                        f"{statement!r}: expected is_simple={expect_simple}, "
                        f"got {result.is_simple} "
                        f"({result.classification_reasoning})"
                    )
                if not expect_simple and result.is_simple is False:
                    # COMPLEX options must land on a real taxonomy anchor,
                    # not the degenerate Simple leaf.
                    assert "Simple" not in result.meaning, statement

        assert not failures, "\n".join(failures)
