from abc import abstractmethod, ABC
from typing import List

from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.wheel import Wheel


class WheelBuilder(ABC):
    @abstractmethod
    async def build(self, text: str, config: WheelBuilderConfig = None) -> List[Wheel]: ...
