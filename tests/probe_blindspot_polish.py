"""Live smoke of the notebook's Path B polishing loop: first card, reject, next card.

    poetry run python tests/probe_blindspot_polish.py
"""
from __future__ import annotations

import asyncio

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings


async def main() -> None:
    DialecticalReasoning.setup(Settings.from_env())
    from dialectical_framework.agents.analyst.skills.sketch_tetrad import SketchTetrad
    from dialectical_framework.concerns.add_input import capture_input
    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.scope_context import scope
    from dialectical_framework.graph.views import exploration_view, perspective_view

    text = "I should quit my job and start my own company."
    case = Case(); case.commit()
    with scope(case.sid):
        source = await capture_input(text)
        first = (await SketchTetrad(input_hashes=[source.hash]).resolve())[0]
        v1 = perspective_view(first)
        print("card 1:", v1.t.text, "|", v1.a.text, "| A+:", v1.a_plus.text)
        first.discarded = "Too obvious — I know the security argument."
        first.save()
        ctx = (f"Already shown to the person: «{v1.t.text} vs {v1.a.text}». Their reaction: "
               '"Too obvious — I know the security argument. What am I REALLY not seeing?". '
               "Build a DIFFERENT tension — never a restatement of what was shown.")
        second = (await SketchTetrad(input_hashes=[source.hash], context=ctx).resolve())[0]
        v2 = perspective_view(second)
        print("card 2:", v2.t.text, "|", v2.a.text, "| A+:", v2.a_plus.text)
        the_map = exploration_view()
        print("map:", [(p.t.text, "set aside" if p.discarded else "standing") for p in the_map.perspectives])


if __name__ == "__main__":
    asyncio.run(main())
