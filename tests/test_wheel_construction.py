from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.wheel2 import Wheel2, ALIAS_T


def test_wheel_construction():
    thesis = {ALIAS_T: DialecticalComponent.from_str(ALIAS_T, "T is a good thing.")}

    w = Wheel2(t=thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2.model_validate(thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2.model_validate({"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2(**thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2(**{"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2()
    setattr(w, ALIAS_T, thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = Wheel2()
    setattr(w, "t", thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)