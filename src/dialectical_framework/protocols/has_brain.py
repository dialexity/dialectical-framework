from typing import Protocol, runtime_checkable

from dependency_injector.wiring import Provide, inject

from dialectical_framework.brain import Brain
from dialectical_framework.enums.di import DI


@inject
def di_brain(brain: Brain = Provide[DI.brain]) -> Brain:
    return brain


@runtime_checkable
class HasBrain(Protocol):
    @property
    def brain(self) -> Brain:
        return di_brain()
