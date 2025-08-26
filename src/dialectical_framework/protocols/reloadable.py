from abc import ABC, abstractmethod
from typing import Protocol, Self, runtime_checkable


class Reloadable(ABC):
    @abstractmethod
    def reload(self, **kwargs) -> Self: ...
