"""Stage 5: score generated samples four ways and write results tables."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections import defaultdict
from pathlib import Path

from acsi_demo.harness.scoring import score_path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
RESULTS = ROOT / "results"
FAMILIES = ["upload", "token", "payment", "secret", "database"]


def family_from_name(name: str) -> str | None:
    for fam in FAMILIES:
        if name.startswith(fam + "_"):
            return fam
    return None


async def main_async(limit: int | None = None) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "failures").mkdir(parents=True, exist_ok=True)
    files = sorted(SAMPLES.glob("*.py"))
    if limit is not None:
        files = files[:limit]

    rows = []
    per_family: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "samples": 0,
            "pass_normal": 0,
            "pass_crash_only": 0,
            "pass_generic_leftover": 0,
            "pass_oracle": 0,
        }
    )
    oracle_failures = []

    for path in files:
        family = family_from_name(path.name)
        if family is None:
            continue
        report = await score_path(family, path)
        rows.append(
            {
                "sample": path.name,
                "family": family,
                "pass_normal": int(report.normal.passed),
                "pass_crash_only": int(report.crash_only.passed),
                "pass_generic_leftover": int(report.generic_leftover.passed),
                "pass_oracle": int(report.oracle.passed),
                "oracle_reason": report.oracle.reason,
            }
        )
        agg = per_family[family]
        agg["samples"] += 1
        agg["pass_normal"] += int(report.normal.passed)
        agg["pass_crash_only"] += int(report.crash_only.passed)
        agg["pass_generic_leftover"] += int(report.generic_leftover.passed)
        agg["pass_oracle"] += int(report.oracle.passed)
        if not report.oracle.passed:
            oracle_failures.append((family, path, report))
        print(
            f"{path.name}: normal={report.normal.passed} crash={report.crash_only.passed} "
            f"leftover={report.generic_leftover.passed} oracle={report.oracle.passed}"
        )

    csv_path = RESULTS / "results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample",
                "family",
                "pass_normal",
                "pass_crash_only",
                "pass_generic_leftover",
                "pass_oracle",
                "oracle_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "| Family | Samples | Pass normal | Pass crash-only | Pass generic leftover | Pass oracle |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    totals = defaultdict(int)
    for fam in FAMILIES:
        a = per_family[fam]
        lines.append(
            f"| {fam} | {a['samples']} | {a['pass_normal']} | {a['pass_crash_only']} | "
            f"{a['pass_generic_leftover']} | {a['pass_oracle']} |"
        )
        for k, v in a.items():
            totals[k] += v
    lines.append(
        f"| Total | {totals['samples']} | {totals['pass_normal']} | {totals['pass_crash_only']} | "
        f"{totals['pass_generic_leftover']} | {totals['pass_oracle']} |"
    )
    (RESULTS / "results_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Keep up to 3 failures from different families
    seen = set()
    kept = 0
    for family, path, report in oracle_failures:
        if family in seen:
            continue
        seen.add(family)
        kept += 1
        out = RESULTS / "failures" / f"{path.stem}.md"
        detail = report.oracle.detail
        out.write_text(
            f"# Failure: {path.name}\n\n"
            f"- family: {family}\n"
            f"- checkpoint: {detail.get('label')}\n"
            f"- reason: {report.oracle.reason}\n"
            f"- probes: {json.dumps(detail.get('probes'), indent=2)}\n\n"
            f"## Generated function\n\n```python\n{path.read_text(encoding='utf-8')}\n```\n",
            encoding="utf-8",
        )
        if kept >= 3:
            break

    print(f"wrote {csv_path}")
    print(f"wrote {RESULTS / 'results_table.md'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main_async(limit=args.limit))


if __name__ == "__main__":
    main()
