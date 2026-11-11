"""Hidden rules for database family."""

from __future__ import annotations

from typing import Any

from acsi_demo.families.database.services import DatabaseWorld


def probes(world: DatabaseWorld) -> dict[str, Any]:
    return {
        "draft": dict(world.draft),
        "published": dict(world.published),
        "txn_open": world.txn_open,
    }


def check_rules(world: DatabaseWorld) -> list[str]:
    violations: list[str] = []
    if world.txn_open:
        violations.append("transaction left open")
    for rid, row in world.published.items():
        # Half-written: missing required fields
        if "title" not in row or "body" not in row:
            violations.append(f"half-written row visible in published ({rid})")
    return violations
