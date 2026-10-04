"""The document instrument: `ingest` on real-length material, both per-thesis builds.

Until 2026-10-02 every tetrad-quality figure came from one-sentence Inputs, and
`ingest` is a document procedure. This runs `AnalysisPipeline(text=document)`
on five documents written for the probe — several tensions each, 400–700 words,
authored by the assistant (a bias, recorded; replace with real material when
some exists) — once with the staged per-thesis build (the antithesis ladder +
the four-aspect call) and once with the one-shot writer per extracted thesis
(`analyst.BUILD_PER_THESIS_ONE_SHOT`), and judges every perspective with the
same coherence judge and the same antithesis / parentage auditors as
`probe_tetrad_quality.py`. Extraction is shared by both arms, so the theses
are the same material read the same way; what differs is the build.

    INGEST_DOC_ARMS=staged poetry run pytest tests/e2e/probe_ingest_documents.py --real-llm -q -s
    INGEST_DOC_SET=authored ...                # the five documents written for the probe (default: public)
    (the `oneshot` arm is historical since the route it measured was removed)
    INGEST_DOC_LIMIT=2 ...                     # the first two documents only

One Case per (document, arm). Sequential: one graph writer at a time, and the
auditors run under `using_model`, which re-points the container.
"""

from __future__ import annotations

import collections
import json
import os
import statistics
import time
from pathlib import Path

import pytest

from e2e.config import E2EConfig
from e2e.probe_tetrad_quality import (_audit_kind, _audit_parentage,
                                      _audit_pluses, _wilson)

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"

DOCUMENTS: dict[str, str] = {
    "founder_memo": """Memo to myself before Thursday's board call.

We have eleven months of runway at the current burn and a product that finally works for the
customers we have. The board wants us to raise now, while the numbers look good, and spend the
next eighteen months buying growth: paid acquisition, two more sales hires, a second market.
Their argument is that the window closes — if we grow slowly the category gets defined by
someone with more money, and our head start is worth nothing. I believe that argument. I also
believe that the moment we take the money we stop being able to say no to anything: the hires
have to be fed with leads, the leads have to be bought, and the product roadmap turns into
whatever closes the next quarter.

What we have that nobody else has is that our customers renew without being asked. That came
from three years of saying no to features and fixing the ones we had. Every conversation I have
had with a founder who raised a big round at this stage says the same thing: the first year was
glorious and the second was spent managing the consequences of the first.

I keep landing on a middle path — raise a smaller round, hire one person, grow at the speed the
product can bear — and I distrust it precisely because it feels comfortable. The honest version
of the board's position is that comfort is how good companies stay small. The honest version of
mine is that speed is how good companies become mediocre ones with more customers.

Decisions I am avoiding: whether I actually want to run a company of eighty people; whether
Mara, who built the product, would stay through a year of growth hiring; and whether I am
protecting the product or protecting my own way of working.""",
    "product_retro": """Retrospective: the Q3 release.

We shipped on the date. That is the first time in four releases, and the team is proud of it,
and they should be. We also shipped with the sync feature behind a flag because it was not
ready, and with two known bugs in the export path that we decided were acceptable. Support
tickets are up thirty percent since launch; most are the export bugs, some are confusion about
the half-visible sync.

The argument in the room split two ways and it has not resolved. One side: the date was the
point. We committed to it publicly, sales sold against it, and every previous slip taught
customers that our dates mean nothing. Holding it rebuilt trust that is worth more than two bugs.
The other side: the date was never the point; the product was. We hit a date by lowering the bar,
and the thirty percent in tickets is the cost arriving on a different budget line. Trust in dates
bought with distrust in quality is not a trade, it is a loan.

What I notice is that both sides are describing the same release and both are right about what
they describe. The people who held the date are the ones who talk to customers about commitments.
The people who wanted to slip are the ones who answer the tickets.

Process questions that came up and that I do not want to lose: whether a release should be
allowed to ship behind flags at all, or whether a flag is a slip wearing a costume; whether the
definition of done belongs to engineering or to the people who carry the consequences; and
whether our estimates were wrong or our scope was. The retro ended with a plan to estimate
better. I am not sure estimating was the problem.""",
    "care_letter": """A letter I am not sure I will send.

Dad, you have asked us three times now to stop raising the question of the house, and each time
I have agreed, and each time I have gone home and lain awake. So I am writing instead.

You are eighty-one. The house has stairs you take slowly and a garden you can no longer manage
without the neighbour's son, who will leave for university next year. You fell in March and did
not tell us for a week. You still drive to the shop, and I have seen the dent on the gatepost.

What you say is that the house is your life: fifty years of it, Mum's garden, the room where we
grew up. That moving is the beginning of the end and you would rather have two years there than
ten anywhere else. I do not think you are wrong about that. I think you are right, and it is the
thing I cannot say to Anna because she thinks I am letting you die of pride.

What Anna says is that love means keeping you safe, and that we will be the ones who find you at
the bottom of the stairs, and that you are asking us to carry a risk you will not look at. I do
not think she is wrong either.

So I am stuck between two things that are both true. If we move you, we keep you alive and we
take your life. If we leave you, we honour your life and we wait for the phone call. Everything
in between — the carer who comes twice a week, the rail on the stairs, the promise to stop
driving — you have treated as the thin end of the wedge, and perhaps it is.

I do not know what I am asking. Maybe only that you read this and know that the question is not
going away, and that it is not coming from a wish to manage you.""",
    "process_complaint": """Why I am leaving the platform team — a note for whoever reads exit notes.

For two years the platform team has run on the principle that engineers own their work end to
end: you pick what matters, you build it, you run it. It made us fast and it made us good, and it
is the reason I joined. It is also why nothing we build fits together. Four services, four
logging formats, three ways to deploy, and an on-call rotation where the person paged does not
understand the thing that paged them.

The new director's answer is process: a shared platform roadmap, design reviews before code,
one deployment path, estimates. Half the team hears this as the end of the thing that made the
job worth having. I half-hear it that way too. But I also wrote the fourth logging format, and I
know why I did: because asking would have taken a week and writing it took an afternoon.

What I think the director gets right: autonomy without coordination is not autonomy, it is
twelve people making the same decision twelve times. What I think the team gets right: every
process we have ever added was added to stop a specific pain and then outlived it, and nobody
removes process.

What I do not hear anyone saying is that these are the same problem from two ends. The team wants
to keep deciding; the director wants the decisions to add up. A design review that asks "does
this fit" is coordination. A design review that asks "did you get approval" is control. We have
been arguing about the first while fearing the second.

I am leaving for other reasons. But I would stay for a team that could hold both of those at
once, and I have not seen one.""",
    "policy_note": """Briefing note: the proposal to close the town centre to cars.

The proposal would close the four central streets to private vehicles from 7 am to 7 pm, with
access for deliveries before 10 and for residents' permits at all times. Supporters cite the
pilot: footfall up eighteen percent on the two closed Saturdays, air quality readings down
sharply, and the café owners' association in favour. Opponents cite the same pilot: the three
shops on Mill Street reported their worst two Saturdays of the year, because their customers
come by car from the villages and did not come.

Both are reading the same data correctly. The centre as a whole did better; the edges of the
centre did worse. The pilot moved trade from the shops that depend on the villages to the shops
that depend on the town. Whether that is a success depends on who you think the centre is for.

The deeper disagreement is about what a town centre is. One view: it is a place people go to be
in, and cars are what stopped them going — remove the cars and the place comes back. The other:
it is a place people go to get things done, and access is the whole point — remove the access
and the people go to the retail park, which has plenty.

The committee's options as drafted are the full closure or the status quo. Neither side's
strongest argument is answered by either. The closure does nothing for the village trade; the
status quo does nothing for the air or the footfall. The options the drafting left out — closure
on market days only, a park-and-ride from the villages, closing two streets rather than four —
are the ones that take both arguments seriously, and they are the ones nobody has costed.

Recommendation: do not vote on the two options as drafted.""",
}


#: Real, public-domain material (`tests/e2e/fixtures/documents/*.txt`, ~950-word
#: passages with their provenance on the first line) — the default set since the
#: authored five are the assistant's own prose. `INGEST_DOC_SET=authored` runs those.
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "documents"


def _document_set(name: str) -> dict[str, str]:
    if name == "authored":
        return DOCUMENTS
    docs: dict[str, str] = {}
    for path in sorted(_FIXTURES.glob("*.txt")):
        lines = path.read_text().splitlines()
        body = "\n".join(lines[1:]).strip() if lines and lines[0].startswith("#") else path.read_text()
        docs[path.stem] = body
    return docs


def _fmt(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_ingest_documents(di_container) -> None:
    from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.repositories.node_repository import \
        NodeRepository
    from dialectical_framework.graph.scope_context import scope
    from dialectical_framework.utils.call_census import call_census
    from e2e.probe_aspect_variants import _judge

    arms = [a for a in os.environ.get("INGEST_DOC_ARMS", "staged").split(",") if a]
    limit = int(os.environ.get("INGEST_DOC_LIMIT", "0") or 0)
    doc_set = os.environ.get("INGEST_DOC_SET", "public")
    docs = list(_document_set(doc_set).items())[: limit or None]
    judge = E2EConfig.from_env().judge_model
    # TETRAD_PROBE_ATTEMPTS=N: every staged aspect call draws N and keeps the
    # best by the control statements (`concerns/tetrad_candidates.py`); the
    # file name says so, so the archive's default-run globs stay clean.
    import dialectical_framework.concerns.tetrad_candidates as cands

    attempts = os.environ.get("TETRAD_PROBE_ATTEMPTS")
    if attempts:
        cands.DEFAULT_ASPECT_ATTEMPTS = int(attempts)
    variant = f"-att{attempts}" if attempts else ""
    out = _RESULTS / f"ingest_documents-{doc_set}{variant}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== ingest on {len(docs)} document(s), arms {arms} → {out}", flush=True)

    rows: list[dict] = []
    for name, text in docs:
        for arm in arms:
            if arm == "oneshot":
                # HISTORICAL: measured 2026-10-02 (ingest_documents-20261002-*.json)
                # and removed — the ladder keeps documents. Dev note, "Consolidation 2".
                raise RuntimeError("the oneshot arm is historical: the per-thesis route was removed")
            case = Case()
            case.commit()
            row: dict = {"document": name, "arm": arm, "sid": case.sid, "perspectives": []}
            with scope(case.sid), call_census() as census:
                started = time.monotonic()
                try:
                    pipeline = AnalysisPipeline(text=text)
                    result = await pipeline.resolve()
                    row["seconds"] = round(time.monotonic() - started, 1)
                    row["summary"] = pipeline.report.summary
                    repo = NodeRepository()
                    row["theses"] = [
                        s.text for h in result.thesis_hashes
                        if (s := repo.find_by_hash(h, node_type=Statement)) is not None
                    ]
                    for h in result.perspective_hashes:
                        pp = repo.find_by_hash(h, node_type=Perspective)
                        if pp is None:
                            continue
                        t, a = pp.t.get(), pp.a.get()
                        p = {
                            "hash": h,
                            "thesis": t[0].text if t else None,
                            "antithesis": a[0].text if a else None,
                            "validation": pp.validation,
                        }
                        for pos in ("t_plus", "t_minus", "a_plus", "a_minus"):
                            got = getattr(pp, pos).get()
                            p[pos] = got[0].text if got else None
                        row["perspectives"].append(p)
                except Exception as exc:  # noqa: BLE001
                    row["error"] = repr(exc)
                    row["seconds"] = round(time.monotonic() - started, 1)
            row["calls"] = census.count
            row["provider_s"] = round(census.provider_s, 1)
            # judge + audit, sequential (using_model re-points the container)
            for p in row["perspectives"]:
                if all(p.get(k) for k in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")):
                    p.update(await _judge(p))
                    p.update(await _audit_kind(di_container, judge, p["thesis"], p["antithesis"]))
                    p.update(await _audit_parentage(di_container, judge, p))
                    p.update(await _audit_pluses(di_container, judge, p))
            rows.append(row)
            out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
            judged = [p for p in row["perspectives"] if "pass" in p]
            print(
                f"  [{name:17s} {arm:8s}] {row.get('seconds')}s  calls {row['calls']}  "
                f"theses {len(row.get('theses', []))}  tetrads {len(row['perspectives'])}  "
                f"CC {sum(bool(p['pass']) for p in judged)}/{len(judged)}  "
                f"positions {sum(1 for p in judged if p.get('a_kind') == 'position')}/{len(judged)}"
                + (f"  ERROR {row['error'][:80]}" if row.get("error") else ""),
                flush=True,
            )

    print("\n--- per arm, all documents ---")
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        ps = [p for r in rs for p in r["perspectives"] if "pass" in p]
        restated = sum(
            1 for p in ps for s in ("t_plus", "a_plus")
            if p.get(f"{s}_parent") == "own_pole" and p.get(f"{s}_valence_ok") is False
        )
        print(
            f"  {arm:8s} docs {len(rs)}  tetrads {len(ps)}  CC {_fmt(sum(bool(p['pass']) for p in ps), len(ps))}  "
            f"positions {_fmt(sum(1 for p in ps if p.get('a_kind') == 'position'), len(ps))}  "
            f"restated {restated}/{2*len(ps)}  "
            f"median s/doc {statistics.median([r['seconds'] for r in rs]) if rs else None}  "
            f"median calls/doc {statistics.median([r['calls'] for r in rs]) if rs else None}  "
            f"theses/doc {dict(collections.Counter(len(r.get('theses', [])) for r in rs))}"
        )
