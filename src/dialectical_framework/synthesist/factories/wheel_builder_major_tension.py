from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict


class WheelBuilderMajorTension(WheelBuilder):
    def __init__(self, *, text: str = None, config: ConfigWheelBuilder = None):
        super().__init__(
            text=text,
            config=ReasonFastPolarizedConflict(
                text=text,
                config=config,
            )
        )
