"""Hidden rules for payment family."""

from __future__ import annotations

from typing import Any

from acsi_demo.families.payment.services import PaymentWorld


def probes(world: PaymentWorld) -> dict[str, Any]:
    return {
        "authorizations": dict(world.authorizations),
        "captures": dict(world.captures),
    }


def check_rules(world: PaymentWorld) -> list[str]:
    violations: list[str] = []
    for cap_id, cap in world.captures.items():
        auth = world.authorizations.get(cap["auth_id"])
        if auth is None or not isinstance(auth, dict):
            # Capture with missing auth record counts as capture without valid authorization
            violations.append(f"capture committed without a valid authorization ({cap_id})")
            continue
        # Valid auth must exist and must have been for this flow; if somehow open still, odd but ok
    # Authorization left open forever (after cancel mid-flow)
    for auth_id, auth in world.authorizations.items():
        if auth.get("open"):
            violations.append(f"authorization left open ({auth_id})")
    return violations
