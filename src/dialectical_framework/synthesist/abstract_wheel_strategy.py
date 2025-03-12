from abc import ABC, abstractmethod

from mirascope import Messages

from dialectical_framework.dialectical_component import DialecticalComponent


class AbstractWheelStrategy(ABC):
    @abstractmethod
    def thesis(self, text: str | DialecticalComponent) -> Messages.Type: ...

    @abstractmethod
    def antithesis(self, thesis: str | DialecticalComponent) -> Messages.Type: ...

    @abstractmethod
    def negative_side(self, thesis: str | DialecticalComponent, not_like_this: str | DialecticalComponent = "") -> Messages.Type: ...

    @abstractmethod
    def positive_side(self, thesis: str | DialecticalComponent, antithesis_negative: str | DialecticalComponent) -> Messages.Type: ...