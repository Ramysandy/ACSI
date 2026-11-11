"""Four scoring modes for ACSI samples."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from acsi_demo.harness import runner as R


@dataclass
class ModeResult:
    passed: bool
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreReport:
    family: str
    sample: str
    normal: ModeResult
    crash_only: ModeResult
    generic_leftover: ModeResult
    oracle: ModeResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "sample": self.sample,
            "normal": asdict(self.normal),
            "crash_only": asdict(self.crash_only),
            "generic_leftover": asdict(self.generic_leftover),
            "oracle": asdict(self.oracle),
        }


async def score_normal(bundle: R.FamilyBundle, handler: R.Handler) -> ModeResult:
    outcome, world = await R.run_success(bundle, handler)
    if not outcome.ok:
        return ModeResult(False, f"run failed: {outcome.exception}")
    ok, reason = bundle.functional_check(outcome.result, world)
    return ModeResult(ok, reason if ok else reason or "functional check failed")


async def _iter_injection_runs(
    bundle: R.FamilyBundle, handler: R.Handler
) -> list[tuple[str, R.RunOutcome, Any, Any]]:
    """Cancel at each checkpoint, then one timeout-mode run.

    Returns (label, outcome, world, snapshot). Snapshot is captured immediately so
    later runs that replace the family world cannot wipe filesystem state.
    """
    n, names, dry = await R.dry_run_count(bundle, handler)
    runs: list[tuple[str, R.RunOutcome, Any, Any]] = []
    if not dry.ok:
        n = max(n, len(dry.checkpoints_seen))
    for i in range(1, n + 1):
        outcome, world = await R.run_cancel_at(bundle, handler, i)
        label = f"cancel@{i}:{names[i - 1] if i - 1 < len(names) else '?'}"
        snap = R.snapshot_world(bundle, world)
        runs.append((label, outcome, world, snap))
    tout, world = await R.run_timeout_mode(bundle, handler)
    runs.append(("timeout", tout, world, R.snapshot_world(bundle, world)))
    return runs


def _is_benign_cancel_outcome(outcome: R.RunOutcome) -> bool:
    """Crash-only: cancelled/timeout without unexpected exceptions is OK."""
    if outcome.cancelled or outcome.timed_out:
        return True
    if outcome.ok:
        return True
    if outcome.exception:
        if "CancelledError" in (outcome.exception or ""):
            return True
        return False
    return True


async def score_crash_only(bundle: R.FamilyBundle, handler: R.Handler) -> ModeResult:
    runs = await _iter_injection_runs(bundle, handler)
    for label, outcome, _world, _snap in runs:
        if not _is_benign_cancel_outcome(outcome):
            return ModeResult(
                False,
                f"{label}: unexpected exception {outcome.exception}",
                {"label": label, "exception": outcome.exception},
            )
    return ModeResult(True, f"survived {len(runs)} injection runs")


async def score_generic_leftover(bundle: R.FamilyBundle, handler: R.Handler) -> ModeResult:
    """All-or-nothing: after cancel/timeout, state must equal initial OR full success.

    Does NOT use family security rules.
    """
    initial = R.initial_world_snapshot(bundle)
    success_outcome, success_world = await R.run_success(bundle, handler)
    if not success_outcome.ok:
        return ModeResult(False, f"cannot establish success state: {success_outcome.exception}")
    success_snap = R.snapshot_world(bundle, success_world)

    runs = await _iter_injection_runs(bundle, handler)
    for label, outcome, _world, snap in runs:
        if not _is_benign_cancel_outcome(outcome):
            continue
        if snap == initial or snap == success_snap:
            continue
        return ModeResult(
            False,
            f"{label}: leftover state is neither initial nor success",
            {"label": label, "snapshot": snap, "initial": initial, "success": success_snap},
        )
    return ModeResult(True, "all-or-nothing held for all injections")


async def score_oracle(bundle: R.FamilyBundle, handler: R.Handler) -> ModeResult:
    # Evaluate rules immediately after each run (before the next create_world).
    n, names, dry = await R.dry_run_count(bundle, handler)
    if not dry.ok:
        n = max(n, len(dry.checkpoints_seen))
    labeled: list[tuple[str, R.RunOutcome, Any]] = []
    for i in range(1, n + 1):
        outcome, world = await R.run_cancel_at(bundle, handler, i)
        label = f"cancel@{i}:{names[i - 1] if i - 1 < len(names) else '?'}"
        violations = bundle.rules.check_rules(world)
        if violations:
            reason = violations[0]
            probes = bundle.rules.probes(world)
            return ModeResult(
                False,
                f"{label}: {reason}",
                {
                    "label": label,
                    "reason": reason,
                    "probes": probes,
                    "checkpoint_index": outcome.checkpoint_index,
                    "checkpoint_name": outcome.checkpoint_name,
                },
            )
        labeled.append((label, outcome, world))
    tout, world = await R.run_timeout_mode(bundle, handler)
    violations = bundle.rules.check_rules(world)
    if violations:
        reason = violations[0]
        probes = bundle.rules.probes(world)
        return ModeResult(
            False,
            f"timeout: {reason}",
            {
                "label": "timeout",
                "reason": reason,
                "probes": probes,
                "checkpoint_index": tout.checkpoint_index,
                "checkpoint_name": tout.checkpoint_name,
            },
        )
    return ModeResult(True, "no security rule violated")


async def score_all(
    family: str,
    handler: R.Handler,
    sample_name: str = "",
) -> ScoreReport:
    bundle = R.load_family(family)
    normal = await score_normal(bundle, handler)
    crash = await score_crash_only(bundle, handler)
    leftover = await score_generic_leftover(bundle, handler)
    oracle = await score_oracle(bundle, handler)
    return ScoreReport(
        family=family,
        sample=sample_name,
        normal=normal,
        crash_only=crash,
        generic_leftover=leftover,
        oracle=oracle,
    )


def score_all_sync(family: str, handler: R.Handler, sample_name: str = "") -> ScoreReport:
    return asyncio.run(score_all(family, handler, sample_name))


async def score_path(family: str, path: Path) -> ScoreReport:
    bundle = R.load_family(family)
    handler = R.load_handler_from_path(path, bundle.handler_name)
    return await score_all(family, handler, sample_name=path.name)
