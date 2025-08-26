from typing import runtime_checkable, Protocol

from dependency_injector.wiring import Provide, inject

from dialectical_framework.config import Config
from dialectical_framework.enums.di import DI


@inject
def di_config(config: Config = Provide[DI.config]) -> Config:
    return config


@runtime_checkable
class HasConfig(Protocol):
    @property
    def config(self) -> Config:
        return di_config()
