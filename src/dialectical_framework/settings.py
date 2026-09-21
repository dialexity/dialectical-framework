from __future__ import annotations

import os
from typing import Optional, Self

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dialectical_framework.enums.causality_preset import CausalityPreset


class Settings(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    ai_model: str = Field(..., description="AI model in 'provider/model' format (e.g., 'bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0').")
    # Two models, one seam. `ai_model` runs the CONVERSATION (the tool-path call
    # every agent turn makes); `reasoning_model`, when set, runs every STRUCTURED
    # call — the framework's own reasoning: tetrads, classification, extraction,
    # transformations, the decision classifier. Routed in `use_brain` by call
    # shape, so no concern has to know. Unset = one model for everything.
    # Measured reason (rounds.md, `sonnet-thinking`): identical prompts, the
    # extraction concern's unsupported-claim rate is 34.6% on Haiku 4.5 and
    # 7.0% on Sonnet 5 — the model is the lever, not any thinking level.
    reasoning_model: Optional[str] = Field(default=None, description="Model for the framework's structured (reasoning) calls, 'provider/model'. None = same as ai_model.")
    component_length: int = Field(default=7, description="Approximate length in words of the statement.")
    transition_length: int = Field(default=15, description="Approximate maximum length in words of a transition statement (fuller than a component headline).")
    max_wheel_layer: int = Field(default=4, description="Maximum wheel layer (PP count per wheel) to build. Layers above this are skipped regardless of nexus size.")
    cycle_preset: str = Field(default=CausalityPreset.AUTO, description="Default preset for causality estimation (e.g., preset:auto, preset:realistic, preset:desirable, preset:feasible, preset:balanced).")

    # Context-dump quality filter (DialecticalContext). Perspectives below
    # these floors are suppressed from the Advisor's dump (a count line notes
    # them; inspect_node still reaches them). Quality scales: docs/scoring.md.
    # HS bands: 0.5-0.7 moderate, 0.3-0.5 weak, <0.3 barely an antithesis.
    # area (SP) bands: >=0.7 clear differentiation, 0.3-0.7 acceptable,
    # <0.3 aspects blur together.
    # DV: 0-1, naturalness of the dialectical relationship; <0.3 = forced/
    # distorted framing (comparative, no theory-derived cutoff).
    advisor_polarity_quality_min_hs: float = Field(default=0.5, description="Polarity quality floor: suppress perspectives whose antithesis HS (how genuine the T-A opposition is, 0.0-1.0) is below this. 0 disables.")
    # The SP + DV floors together operationalize the paper's acceptance pair
    # (SP > 0.5 AND DV > 0.5 [P0 p.12]) as soft context-pruning — deliberately
    # more conservative defaults than the paper's 0.5 (thresholds are per-LLM
    # calibrated), and pruning the dump, never the graph.
    advisor_perspective_quality_min_sp: float = Field(default=0.3, description="Perspective quality floor: suppress perspectives whose SP (Synthesis Potential = code `area`, differentiation of constructive over destructive aspects, ~0-2) is below this. 0 disables.")
    advisor_perspective_quality_min_dv: float = Field(default=0.3, description="Perspective quality floor: suppress perspectives whose DV (Dialectical Validity — naturalness of the dialectical relationship, 0.0-1.0) is below this. 0 disables.")
    advisor_wheel_quality_top_plausible: int = Field(default=3, description="Max wheels rendered per cycle in the unscoped context dump, top-normalized-%. Advisory-mode (nexus-pinned) dumps are exempt. 0 = unlimited.")

    # Depth budget for the Advisor's SILENT exploration (its `explore` tool).
    # "Rich vs simple" exploration is a runtime budget, not a schema concept:
    # all wheels are always built + estimated (structural, cheap); the budget
    # caps the expensive stages. The Navigator/Explorer path is user-driven
    # and ignores this.
    advisor_max_perspectives_per_exploration: int = Field(default=2, description="Max perspectives woven per silent Advisor explore call; excess is reported as deferred (weave in a follow-up call), never silently dropped. 0 = unlimited.")

    # Practical-feasibility auditing of new Transformations. OFF by default,
    # because it is an ANALYTICAL ANNOTATION rather than part of building a wheel:
    #
    #   - Nothing in the code branches on what it produces. The
    #     FeasibilityEstimation is rendered when present and omitted when absent
    #     (dialectical_context._format_transition_scores, inspect_node, and
    #     rendering.adopted_pathway_summary on a decision's ground line), and the
    #     critique Rationale it writes has no reader anywhere in the tree.
    #     Resume accounting, wheel_completeness, build_status and every score are
    #     untouched by its absence — a wheel built without it is not "partial".
    #   - It cost 40% of `explore`'s entire provider spend: two calls per
    #     Transformation (Ac+ and Re+), 12 calls / 147.4s at 1 PP, ~12.3s each
    #     against a 7.8s mean, the only concern billed twice per Transformation
    #     (`tests/e2e/probe_explore_cost.py`).
    #
    # What turning it off actually costs is ONE ranking input: both agents'
    # prompts say "prefer high-feasibility + low-to-moderate insight first", and
    # without it that rule orders on insight alone. Both prompts state this
    # explicitly, because a missing number must not read as a low one — and note
    # that absence was ALREADY the common case: only Ac+/Re+ are ever audited,
    # so Ac-/Re- have never carried a feasibility band even with this on.
    #
    # This is the EAGER path only, and it is a startup switch (settings resolve
    # process-wide through the DI container). A person in a conversation asks
    # instead: the `audit_feasibility` tool runs the same concern on the pathways
    # they raised, so the spend follows the interest. Turn this on for
    # programmatic analytical runs with no agent in the loop, where nobody will
    # ever ask and the band is worth the latency on everything.
    audit_transformations: bool = Field(default=False, description="EAGERLY audit every new Transformation's Ac+/Re+ transitions for practical feasibility. Adds 2 provider calls per Transformation and writes FeasibilityEstimations plus critique Rationales; nothing in the framework depends on them. Off by default — agents reach the same concern on demand via the audit_feasibility tool.")

    # A MODE, not an on/off for feasibility scoring. That distinction is the whole
    # point of the setting: turning this off does not remove the band, it removes
    # the AUTOMATIC route to it and leaves the manual one, because
    # `audit_feasibility` is a tool and stays a tool in both modes. There is no
    # state of this flag in which a person cannot ask what a recipe costs.
    #
    #   automatic (True)  — the deferred drain scores the pathway a recorded
    #                       decision is grounded on, off the turn, without being
    #                       asked. This is what makes the band MEASURABLE: the
    #                       model elected `audit_feasibility` in 1 of 6 A2 cells
    #                       (`a15-floor`) and 0 of 6 (`weave-offturn`), so under
    #                       election alone the band effectively does not exist and
    #                       no round can say what it is worth.
    #   manual (False)    — nothing is scored unless the model or the person asks
    #                       for it. The elective rate above is then the rate.
    #
    # Priced, not assumed. `feasibility-offturn` ran the automatic mode across 18
    # cells: the band reached 5 of 5 records that ground a pathway (against a 0/6
    # baseline), and it cost **+46% A2 cell wall** (701.0s vs 479.1s mean) plus one
    # turn where the person waited **284.5s** — 95% of that turn's reply path — for
    # off-turn work to settle. On the same round the seam the band was aimed at,
    # wobble discrimination, did NOT move (1/3 pairs, both rounds), and the one
    # correct reassure did not cite the record. So automatic mode was PAYING for a
    # band nothing had been shown to use.
    #
    # DEFAULT FLIPPED TO MANUAL 2026-09-15, and the elective route was repaired in
    # the same change rather than left to chance. Automatic was the default only
    # because flipping it would have un-measured the round that priced it — a
    # research reason, which expires when the build ships and real conversations
    # become the measurement. What made manual mode untrustworthy was the 1/6 and
    # 0/6 election rate, and that rate had a cause: the engine prompt named ONE
    # affirmative moment for the tool (the person asks) against THREE prohibitions
    # written to stop the eager spend, so suppression won. The prompt now names the
    # two moments automatic mode was actually covering — the closing, on the one
    # recipe about to be recorded, and the wobble turn, when what resurfaced is
    # whether the recipe can still be carried out. Same scope, same ~2 calls,
    # asked for on the turn it is needed instead of drained off every closing.
    # Whether that lands is the next round's measurement, not a claim here.
    #
    # Startup switch, like `audit_transformations` — settings resolve process-wide
    # through the DI container, so this cannot be flipped mid-conversation. Turn it
    # ON for benches and programmatic runs where no agent will ever elect anything
    # and the band must exist on every record for the round to be able to read it.
    automatic_feasibility_audit: bool = Field(default=False, description="Score the pathway a recorded decision is grounded on automatically, off the turn, instead of leaving it to the model to elect the audit_feasibility tool. A MODE, not a feature switch: the tool stays available when this is off, so feasibility is always reachable by asking. Off by default — it cost +46% A2 cell wall and one 284.5s wait, and the engine prompt now names the closing and the wobble turn as moments to elect the tool. Turn on for benches that need the band on every record.")

    # What the step-2 thesis gate sees. ON by default = the behaviour that has
    # always run, because this is a REASONING change and the default may only
    # move on a measurement.
    #
    # `ThesisExtraction` reads a source in two steps: step 1 extracts content
    # items from the window, step 2 checks each item, one call per item, fanned
    # out over `isolate()`. `isolate()` copies step 1's history, and step 1's
    # request has the whole window inside `<source_text>` — so every one of those
    # calls re-sends the document. Measured on a 120 KB ingest
    # (`tests/e2e/probe_ingest_cost.py`): 207,047 tokens across 24 calls, 75% of
    # everything the size of the document costs on that path, and all 184,438
    # cache-write tokens with 0 reads, since the entries are written by
    # CONCURRENT siblings and an entry is readable only after the call that wrote
    # it returns. Turning this off cuts size-driven prefill ~4x and takes the
    # pure-loss cache surcharge with it.
    #
    # What it costs is a judgement call, which is why it is a knob and not an
    # edit: `_step2_prompt` is fully self-contained (it names the item and its
    # type and asks four questions about it), and the sibling items still travel
    # in step 1's ANSWER, so the source is the only thing dropped.
    #
    # OFF WAS MEASURED THREE TIMES AND IS NOT ADOPTED, and the reason is not that
    # it lost. `probe_step2_isolate_ab.py` ran it as arm C against arm A on
    # 2026-09-17, 72 gate calls per arm per run over three documents, and its
    # preregistered endpoints returned a DIFFERENT VERDICT EACH TIME on the same
    # code and the same models: don't take, take, no call. What is stable is that
    # the saving projects to **6.7-7.2x** at `CHUNK_SIZE` and that the gate's
    # keep/drop decision does not move at all — A-vs-C 0.0% in all three runs, 216
    # paired comparisons, against within-arm floors of 0.0%. What is not stable is
    # the blinded judge on faithfulness: it leaned toward arm A every run (pooled
    # 19-6 with 11 ties, 76% of decided comparisons) but its tie rate went 1, 6, 4
    # of 12 and its positional control went 62%, 47%, 73%, so its pass/fail turns
    # on how often it shrugs. The two instruments built to remove that confound
    # both find NOTHING: equalising the two sets' sizes gives A 3 / C 4 then
    # A 4 / C 4, and an unpaired per-claim support check — every candidate rated
    # against the source on its own, no second set to be longer than — puts arm A
    # at 43.3% not-supported and arm C at 45.7%, a 2.4pp gap inside arm A's own
    # 38pp rep-to-rep swing. So the honest state is: no reasoning cost has been
    # demonstrated, and no stable positive result exists to move a reasoning
    # default on either. It stays ON because every stable measurement is neutral
    # and the only lean there is favours ON. Turn it off against your own corpus.
    #
    # THE SIBLING ITEMS ARE KEPT ON EVIDENCE, not out of caution. A stricter arm
    # that dropped step 1's history ENTIRELY — a fresh conversation with the same
    # system prompt and nothing else — was measured and REJECTED TWICE. On
    # 2026-09-11 (commit 52194e0) both self-consistency floors were 0.0% while the
    # arms disagreed on 5.6% of gate decisions, and all five flips were the same
    # field the same way, `is_substantive` false with the history and true without
    # it: "substantive" means the item adds something to THIS document, and nothing
    # in an item says that about itself, so a gate with no context admits
    # restatements. That effect reproduced in ONE of the three 2026-09-17 runs
    # (5.6%, 4 of 72, all four the same direction as before), which is what an
    # effect of five items in ninety looks like at this many reps. A second one
    # appeared alongside it — 22 of 72 items came back `is_atomic` true-with-history
    # and false-without, all one direction, and the no-history arm yielded **18%
    # more candidates** than arm A. `is_atomic` is read by no code but the same call
    # returns `atomic_theses`, which IS the output, so a gate with no context also
    # cuts items finer. Either way the answer is the same: the gate needs what the
    # document ESTABLISHED, which is step 1's answer, and that is what the OFF arm
    # keeps while dropping the passage itself.
    extraction_step2_carries_source: bool = Field(default=True, description="Let the step-2 thesis gate see the source window it was extracted from, by carrying step 1's history into each gated call. On by default (current behaviour), and it stays the default because three A/B runs never produced a stable result to move it on: the cost saving and the gate's keep/drop decisions replicate, the judge on faithfulness does not (tests/e2e/probe_step2_isolate_ab.py). Off sends the system prompt, step 1's answer and the gate's own self-contained question, cutting the ~4x size-driven prefill cost of the ingest path; the extracted items still travel, only the raw passage is elided.")

    # Graph database configuration (Memgraph or Neo4j)
    graph_db_vendor: str = Field(default="memgraph", description="Graph database vendor: 'memgraph' or 'neo4j'")
    graph_db_host: str = Field(default="127.0.0.1", description="Graph database host")
    graph_db_port: int = Field(default=7687, description="Graph database port")
    graph_db_username: Optional[str] = Field(default=None, description="Graph database username (required for Neo4j, optional for Memgraph)")
    graph_db_password: Optional[str] = Field(default=None, description="Graph database password (required for Neo4j, optional for Memgraph)")
    graph_db_encrypted: bool = Field(default=False, description="Use encrypted connection (SSL/TLS)")
    graph_db_client_name: str = Field(default="dialectical_framework", description="Client name for connection identification")

    # Effect logging: directory for JSONL effect logs. None = disabled.
    # When set, graph mutations and tool calls are logged to <dir>/<sid>/<agent>.jsonl
    effect_log_dir: Optional[str] = Field(default=None, description="Directory for effect JSONL logs. None = disabled.")

    # Extended thinking: None = disabled, or one of the levels below.
    # Levels map to provider-specific token budgets (% of max_tokens for Anthropic):
    #   "none"    - disable thinking entirely
    #   "minimal" - minimum budget (1024 tokens)
    #   "low"     - 20% of max_tokens
    #   "medium"  - 40% of max_tokens
    #   "high"    - 60% of max_tokens
    #   "max"     - 80% of max_tokens
    # Claude 5 models take no token budget — they accept only adaptive thinking with a
    # coarse effort label, so the level is mapped there instead (utils/thinking_compat.py).
    # If the model doesn't support thinking, the setting is silently ignored (warning logged).
    # The CONVERSATIONAL thinking level — the tool-path call every agent turn
    # makes. A deployment default that a head's `thinking=` overrides per
    # session (the person's own toggle). Never reaches a structured concern
    # call: those cannot think in their default formatting mode, and none opts
    # in — concerns get their own MODEL instead (`reasoning_model` above).
    # Measured: on Haiku 4.5 "medium" is ~450 hidden output tokens and ~3x the
    # call with no election gain; on Sonnet 5 it is close to free and close to
    # a no-op (rounds.md: `thinking-off`, `sonnet-thinking`).
    conversation_thinking_level: Optional[str] = Field(default=None, description="Extended thinking level for the conversational (tool-path) call; the deployment default a head's thinking= overrides per session. None = disabled.")

    # TCP connect timeout for the Bedrock client, in seconds.
    #
    # The Anthropic SDK defaults this to 5s, which is generous for a warm
    # datacenter link and too tight for anything else: a cold TLS handshake over
    # a mobile/tethered/VPN connection measured 7.7s here, so the FIRST call on
    # every fresh connection failed. That is a whole class of "the framework
    # doesn't work on my laptop" — and it hits the parallel stages hardest
    # (ExplorationPipeline, ExploreTransformations), because each concurrent
    # call opens its own cold connection while a single sequential call reuses
    # one that already handshaked. Read/write timeouts keep the SDK defaults;
    # slow generation is not the problem being solved here.
    llm_connect_timeout_s: float = Field(default=30.0, description="TCP/TLS connect timeout for LLM calls, in seconds. Raise on slow or high-latency links.")

    @classmethod
    def from_partial(cls, partial_settings: Optional[Settings] = None) -> Self:
        """
        Create Settings by merging partial settings with environment defaults.
        Fields not explicitly set on partial_settings are filled from
        Settings.from_env().

        Only EXPLICITLY SET fields override (exclude_unset) — a field left at
        its Pydantic default does not stomp an env-configured value. Fields
        explicitly set to None are also dropped (None never means "unset the
        env value" for any Settings field).
        """
        if partial_settings is None:
            return cls.from_env()

        # Get full defaults from environment
        env_defaults = cls.from_env()

        # Only fields the caller explicitly set, and not to None
        partial_dict = {
            k: v
            for k, v in partial_settings.model_dump(exclude_unset=True).items()
            if v is not None
        }

        # Convert env_defaults to dict
        env_dict = env_defaults.model_dump()

        # Merge: explicitly-set partial fields override env defaults
        merged_dict = {**env_dict, **partial_dict}

        # Create new instance from merged data
        return cls(**merged_dict)

    @classmethod
    def from_env(cls) -> Self:
        """
        Static method to set up and return a Config instance.
        It uses environment variables or hardcoded defaults for configuration.
        """
        load_dotenv()

        model = os.getenv("DIALEXITY_DEFAULT_MODEL", None)
        if not model:
            raise ValueError(
                "Missing required environment variable: DIALEXITY_DEFAULT_MODEL "
                "(must be in 'provider/model' format, e.g., 'bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0')"
            )

        return cls(
            ai_model=model,
            reasoning_model=os.getenv("DIALEXITY_REASONING_MODEL") or None,
            component_length=int(os.getenv("DIALEXITY_DEFAULT_COMPONENT_LENGTH", 7)),
            transition_length=int(os.getenv("DIALEXITY_DEFAULT_TRANSITION_LENGTH", 15)),
            max_wheel_layer=int(os.getenv("DIALEXITY_MAX_WHEEL_LAYER", 4)),
            cycle_preset=CausalityPreset.AUTO,
            advisor_polarity_quality_min_hs=float(os.getenv("DIALEXITY_ADVISOR_POLARITY_QUALITY_MIN_HS", 0.5)),
            advisor_perspective_quality_min_sp=float(os.getenv("DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_SP", 0.3)),
            advisor_perspective_quality_min_dv=float(os.getenv("DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_DV", 0.3)),
            advisor_wheel_quality_top_plausible=int(os.getenv("DIALEXITY_ADVISOR_WHEEL_QUALITY_TOP_PLAUSIBLE", 3)),
            advisor_max_perspectives_per_exploration=int(os.getenv("DIALEXITY_ADVISOR_MAX_PERSPECTIVES_PER_EXPLORATION", 2)),
            audit_transformations=os.getenv("DIALEXITY_AUDIT_TRANSFORMATIONS", "false").lower() == "true",
            automatic_feasibility_audit=os.getenv("DIALEXITY_AUTOMATIC_FEASIBILITY_AUDIT", "false").lower() == "true",
            extraction_step2_carries_source=os.getenv("DIALEXITY_EXTRACTION_STEP2_CARRIES_SOURCE", "true").lower() == "true",
            graph_db_vendor=os.getenv("DIALEXITY_GRAPH_DB_VENDOR", "memgraph"),
            graph_db_host=os.getenv("DIALEXITY_GRAPH_DB_HOST", "127.0.0.1"),
            graph_db_port=int(os.getenv("DIALEXITY_GRAPH_DB_PORT", 7687)),
            graph_db_username=os.getenv("DIALEXITY_GRAPH_DB_USERNAME"),
            graph_db_password=os.getenv("DIALEXITY_GRAPH_DB_PASSWORD"),
            graph_db_encrypted=os.getenv("DIALEXITY_GRAPH_DB_ENCRYPTED", "false").lower() == "true",
            graph_db_client_name=os.getenv("DIALEXITY_GRAPH_DB_CLIENT_NAME", "dialectical_framework"),
            conversation_thinking_level=os.getenv("DIALEXITY_CONVERSATION_THINKING_LEVEL") or None,
            llm_connect_timeout_s=float(os.getenv("DIALEXITY_LLM_CONNECT_TIMEOUT_S", 30.0)),
            effect_log_dir=os.getenv("DIALEXITY_GRAPH_LOG_DIR"),
        )