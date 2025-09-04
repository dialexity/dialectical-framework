from typing import Protocol, runtime_checkable

from dependency_injector.wiring import Provide, inject

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings


@inject
def di_settings(settings: Settings = Provide[DI.settings]) -> Settings:
    return settings


@runtime_checkable
class SettingsAware(Protocol):
    @property
    def settings(self) -> Settings:
        return di_settings()
