"""The machinery arm of the wise pill: Ac+/Re+/S+ from the framework, then the same writer.

`probe_synthesis_arms_corners.py` rendered the pill from the six CORNERS of an existing
tetrad and let the writer improvise the move ("the fix isn't X, it's Z") — which
is Transformation-level (Ac+: T- → A+, Re+: A- → T+) and the "what becomes
possible only with both" is Wheel-level (S+). The owner's question: why not
the machinery that computes exactly those? This arm answers it the way the
project's ceiling-not-floor rule demands — the same tetrads, the machinery's
own pathways and synthesis, the SAME writer prompt with its inputs swapped,
side by side with the corner-only pill.

Per tetrad, no re-reasoning of the tetrad itself: `SketchTetrad(sketch=)`
persists the already-drawn six texts (classify, score, ground, validate),
`run_exploration_detailed` builds the 1-PP wheel (2 edges, 6 Transformations,
one per insight band per edge) and its synthesis, then the pathways and S+/S-
are read back and handed to the writer. Graph writes are sequential (one case
per tetrad, one at a time).

    poetry run pytest tests/e2e/probe_synthesis_arms_machinery.py --real-llm -q -s
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.tools.explore import \
    run_exploration_detailed
from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
    SketchTetrad
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.add_input import capture_input
from dialectical_framework.concerns.view_sketch import \
    ViewSketchPerspectiveDto
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.rendering import \
    find_nexus_for_transformation
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository
from dialectical_framework.graph.scope_context import scope
from e2e.probe_synthesis_arms_corners import SYSTEM, WisdomDto

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
#: The corner-only pills, for the side-by-side.
_CORNER_RUN = _RESULTS / "wisdom_line-20261004-153912.json"


class MachineryWisdomDto(WisdomDto):
    """The same three pieces; `your_side`/`other_side` keep their meaning, the
    paragraph is now written FROM the pathways and the synthesis."""

    paragraph: str = Field(
        description=(
            "At most 60 words, second person. Hold the tension (do not resolve it), "
            "credit what is right in their position, then say THE MOVE — the one "
            "pathway among those given that turns their trap into the other side's "
            "strength — and what the synthesis names as possible only with both. "
            "Use the pathway and synthesis texts given; add no step they do not "
            "contain. Their particulars, not generalities. No framework words."
        )
    )


def _machinery_prompt(r: dict, pathways: list[dict], s_plus: str | None, s_minus: str | None) -> str:
    lines = [f'They said: "{r["utterance"]}"', "",
             f"Position (T): {r['thesis']}", f"Stands against (A): {r['antithesis']}",
             f"T developed well (T+): {r['t_plus']}", f"T's trap (T-): {r['t_minus']}",
             f"A developed well (A+): {r['a_plus']}", f"A's trap (A-): {r['a_minus']}", "",
             "Pathways the framework derived (each: the ACTION that turns T's trap into A's strength, the REFLECTION that turns A's trap into T's strength, and how each degrades when done one-sidedly), from shallow to deep:"]
    for p in pathways:
        lines.append(f"- [{p.get('category') or 'uncategorised'}] action: {p.get('ac_plus')} | reflection: {p.get('re_plus')} | action's degradation: {p.get('ac_minus')} | reflection's degradation: {p.get('re_minus')}")
    lines += ["", f"What becomes possible only with both (S+): {s_plus or '(not generated)'}",
              f"What it collapses into otherwise (S-): {s_minus or '(not generated)'}", "", "Write the three pieces."]
    return "\n".join(lines)


def _transition_text(manager) -> str | None:
    result = manager.get()
    if not result:
        return None
    transition = result[0]
    return (transition.instruction or transition.summary or "").strip() or None


def _read_pathways(tr_hashes: list[str]) -> tuple[list[dict], str | None, str | None]:
    repo = NodeRepository()
    pathways: list[dict] = []
    nexus = None
    for h in dict.fromkeys(tr_hashes):
        tr = repo.find_by_hash(h, Transformation)
        if tr is None:
            continue
        nexus = nexus or find_nexus_for_transformation(tr)
        row = {"hash": tr.short_hash, "category": tr.insight_category}
        for key, manager in (("ac_plus", tr.ac_plus), ("re_plus", tr.re_plus), ("ac_minus", tr.ac_minus), ("re_minus", tr.re_minus)):
            row[key] = _transition_text(manager)
        ac = tr.ac_plus.get()
        if ac:
            row["insight"] = getattr(ac[1], "insight", None)
            row["proactiveness"] = getattr(ac[1], "proactiveness", None)
        pathways.append(row)
    s_plus = s_minus = None
    if nexus is not None:
        for _cycle, wheel in WheelRepository().find_by_nexus(nexus):
            for synth, _ in wheel.synthesis.all():
                sp, sm = synth.s_plus.get(), synth.s_minus.get()
                s_plus = sp[0].text if sp else s_plus
                s_minus = sm[0].text if sm else s_minus
    # one edge pair: the opposite edge's Transformations are role-swapped twins,
    # so dedup by (ac_plus, re_plus) text to show each move once
    seen: set = set()
    unique = []
    for p in sorted(pathways, key=lambda p: (p.get("insight") or 0)):
        key = frozenset((p.get("ac_plus"), p.get("re_plus")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique, s_plus, s_minus


async def _arm(r: dict) -> dict:
    out = {k: r.get(k) for k in ("utterance", "thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus", "pass")}
    out["corner_paragraph"] = r.get("paragraph")
    case = Case()
    case.commit()
    out["sid"] = case.sid
    started = time.perf_counter()
    try:
        with scope(case.sid):
            source = await capture_input(r["utterance"])
            sketch = ViewSketchPerspectiveDto(
                thesis=r["thesis"], antithesis=r["antithesis"],
                t_plus_vs_a_minus_axis="", t_plus=r["t_plus"], a_minus=r["a_minus"],
                a_plus_vs_t_minus_axis="", a_plus=r["a_plus"], t_minus=r["t_minus"],
            )
            skill = SketchTetrad(input_hashes=[source.hash], sketch=sketch)
            pps = await skill.resolve()
            if not pps:
                out["error"] = f"nothing persisted: {skill.report.summary}"
                return out
            out["persist_s"] = round(time.perf_counter() - started, 1)
            t1 = time.perf_counter()
            report, tr_hashes = await run_exploration_detailed(
                perspective_hashes=[pps[0].hash], intent=r["utterance"], nexus_hash=None
            )
            out["explore_s"] = round(time.perf_counter() - t1, 1)
            out["transformations"] = len(set(tr_hashes))
            pathways, s_plus, s_minus = _read_pathways(list(tr_hashes))
            out.update(pathways=pathways, s_plus=s_plus, s_minus=s_minus)
            if not pathways:
                out["error"] = "no pathways read back"
                out["report_head"] = report[:600]
                return out
            t2 = time.perf_counter()
            conversation = ConversationFacilitator()
            conversation.set_system_prompt(SYSTEM)
            dto = await conversation.submit(MachineryWisdomDto, _machinery_prompt(r, pathways, s_plus, s_minus))
            out.update(your_side=dto.your_side, other_side=dto.other_side, paragraph=dto.paragraph,
                       render_s=round(time.perf_counter() - t2, 1))
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        out["error"] = repr(exc)
    out["total_s"] = round(time.perf_counter() - started, 1)
    return out


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_machinery_pill(di_container) -> None:
    rows = json.loads(_CORNER_RUN.read_text())
    rows = [r for r in rows if r.get("a_plus")]
    out = _RESULTS / f"wisdom_machinery-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== machinery pill on {len(rows)} tetrads → {out}", flush=True)
    done: list[dict] = []
    for i, r in enumerate(rows, 1):
        result = await _arm(r)
        done.append(result)
        out.write_text(json.dumps(done, indent=2, ensure_ascii=False))
        print(f"\n{i}. **{r['utterance']}**  persist {result.get('persist_s')}s  explore {result.get('explore_s')}s  "
              f"transformations {result.get('transformations')}  total {result.get('total_s')}s", flush=True)
        if result.get("error"):
            print(f"   ERROR {result['error']}", flush=True)
            continue
        for p in result["pathways"]:
            print(f"   [{p.get('category')}] Ac+: {p.get('ac_plus')}\n   {' ' * len(str(p.get('category')))}   Re+: {p.get('re_plus')}", flush=True)
        print(f"   S+: {result.get('s_plus')}\n   S-: {result.get('s_minus')}", flush=True)
        print(f"   corner   : {result.get('corner_paragraph')}", flush=True)
        print(f"   machinery: {result.get('paragraph')}", flush=True)
        print(f"   your side: {result.get('your_side')}\n   other    : {result.get('other_side')}", flush=True)
    ok = [d for d in done if not d.get("error")]
    if ok:
        med = lambda k: sorted(d[k] for d in ok if d.get(k) is not None)[len(ok) // 2]
        print(f"\n--- {len(ok)}/{len(done)} built; median persist {med('persist_s')}s, explore {med('explore_s')}s, total {med('total_s')}s", flush=True)
