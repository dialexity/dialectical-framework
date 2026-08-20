"""Guards for `tests/e2e/power.py` — free, no provider, no graph.

A power calculator that is quietly wrong is worse than none: it would license
underpowered runs with a number that looks like diligence. So the Fisher
implementation is cross-checked against the independently-written one in
`probe_tetrad_pole.py` (the two were typed separately and must agree), McNemar is
checked against hand-computable binomial values, and the power functions are
checked for the monotonicity and boundary behaviour any correct version must have.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e.power import (fisher_exact_two_sided, fisher_power,  # noqa: E402
                       mcnemar_exact_two_sided, mcnemar_power, min_n_for)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """No graph is touched here; override the autouse DB fixture."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestFisherAgreesWithTheOtherImplementation:
    """The archive now has two Fisher functions; they must not disagree."""

    @pytest.mark.parametrize(
        "table",
        [
            (3, 9, 0, 24),  # the taxonomy-cross post-hoc table
            (13, 59, 4, 68),  # parentage baseline vs post-fix run 1
            (13, 59, 9, 63),  # parentage baseline vs replication
            (6, 6, 7, 5),  # the classifier form test, a true null
            (0, 12, 0, 12),  # both arms empty
            (12, 0, 0, 12),  # complete separation
            (1, 1, 1, 1),  # smallest non-degenerate
        ],
    )
    def test_matches_probe_tetrad_pole(self, table):
        from e2e.probe_tetrad_pole import \
            _fisher_exact_two_sided as other  # noqa: PLC0415

        assert fisher_exact_two_sided(*table) == pytest.approx(other(*table), abs=1e-9)

    def test_known_values(self):
        # A null table must not be significant; total separation at n=12 must be.
        assert fisher_exact_two_sided(6, 6, 7, 5) == pytest.approx(1.0, abs=1e-9)
        assert fisher_exact_two_sided(12, 0, 0, 12) < 1e-5
        assert fisher_exact_two_sided(3, 9, 0, 24) == pytest.approx(0.0308, abs=5e-4)


class TestMcnemar:
    def test_no_discordant_pairs_is_not_evidence(self):
        assert mcnemar_exact_two_sided(0, 0) == 1.0

    def test_hand_computable(self):
        # b=1, c=0: two-sided p = 2 * (1/2)^1 = 1.0
        assert mcnemar_exact_two_sided(1, 0) == pytest.approx(1.0)
        # b=5, c=0: 2 * (1/2)^5 = 0.0625 — famously just misses 0.05
        assert mcnemar_exact_two_sided(5, 0) == pytest.approx(0.0625)
        # b=6, c=0: 2 * (1/2)^6 = 0.03125
        assert mcnemar_exact_two_sided(6, 0) == pytest.approx(0.03125)
        assert mcnemar_exact_two_sided(3, 3) == pytest.approx(1.0)

    def test_symmetric_in_its_arguments(self):
        assert mcnemar_exact_two_sided(8, 2) == mcnemar_exact_two_sided(2, 8)


class TestPowerBehaviour:
    def test_a_true_null_has_power_near_alpha(self):
        # No effect: the chance of "significance" is the false-positive rate, which
        # for a conservative exact test sits at or below alpha.
        assert fisher_power(72, 0.18, 0.18) <= 0.06

    def test_power_increases_with_n(self):
        small = fisher_power(48, 0.40, 0.15)
        large = fisher_power(96, 0.40, 0.15)
        assert small < large

    def test_power_increases_with_effect_size(self):
        assert fisher_power(72, 0.40, 0.30) < fisher_power(72, 0.40, 0.10)

    def test_the_number_that_reframed_the_parentage_result(self):
        """The archive's parentage probe ran at n=72/arm for an 18%->9% effect.

        If this ever climbs near 0.8, either the calculator broke or someone
        changed the assumed rates — both of which would retroactively change how
        `probe_tetrad_pole.py`'s NOT CONFIRMED verdict should be read.
        """
        assert fisher_power(72, 0.18, 0.09) == pytest.approx(0.28, abs=0.03)

    def test_enrichment_beats_brute_force_n(self):
        """Doubling the base rate buys more than doubling n — the design claim."""
        bigger_n = fisher_power(144, 0.18, 0.09)
        enriched = fisher_power(72, 0.40, 0.20)
        assert enriched > bigger_n

    def test_min_n_for_finds_a_sufficient_n(self):
        n = min_n_for(0.40, 0.20, target=0.80)
        assert n is not None
        assert fisher_power(n, 0.40, 0.20) >= 0.80
        # and it should be minimal to within the step it scans
        assert fisher_power(n - 12, 0.40, 0.20) < 0.80

    def test_min_n_returns_none_rather_than_lying_when_unreachable(self):
        assert min_n_for(0.20, 0.199, target=0.80, cap=48) is None


class TestPairingIsNotAFreeWin:
    """The design claim that decided against a paired parentage re-run."""

    def test_pairing_pays_when_the_fix_is_near_monotone(self):
        assert mcnemar_power(144, 0.11, 0.02) > 0.80

    def test_pairing_collapses_when_noise_dominates_discordance(self):
        # Same total discordance, split more evenly: power falls off a cliff.
        assert mcnemar_power(144, 0.08, 0.05) < 0.20

    def test_noise_dominated_pairing_loses_to_unpaired_fisher(self):
        """Why the re-run was not simply reorganised as a paired design."""
        paired = mcnemar_power(144, 0.08, 0.05)
        unpaired = fisher_power(144, 0.18, 0.09)
        assert paired < unpaired
