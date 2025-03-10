from abc import ABC, abstractmethod

from mirascope import Messages


class AbstractWheelStrategy(ABC):
    @abstractmethod
    def thesis(self, text: str) -> Messages.Type: ...

    @abstractmethod
    def antithesis(self, thesis: str) -> Messages.Type: ...

    @abstractmethod
    def negative_side(self, thesis: str, not_like_this: str = "") -> Messages.Type: ...

    @abstractmethod
    def positive_side(self, thesis: str, antithesis_negative: str) -> Messages.Type: ...