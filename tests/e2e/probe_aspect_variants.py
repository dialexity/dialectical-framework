"""Which half carries the tetrad-coherence gap — and which aspect-side suspect moves it?

WHY THIS EXISTS
===============
`docs/dev-notes/antithesis-selection.md` ends on a comparison: the Consultant's
view turn (one call, whole tetrad) passed the pipeline's own coherence judge
24/40 against the staged pipeline's 14-16/40. Five in-pipeline fixes were null or
worse. This probe isolates the ASPECT half without touching the graph: it
replays `AspectGeneration`'s full-tetrad call on fixed (thesis, antithesis)
pairs and varies one thing per arm.

GRAPH-FREE BY CONSTRUCTION. Statements are unsaved; nothing is committed; the
judge is `ControlStatementsCheck._evaluate_control_statement` on the pipeline's
exact control-statement format. Run as a plain script, never under pytest:

    poetry run python tests/e2e/probe_aspect_variants.py            # run / resume
    poetry run python tests/e2e/probe_aspect_variants.py --report   # table only

PAIRS (40 each, same 40 utterances)
  P  the pipeline's own first-tetrad T/A (`set_a-20260930-094654.json`,
     `set_b-20260930-134741.json` — the final-stack runs)
  V  the Consultant view turn's T/A (`path_a_cc-20261001.json`)

ARMS (paired on the same pairs)
  base       P  production prompt unchanged — the HARNESS VALIDITY check: must
                land near the pipeline's own 14/40 on these pairs
  ctx        P  + the full utterance as `<context>`               [suspect 1]
  noapex     P  - the four "Taxonomy apex concepts" lines          [suspect 5]
  textonly   P  flat texts-only DTO, no HS/K scales or scores      [suspect 4]
  terms      P  + utterance as context + "in the person's own terms" [suspect 6]
  viewstyle  P  pipeline T/A fixed; aspects by ONE json-mode thinking call on
                the Consultant's conversation, view-sketch procedure  [swap]
  base       V  the view turn's T/A through the PRODUCTION aspect prompt [swap]

ROUND 2 — which ingredient of `viewstyle` carries its gain (S system prompt,
U utterance as the conversation, K thinking json-mode call, X texts-only):
  viewstyle_nothink  P  viewstyle with thinking OFF                    [-K]
  prodsys_viewuser   P  viewstyle on `AspectGeneration.SYSTEM_PROMPT`  [-S]
  viewsys_produser   P  the Consultant's system prompt + conversation, but the
                        production `_tetrad_prompt` + `TetradDto`, no thinking
  textonly_ctx       P  `textonly` + the utterance as `<context>`      [X+U]
plus a DRIFT AUDIT of the `viewstyle` rows (judge model, no generation): are
the aspects built on the GIVEN thesis/antithesis or on a reworded tension?

Classification (the branch selects the apex rows in the prompt) is read once
per pair and cached in the result file, so every arm on a pair sees the same
apex. P classifies the UTTERANCE (production classifies the full text and
stores the headline); V classifies its thesis text.

Resumable: rows are persisted after every item; a rerun skips what is done.
`--budget SECONDS` stops launching new items so one invocation stays bounded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mirascope import llm  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from dialectical_framework.dialectical_reasoning import \
    DialecticalReasoning  # noqa: E402
from dialectical_framework.settings import Settings  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
OUT = RESULTS / "aspect_variants-20261001.json"
P_FILES = ("set_a-20260930-094654.json", "set_b-20260930-134741.json")
V_FILE = "path_a_cc-20261001.json"

ARMS: tuple[tuple[str, str], ...] = (
    ("base", "P"),
    ("ctx", "P"),
    ("noapex", "P"),
    ("textonly", "P"),
    ("terms", "P"),
    ("viewstyle", "P"),
    ("base", "V"),
    # Round 2: which ingredient of `viewstyle` carries its gain. It differs from
    # `base` in four things at once — (S) the system prompt, (U) the utterance
    # as the conversation, (K) a thinking json-mode call, (X) texts-only output.
    ("viewstyle_nothink", "P"),   # viewstyle minus K
    ("prodsys_viewuser", "P"),    # viewstyle with the PRODUCTION system prompt (minus S)
    ("viewsys_produser", "P"),    # S + U, but the production user prompt + TetradDto, no thinking
    ("textonly_ctx", "P"),        # X + U on the production system prompt
    # Round 3: ablate `AspectGeneration.SYSTEM_PROMPT` on the PRODUCTION shape
    # (production user prompt, `TetradDto`, forced tool, no thinking, no
    # utterance) — only the system prompt varies.
    ("sys_no_mistakes", "P"),
    ("sys_no_plus_mistake", "P"),
    ("sys_no_examples", "P"),
    ("sys_minimal", "P"),
    ("sys_no_truth_criterion", "P"),
    # Round 4: replicate the one promising cut (two FRESH generations per pair,
    # kept apart from the first run's rows), and run it on the WEAK tier — the
    # tier its paragraph was added for. `#rN` / `#weak` are suffixes on the arm
    # whose prompt is used; classification is NEVER re-read for these.
    ("base#r1", "P"),
    ("sys_no_plus_mistake#r1", "P"),
    ("base#r2", "P"),
    ("sys_no_plus_mistake#r2", "P"),
    ("base#weak", "P"),
    ("sys_no_plus_mistake#weak", "P"),
)

WEAK_ARMS = ("base#weak", "sys_no_plus_mistake#weak")

# Round 5 (2026-10-01): the cut shipped to the working tree and did NOT show
# end to end (pipeline first-tetrad CC 14/40 before, 14/40 after). P2 = the 40
# first-tetrad (thesis, antithesis) pairs of THAT pipeline run — pairs the cut
# was never selected on — through the production shape with the paragraph
# (`old`, rebuilt from commit b96483b) and without it (`new`, the live prompt),
# two generations each. Separates winner's curse from a harness/pipeline gap.
P2_FILES = (
    "set_a-20261001-070130.json",
    "set_a-default-off05-20261001-070823.json",
    "set_a-default-off10-20261001-071404.json",
    "set_a-default-off15-20261001-071955.json",
    "set_b-20261001-072536.json",
    "set_b-default-off05-20261001-073124.json",
    "set_b-default-off10-20261001-074013.json",
    "set_b-default-off15-20261001-075035.json",
)
P2_ARMS: tuple[tuple[str, str], ...] = (
    ("old#p2r1", "P2"),
    ("new#p2r1", "P2"),
    ("old#p2r2", "P2"),
    ("new#p2r2", "P2"),
)
ARMS = ARMS + P2_ARMS
OLD_PROMPT_COMMIT = "b96483b"


def _old_system_prompt() -> str:
    """`AspectGeneration.SYSTEM_PROMPT` as of `OLD_PROMPT_COMMIT`, evaluated
    from that commit's source, and asserted to differ from the live prompt by
    exactly the one "mistake to avoid on a plus" paragraph."""
    import ast
    import subprocess

    from dialectical_framework.concerns import aspect_generation
    from dialectical_framework.concerns.scoring_scales import \
        ASPECT_DEFINITIONS

    source = subprocess.run(
        ["git", "show", f"{OLD_PROMPT_COMMIT}:src/dialectical_framework/concerns/aspect_generation.py"],
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parent.parent.parent,
    ).stdout
    node = next(
        n for n in ast.parse(source).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SYSTEM_PROMPT" for t in n.targets)
    )
    old = eval(  # noqa: S307 — our own source at a pinned commit
        compile(ast.Expression(node.value), "<old SYSTEM_PROMPT>", "eval"),
        {"ASPECT_DEFINITIONS": ASPECT_DEFINITIONS},
    )
    old_paras = old.split("\n\n")
    new_paras = aspect_generation.SYSTEM_PROMPT.split("\n\n")
    extra = [x for x in old_paras if x not in new_paras]
    assert len(extra) == 1 and extra[0].startswith("The mistake to avoid on a plus."), extra
    assert [x for x in old_paras if x is not extra[0]] == new_paras, "prompts differ by more than the one paragraph"
    return old

#: Arms whose two pluses get the archive's parentage/valence audit — the plus
#: examples were added to cut restatement, so removing them must be read in
#: BOTH directions (`own_pole`+valence false = restatement; `other_pole` /
#: `neither` = the over-correction).
PARENTAGE_ARMS = (
    "base", "sys_no_mistakes", "sys_no_plus_mistake", "sys_no_examples",
    "sys_minimal", "sys_no_truth_criterion",
    "base#weak", "sys_no_plus_mistake#weak",
)


def _system_variant(arm: str) -> str:
    """`AspectGeneration.SYSTEM_PROMPT` with one cut, by paragraph. Every cut
    asserts it matched, so an edit to the production prompt cannot turn an arm
    into a silent copy of `base`."""
    from dialectical_framework.concerns import aspect_generation

    full = aspect_generation.SYSTEM_PROMPT
    paras = full.split("\n\n")

    def drop(prefixes: tuple[str, ...]) -> str:
        kept = [x for x in paras if not x.startswith(prefixes)]
        assert len(kept) == len(paras) - len(prefixes), (arm, prefixes)
        return "\n\n".join(kept)

    # HISTORICAL since 2026-10-01: the plus-mistake paragraph was removed from
    # the production prompt on this probe's evidence, so `sys_no_plus_mistake`
    # IS `base` now and the two arms that drop it fail their match assertion
    # by design. Re-running them needs the paragraph from commit b96483b.
    minus_mistake = "The mistake to avoid, on that same Courage/Fear pair."
    plus_mistake = "The mistake to avoid on a plus."
    closing = "Generate aspect statements that fit the semantic structure."
    if arm == "sys_no_mistakes":
        return drop((minus_mistake, plus_mistake))
    if arm == "sys_no_plus_mistake":
        return drop((plus_mistake,))
    if arm == "sys_no_examples":
        cut = paras.index("## Examples")
        assert paras[-1] == closing
        return "\n\n".join(paras[:cut] + [closing])
    if arm == "sys_minimal":
        assert paras[0].startswith("You are a dialectical aspect generator.")
        assert paras[1].startswith("Your task is to generate aspects")
        return "\n\n".join(paras[:2])
    if arm == "sys_no_truth_criterion":
        return drop(("Truth criterion:",))
    raise ValueError(arm)


#: Set once every pair is classified; after that nothing may classify again.
FROZEN_CLASSIFICATIONS = False

TERMS_LINE = "Write every aspect in the person's own terms."


class FlatTetradDto(BaseModel):
    """`TetradDto` with the scores taken out: axes and four statements only."""

    t_plus_vs_a_minus_axis: str = Field(
        description=(
            "The single dimension on which T+ and A- are opposite ends "
            "(e.g. 'closeness'). If T and A share no such dimension, the pair "
            "is not a genuine contradiction — say so here."
        )
    )
    t_plus: str = Field(
        description=(
            "T+ - the THESIS developed constructively, so that it also strengthens "
            "what A offers. Derive it from T, then place it at the positive end of "
            "the axis above."
        )
    )
    a_minus: str = Field(
        description=(
            "A- - the ANTITHESIS overdeveloped: A pushed one-sidedly with T "
            "underdeveloped, i.e. what A itself degenerates into. Derive it from A, "
            "never by negating T+, then place it at the negative end of the axis above."
        )
    )
    a_plus_vs_t_minus_axis: str = Field(
        description=(
            "The single dimension on which A+ and T- are opposite ends. If A "
            "and T share no such dimension, say so here rather than inventing "
            "two unrelated aspects."
        )
    )
    a_plus: str = Field(
        description=(
            "A+ - the ANTITHESIS developed constructively, so that it also strengthens "
            "what T offers. Derive it from A, then place it at the positive end of "
            "the axis above."
        )
    )
    t_minus: str = Field(
        description=(
            "T- - the THESIS overdeveloped: T pushed one-sidedly with A "
            "underdeveloped, i.e. what T itself degenerates into. Derive it from T, "
            "never by negating A+, then place it at the negative end of the axis above."
        )
    )


def _load_pairs() -> dict[str, list[dict[str, str]]]:
    p: list[dict[str, str]] = []
    for name in P_FILES:
        for item in json.loads((RESULTS / name).read_text()):
            if not item.get("perspectives"):
                continue
            first = item["perspectives"][0]
            p.append(
                {
                    "utterance": item["utterance"],
                    "thesis": first["thesis"],
                    "antithesis": first["antithesis"],
                    "ref_pass": bool(first.get("cc_pass")),
                }
            )
    v: list[dict[str, str]] = []
    path_a = json.loads((RESULTS / V_FILE).read_text())
    for key in ("A", "B"):
        for row in path_a[key]:
            if not row.get("drawn"):
                continue
            v.append(
                {
                    "utterance": row["utterance"],
                    "thesis": row["t"],
                    "antithesis": row["a"],
                    "ref_pass": bool(row.get("pass")),
                }
            )
    p2: list[dict[str, str]] = []
    for name in P2_FILES:
        path = RESULTS / name
        if not path.exists():
            continue
        for item in json.loads(path.read_text()):
            if not item.get("perspectives"):
                continue
            first = item["perspectives"][0]
            p2.append(
                {
                    "utterance": item["utterance"],
                    "thesis": first["thesis"],
                    "antithesis": first["antithesis"],
                    "ref_pass": bool(first.get("cc_pass")),
                }
            )
    return {"P": p, "V": v, "P2": p2}


def _load_state() -> dict[str, Any]:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"classifications": {}, "rows": {}}


def _save_state(state: dict[str, Any]) -> None:
    OUT.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def _key(arm: str, source: str, utterance: str) -> str:
    return f"{arm}|{source}|{utterance}"


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# --- generation ---------------------------------------------------------------


async def _classify(
    state: dict[str, Any], source: str, pair: dict[str, str]
) -> Optional[str]:
    """The thesis meaning for a pair, read once and cached (None = failed)."""
    from dialectical_framework.concerns.statement_classification import \
        StatementClassification

    ckey = f"{source}|{pair['utterance']}"
    cached = state["classifications"].get(ckey)
    if cached is not None:
        return cached["meaning"]
    if FROZEN_CLASSIFICATIONS and source in ("P", "V"):
        # Rounds after the first reuse the cached apex: the classifier prompt
        # may be mid-edit in src, and a re-read would move the condition.
        raise RuntimeError(f"no cached classification for {ckey}")
    # Production classifies the FULL text and stores the headline; V's thesis
    # is already the head's own wording, so it is classified as it stands.
    text = pair["utterance"] if source in ("P", "P2") else pair["thesis"]
    result = await StatementClassification().resolve(statement=text)
    state["classifications"][ckey] = {
        "meaning": result.meaning,
        "simple": bool(result.is_simple),
        "classified_text": text,
    }
    _save_state(state)
    return result.meaning


def _service(pair: dict[str, str], meaning: str, text: str):
    from dialectical_framework.concerns.aspect_generation import \
        AspectGeneration
    from dialectical_framework.concerns.statement_classification import \
        StatementClassification
    from dialectical_framework.graph.nodes.statement import Statement

    thesis = Statement(text=pair["thesis"], meaning=meaning)
    antithesis = Statement(
        text=pair["antithesis"],
        meaning=StatementClassification.lookup_antithesis_meaning(thesis),
    )
    svc = AspectGeneration()
    svc._thesis = thesis
    svc._antithesis = antithesis
    svc._text = text
    svc._not_like_these = []
    svc._existing_pps = []
    return svc


def _strip_apex(prompt: str) -> str:
    start = prompt.index("Taxonomy apex concepts for reference:")
    end = prompt.index("Build the tetrad as its two diagonal contradiction pairs")
    return prompt[:start] + prompt[end:]


def _strip_scales(prompt: str, max_words: int) -> str:
    start = prompt.index("Generate each aspect (1-")
    return prompt[:start] + f"Generate each aspect (1-{max_words} words)."


async def _production_call(
    prompt: str, dto: type[BaseModel], system: Optional[str] = None
) -> BaseModel:
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from dialectical_framework.concerns import aspect_generation

    conversation = ConversationFacilitator()
    conversation.set_system_prompt(system or aspect_generation.SYSTEM_PROMPT)
    return await conversation.submit(response_model=dto, user_content=prompt)


def _view_request(pair: dict[str, str], max_words: int) -> str:
    from dialectical_framework.concerns.view_sketch import view_sketch_prompt

    focus = (
        "the full perspective for ONE tension, with its two sides EXACTLY as "
        f'given and not reworded — thesis: "{pair["thesis"]}"; antithesis: '
        f'"{pair["antithesis"]}". Build the four aspects and both axes for it.'
    )
    return view_sketch_prompt(focus, max_words)


async def _viewstyle_call(
    pair: dict[str, str], *, think: bool = True, production_system: bool = False
) -> BaseModel:
    """Pipeline T/A fixed; the aspects by one json-mode call over the utterance
    as the conversation, with the view sketch's request and a texts-only DTO.

    `think=False` drops the thinking (K); `production_system=True` swaps the
    Consultant's persona + method for `AspectGeneration.SYSTEM_PROMPT` (S),
    keeping the utterance as the conversation's one user message.
    """
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from dialectical_framework.concerns import aspect_generation

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA,
        messages=[llm.messages.user(pair["utterance"])],
    )
    level = head._conversation._thinking_kwargs().get("thinking") if think else None
    turn = ConversationFacilitator(format_mode="json", thinking=level)
    if production_system:
        turn.set_system_prompt(aspect_generation.SYSTEM_PROMPT)
        turn.add_user_message(pair["utterance"])
    else:
        turn._messages = head._conversation._messages
    prompt = _view_request(pair, head._conversation.settings.component_length)
    return await turn.submit(FlatTetradDto, prompt)


async def _viewsys_produser_call(pair: dict[str, str], meaning: str) -> BaseModel:
    """The Consultant's system prompt and conversation, but the PRODUCTION user
    prompt and `TetradDto` (scores included), in the production call shape
    (forced tool, no thinking)."""
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from dialectical_framework.concerns.aspect_generation import TetradDto

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA,
        messages=[llm.messages.user(pair["utterance"])],
    )
    turn = ConversationFacilitator()
    turn._messages = head._conversation._messages
    prompt = _service(pair, meaning, "")._tetrad_prompt("")
    return await turn.submit(response_model=TetradDto, user_content=prompt)


def _texts(result: BaseModel) -> dict[str, str]:
    def text(value: Any) -> str:
        return (getattr(value, "statement", value) or "").strip()

    return {
        "t_plus": text(result.t_plus),
        "t_minus": text(result.t_minus),
        "a_plus": text(result.a_plus),
        "a_minus": text(result.a_minus),
        "axis_1": (result.t_plus_vs_a_minus_axis or "").strip(),
        "axis_2": (result.a_plus_vs_t_minus_axis or "").strip(),
    }


async def _generate(arm: str, pair: dict[str, str], meaning: str) -> dict[str, str]:
    from dialectical_framework.concerns.aspect_generation import TetradDto

    arm = arm.split("#", 1)[0]  # `#r1` / `#weak` reuse the named arm's prompt
    if arm in ("old", "new"):
        prompt = _service(pair, meaning, "")._tetrad_prompt("")
        system = _old_system_prompt() if arm == "old" else None  # None = live prompt
        return _texts(await _production_call(prompt, TetradDto, system))

    if arm == "viewstyle":
        return _texts(await _viewstyle_call(pair))
    if arm == "viewstyle_nothink":
        return _texts(await _viewstyle_call(pair, think=False))
    if arm == "prodsys_viewuser":
        return _texts(await _viewstyle_call(pair, production_system=True))
    if arm == "viewsys_produser":
        return _texts(await _viewsys_produser_call(pair, meaning))

    if arm.startswith("sys_"):
        prompt = _service(pair, meaning, "")._tetrad_prompt("")
        return _texts(await _production_call(prompt, TetradDto, _system_variant(arm)))

    text = pair["utterance"] if arm in ("ctx", "terms", "textonly_ctx") else ""
    svc = _service(pair, meaning, text)
    prompt = svc._tetrad_prompt("")
    dto: type[BaseModel] = TetradDto
    if arm == "noapex":
        prompt = _strip_apex(prompt)
    elif arm in ("textonly", "textonly_ctx"):
        prompt = _strip_scales(prompt, svc.settings.component_length)
        dto = FlatTetradDto
    elif arm == "terms":
        prompt = f"{prompt}\n\n{TERMS_LINE}"
    return _texts(await _production_call(prompt, dto))


async def _judge(aspects: dict[str, str]) -> dict[str, Any]:
    from dialectical_framework.concerns.control_statements_check import \
        ControlStatementsCheck

    s1 = f'"{aspects["t_plus"]}" without "{aspects["a_plus"]}" yields "{aspects["t_minus"]}"'
    s2 = f'"{aspects["a_plus"]}" without "{aspects["t_plus"]}" yields "{aspects["a_minus"]}"'
    a, b = await asyncio.gather(
        ControlStatementsCheck()._evaluate_control_statement(s1, ""),
        ControlStatementsCheck()._evaluate_control_statement(s2, ""),
    )
    return {
        "cc": [a.coherence_score, b.coherence_score],
        "dv": [a.dialectical_validity, b.dialectical_validity],
        "pass": a.coherence_score >= 0.7 and b.coherence_score >= 0.7,
    }


class _DriftVerdict(BaseModel):
    verdict: Literal["on_given", "drifted"] = Field(
        description=(
            "ON_GIVEN: the four aspects develop and overdevelop the thesis and the "
            "antithesis AS GIVEN. DRIFTED: one or more aspects are built on a "
            "reworded, shifted or substituted tension — a different thesis or "
            "antithesis than the two stated."
        )
    )
    reasoning: str = Field(description="One sentence: which aspect decided it.")


_DRIFT_SYSTEM = """You audit whether a tetrad's four aspects were built on the thesis and antithesis it was GIVEN.
T+ and T- must develop / overdevelop the given thesis; A+ and A- must develop / overdevelop the given antithesis. Rephrasing in other words is fine. DRIFT is when an aspect is really about a different position than the one given — the tension was quietly replaced by another one. Do not judge quality, only whether the given pair is what the aspects are about."""


async def _drift_audit(container: Any, state: dict[str, Any], pairs: dict[str, list[dict[str, str]]]) -> None:
    """One judge-model call per `viewstyle` row; no generation. Runs alone —
    `using_model` re-points the container, so nothing else may be in flight."""
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from e2e.config import E2EConfig
    from e2e.modelctx import using_model

    drift = state.setdefault("drift", {})
    judge_model = E2EConfig.from_env().judge_model
    sem = asyncio.Semaphore(5)

    async def one(row: dict[str, Any]) -> None:
        async with sem:
            try:
                conversation = ConversationFacilitator()
                conversation.set_system_prompt(_DRIFT_SYSTEM)
                verdict = await conversation.submit(
                    _DriftVerdict,
                    f'Given thesis: "{row["t"]}"\nGiven antithesis: "{row["a"]}"\n\n'
                    f'T+: "{row["t_plus"]}"\nT-: "{row["t_minus"]}"\n'
                    f'A+: "{row["a_plus"]}"\nA-: "{row["a_minus"]}"\n\n'
                    "Are the aspects built on the given pair?",
                )
                drift[row["utterance"]] = {
                    "verdict": verdict.verdict,
                    "reasoning": verdict.reasoning,
                    "judge": judge_model,
                }
            except Exception as exc:  # noqa: BLE001
                drift[row["utterance"]] = {"verdict": None, "error": repr(exc)[:200]}
            _save_state(state)

    todo = []
    for pair in pairs["P"]:
        row = state["rows"].get(_key("viewstyle", "P", pair["utterance"]))
        if row is None or row.get("error"):
            continue
        done = drift.get(pair["utterance"])
        if done is None or done.get("verdict") is None:
            todo.append(row)
    if not todo:
        return
    print(f"drift audit: {len(todo)} viewstyle row(s), judge {judge_model}", flush=True)
    with using_model(container, judge_model):
        await asyncio.gather(*(one(row) for row in todo))


async def _weak_tier(
    container: Any, state: dict[str, Any], pairs: dict[str, list[dict[str, str]]],
    started: float, budget_s: float, configured_model: str, retry_errors: bool,
) -> None:
    """`WEAK_ARMS`: GENERATION on the weak tier, judging on the configured model.

    Two phases, never interleaved, because `using_model` re-points the ONE
    container: entered per task inside a gather, overlapping contexts restore
    each other's "previous" and the batch ends on the wrong model. So the
    context is entered ONCE around the whole generation batch, every generation
    asserts the model it is about to call, and judging starts only after the
    context has exited and the configured model is asserted back.
    """
    from e2e.config import E2EConfig
    from e2e.modelctx import using_model

    weak_model = E2EConfig.from_env().tiers["weak"]
    sem = asyncio.Semaphore(5)
    to_generate = []
    for arm in WEAK_ARMS:
        for pair in pairs["P"]:
            row = state["rows"].get(_key(arm, "P", pair["utterance"]))
            if row is None or (retry_errors and row.get("error")):
                to_generate.append((arm, pair))

    async def generate(arm: str, pair: dict[str, str]) -> None:
        async with sem:
            if time.monotonic() - started > budget_s:
                return
            assert container.settings().ai_model == weak_model, container.settings().ai_model
            row: dict[str, Any] = {
                "arm": arm, "source": "P", "utterance": pair["utterance"],
                "t": pair["thesis"], "a": pair["antithesis"], "generator": weak_model,
            }
            t0 = time.monotonic()
            try:
                meaning = await _classify(state, "P", pair)  # cached; raises if not
                aspects = await _generate(arm, pair, meaning)
                row.update(aspects)
                if not all(aspects[k] for k in ("t_plus", "t_minus", "a_plus", "a_minus")):
                    row["error"] = "incomplete tetrad"
            except Exception as exc:  # noqa: BLE001
                row["error"] = repr(exc)[:300]
            row["seconds"] = round(time.monotonic() - t0, 1)
            state["rows"][_key(arm, "P", pair["utterance"])] = row
            _save_state(state)

    if to_generate:
        print(f"weak tier: generating {len(to_generate)} tetrad(s) on {weak_model}", flush=True)
        with using_model(container, weak_model):
            await asyncio.gather(*(generate(*item) for item in to_generate))
    assert container.settings().ai_model == configured_model, container.settings().ai_model

    to_judge = [
        row
        for arm in WEAK_ARMS
        for pair in pairs["P"]
        if (row := state["rows"].get(_key(arm, "P", pair["utterance"]))) is not None
        and not row.get("error") and "cc" not in row
    ]

    async def judge(row: dict[str, Any]) -> None:
        async with sem:
            if time.monotonic() - started > budget_s:
                return
            assert container.settings().ai_model == configured_model
            try:
                row.update(await _judge(row))
                row["judge"] = configured_model
            except Exception as exc:  # noqa: BLE001
                row["error"] = repr(exc)[:300]
            _save_state(state)
            print(f"  [{'PASS' if row.get('pass') else 'fail'}] {row['arm']:24s} weak  {row['utterance'][:48]}", flush=True)

    if to_judge:
        print(f"weak tier: judging {len(to_judge)} tetrad(s) on {configured_model}", flush=True)
        await asyncio.gather(*(judge(row) for row in to_judge))


async def _parentage_audit(
    container: Any, state: dict[str, Any], pairs: dict[str, list[dict[str, str]]],
    started: float, budget_s: float,
) -> None:
    """The archive's pole auditor on T+ and A+ of every `PARENTAGE_ARMS` row —
    `probe_tetrad_pole._audit_prompt` + `_PoleVerdict`, exactly as
    `probe_tetrad_quality._audit_parentage` runs it. Runs alone (`using_model`)."""
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from e2e.config import E2EConfig
    from e2e.modelctx import using_model
    from e2e.probe_tetrad_pole import _audit_prompt, _PoleVerdict

    store = state.setdefault("parentage", {})
    judge_model = E2EConfig.from_env().judge_model
    sem = asyncio.Semaphore(5)
    todo: list[tuple[str, dict[str, Any], str]] = []
    for arm in PARENTAGE_ARMS:
        for pair in pairs["P"]:
            key = _key(arm, "P", pair["utterance"])
            row = state["rows"].get(key)
            if row is None or row.get("error"):
                continue
            for field in ("t_plus", "a_plus"):
                if (store.get(key) or {}).get(field, {}).get("parent") is None:
                    todo.append((key, row, field))
    if not todo:
        return
    print(f"parentage audit: {len(todo)} plus(es), judge {judge_model}", flush=True)

    async def one(key: str, row: dict[str, Any], field: str) -> None:
        async with sem:
            if time.monotonic() - started > budget_s:
                return
            position = "T+" if field == "t_plus" else "A+"
            own, other = (row["t"], row["a"]) if field == "t_plus" else (row["a"], row["t"])
            try:
                conversation = ConversationFacilitator()
                conversation.set_system_prompt(_audit_prompt(own, other, position, row[field]))
                verdict = await conversation.submit(
                    _PoleVerdict, "Audit the aspect against the structural rule."
                )
                store.setdefault(key, {})[field] = {
                    "parent": verdict.parent,
                    "valence_ok": bool(verdict.valence_matches_claim),
                    "why": verdict.why,
                }
            except Exception as exc:  # noqa: BLE001
                store.setdefault(key, {})[field] = {"parent": None, "error": repr(exc)[:200]}
            _save_state(state)

    with using_model(container, judge_model):
        await asyncio.gather(*(one(*item) for item in todo))


async def _run(budget_s: float, retry_errors: bool) -> None:
    container = DialecticalReasoning.setup(Settings.from_env())
    pairs = _load_pairs()
    state = _load_state()
    started = time.monotonic()
    sem = asyncio.Semaphore(5)
    global FROZEN_CLASSIFICATIONS
    FROZEN_CLASSIFICATIONS = all(
        f"{source}|{pair['utterance']}" in state["classifications"]
        for source in ("P", "V")
        for pair in pairs[source]
    )
    configured_model = container.settings().ai_model
    todo: list[tuple[str, str, dict[str, str]]] = []
    for arm, source in ARMS:
        if arm in WEAK_ARMS:
            continue
        for pair in pairs[source]:
            row = state["rows"].get(_key(arm, source, pair["utterance"]))
            if row is None or (retry_errors and row.get("error")):
                todo.append((arm, source, pair))
    print(f"{len(todo)} item(s) to run; budget {budget_s:.0f}s", flush=True)

    # Classify every pair ONCE, before any arm runs: arms on one pair start
    # together, and a cache filled inside them would be read before written —
    # four arms, four classifications, four possibly different apex rows.
    async def classify(source: str, pair: dict[str, str]) -> None:
        async with sem:
            if time.monotonic() - started > budget_s:
                return
            try:
                await _classify(state, source, pair)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! classify {source} {pair['utterance'][:40]}: {exc!r}"[:200], flush=True)

    await asyncio.gather(
        *(
            classify(source, pair)
            for source in ("P", "V", "P2")
            for pair in pairs[source]
            if f"{source}|{pair['utterance']}" not in state["classifications"]
        )
    )

    async def one(arm: str, source: str, pair: dict[str, str]) -> None:
        async with sem:
            if time.monotonic() - started > budget_s:
                return
            key = _key(arm, source, pair["utterance"])
            row: dict[str, Any] = {
                "arm": arm,
                "source": source,
                "utterance": pair["utterance"],
                "t": pair["thesis"],
                "a": pair["antithesis"],
            }
            t0 = time.monotonic()
            try:
                meaning = await _classify(state, source, pair)
                aspects = await _generate(arm, pair, meaning)
                row.update(aspects)
                if not all(aspects[k] for k in ("t_plus", "t_minus", "a_plus", "a_minus")):
                    row["error"] = "incomplete tetrad"
                else:
                    row.update(await _judge(aspects))
            except Exception as exc:  # noqa: BLE001 — a probe records, never hides
                row["error"] = repr(exc)[:300]
            row["seconds"] = round(time.monotonic() - t0, 1)
            state["rows"][key] = row
            _save_state(state)
            tag = "ERR " if row.get("error") else ("PASS" if row.get("pass") else "fail")
            print(f"  [{tag}] {arm:9s} {source} {row['seconds']:5.1f}s  {pair['utterance'][:48]}", flush=True)

    await asyncio.gather(*(one(*item) for item in todo))
    await _weak_tier(container, state, pairs, started, budget_s, configured_model, retry_errors)
    left = sum(
        1
        for arm, source in ARMS
        for pair in pairs[source]
        if (row := state["rows"].get(_key(arm, source, pair["utterance"]))) is None
        or (not row.get("error") and "cc" not in row)
    )
    print(f"\ndone this invocation; {left} item(s) still to run", flush=True)
    if time.monotonic() - started < budget_s:
        await _drift_audit(container, state, pairs)
    if left == 0 and time.monotonic() - started < budget_s:
        await _parentage_audit(container, state, pairs, started, budget_s)


def _report() -> None:
    pairs = _load_pairs()
    state = _load_state()
    rows = state["rows"]

    def verdicts(arm: str, source: str) -> dict[str, Optional[bool]]:
        out: dict[str, Optional[bool]] = {}
        for pair in pairs[source]:
            row = rows.get(_key(arm, source, pair["utterance"]))
            if row is None or row.get("error"):
                out[pair["utterance"]] = None
            else:
                out[pair["utterance"]] = bool(row["pass"])
        return out

    base = verdicts("base", "P")
    view = verdicts("viewstyle", "P")

    def paired(v: dict[str, Optional[bool]], ref: dict[str, Optional[bool]]) -> str:
        both = only_arm = only_ref = neither = 0
        for u, x in v.items():
            b = ref.get(u)
            if x is None or b is None:
                continue
            if x and b:
                both += 1
            elif x:
                only_arm += 1
            elif b:
                only_ref += 1
            else:
                neither += 1
        return f"{both:2d}/{only_arm:2d}/{only_ref:2d}/{neither:2d}"

    print("arm                src  CC pass        95% Wilson  miss  vs base|P (both/only arm/only ref/neither)  vs viewstyle|P")
    for arm, source in ARMS:
        v = verdicts(arm, source)
        scored = [x for x in v.values() if x is not None]
        k, n = sum(scored), len(scored)
        lo, hi = _wilson(k, n)
        missing = len(v) - n
        line = f"{arm:24s} {source}    {k:2d}/{n:2d} ({100*k/max(n,1):3.0f}%)  {100*lo:3.0f}–{100*hi:3.0f}%    {missing:2d}"
        if source == "P" and arm != "base":
            line += f"    {paired(v, base)}"
        elif (arm, source) == ("base", "V"):
            line += f"    {paired(v, base)}"
        else:
            line += "    " + " " * 11
        if (arm, source) != ("viewstyle", "P"):
            line += f"                              {paired(v, view)}"
        print(line)

    for source, label in (("P", "pipeline's own first tetrad"), ("V", "view turn's own tetrad")):
        ref = sum(1 for pair in pairs[source] if pair["ref_pass"])
        print(f"reference: {label} passed {ref}/{len(pairs[source])} on these pairs")
    harness = verdicts("base", "P")
    agree = sum(
        1
        for pair in pairs["P"]
        if harness[pair["utterance"]] is not None
        and harness[pair["utterance"]] == pair["ref_pass"]
    )
    scored = sum(1 for x in harness.values() if x is not None)
    print(f"harness base|P vs the pipeline's own verdict on the same pair: agree {agree}/{scored}")
    def count2(v: dict[str, Optional[bool]]) -> tuple[int, int]:
        xs = [x for x in v.values() if x is not None]
        return sum(xs), len(xs)

    # --- round 4: replication and weak tier ---
    def count(arm: str) -> tuple[int, int]:
        v = [x for x in verdicts(arm, "P").values() if x is not None]
        return sum(v), len(v)

    if any(k.startswith("base#r") for k in rows):
        print("\nreplication (configured model), base vs sys_no_plus_mistake:")
        pooled = {"base": [0, 0], "sys_no_plus_mistake": [0, 0]}
        fresh = {"base": [0, 0], "sys_no_plus_mistake": [0, 0]}
        for suffix in ("", "#r1", "#r2"):
            b, c = verdicts("base" + suffix, "P"), verdicts("sys_no_plus_mistake" + suffix, "P")
            kb, nb = count("base" + suffix)
            kc, nc = count("sys_no_plus_mistake" + suffix)
            print(f"  generation {suffix or 'first'}: base {kb}/{nb}  cut {kc}/{nc}  paired cut vs base (both/only cut/only base/neither) {paired(c, b)}")
            for name, k, n in (("base", kb, nb), ("sys_no_plus_mistake", kc, nc)):
                pooled[name][0] += k; pooled[name][1] += n
                if suffix:
                    fresh[name][0] += k; fresh[name][1] += n
        for label, table in (("fresh two generations", fresh), ("pooled three generations", pooled)):
            for name, (k, n) in table.items():
                lo, hi = _wilson(k, n)
                print(f"  {label}: {name:20s} {k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)")
    if any(k.startswith("base#weak") for k in rows):
        gens = {r.get("generator") for r in rows.values() if r["arm"] in WEAK_ARMS}
        errs = sum(1 for r in rows.values() if r["arm"] in WEAK_ARMS and r.get("error"))
        print(f"\nweak tier (generator {gens}; errors {errs}):")
        for arm in WEAK_ARMS:
            k, n = count(arm); lo, hi = _wilson(k, n)
            print(f"  {arm:26s} CC {k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)")
        print(f"  paired cut vs base (both/only cut/only base/neither) {paired(verdicts(WEAK_ARMS[1], 'P'), verdicts(WEAK_ARMS[0], 'P'))}")

    if any(k.startswith("old#p2") for k in rows):
        ref = sum(1 for pair in pairs["P2"] if pair["ref_pass"])
        print(f"\nP2 — the cut pipeline run's own first-tetrad pairs (pipeline's own verdict: {ref}/{len(pairs['P2'])}):")
        tot = {"old": [0, 0], "new": [0, 0]}
        for g in ("p2r1", "p2r2"):
            o, n_ = verdicts(f"old#{g}", "P2"), verdicts(f"new#{g}", "P2")
            ko, no = count2(o); kn, nn = count2(n_)
            tot["old"][0] += ko; tot["old"][1] += no; tot["new"][0] += kn; tot["new"][1] += nn
            agree = sum(1 for pair in pairs["P2"] if n_.get(pair["utterance"]) is not None and n_[pair["utterance"]] == pair["ref_pass"])
            print(f"  generation {g}: old {ko}/{no}  new {kn}/{nn}  paired new vs old (both/only new/only old/neither) {paired(n_, o)}  | new agrees with pipeline verdict {agree}/{nn}")
        for name, (k, n) in tot.items():
            lo, hi = _wilson(k, n)
            print(f"  {name}: {k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)")

    parentage = state.get("parentage", {})
    if parentage:
        print("\nplus parentage (T+ and A+, out of 80): own_pole / other_pole / neither / unreadable | valence false | restatement (own_pole & valence false) | unjudged")
        for arm in PARENTAGE_ARMS:
            counts = {"own_pole": 0, "other_pole": 0, "neither": 0, "unreadable": 0}
            valence_false = restated = unjudged = 0
            for pair in pairs["P"]:
                entry = parentage.get(_key(arm, "P", pair["utterance"])) or {}
                for field in ("t_plus", "a_plus"):
                    verdict = entry.get(field) or {}
                    if verdict.get("parent") is None:
                        unjudged += 1
                        continue
                    counts[verdict["parent"]] += 1
                    if not verdict["valence_ok"]:
                        valence_false += 1
                        if verdict["parent"] == "own_pole":
                            restated += 1
            print(f"  {arm:24s} {counts['own_pole']:2d} / {counts['other_pole']:2d} / {counts['neither']:2d} / {counts['unreadable']:2d} | {valence_false:2d} | {restated:2d} | {unjudged:2d}")
    drift = state.get("drift", {})
    if drift:
        groups: dict[str, list[bool]] = {}
        for u, d in drift.items():
            x = view.get(u)
            if d.get("verdict") is None or x is None:
                continue
            groups.setdefault(d["verdict"], []).append(x)
        for name, xs in sorted(groups.items()):
            print(f"drift audit of viewstyle: {name} {len(xs)}/40, CC pass {sum(xs)}/{len(xs)}")
        unjudged = sum(1 for d in drift.values() if d.get("verdict") is None)
        if unjudged:
            print(f"drift audit: {unjudged} row(s) not judged")
    simple = sum(1 for c in state["classifications"].values() if c.get("simple"))
    print(f"classifications cached: {len(state['classifications'])} ({simple} SIMPLE)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--budget", type=float, default=520.0)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    if args.report:
        _report()
        return
    asyncio.run(_run(args.budget, args.retry_errors))
    _report()


if __name__ == "__main__":
    main()
