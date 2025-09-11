from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.wheel_segment import ALIAS_T
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


def test_wu_construction():
    thesis = {ALIAS_T: DialecticalComponent(alias=ALIAS_T, statement="T is a good thing.")}

    w = WisdomUnit(t=thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit.model_validate(thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit.model_validate({"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit(**thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit(**{"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit()
    setattr(w, ALIAS_T, thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = WisdomUnit()
    setattr(w, "t", thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)
