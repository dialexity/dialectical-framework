from utils.dc_replace import dc_replace, dc_safe_replace


def test_dc_replace():
    text = 'T- is a good thing. "T-" is a bad thing. (T-) is a neutral thing. T-.'
    dialectical_component_name = 'T-'
    replace_to = 'A-'
    assert dc_replace(text, dialectical_component_name, replace_to) == text.replace(dialectical_component_name, replace_to)

def test_dc_safe_replace():
    text1 = 'T- is a good thing. "A-" is a bad thing. (T-) is a neutral thing. Whatever A.'
    text2 = 'A- is a good thing. "T-" is a bad thing. (A-) is a neutral thing. Whatever T.'
    assert dc_safe_replace(text1, {'T': 'A', 'A' : 'T', 'T-': 'A-', 'A-': 'T-'}) == text2