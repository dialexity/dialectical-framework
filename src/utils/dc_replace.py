import re


def dc_replace(text: str, dialectical_component_name: str, replace_to: str) -> str:
    """
    # 1. **`(?<!\w)`**: Ensures `T-` is not preceded by a word character (prevents matches like `T-something`).
    # 2. **`(["'\(\[\{]?)`**: Matches an optional opening character like `"`, `'`, `(`, `[`, or `{`. This is captured in group `\1`.
    # 3. **`T-` **: Matches the literal `T-`.
    # 4. **`(\s|[\]'"}).,!?:]|$)`**:
    #     - Matches any of the following right after `T-`:
    #         - A space (`\s`) (e.g., `T- something` or `T-`).
    #         - A closing punctuation mark like `]`, `'`, `"`, `)`, `}`.
    #         - Specific punctuation characters: `.`, `,`, `!`, `?`, or `:`.
    #         - The end of the line (`$`).
    #
    #     - This captures both proper sentence endings (e.g., `T-.`) and cases where punctuation appears mid-sentence (e.g., `T-,` or `T-!`).
    """
    return re.sub(
        r'(?<!\w)(["\'\(\[\{]?)' rf"{dialectical_component_name}" r'(\s|[\]\'\"\)\},.!?:]|$)',
        # Replacement pattern (preserves surrounding characters and spaces)
        r'\1' rf"{replace_to}" r'\2',
        text
    )

def dc_safe_replace(text: str, replacements: dict) -> str:
    result = text
    for key, value in replacements.items():
        result = dc_replace(result, key, f"_{key}_")

    for key, value in replacements.items():
        result = dc_replace(result,f"_{key}_", value)
    return result