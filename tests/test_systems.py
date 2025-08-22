import pytest
from langfuse.decorators import observe

from dialectical_framework.config import Config
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.reason_conversational import ReasonConversational

@pytest.mark.asyncio
@observe()
async def test_seasons():
    factory = DialecticalReasoning.create_wheel_builder(text="4 seasons")
    factory.config.component_length = 1

    wheels = await factory.build_wheel_permutations(theses=["Summer", "Spring"])
    assert wheels[0].order == 2

    for w in wheels:
        print("\n")
        print(w)

    assert len(wheels) == 2
    assert wheels[0].cycle.dialectical_components[0].statement == "Summer"
    assert wheels[0].cycle.dialectical_components[1].statement == "Autumn" or wheels[0].cycle.dialectical_components[0].statement == "Fall"
    assert wheels[0].cycle.dialectical_components[2].statement == "Winter"
    assert wheels[0].cycle.dialectical_components[3].statement == "Spring"