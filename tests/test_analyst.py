import asyncio
from math import factorial
from typing import List

from langfuse.decorators import observe

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.cycle import Cycle

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"


@observe()
def test_thought_mapping():
    nr_of_thoughts = 3
    reasoner = ThoughtMapping(user_message)
    cycles: List[Cycle] = asyncio.run(reasoner.extract(nr_of_thoughts))
    assert len(cycles) == factorial(nr_of_thoughts - 1)
    print("\n")
    for cycle in cycles:
        assert len(cycle.dialectical_components) == nr_of_thoughts
        print(cycle.__str__())