"""
The wheel dump renders its synthesis BEFORE its transformations.

`read-reach` (2026-09-21) found the synthesis to be the least-used section of
the dump in every arm — best overlap with the replies 0.17-0.41 against
0.36-0.50 for the pathways — and it was rendered two lines long at the END of
each wheel, ~63 lines below the wheel heading, after twelve transformations.
The line that says where the whole arrangement heads was the last thing under
it. Pinned on the renderer's source order, because building a wheel with
transformations and a synthesis under mock brain is a multi-second fixture for
a fact that is one line of code.
"""

from __future__ import annotations

import inspect

import pytest

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def test_the_synthesis_is_rendered_before_the_transformations():
    source = inspect.getsource(DialecticalContext._dump_wheel)
    synthesis_at = source.index("self._dump_synthesis(wheel, pp_index)")
    transformations_at = source.index("for tr in wheel.transformations:")
    assert synthesis_at < transformations_at, (
        "the synthesis must lead the wheel block; rendered after twelve "
        "transformations it was the least-used section of the whole dump"
    )
