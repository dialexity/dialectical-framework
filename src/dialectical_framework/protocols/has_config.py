from __future__ import annotations

from dependency_injector.wiring import Provide, inject

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings


@inject
def _di_settings(settings: Settings = Provide[DI.settings]) -> Settings:
    return settings


class SettingsAware:
    """Mixin providing access to Settings via DI."""

    @property
    def settings(self) -> Settings:
        return _di_settings()
