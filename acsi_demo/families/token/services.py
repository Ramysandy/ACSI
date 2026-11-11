"""Fake token store + API for the token family."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from acsi_demo.harness.checkpoint import checkpoint

FAMILY_META = {
    "handler_name": "handle_token_use",
    "description": "Refresh a token, use it, then revoke it",
}

_world: "TokenWorld | None" = None
_keepalive: list["TokenWorld"] = []

INITIAL_TOKEN = "old-token"


class TokenWorld:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="acsi_token_")
        self.root = Path(self._tmp.name)
        self.temp_dir = self.root / "tmp"
        self.temp_dir.mkdir()
        self.store: dict[str, dict[str, Any]] = {
            "user-1": {"value": INITIAL_TOKEN, "valid": True},
        }
        self.api_calls: list[str] = []

    def close(self) -> None:
        self._tmp.cleanup()


def create_world() -> TokenWorld:
    global _world
    _world = TokenWorld()
    _keepalive.append(_world)
    return _world


def clear_keepalive() -> None:
    while _keepalive:
        w = _keepalive.pop()
        try:
            w.close()
        except Exception:
            pass



def get_world() -> TokenWorld:
    if _world is None:
        raise RuntimeError("world not initialized")
    return _world


def snapshot(world: TokenWorld) -> dict[str, Any]:
    temps = (
        sorted(p.name for p in world.temp_dir.iterdir() if p.is_file())
        if world.temp_dir.exists()
        else []
    )
    return {
        "store": {k: dict(v) for k, v in sorted(world.store.items())},
        "temp_files": temps,
        "api_calls": list(world.api_calls),
    }


def build_call_args(world: TokenWorld) -> tuple[tuple, dict]:
    return ("user-1",), {}


def functional_check(result: Any, world: TokenWorld) -> tuple[bool, str]:
    if "user-1" in world.store and world.store["user-1"].get("valid"):
        return False, "token still valid after success path (should be revoked)"
    if not world.api_calls:
        return False, "API was never called"
    temps = list(world.temp_dir.iterdir()) if world.temp_dir.exists() else []
    if temps:
        return False, "temp token files left on disk after success"
    return True, "token used and revoked"


async def refresh_token(user_id: str) -> str:
    await checkpoint("store.refresh_token")
    world = get_world()
    new_val = f"tok-{user_id}-fresh"
    world.store[user_id] = {"value": new_val, "valid": True}
    return new_val


async def write_temp_token(user_id: str, token: str) -> str:
    await checkpoint("store.write_temp_token")
    world = get_world()
    path = world.temp_dir / f"{user_id}.token"
    path.write_text(token, encoding="utf-8")
    return str(path)


async def call_api(token: str) -> str:
    await checkpoint("api.call_api")
    world = get_world()
    for uid, meta in world.store.items():
        if meta.get("value") == token and meta.get("valid"):
            world.api_calls.append(uid)
            return f"ok:{uid}"
    raise PermissionError("invalid token")


async def revoke_token(user_id: str) -> None:
    await checkpoint("store.revoke_token")
    world = get_world()
    if user_id in world.store:
        world.store[user_id]["valid"] = False


async def clear_temp_token(user_id: str) -> None:
    await checkpoint("store.clear_temp_token")
    world = get_world()
    path = world.temp_dir / f"{user_id}.token"
    if path.exists():
        path.unlink()


async def secure_cleanup(user_id: str) -> None:
    """Revoke + clear temp (success-path cleanup). Mutate then checkpoint."""
    world = get_world()
    if user_id in world.store:
        world.store[user_id]["valid"] = False
    path = world.temp_dir / f"{user_id}.token"
    if path.exists():
        path.unlink()
    await checkpoint("store.secure_cleanup")


async def rollback_token(user_id: str) -> None:
    """Restore initial credential state. Mutate then checkpoint."""
    world = get_world()
    world.store[user_id] = {"value": INITIAL_TOKEN, "valid": True}
    path = world.temp_dir / f"{user_id}.token"
    if path.exists():
        path.unlink()
    world.api_calls = [c for c in world.api_calls if c != user_id]
    await checkpoint("store.rollback_token")
