from abc import ABC, abstractmethod
from typing import TypeVar

BasicWheelWithSubTypes = TypeVar("BasicWheelWithSubTypes", bound="BasicWheel")

class AbstractWheelFactory(ABC):
    """
    Abstract Base Class for all Wheel Factories.
    Concrete wheel_factories must implement the create_wheel method.
    """

    @abstractmethod
    def generate(self, input_text: str) -> BasicWheelWithSubTypes: ...
    """
    Subclasses must implement basic generation of a wheel from a given input text.
    """

    @abstractmethod
    def redefine(self, input_text: str, original: BasicWheelWithSubTypes, **modified_dialectical_components) -> BasicWheelWithSubTypes: ...
    """
    Subclasses must implement the regeneration/adjustments of a wheel, provided that some components have been modified.
    The modifications are provided dialectical component names and their new values.
    Names are the fields of the BasicWheel class.
    
    @return: a copy of the original wheel with the modified components.
    """