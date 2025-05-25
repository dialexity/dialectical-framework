from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class SingleConcept(WheelBuilder):
    def __init__(self, *, thesis: str = None):
        if thesis and thesis.strip():
            self._theses = [thesis]

        self._theses = None

    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        reasoner = ReasonFastAndSimple(
            text=text,
            config=config,
        )
        wu = await reasoner.think(thesis=self._theses[0] if self._theses else None)
        return Wheel(wu)