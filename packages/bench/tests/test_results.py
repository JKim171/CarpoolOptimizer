import json
from pathlib import Path

from carpool_bench import report


def test_the_committed_tables_match_the_committed_results():
    # The same guard as the API contract and the demo event: the tables are generated, so a stale
    # copy fails the build rather than misreporting the numbers. `make bench-report` fixes it.
    root = Path(__file__).resolve().parents[3] / "docs/benchmarks"
    results = json.loads((root / "results.json").read_text())
    assert (root / "README.md").read_text() == report.render(results)
