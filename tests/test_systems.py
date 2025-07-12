import pytest
from langfuse.decorators import observe

from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.reason_conversational import ReasonConversational

@pytest.mark.asyncio
@observe()
async def test_seasons1():
    factory = WheelBuilder(
        text="4 seasons",
        config=ConfigWheelBuilder(component_length=1)
    )

    wheels = await factory.build_wheel_permutations(theses=["Summer", "Spring"])
    assert len(wheels) == 2
    assert wheels[0].order == 2
    for w in wheels:
        print("\n")
        print(w)

@pytest.mark.asyncio
@observe()
async def test_seasons2():
    factory = WheelBuilder(
        text="4 seasons",
        config=ReasonConversational(config=ConfigWheelBuilder(component_length=1))
    )

    wheels = await factory.build_wheel_permutations(theses=["Summer", "Spring"])
    assert len(wheels) == 2
    assert wheels[0].order == 2
    for w in wheels:
        print("\n")
        print(w)