from abc import abstractmethod, ABC
from typing import runtime_checkable, Protocol, Self


class Reloadable(ABC):
    @abstractmethod
    def reload(self, **kwargs) -> Self: ...
