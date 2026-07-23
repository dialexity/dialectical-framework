"""Shared scoring vocabulary for dialectical prompts.

Single source of truth for the aspect definitions and the HS / complementarity
scales that were previously re-typed — and drifting — across concerns. Import
these fragments into system prompts so the generator and the classifier judge
tetrads by identical rules.

This is the aspect-side counterpart to ac_re_taxonomy.py (the transformation-side
scoring taxonomy): both are pure scoring-vocabulary modules, no service class.
"""

from __future__ import annotations

# Canonical tetrad aspect definitions.
# Names the two properties that distinguish dialectical aspects from mere
# pros/cons: cross-enhancement (a "+" aspect strengthens the OPPOSITE side too)
# and diagonal contradiction (each aspect contradicts its diagonal counterpart).
ASPECT_DEFINITIONS = """## Aspect Definitions

A dialectical tetrad adds four aspects around the T-A opposition:

- **T+** — A constructive development of T that also strengthens what A offers; it balances the opposition instead of overpowering it. Contradicts A-.
- **A+** — A constructive development of A that also strengthens what T offers; it balances the opposition instead of overpowering it. Contradicts T-.
- **T-** — An exaggeration of T: overdevelops T's own side while underdeveloping A. A one-sided overextension, not merely "a downside of T". Contradicts A+.
- **A-** — An exaggeration of A: overdevelops A's own side while underdeveloping T. A one-sided overextension, not merely "a downside of A". Contradicts T+."""


# HS band definitions (descending, best-first). Half-open bands: each includes
# its lower bound and excludes its upper; the top band includes 1.0. The
# "above 0.1 = valid" gate matches the code check `heuristic_similarity > 0.1`.
HS_SCALE = """## HS (Heuristic Similarity) Scale

How well the statement represents the apex concept for its position. Each band includes its lower bound and excludes its upper; the top band includes 1.0:

- 0.9-1.0 — Exemplary: near-perfect match to the apex
- 0.7-0.9 — Very similar: captures most of the apex
- 0.5-0.7 — Related: captures part of the apex, moderate fit
- 0.3-0.5 — Weakly related: right category, poor representation
- 0.1-0.3 — Barely related: likely belongs to a different position
- 0.0-0.1 — Unrelated: wrong category entirely

A value above 0.1 is valid for the position (quality varies by band); 0.1 or below means wrong category."""


# Complementarity anchors. The final line is the S3 fix: it stops the classifier
# from penalising a correct diagonal contradiction as a complementarity defect.
COMPLEMENTARITY_SCALE = """## Complementarity Scale (K_T, K_A)

How well the aspect complements, balances, and contributes to the constructive development of T (K_T) and A (K_A), each from 0.0 to 1.0:

- 1.0 — Strongly complements and balances it
- 0.5 — Neutral: neither adds to nor detracts from it
- 0.0 — Does not complement it: contributes nothing to its constructive development

Diagonal contradiction (T+ vs A-, A+ vs T-) is a structural requirement, not a complementarity defect — do not lower K for it."""
