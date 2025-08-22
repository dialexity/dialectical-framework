from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.config import Config
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict


class WheelBuilderMajorTension(WheelBuilder):
    def __init__(self, *, text: str = None, config: Config = None):
        super().__init__(
            text=text,
            config=ReasonFastPolarizedConflict(
                text=text,
                config=config,
            )
        )
