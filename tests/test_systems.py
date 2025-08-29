import pytest
from langfuse.decorators import observe

from dialectical_framework.dialectical_reasoning import DialecticalReasoning


@pytest.mark.asyncio
@observe()
async def test_seasons():
    factory = DialecticalReasoning.wheel_builder(text="4 seasons")
    factory.settings.component_length = 1

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