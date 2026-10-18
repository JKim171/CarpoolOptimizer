"""`python -m carpool_bench run` solves the grid; `python -m carpool_bench report` renders it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from carpool_domain import Distribution

from . import harness, report


def _progress(record: dict[str, Any]) -> None:
    gap = "" if "objective" not in record else f" objective={record['objective']:.0f}"
    proven = " proven" if record.get("optimal") else ""
    print(
        f"n={record['n']} ratio={record['driver_ratio']} {record['distribution']} "
        f"seed={record['seed']} {record['solver']}: {record['seconds']:.2f} s{gap}{proven}",
        file=sys.stderr,
        flush=True,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="carpool_bench")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="solve the benchmark grid and write the results")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--sizes", type=int, nargs="+", default=list(harness.SIZES))
    run.add_argument("--driver-ratios", type=float, nargs="+", default=list(harness.DRIVER_RATIOS))
    run.add_argument(
        "--distributions",
        type=Distribution,
        nargs="+",
        default=list(harness.DISTRIBUTIONS),
        choices=list(Distribution),
    )
    run.add_argument("--seeds", type=int, nargs="+", default=list(harness.SEEDS))

    render = commands.add_parser("report", help="render results as Markdown")
    render.add_argument("results", type=Path)
    render.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "run":
        cases = harness.grid(args.sizes, args.driver_ratios, args.distributions, args.seeds)
        results = harness.run(cases, on_record=_progress)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1) + "\n")
    else:
        args.out.write_text(report.render(json.loads(args.results.read_text())))


if __name__ == "__main__":
    main()
