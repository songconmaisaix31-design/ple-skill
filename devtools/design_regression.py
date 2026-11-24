"""Original, independent storage-scheduling fixture and artifact grader."""

import argparse
import csv
from dataclasses import asdict, dataclass
import io
from itertools import product
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Site:
    initial_storage_units: int
    min_storage_units: int
    max_storage_units: int
    min_final_storage_units: int
    max_final_storage_units: int
    allowed_pump_units: tuple[int, ...]


@dataclass(frozen=True)
class Period:
    period: int
    demand_units: int
    max_pump_units: int
    tariff_cents_per_unit: int


VARIANTS = {
    "a": (
        Site(3, 1, 7, 2, 3, (0, 2, 4)),
        tuple(Period(*row) for row in (
            (1, 2, 4, 8), (2, 3, 2, 3), (3, 3, 4, 13),
            (4, 2, 4, 2), (5, 4, 2, 16), (6, 2, 4, 5),
        )),
    ),
    "b": (
        Site(4, 1, 8, 3, 4, (0, 1, 3, 5)),
        tuple(Period(*row) for row in (
            (1, 3, 3, 4), (2, 2, 5, 12), (3, 4, 3, 3),
            (4, 1, 5, 8), (5, 3, 1, 14), (6, 3, 5, 2),
        )),
    ),
    "c": (
        Site(1, 0, 5, 2, 2, (0, 1, 2, 3, 4, 5)),
        tuple(Period(*row) for row in (
            (1, 2, 4, 4), (2, 2, 0, 0), (3, 3, 5, 1),
            (4, 2, 4, 6), (5, 2, 0, 0), (6, 2, 5, 2),
        )),
    ),
    "d": (
        Site(6, 2, 10, 6, 7, (0, 2, 3, 5)),
        tuple(Period(*row) for row in (
            (1, 4, 5, 7), (2, 2, 3, 2), (3, 4, 5, 5),
            (4, 3, 0, 21), (5, 2, 3, 3), (6, 3, 5, 8),
        )),
    ),
    "e": (
        Site(7, 3, 12, 8, 8, (1, 3, 4, 7)),
        tuple(Period(*row) for row in (
            (1, 3, 4, 9), (2, 5, 7, 4), (3, 2, 3, 4),
            (4, 6, 7, 12), (5, 3, 4, 0), (6, 4, 7, 6),
        )),
    ),
    "f": (
        Site(5, 2, 11, 4, 6, (0, 1, 4, 6)),
        tuple(Period(*row) for row in (
            (1, 3, 4, 10), (2, 4, 6, 1), (3, 0, 1, 14),
            (4, 5, 6, 6), (5, 2, 4, 4), (6, 5, 6, 9),
        )),
    ),
    "g": (
        Site(4, 1, 13, 6, 6, (0, 2, 5, 8)),
        tuple(Period(*row) for row in (
            (1, 1, 5, 5), (2, 5, 8, 11), (3, 2, 2, 2),
            (4, 6, 8, 7), (5, 3, 5, 5), (6, 3, 2, 0),
        )),
    ),
    "h": (
        Site(8, 2, 14, 6, 6, (0, 2, 4, 7)),
        tuple(Period(*row) for row in (
            (1, 4, 4, 7), (2, 3, 7, 3), (3, 5, 4, 10),
            (4, 2, 2, 1), (5, 5, 7, 8), (6, 1, 4, 6),
        )),
    ),
    "i": (
        Site(3, 0, 9, 3, 5, (0, 1, 3, 6)),
        tuple(Period(*row) for row in (
            (1, 1, 3, 8), (2, 4, 6, 2), (3, 5, 6, 7),
            (4, 1, 0, 12), (5, 4, 6, 4), (6, 1, 3, 1),
        )),
    ),
    "j": (
        Site(6, 1, 12, 5, 7, (0, 2, 5, 7)),
        tuple(Period(*row) for row in (
            (1, 3, 5, 11), (2, 5, 7, 2), (3, 2, 2, 9),
            (4, 4, 5, 4), (5, 1, 2, 13), (6, 4, 7, 1),
        )),
    ),
    "k": (
        Site(5, 2, 13, 6, 8, (1, 3, 6, 8)),
        tuple(Period(*row) for row in (
            (1, 4, 6, 6), (2, 2, 3, 14), (3, 6, 8, 3),
            (4, 3, 3, 10), (5, 5, 8, 2), (6, 2, 6, 7),
        )),
    ),
    "l": (
        Site(7, 1, 14, 5, 8, (0, 3, 5, 8)),
        tuple(Period(*row) for row in (
            (1, 3, 5, 12), (2, 6, 8, 2), (3, 2, 3, 10),
            (4, 5, 5, 5), (5, 2, 8, 1), (6, 4, 5, 8),
        )),
    ),
    "m": (
        Site(4, 0, 11, 4, 6, (0, 2, 4, 6)),
        tuple(Period(*row) for row in (
            (1, 2, 4, 9), (2, 4, 6, 3), (3, 5, 6, 1),
            (4, 1, 2, 12), (5, 3, 4, 4), (6, 2, 6, 7),
        )),
    ),
    "n": (
        Site(6, 1, 13, 5, 7, (0, 2, 4, 7)),
        tuple(Period(*row) for row in (
            (1, 3, 4, 8), (2, 5, 7, 1), (3, 2, 2, 11),
            (4, 4, 4, 5), (5, 3, 7, 2), (6, 3, 4, 9),
        )),
    ),
    "o": (
        Site(5, 0, 12, 4, 6, (0, 1, 4, 6)),
        tuple(Period(*row) for row in (
            (1, 2, 4, 10), (2, 5, 6, 2), (3, 4, 6, 7),
            (4, 1, 1, 12), (5, 3, 4, 3), (6, 3, 6, 6),
        )),
    ),
    "p": (
        Site(8, 1, 15, 6, 8, (0, 2, 5, 8)),
        tuple(Period(*row) for row in (
            (1, 4, 5, 9), (2, 6, 8, 2), (3, 3, 5, 12),
            (4, 5, 8, 3), (5, 2, 2, 10), (6, 4, 8, 5),
        )),
    ),
    "q": (
        Site(5, 0, 12, 4, 6, (0, 1, 4, 7)),
        tuple(Period(*row) for row in (
            (1, 3, 4, 11), (2, 5, 7, 1), (3, 2, 1, 13),
            (4, 4, 7, 5), (5, 3, 4, 3), (6, 2, 7, 8),
        )),
    ),
    "r": (
        Site(8, 1, 15, 6, 8, (0, 2, 5, 8)),
        tuple(Period(*row) for row in (
            (1, 3, 5, 11), (2, 6, 8, 2), (3, 3, 5, 12),
            (4, 5, 8, 3), (5, 3, 5, 7), (6, 4, 8, 5),
        )),
    ),
    "s": (
        Site(5, 0, 12, 4, 6, (0, 1, 4, 7)),
        tuple(Period(*row) for row in (
            (1, 3, 4, 11), (2, 4, 7, 3), (3, 2, 1, 13),
            (4, 5, 7, 8), (5, 3, 4, 3), (6, 2, 7, 8),
        )),
    ),
}
SCHEDULE_COLUMNS = ("period", "pump_units", "end_storage_units", "period_cost_cents")
RESULT_FILENAMES = {"schedule.csv", "summary.json"}
MAX_RESULT_BYTES = 16384
UNSIGNED_INTEGER = re.compile(r"[0-9]{1,8}")

TASK = """Plan six periods of operation for a fictitious classroom water storage tank.

Read `input/site.json` for initial storage, bounds, and the allowable discrete
pump volumes. Read `input/periods.csv` for demand, pump availability, and the
tariff in each period.

Choose one pump volume for each period. It must be an allowed volume and at
most that period's pump limit. End-of-period storage is the preceding storage
plus that period's pumped volume minus that period's demand. Meet all demand,
use the same storage bounds in every period, and finish within the specified
final storage bounds. All bounds are inclusive. Pumping costs the number of
units pumped times the period's tariff. Among feasible schedules, minimize
total pumping cost. Any schedule tied for minimum cost is acceptable.

Save these two files under `output/`.

- `output/schedule.csv` has the exact header
  `period,pump_units,end_storage_units,period_cost_cents` and one row per period
  in period order. Write all four values as base-10 integers.
- `output/summary.json` is a JSON object containing exactly the three integer
  fields `total_pump_units`, `final_storage_units`, and `total_cost_cents`.
"""


def prepare(root: Path, variant: str = "a"):
    """Create a new workspace with only the task and its inputs."""
    site, periods = VARIANTS[variant]
    root.mkdir()
    input_dir = root / "input"
    input_dir.mkdir()
    (root / "task.md").write_text(TASK, encoding="utf-8")
    (input_dir / "site.json").write_text(json.dumps(asdict(site), indent=2) + "\n", encoding="utf-8")
    with (input_dir / "periods.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = [asdict(period) for period in periods]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _optimal_cost(site, periods):
    """Enumerate submitted-choice space using only trusted fixture values."""
    choices = [
        tuple(n for n in site.allowed_pump_units if n <= p.max_pump_units)
        for p in periods
    ]
    costs = []
    for volumes in product(*choices):
        stock = site.initial_storage_units
        objective = 0
        for volume, period in zip(volumes, periods):
            stock += volume - period.demand_units
            if not site.min_storage_units <= stock <= site.max_storage_units:
                break
            objective += volume * period.tariff_cents_per_unit
        else:
            if site.min_final_storage_units <= stock <= site.max_final_storage_units:
                costs.append(objective)
    return min(costs)


def _read_result(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path.name} must be a regular file")
    with path.open("rb") as stream:
        data = stream.read(MAX_RESULT_BYTES + 1)
    if len(data) > MAX_RESULT_BYTES:
        raise ValueError(f"{path.name} exceeds the result size limit")
    return data.decode("utf-8")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("summary.json contains duplicate keys")
        obj[key] = value
    return obj


def _reject_constant(_, /):
    raise ValueError("summary.json contains a non-finite number")


def _submitted_cost(root, site, periods):
    output = root / "output"
    if output.is_symlink() or not output.is_dir():
        raise ValueError("output must be a directory")
    if {path.name for path in output.iterdir()} != RESULT_FILENAMES:
        raise ValueError("output must contain exactly schedule.csv and summary.json")

    schedule = csv.reader(io.StringIO(_read_result(output / "schedule.csv"), newline=""), strict=True)
    if tuple(next(schedule, ())) != SCHEDULE_COLUMNS:
        raise ValueError("schedule.csv has incorrect column names or order")
    rows = list(schedule)
    if len(rows) != len(periods):
        raise ValueError("schedule.csv must have one row per period")

    storage = site.initial_storage_units
    total_units = total_cost = 0
    for row, period in zip(rows, periods):
        if len(row) != len(SCHEDULE_COLUMNS) or not all(UNSIGNED_INTEGER.fullmatch(n) for n in row):
            raise ValueError(f"period {period.period} must have four nonnegative integer cells")
        index, units, reported_storage, reported_cost = map(int, row)
        if index != period.period:
            raise ValueError("schedule.csv rows must be in period order")
        if units not in site.allowed_pump_units or units > period.max_pump_units:
            raise ValueError(f"period {index} violates the allowed pump volume or limit")
        storage = storage + units - period.demand_units
        if not site.min_storage_units <= storage <= site.max_storage_units:
            raise ValueError(f"period {index} violates the storage bounds")
        if reported_storage != storage:
            raise ValueError(f"period {index} does not conserve volume")
        cost = units * period.tariff_cents_per_unit
        if reported_cost != cost:
            raise ValueError(f"period {index} cost does not match volume and tariff")
        total_units += units
        total_cost += cost
    if not site.min_final_storage_units <= storage <= site.max_final_storage_units:
        raise ValueError("final storage is outside the required bounds")

    summary = json.loads(_read_result(output / "summary.json"),
                         parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    expected = {
        "total_pump_units": total_units,
        "final_storage_units": storage,
        "total_cost_cents": total_cost,
    }
    if (not isinstance(summary, dict) or any(type(value) is not int for value in summary.values())
            or summary != expected):
        raise ValueError("summary.json does not match the integer totals from the schedule")
    return total_cost


def grade(root: Path, variant: str = "a"):
    """Validate submitted files and measure their cost against the independent optimum."""
    site, periods = VARIANTS[variant]
    optimum = _optimal_cost(site, periods)
    try:
        cost = _submitted_cost(root, site, periods)
    except (OSError, ValueError, csv.Error, RecursionError) as error:
        return {"feasible": False, "optimal": False, "score": 0.0,
                "submitted_cost_cents": None, "optimal_cost_cents": optimum, "reason": str(error)}
    return {"feasible": True, "optimal": cost == optimum, "score": optimum / cost,
            "submitted_cost_cents": cost, "optimal_cost_cents": optimum,
            "reason": "minimum-cost schedule" if cost == optimum else "feasible with higher cost"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", type=Path, metavar="WORKSPACE", help="create a fresh fixture")
    mode.add_argument("--grade", type=Path, metavar="WORKSPACE", help="grade a prepared fixture's files")
    parser.add_argument("--variant", choices=VARIANTS, default="a")
    args = parser.parse_args()
    if args.prepare is not None:
        try:
            prepare(args.prepare, args.variant)
        except OSError as error:
            parser.error(str(error))
        print(args.prepare.resolve())
        return 0
    result = grade(args.grade, args.variant)
    print(json.dumps(result, indent=2))
    return 0 if result["feasible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

