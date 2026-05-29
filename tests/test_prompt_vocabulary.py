"""
Regression tests for app prompt vocabulary.

These tests hit the real LLM and assert the output follows vocabulary rules
from apps.py. They catch prompt bugs where the model misapplies terms.

Run: poetry run pytest tests/test_prompt_vocabulary.py --real-llm -v

Add a new test for each vocabulary bug that gets fixed in apps.py.
"""

from __future__ import annotations

import re

import pytest

from dialectical_framework.agents.analyst.analyst import Analyst
from dialectical_framework.agents.apps import DEFAULT_APP
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.real_llm


class TestVocabularyRegression:
    """Each test targets a specific vocabulary bug that was observed and fixed."""

    @pytest.mark.asyncio
    async def test_t_minus_not_called_blindspot(self):
        """
        BUG: Haiku labeled T- as "The Blindspot" in position tables.
        FIX: Added explicit "VISIBLE to the position-holder (not a blindspot)"
             to T- vocabulary entry, plus example table in Presentation Defaults.

        T- is the holder's own visible concern/exaggeration.
        "Blindspot" belongs exclusively to A+ and A- (opposition territory).
        """
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = Analyst(app_preamble=DEFAULT_APP)
            response = await analyst.chat("Spirituality vs Love")

        response_lower = response.lower()

        # T- must never be labeled as blindspot
        # Match patterns like "T- (The Blindspot)" or "T- (Blindspot)"
        t_minus_blindspot = re.search(
            r"t-\s*\(?[^)]*blind\s*spot", response_lower
        )
        assert t_minus_blindspot is None, (
            f"T- was labeled as a blindspot. "
            f"Match: '{t_minus_blindspot.group()}' in response"
        )

        # T+ must never be labeled as blindspot either
        t_plus_blindspot = re.search(
            r"t\+\s*\(?[^)]*blind\s*spot", response_lower
        )
        assert t_plus_blindspot is None, (
            f"T+ was labeled as a blindspot. "
            f"Match: '{t_plus_blindspot.group()}' in response"
        )
