from abc import abstractmethod, ABC

from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.wheel import Wheel

class TransitionBuilder(WheelBuilder):
    def __init__(self, builder: WheelBuilder):
        super().__init__()
        self._decorated_builder = builder

    @abstractmethod
    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        """ Subclasses should implement the fancy logic of adding transitions and calling the decorated builder """
        pass
