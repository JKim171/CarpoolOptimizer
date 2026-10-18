"""The benchmark regression gate (docs/design.md 8.5).

Unit and property tests cannot see a refactor that keeps every answer feasible while making them
all worse; this can. LNS is held to a gap against the proven optimum of a dozen small instances.
It runs on a fixed number of iterations rather than a clock, so the numbers are the same on every
machine and a failure is a change in the code, never in the runner.

Proving the optima takes most of a minute, so they are recorded here and one is proven again on
every run. If the generator or the objective changes, that check fails, and so does any instance
LNS appears to beat: regenerate the table then.

The thresholds sit just above what the solver achieves today. A change that makes it better
should tighten them; one that has to make it worse should say so by loosening them.
"""

import statistics

import pytest

from carpool_bench import exact, harness
from carpool_domain import Distribution, evaluate, greedy, lns

#: Close to what production's one-second budget buys on a seat-short 50-person event. A longer run
#: lets instances this small converge whatever the search does, which would hide a regression.
ITERATIONS = 600

#: (n, driver ratio, distribution) -> (optimal objective, its routing cost), all with seed 1.
OPTIMA = {
    (20, 0.2, Distribution.UNIFORM): (333979.0, 33979.0),
    (20, 0.2, Distribution.CLUSTERED): (525172.0, 25172.0),
    (20, 0.2, Distribution.RADIAL): (431788.0, 31788.0),
    (20, 0.35, Distribution.UNIFORM): (36953.0, 36953.0),
    (20, 0.35, Distribution.CLUSTERED): (39096.0, 39096.0),
    (20, 0.35, Distribution.RADIAL): (37054.0, 37054.0),
    (30, 0.2, Distribution.UNIFORM): (352621.0, 52621.0),
    (30, 0.2, Distribution.CLUSTERED): (439724.0, 39724.0),
    (30, 0.2, Distribution.RADIAL): (542151.0, 42151.0),
    (30, 0.35, Distribution.UNIFORM): (57853.0, 57853.0),
    (30, 0.35, Distribution.CLUSTERED): (55785.0, 55785.0),
    (30, 0.35, Distribution.RADIAL): (51223.0, 51223.0),
}


def _case(key):
    n, ratio, distribution = key
    return harness.Case(n, ratio, distribution, 1)


#: With seats for everyone, at the measured worst of 1.89%.
ROOMY_WORST = 0.025
#: Seat-short (a fifth driving), at a measured mean of 2.27% and worst of 5.91%. Without LNS's
#: cheapest-first start these were 4.04% and 14.5%, without its cheapest-first rebuilds 5.82% and
#: 14.0%, and without either 9.21% and 28.8%.
SHORT_MEAN = 0.03
SHORT_WORST = 0.08


@pytest.fixture(scope="module")
def gaps():
    found = {}
    for key, (optimum, routing) in OPTIMA.items():
        case = _case(key)
        instance = case.instance()
        searched = lns.solve(instance, initial=greedy.solve(instance), iterations=ITERATIONS)
        found[case] = (evaluate(instance, searched).total - optimum) / routing
    return found


def test_the_recorded_optima_are_still_optimal():
    key = (20, 0.35, Distribution.CLUSTERED)
    instance = _case(key).instance()
    result = exact.solve(instance)

    assert result.optimal
    assert result.solution is not None
    assert evaluate(instance, result.solution).total == OPTIMA[key][0]


def test_lns_never_appears_to_beat_a_recorded_optimum(gaps):
    assert min(gaps.values()) >= -1e-9, _describe(gaps)


def _describe(gaps):
    return {f"n={c.n} {c.driver_ratio} {c.distribution.value}": f"{g:.2%}" for c, g in gaps.items()}


def test_lns_stays_near_optimal_when_everyone_fits(gaps):
    roomy = {c: g for c, g in gaps.items() if c.driver_ratio == 0.35}
    assert max(roomy.values()) <= ROOMY_WORST, _describe(roomy)


def test_lns_stays_near_optimal_when_seats_run_short(gaps):
    short = {c: g for c, g in gaps.items() if c.driver_ratio == 0.2}
    assert statistics.mean(short.values()) <= SHORT_MEAN, _describe(short)
    assert max(short.values()) <= SHORT_WORST, _describe(short)
