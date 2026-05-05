import re


def dc_replace(text: str, alias: str, replace_to: str) -> str:
    """
    Replace a statement alias in text, respecting word boundaries.

    Use this for single replacements where there's no risk of overlapping aliases.
    For multiple replacements with overlapping aliases (e.g., T, T+, T-), use dc_safe_replace.

    Args:
        text: The text to perform replacement in
        alias: The alias to find (e.g., "T-", "C1_1")
        replace_to: The replacement string (e.g., "A-", "T1")

    Returns:
        Text with replacements made

    Example:
        >>> dc_replace("T- causes A+", "T-", "A-")
        "A- causes A+"

    Regex details:
    - `(?<!\\w)`: Not preceded by word character (prevents "AT-" matching)
    - `(["'([{]?)`: Optional opening bracket/quote (captured)
    - `<alias>`: The literal alias (escaped)
    - `(\\s|[]'"}).,!?:]|$)`: Followed by space, punctuation, or end (captured)
    """
    return re.sub(
        r'(?<!\w)(["\'\(\[\{]?)'
        rf"{re.escape(alias)}"
        r"(\s|[\]\'\"\)\},.!?:]|$)",
        # Replacement pattern (preserves surrounding characters and spaces)
        r"\1" rf"{replace_to}" r"\2",
        text,
        flags=re.VERBOSE,
    )


def dc_safe_replace(text: str, replacements: dict[str, str]) -> str:
    """
    Replace multiple statement aliases safely, handling overlapping keys.

    Use this when replacing multiple aliases that could overlap (e.g., swapping T↔A
    where T, T+, T-, A, A+, A- all exist). Direct replacement would corrupt longer
    aliases (replacing "T" first would turn "T+" into "A+").

    This function uses a two-pass approach:
    1. Replace all aliases with temporary placeholders (_T_, _A_, etc.)
    2. Replace placeholders with final values

    Args:
        text: The text to perform replacements in
        replacements: Dict mapping aliases to their replacements

    Returns:
        Text with all replacements made safely

    Example:
        >>> dc_safe_replace(
        ...     "T- contradicts A+",
        ...     {"T": "A", "A": "T", "T-": "A-", "A+": "T+"}
        ... )
        "A- contradicts T+"

    When to use dc_safe_replace vs dc_replace:
    - dc_replace: Single replacement, no overlap risk (e.g., C1_1 → T1)
    - dc_safe_replace: Multiple replacements with overlapping aliases (e.g., T↔A swap)
    """
    result = text
    # Sort keys by length in descending order to replace longer keys first
    sorted_keys = sorted(replacements.keys(), key=len, reverse=True)

    # First pass: replace with temporary placeholders
    for key in sorted_keys:
        result = dc_replace(result, key, f"_{key}_")

    # Second pass: replace placeholders with final values
    for key in sorted_keys:
        result = dc_replace(result, f"_{key}_", replacements[key])

    return result
