import pytest
from langfuse.decorators import observe

from dialectical_framework.dialectical_reasoning import DialecticalReasoning

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"


@pytest.mark.asyncio
@observe()
async def test_find_polarities_single():
    """Quick test for a single parameter - click to run!"""
    await _test_find_polarities_logic(
        given=[(None, None)],
        expected_count=1
    )


@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("given,expected_count", [
    (None, 1),
    ([], 1),
    # Single polarity - both empty
    ([(None, None)], 1),
    # Single polarity - thesis provided
    ([("Love", None)], 1),
    # Single polarity - antithesis provided
    ([(None, "Hate")], 1),
    # Single polarity - both provided
    ([("Love", "Hate")], 1),
    # Multiple polarities - mixed
    ([("Russia started war", None), (None, "Ukraine started war")], 2),
    # Multiple polarities - all empty
    ([(None, None), (None, None)], 2),
    # Multiple polarities - various combinations
    ([("Love", None), (None, "Home"), ("Peace", "War"), (None, None)], 4),
])
async def test_find_polarities(given, expected_count):
    await _test_find_polarities_logic(given, expected_count)


async def _test_find_polarities_logic(given, expected_count):
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    polarities = await factory.extractor.extract_polarities(given=given)

    assert len(polarities) == expected_count

    print("\n")
    # Print results
    for t, a in polarities:
        print(t)
        print(a)
        print("\n")

    # Verify all components exist and have correct aliases
    for i, (t, a) in enumerate(polarities):
        assert t is not None and a is not None


@pytest.mark.asyncio
@observe()
async def test_extract_polarities_selective_at_single_index():
    """Test selective generation at a single index"""
    factory = DialecticalReasoning.wheel_builder(text=user_message)

    # Create a matrix with some known values
    given = [
        ("Love", None),  # Index 0: will generate antithesis
        ("Peace", None),  # Index 1: will NOT generate (not in 'at')
        ("Courage", None),  # Index 2: will NOT generate (not in 'at')
    ]

    # Generate only at index 0
    result = await factory.extractor.extract_polarities(given=given, at=0)

    assert len(result) == 3
    # Index 0 should have both thesis and antithesis
    assert result[0][0] is not None
    assert result[0][1] is not None
    assert result[0][0].statement == "Love"
    # Indices 1 and 2 should only have thesis, no antithesis
    assert result[1][0] is not None
    assert result[1][1] is None
    assert result[2][0] is not None
    assert result[2][1] is None

    print("\n=== Test: Single Index ===")
    for i, (t, a) in enumerate(result):
        print(f"Index {i}: T={t.statement if t else 'None'}, A={a.statement if a else 'None'}")


@pytest.mark.asyncio
@observe()
async def test_extract_polarities_selective_at_multiple_indices():
    """Test selective generation at multiple indices"""
    factory = DialecticalReasoning.wheel_builder(text=user_message)

    # Create a matrix with some known values
    given = [
        ("Love", None),  # Index 0: will generate
        ("Peace", None),  # Index 1: will NOT generate
        ("Courage", None),  # Index 2: will generate
    ]

    # Generate only at indices 0 and 2
    result = await factory.extractor.extract_polarities(given=given, at=[0, 2])

    assert len(result) == 3
    # Indices 0 and 2 should have both thesis and antithesis
    assert result[0][0] is not None
    assert result[0][1] is not None
    assert result[2][0] is not None
    assert result[2][1] is not None
    # Index 1 should only have thesis
    assert result[1][0] is not None
    assert result[1][1] is None

    print("\n=== Test: Multiple Indices ===")
    for i, (t, a) in enumerate(result):
        print(f"Index {i}: T={t.statement if t else 'None'}, A={a.statement if a else 'None'}")


@pytest.mark.asyncio
@observe()
async def test_extract_polarities_selective_with_not_like_these():
    """Test that other values are passed as not_like_these"""
    factory = DialecticalReasoning.wheel_builder(text=user_message)

    # Create a matrix where generating at one index should avoid duplicating others
    given = [
        ("Love", "Hate"),  # Index 0: complete, will be used as not_like_these
        ("Peace", None),  # Index 1: will generate antithesis, should not duplicate "Hate"
    ]

    result = await factory.extractor.extract_polarities(given=given, at=1)

    assert len(result) == 2
    # Index 0 should remain unchanged
    assert result[0][0].statement == "Love"
    assert result[0][1].statement == "Hate"
    # Index 1 should have generated antithesis different from "Hate"
    assert result[1][0].statement == "Peace"
    assert result[1][1] is not None
    assert result[1][1].statement.lower() != "hate"

    print("\n=== Test: With not_like_these ===")
    for i, (t, a) in enumerate(result):
        print(f"Index {i}: T={t.statement if t else 'None'}, A={a.statement if a else 'None'}")


@pytest.mark.asyncio
@observe()
async def test_extract_polarities_out_of_bounds_error():
    """Test that out of bounds indices raise IndexError"""
    factory = DialecticalReasoning.wheel_builder(text=user_message)

    given = [
        ("Love", None),
        ("Peace", None),
    ]

    # Try to access index 3 when only 2 elements exist
    with pytest.raises(IndexError, match="Index 3 is out of bounds"):
        await factory.extractor.extract_polarities(given=given, at=3)

    # Try negative index
    with pytest.raises(IndexError, match="Index -1 is out of bounds"):
        await factory.extractor.extract_polarities(given=given, at=-1)

    print("\n=== Test: Out of bounds error raised correctly ===")


@pytest.mark.asyncio
@observe()
async def test_extract_polarities_default_behavior():
    """Test that default behavior (at=None) still works"""
    factory = DialecticalReasoning.wheel_builder(text=user_message)

    given = [
        ("Love", None),
        ("Peace", None),
    ]

    # Without 'at' parameter, should generate all missing components
    result = await factory.extractor.extract_polarities(given=given)

    assert len(result) == 2
    # Both should have thesis and antithesis
    assert all(t is not None and a is not None for t, a in result)

    print("\n=== Test: Default Behavior ===")
    for i, (t, a) in enumerate(result):
        print(f"Index {i}: T={t.statement}, A={a.statement}")
