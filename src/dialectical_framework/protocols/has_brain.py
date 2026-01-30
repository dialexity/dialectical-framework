from __future__ import annotations

from dependency_injector.wiring import Provide, inject

from dialectical_framework.brain import Brain
from dialectical_framework.enums.di import DI


@inject
def di_brain(brain: Brain = Provide[DI.brain]) -> Brain:
    return brain


class HasBrain:
    """Mixin providing access to the Brain instance via DI."""

    @property
    def brain(self) -> Brain:
        return di_brain()
