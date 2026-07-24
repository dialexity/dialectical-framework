from dialectical_framework.utils.dc_replace import dc_replace, dc_safe_replace


def test_dc_replace():
    text = 'T- is a good thing. "T-" is a bad thing. (T-) is a neutral thing. T-.'
    dialectical_component_name = "T-"
    replace_to = "A-"
    assert dc_replace(text, dialectical_component_name, replace_to) == text.replace(
        dialectical_component_name, replace_to
    )


def test_dc_replace_punctuation_boundaries():
    # Semicolon, hyphen, slash and em-dash must count as alias boundaries
    assert dc_replace("C1_1; then more", "C1_1", "growth") == "growth; then more"
    assert dc_replace("C1_1-driven change", "C1_1", "growth") == "growth-driven change"
    assert dc_replace("C1_1/C1_2 pair", "C1_1", "growth") == "growth/C1_2 pair"
    assert dc_replace("C1_1—next", "C1_1", "growth") == "growth—next"
    # Longer alias with same prefix must not be clipped
    assert dc_replace("C1_1 and C1_10", "C1_1", "growth") == "growth and C1_10"


def test_dc_replace_replacement_is_literal():
    # Replacement text is arbitrary prose — backslashes and group refs
    # must not be interpreted as regex replacement templates
    assert dc_replace("C1_1 works", "C1_1", r"path\to\thing") == r"path\to\thing works"
    assert dc_replace("C1_1 works", "C1_1", r"uses \1 notation") == r"uses \1 notation works"


def test_dc_safe_replace():
    text1 = 'T- is a good thing. "A-" is a bad thing. (T-) is a neutral thing. Whatever A. (T+)'
    text2 = 'A- is a good thing. "T-" is a bad thing. (A-) is a neutral thing. Whatever T. (A+)'
    assert (
        dc_safe_replace(text1, {"T": "A", "A": "T", "T-": "A-", "A-": "T-", "T+": "A+"})
        == text2
    )
