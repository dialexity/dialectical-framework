from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.base_wheel import BaseWheel, ALIAS_T


def test_wheel_construction():
    thesis = {ALIAS_T: DialecticalComponent.from_str(ALIAS_T, "T is a good thing.")}

    w = BaseWheel(t=thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel.model_validate(thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel.model_validate({"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel(**thesis)
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel(**{"t": thesis.get(ALIAS_T)})
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel()
    setattr(w, ALIAS_T, thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)

    w = BaseWheel()
    setattr(w, "t", thesis.get(ALIAS_T))
    assert w.t == thesis.get(ALIAS_T)