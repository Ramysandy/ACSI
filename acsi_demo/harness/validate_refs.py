"""Stage 3: validate reference solutions against all four scoring modes."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass

from acsi_demo.harness.scoring import score_all

FAMILIES = ["upload", "token", "payment", "secret", "database"]


@dataclass
class Row:
    family: str
    kind: str
    normal: bool
    crash_only: bool
    generic_leftover: bool
    oracle: bool
    notes: str = ""


async def score_ref(family: str, kind: str) -> Row:
    mod = importlib.import_module(f"acsi_demo.families.{family}.ref_{kind}")
    bundle_meta = importlib.import_module(f"acsi_demo.families.{family}.services").FAMILY_META
    handler = getattr(mod, bundle_meta["handler_name"])
    report = await score_all(family, handler, sample_name=f"ref_{kind}")
    notes = []
    if kind == "safe" and not report.oracle.passed:
        notes.append(f"oracle: {report.oracle.reason}")
    if kind == "unsafe" and report.oracle.passed:
        notes.append("oracle unexpectedly passed")
    if kind == "safe":
        for name, mode in [
            ("normal", report.normal),
            ("crash_only", report.crash_only),
            ("generic_leftover", report.generic_leftover),
            ("oracle", report.oracle),
        ]:
            if not mode.passed:
                notes.append(f"{name}: {mode.reason}")
    if kind == "unsafe" and not report.oracle.passed:
        notes.append(report.oracle.reason)
    return Row(
        family=family,
        kind=kind,
        normal=report.normal.passed,
        crash_only=report.crash_only.passed,
        generic_leftover=report.generic_leftover.passed,
        oracle=report.oracle.passed,
        notes="; ".join(notes),
    )


async def main_async() -> int:
    rows: list[Row] = []
    for family in FAMILIES:
        for kind in ("unsafe", "safe"):
            rows.append(await score_ref(family, kind))

    headers = ("family", "kind", "normal", "crash", "leftover", "oracle", "notes")
    print(" | ".join(headers))
    print("-" * 100)
    failures = 0
    for r in rows:
        print(
            f"{r.family:10} | {r.kind:6} | {r.normal!s:5} | {r.crash_only!s:5} | "
            f"{r.generic_leftover!s:5} | {r.oracle!s:5} | {r.notes}"
        )
        if r.kind == "safe":
            if not (r.normal and r.crash_only and r.generic_leftover and r.oracle):
                failures += 1
        else:
            if r.oracle:
                failures += 1
            # Unsafe should still pass normal happy-path
            if not r.normal:
                failures += 1

    print()
    if failures:
        print(f"VALIDATION FAILED ({failures} issue(s))")
        return 1
    print("VALIDATION OK: all ref_unsafe fail oracle; all ref_safe pass all four modes")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
