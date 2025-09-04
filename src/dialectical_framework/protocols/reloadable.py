from abc import ABC, abstractmethod
from typing import Self


class Reloadable(ABC):
    @abstractmethod
    def reload(self, **kwargs) -> Self: ...
