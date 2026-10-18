from dataclasses import replace

import pytest

from carpool_bench import harness, report
from carpool_domain import Distribution, Solution

QUICK = harness.Settings(lns_budget_seconds=0.05, exact_time_limit_seconds=60)


@pytest.fixture(scope="module")
def results():
    cases = harness.grid([12, 30], [0.35], [Distribution.CLUSTERED], [1])
    return harness.run(cases, replace(QUICK, exact_max_n=12))


def _solvers(results, n):
    return {r["solver"]: r for r in results["runs"] if r["n"] == n}


def test_each_case_is_solved_three_ways_up_to_the_exact_limit(results):
    assert set(_solvers(results, 12)) == {"greedy", "lns", "exact"}
    assert set(_solvers(results, 30)) == {"greedy", "lns"}


def test_the_optimum_is_no_worse_than_either_heuristic(results):
    solved = _solvers(results, 12)
    assert solved["exact"]["optimal"]
    assert (
        solved["exact"]["objective"] <= solved["lns"]["objective"] <= solved["greedy"]["objective"]
    )


def test_the_environment_records_the_settings_the_run_used(results):
    assert results["environment"]["lns_budget_seconds"] == QUICK.lns_budget_seconds
    assert results["environment"]["exact_max_n"] == 12


def test_an_infeasible_answer_is_never_measured():
    instance = harness.Case(10, 0.35, Distribution.UNIFORM, 1).instance()
    with pytest.raises(AssertionError, match="infeasible"):
        harness.measure(instance, Solution())


def test_the_gap_is_measured_on_routing_cost_not_on_the_penalty():
    optimum = {"objective": 101_000.0, "routing_cost": 1_000.0}
    assert report.gap({"objective": 101_050.0}, optimum) == pytest.approx(0.05)


def test_the_report_counts_only_instances_the_exact_model_was_asked_to_solve(results):
    rendered = report.render(results)
    assert "| 12 | 0.35 | 1/1 |" in rendered
    assert "| clustered | 1/1 |" in rendered
    assert "| 30 | 0.35 | 1 |" in rendered
