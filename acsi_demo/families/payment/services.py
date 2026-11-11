"""Fake payment ledger for authorize/capture."""

from __future__ import annotations

from typing import Any

from acsi_demo.harness.checkpoint import checkpoint

FAMILY_META = {
    "handler_name": "handle_payment",
    "description": "Authorize then capture a payment",
}

_world: "PaymentWorld | None" = None


class PaymentWorld:
    def __init__(self) -> None:
        # auth_id -> {amount, open: bool}
        self.authorizations: dict[str, dict[str, Any]] = {}
        # capture_id -> {auth_id, amount}
        self.captures: dict[str, dict[str, Any]] = {}
        self._next = 1

    def close(self) -> None:
        pass


def create_world() -> PaymentWorld:
    global _world
    _world = PaymentWorld()
    return _world


def get_world() -> PaymentWorld:
    if _world is None:
        raise RuntimeError("world not initialized")
    return _world


def snapshot(world: PaymentWorld) -> dict[str, Any]:
    return {
        "authorizations": {k: dict(v) for k, v in sorted(world.authorizations.items())},
        "captures": {k: dict(v) for k, v in sorted(world.captures.items())},
    }


def build_call_args(world: PaymentWorld) -> tuple[tuple, dict]:
    return (25.0, "order-1"), {}


def functional_check(result: Any, world: PaymentWorld) -> tuple[bool, str]:
    if not world.captures:
        return False, "no capture committed"
    for cap in world.captures.values():
        auth = world.authorizations.get(cap["auth_id"])
        if auth is None:
            return False, "capture without authorization record"
        if auth.get("open"):
            return False, "authorization still open after capture"
    return True, "authorized and captured"


async def authorize(amount: float, order_id: str) -> str:
    await checkpoint("ledger.authorize")
    world = get_world()
    auth_id = f"auth-{world._next}"
    world._next += 1
    world.authorizations[auth_id] = {"amount": amount, "order_id": order_id, "open": True}
    return auth_id


async def capture(auth_id: str, amount: float) -> str:
    await checkpoint("ledger.capture")
    world = get_world()
    cap_id = f"cap-{world._next}"
    world._next += 1
    world.captures[cap_id] = {"auth_id": auth_id, "amount": amount}
    if auth_id in world.authorizations:
        world.authorizations[auth_id]["open"] = False
    return cap_id


async def void_authorization(auth_id: str) -> None:
    """Close/remove an open authorization. Mutate then checkpoint."""
    world = get_world()
    if auth_id in world.authorizations:
        world.authorizations[auth_id]["open"] = False
        # Remove entirely so cancel mid-flow restores toward initial empty ledger
        del world.authorizations[auth_id]
    # Also drop captures that referenced it (should not happen on void path)
    await checkpoint("ledger.void_authorization")


async def rollback_payment() -> None:
    """Clear ledger back toward empty. Mutate then checkpoint."""
    world = get_world()
    world.authorizations.clear()
    world.captures.clear()
    await checkpoint("ledger.rollback_payment")
