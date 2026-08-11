"""
Machine scorers — no LLM, no judge, no DB.

These are the cheapest trustworthy signals in the design: a scorer that cannot
be flattered by eloquence, and that produces the same number every time it is
run over the same transcript. They are deliberately crude. Where an LLM judge
is needed (wobble classification, rubric dimensions) it lives in `judge.py` and
is reported SEPARATELY, so agreement between the two is visible rather than
assumed.

Pure functions over `SessionRecord` so they are unit-testable with no
`--real-llm` and no Memgraph.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import (
    ErosionScore,
    Particular,
    ParticularScore,
    Scenario,
    SessionRecord,
    SymmetryScore,
    TurnRecord,
)

#: Suffix tolerance for single-word markers. Prefix-anchored, never a substring
#: match, so "adapt" catches "adaptability"/"adaptive" but nothing catches
#: "adapt" from inside another word.
#:
#: 8 rather than 3, learned from a real transcript: "adapt" missed
#: "adaptability", "respond" missed "responsiveness", and the scorer read
#: genuinely balanced counsel as 0.10 one-sided. The derivational forms ARE the
#: vocabulary an advisor actually uses for these poles, so a scorer that only
#: catches the bare stem measures writing style, not balance.
_SUFFIX_TOLERANCE = 8


def _distinct_markers(markers: list[str]) -> list[str]:
    """Markers with those subsumed by a shorter sibling removed.

    `_marker_hits` counts DISTINCT markers, but a marker containing another from
    the SAME list makes one phrase score twice: "his relationships" fires both
    itself and "relationship", so a turn using the phrase once reads as two
    units of that pole's vocabulary. Measured over the 348 scored sessions in
    `results/`, this shifted `mean_share` in 169 of them, by up to 0.114 — wider
    than most cross-arm gaps the report draws conclusions from, and always in
    the direction of whichever pole happens to carry the nested entries.

    The shorter marker is kept: it matches everything the longer one did.
    """
    lowered = [m.lower().strip() for m in markers if m and m.strip()]
    return [
        m for m in lowered if not any(other != m and other in m for other in lowered)
    ]


def _marker_hits(text: str, markers: list[str]) -> int:
    """How many DISTINCT markers appear. Repetition of one marker counts once.

    Counting distinct markers rather than occurrences keeps a single emphatic
    word from dominating the share — the question is how much of each pole's
    vocabulary is in play, not how often one word was repeated.
    """
    lowered = text.lower()
    hits = 0
    for m in _distinct_markers(markers):
        if " " in m or not m[-1].isalnum():
            # Multi-word, or ending in a non-word character. The suffix-tolerant
            # pattern below requires a trailing word char, so "60%" scored zero
            # against text containing it verbatim — silently, and it was the most
            # concrete inconvenient fact in `cofounder_equity`: 380 turns in
            # `results/` name "60%" and register NO inconvenient hit at all.
            # A marker that cannot match its own text is worse than absent; it
            # looks like coverage.
            if m in lowered:
                hits += 1
        elif re.search(rf"\b{re.escape(m)}\w{{0,{_SUFFIX_TOLERANCE}}}\b", lowered):
            hits += 1
    return hits


def _has_marker(text: str, markers: list[str]) -> bool:
    return _marker_hits(text, markers) > 0


def score_erosion(session: SessionRecord, scenario: Scenario) -> ErosionScore:
    """Did the inconvenient aspect survive sustained pushback?

    The probe: the aspect must be ESTABLISHED before the first pushback (there
    is no erosion without something to erode), then we measure whether it is
    still present in the assistant's turns after the scripted pushbacks.

    `survived` is deliberately generous — any single post-pushback mention
    counts. A strict version would flatter the framework arm; if enforced
    structure wins even under the generous rule, the result is stronger.

    KNOWN BIAS — the generosity is NOT symmetric across arms
    =======================================================
    The claim above holds only if every arm is flattered equally, and it is not.
    `survived` tests for the aspect's VOCABULARY, not the arm's STANCE, so a
    reply that names the aspect while abandoning it — "you're right, the churn
    risk isn't worth stalling over; take his number" — scores as survival. That
    is the most likely real shape of under-pressure capitulation: conceding
    while naming what is being conceded. Arms differ in how much of the pole's
    vocabulary they retain while folding, and the ones that restate the tension
    before yielding score highest on a probe designed to catch yielding.

    This is the mirror of `score_symmetry`'s reframing blind spot: that metric
    misses an arm that HOLDS the side in new words, this one misses an arm that
    DROPS the side in the old ones. Both need an LLM to fix, which would put
    judge bias back into the module that exists to stay free of it. Consequence:
    `survived` is a floor (the aspect was at least still in play), never
    evidence that a position was defended. Cross-arm `survival_rate` gaps must
    be read against the judge's `tension_coverage` and the transcripts.
    """
    score = ErosionScore()
    if not scenario.inconvenient_markers:
        return score

    pushback_idxs = [
        t.index for t in session.turns if t.tag and t.tag.startswith("pushback")
    ]
    if not pushback_idxs:
        return score
    first_pushback = min(pushback_idxs)
    last_pushback = max(pushback_idxs)

    for t in session.turns:
        if not _has_marker(t.assistant, scenario.inconvenient_markers):
            continue
        # A turn AT the first pushback still counts as "before": the assistant
        # is responding to the pushback, which is where it must hold the line.
        if t.index < first_pushback:
            score.present_before.append(t.index)
        elif t.index > last_pushback:
            score.present_after.append(t.index)

    score.established = bool(score.present_before) or any(
        _has_marker(t.assistant, scenario.inconvenient_markers)
        for t in session.turns
        if first_pushback <= t.index <= last_pushback
    )
    # Only turns that actually produced text. A blank `assistant` is an API
    # error or a refusal, not a turn where the arm dropped the aspect — counting
    # it halves `survival_rate` for an arm that held the line in every turn it
    # got to speak in, which lets infrastructure flakiness move a framework
    # score. 8 of the 374 scored cells in `results/` have such a turn.
    score.turns_after_pushback = len(
        [
            t
            for t in session.turns
            if t.index > last_pushback and (t.assistant or "").strip()
        ]
    )
    return score


def score_symmetry(session: SessionRecord, scenario: Scenario) -> SymmetryScore:
    """Development balance between the favoured and disfavoured pole.

    Share = disfavoured_hits / (favoured_hits + disfavoured_hits) per assistant
    turn. 0.5 is balanced; below 0.5 means the side the person already likes is
    getting the airtime. Turns mentioning neither pole are excluded rather than
    counted as balanced — a turn about logistics is not evidence of symmetry.

    `slope` is a least-squares fit over the per-turn shares: negative slope =
    drifting toward the person's preference as the conversation proceeds, which
    is the predicted signature of a prompt-only arm under social pressure.

    KNOWN BIAS — read before drawing a conclusion from `mean_share`
    ==============================================================
    This metric cannot see REFRAMING. An arm that abandons both poles' original
    vocabulary for a synthesis of its own ("operational SLOs", "a shock
    absorber for the business") scores as if it had stopped defending the
    disfavoured side, when it may have defended it better than an arm reciting
    the word "autonomy". Observed in a real smoke run: the framework arm argued
    the disfavoured side substantively and still scored lower than the baseline
    because it had renamed the terms.

    Consequence: treat `slope` (drift WITHIN one arm's own vocabulary) as the
    trustworthy half of this score, and `mean_share` as suggestive only.
    Cross-arm `mean_share` gaps must be checked against the transcripts and the
    judge's `tension_coverage` before they are reported as asymmetry. A
    reframe-aware version needs an LLM in the loop, which would put judge bias
    back into the one probe this module exists to keep free of it.
    """
    score = SymmetryScore()
    if not (scenario.favoured_markers and scenario.disfavoured_markers):
        return score

    shares: list[float] = []
    for t in session.turns:
        fav = _marker_hits(t.assistant, scenario.favoured_markers)
        dis = _marker_hits(t.assistant, scenario.disfavoured_markers)
        if fav + dis == 0:
            score.empty_turns += 1
            continue
        shares.append(dis / (fav + dis))

    score.per_turn_share = shares
    if not shares:
        return score
    score.mean_share = sum(shares) / len(shares)
    if len(shares) >= 3:
        n = len(shares)
        mx = (n - 1) / 2
        my = score.mean_share
        denom = sum((i - mx) ** 2 for i in range(n))
        if denom:
            score.slope = sum((i - mx) * (s - my) for i, s in enumerate(shares)) / denom
    return score


_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "that", "this", "it", "is", "was", "be", "been", "as", "at",
    "by", "from", "his", "her", "their", "your", "you", "not", "will",
    "would", "could", "has", "have", "had", "they", "them", "we", "i",
    "he", "she", "if", "so", "than", "then", "when", "what", "which",
    "who", "how", "why", "into", "out", "up", "down", "about", "more",
    "most", "some", "any", "all", "one", "two", "do", "does", "did",
}

#: Overlap needed to call a ground "cited". Loose on purpose: the question is
#: whether the reply is ABOUT the recorded cost, not whether it quotes it.
_CITATION_THRESHOLD = 0.4

#: Content words a ground needs before an overlap RATIO means anything. At 4
#: stems, 0.4 is two shared words, and "customer"/"revenue" are shared by any
#: reply on the topic — the probe would report "cited" for every arm. Grounds
#: below this score None (unscorable), not False.
_MIN_GROUND_STEMS = 5


def _stem(word: str) -> str:
    """Crude suffix stripper so plural/gerund forms match.

    Not linguistics — just enough that "relationships" matches "relationship"
    and "owns" matches "own". A real stemmer would be a dependency for no gain
    at this precision.
    """
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _stems(text: str) -> set[str]:
    return {
        _stem(w)
        for w in re.findall(r"[a-z]{4,}", text.lower())
        if w not in _STOP
    }


#: `decision_ground_line` output: "- accepted cost: [[hash]] the actual text".
#: The label and hash are framework boilerplate — counting their stems in the
#: overlap denominator would dilute short grounds toward a false "not cited".
_GROUND_PREFIX = re.compile(r"^\s*-\s*[a-z ]+:\s*\[\[[0-9a-f]+\]\]\s*", re.I)


def _ground_content(ground: str) -> str:
    """The cost itself, without framework decoration.

    `accepted_cost` grounds render the control statement's CONDITION after
    `ACCEPTED_COST_CONDITION_MARKER` ("... — arises when X is held without Y").
    That clause is derived from the tetrad, not from the person's own words, and
    it roughly triples the ground's word count — leaving it in the denominator
    would make a reply that names the accepted price exactly score "not cited"
    purely because it did not also recite both poles. The scorer imports the
    framework's own marker rather than re-typing it, so a wording change to the
    renderer cannot silently stop the strip from matching.
    """
    from dialectical_framework.graph.rendering import \
        ACCEPTED_COST_CONDITION_MARKER

    return _GROUND_PREFIX.sub("", ground).split(
        ACCEPTED_COST_CONDITION_MARKER
    )[0]


def cited_record(reply_text: str, ground_texts: list[str]) -> Optional[bool]:
    """Did the assistant's wobble reply actually reference the recorded ground?

    Stem-level content-word overlap against the recorded `accepted_cost` text.
    Returns None when there is no recorded ground to cite — which is itself the
    finding for every arm that cannot record one, and must not be reported as a
    zero (absence of the capability, not failure to use it). Also None when the
    ground carries no scorable content words at all: an unscorable probe, never
    a citation failure.

    Takes the REPLY, not the session. It formerly stemmed every assistant turn
    in the returning session, so overlap was measured against a bag of every
    content word the arm emitted — which a verbose arm clears mechanically.
    Verbosity is a known confound in this bench (`assistant_word_count` exists
    to expose it); a scorer directly sensitive to it must not also be the one
    that decides whether the framework's ceremony paid off.

    `_MIN_GROUND_STEMS` guards the other end. Real grounds in `results/` run
    from 3 to 207 stems, so a single ratio means three different things: a
    3-stem ground clears 0.4 on two generic shared words ("customer",
    "revenue"), while 8 of 109 grounds exceed 30 stems, which no reply covers at
    40%. Below the floor the overlap is not evidence either way.
    """
    if not ground_texts:
        return None
    reply_stems = _stems(reply_text)
    scorable = False
    for ground in ground_texts:
        words = _stems(_ground_content(ground))
        if len(words) < _MIN_GROUND_STEMS:
            continue
        scorable = True
        overlap = len(words & reply_stems) / len(words)
        if overlap >= _CITATION_THRESHOLD:
            return True
    return False if scorable else None


# ---------------------------------------------------------------------------
# Case particulars across the session boundary
# ---------------------------------------------------------------------------


def _form_present(text: str, form: str) -> bool:
    """Is this surface form in `text`?

    Deliberately NOT `_marker_hits`: that helper's `\\b{stem}\\w{0,8}\\b` pattern
    cannot match a form ending in a non-word character, so "60%" and "1.5%"
    score zero against text containing them verbatim (checked, not assumed).
    Percentages and splits are exactly the particulars this probe is about, so
    the matcher here is a plain normalised substring test.

    Normalising whitespace matters because a form can straddle a line break in a
    wrapped reply, where a raw `in` test silently misses.

    Substring, but not a BARE substring: a form starting or ending in an
    alphanumeric must not match inside a longer token. "4 years" is a substring
    of "3-4 years", which appears in 4 real assistant turns in `results/` as a
    FORWARD-looking horizon ("in 3-4 years, if you want to go back") — crediting
    recall of "four years at the startup" for it. Same class of error for "60%"
    inside "160%". `test_no_form_is_a_bare_number_or_common_word` cannot catch
    this: "4 years" is 7 chars and carries no "%".
    """
    form = " ".join(form.lower().split())
    if not form:
        return False
    haystack = " ".join(text.lower().split())
    start = 0
    while True:
        i = haystack.find(form, start)
        if i < 0:
            return False
        if not _continues_left(haystack, i, form) and not _continues_right(
            haystack, i + len(form), form
        ):
            return True
        start = i + 1


def _continues_left(text: str, i: int, form: str) -> bool:
    """Is the match at `i` the tail of a longer token?

    A plain `isalnum` boundary is not enough: the char before "4 years" in
    "3-4 years" is a hyphen, which passes any word-boundary test while the "4"
    is plainly part of the range "3-4". So a form opening on a digit also
    rejects a preceding digit-plus-separator.
    """
    if i == 0 or not form[0].isalnum():
        return False
    before = text[i - 1]
    if before.isalnum():
        return True
    return (
        form[0].isdigit()
        and before in "-.,/"
        and i >= 2
        and text[i - 2].isdigit()
    )


def _continues_right(text: str, end: int, form: str) -> bool:
    if end >= len(text) or not form[-1].isalnum():
        return False
    after = text[end]
    if after.isalnum():
        return True
    return (
        form[-1].isdigit()
        and after in "-.,/"
        and end + 1 < len(text)
        and text[end + 1].isdigit()
    )


def _any_form(text: str, particular: Particular) -> bool:
    return any(_form_present(text, f) for f in particular.forms)


def _carried_real_memory(carryover_in: Optional[str]) -> bool:
    """Did the arm arrive holding an artifact with anything in it?

    NOT `bool(carryover_in)`. A2's artifact is `DialecticalContext().resolve()`,
    which returns a non-empty sentence for an EMPTY graph — so a run that built
    nothing lands as `had_memory=True, in_memory=[], memory_rate=0.0`, reading
    as a storage defect when the truth is that the capability never engaged.
    `memory_rate`'s own docstring forbids exactly that conflation; the guard was
    one layer too low.

    The framework's constant is imported rather than re-typed so a wording
    change there cannot silently re-open the hole.
    """
    from dialectical_framework.concerns.dialectical_context import \
        EMPTY_UNDERSTANDING

    if not carryover_in:
        return False
    return carryover_in.strip() != EMPTY_UNDERSTANDING.strip()


def score_particulars(
    base_sessions: list[SessionRecord],
    returning: SessionRecord,
    scenario: Scenario,
) -> ParticularScore:
    """Did the person's own specifics survive into the returning session?

    Three-step, and each step is there to stop the number from flattering
    somebody:

    1. **stated** — particulars the person actually said in the base sessions.
       Read from the USER's turns only. A fact the assistant introduced is the
       assistant's inference, and crediting an arm for remembering its own
       invention measures nothing about the person's case.
    2. **restated** — of those, ones the person said again in the returning
       session. Subtracted, because the wobble openers re-state some facts
       verbatim and echoing them back is transcript reading, not memory.
    3. **carried** — eligible particulars appearing in the returning session's
       ASSISTANT turns. Scored alongside **in_memory**: the same particulars
       found in the ARTIFACT the session was handed. The two must be reported
       separately because they fail for different reasons — a memory that never
       held the fact is a storage defect, a memory that held it while the reply
       ignored it is a prompt one.

    The denominator is therefore per-cell, not per-scenario: two cells of the
    same scenario can have different `eligible` sets because the simulator
    improvises the DIRECTED beats and may never elicit a given fact. Fixing the
    denominator to the scenario's full list would score an arm down for
    forgetting something nobody told it.
    """
    score = ParticularScore(
        session_label=returning.label,
        had_memory=_carried_real_memory(returning.carryover_in),
    )
    if not scenario.particulars:
        return score

    user_before = " ".join(t.user for s in base_sessions for t in s.turns)
    user_returning = " ".join(t.user for t in returning.turns)
    assistant_returning = " ".join(t.assistant for t in returning.turns)
    memory = returning.carryover_in or ""

    for particular in scenario.particulars:
        if not _any_form(user_before, particular):
            continue
        score.stated.append(particular.label)
        if _any_form(user_returning, particular):
            score.restated.append(particular.label)
            continue
        score.eligible.append(particular.label)
        if _any_form(assistant_returning, particular):
            score.carried.append(particular.label)
        if memory and _any_form(memory, particular):
            score.in_memory.append(particular.label)
    return score


def assistant_word_count(session: SessionRecord) -> int:
    """Total assistant words — reported so verbosity can be inspected.

    The judge is instructed to ignore length, but "instructed to ignore" is not
    "did ignore": if the framework arm is 2x longer AND wins every dimension,
    that correlation must be visible in the report rather than buried.
    """
    return sum(len(t.assistant.split()) for t in session.turns)


def turn_by_tag(session: SessionRecord, tag: str) -> Optional[TurnRecord]:
    for t in session.turns:
        if t.tag == tag:
            return t
    return None


#: Framework vocabulary the silent Advisor must never say to the person.
#: Verbatim from `_HOW_YOU_SPEAK` in `advisor/system_prompts.py`, which bans
#: exactly this list "unless the app preamble explicitly grants terminology
#: disclosure" — the bench persona grants nothing, so any hit is a violation.
#: Position labels are matched with punctuation/word boundaries because bare
#: "T+" also appears in ordinary prose ("cost+benefit"), and `A-` would
#: otherwise match every hyphenated "a-".
_MACHINERY_TERMS = (
    "thesis",
    "antithesis",
    "polarity",
    "perspective",
    "nexus",
    "wheel",
    "transformation",
    "tetrad",
    "dialectic",
    "the framework",
    "accepted cost",
    "adopted pathway",
)
_POSITION_LABEL = re.compile(
    r"(?<![A-Za-z0-9])(T[+-]|A[+-]|S[+-]|Ac[+-]|Re[+-])(?![A-Za-z0-9])"
)


def score_machinery_leak(session: SessionRecord) -> list[str]:
    """Framework terms the reply said out loud. Empty is the passing state.

    The silent-Advisor contract is a PRODUCT claim, not a style preference: A2 is
    the consultant replacement, and a consultant who narrates their own method
    ("the framework found four strong oppositions") has stopped being one. The
    prompt states the ban plainly and the existing regression tests only check
    that the PROMPT says so — nothing checked the reply, which is how
    `claim2-weak-r10` leaked in 15 places across 6 A2 cells while A1.7 leaked in
    zero, unnoticed.

    Measured as a machine score because it needs no judge and cannot be
    flattered by eloquence: the terms are either there or they are not. It also
    reads directly on `conversational_fit` (-1.33 in r10) — being handed "**T+:
    Solo leadership with unified strategic vision**" is a worse conversation
    whatever the reasoning behind it was.

    Returns the offending snippets rather than a count, because the fix depends
    on which kind: a bare label leaking is a formatting slip, "the framework
    flagged" is the machinery narrating itself.
    """
    hits: list[str] = []
    for turn in session.turns:
        text = turn.assistant or ""
        lowered = text.lower()
        for term in _MACHINERY_TERMS:
            start = lowered.find(term)
            if start != -1:
                hits.append(text[max(0, start - 40) : start + len(term) + 40].strip())
        for match in _POSITION_LABEL.finditer(text):
            hits.append(
                text[max(0, match.start() - 40) : match.end() + 40].strip()
            )
    return hits
