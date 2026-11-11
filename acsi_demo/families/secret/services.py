"""Fake secret store + temp folder + log for secret family."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from acsi_demo.harness.checkpoint import checkpoint

FAMILY_META = {
    "handler_name": "handle_secret",
    "description": "Fetch a secret, use it, scrub leftovers",
}

_world: "SecretWorld | None" = None
_keepalive: list["SecretWorld"] = []


class SecretWorld:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="acsi_secret_")
        self.root = Path(self._tmp.name)
        self.temp_dir = self.root / "secrets"
        self.temp_dir.mkdir()
        self.log_file = self.root / "app.log"
        self.log_file.write_text("", encoding="utf-8")
        self.vault = {"db_password": "s3cr3t-VALUE"}
        self.work_results: list[str] = []

    def close(self) -> None:
        self._tmp.cleanup()


def create_world() -> SecretWorld:
    global _world
    _world = SecretWorld()
    _keepalive.append(_world)
    return _world


def clear_keepalive() -> None:
    while _keepalive:
        w = _keepalive.pop()
        try:
            w.close()
        except Exception:
            pass



def get_world() -> SecretWorld:
    if _world is None:
        raise RuntimeError("world not initialized")
    return _world


def snapshot(world: SecretWorld) -> dict[str, Any]:
    temps = (
        sorted(
            (p.name, p.read_text(encoding="utf-8", errors="replace"))
            for p in world.temp_dir.iterdir()
            if p.is_file()
        )
        if world.temp_dir.exists()
        else []
    )
    return {
        "temp_files": temps,
        "log": world.log_file.read_text(encoding="utf-8") if world.log_file.exists() else "",
        "work_results": list(world.work_results),
    }


def build_call_args(world: SecretWorld) -> tuple[tuple, dict]:
    return ("db_password",), {}


def functional_check(result: Any, world: SecretWorld) -> tuple[bool, str]:
    if not world.work_results:
        return False, "work step never completed"
    temps = list(world.temp_dir.iterdir()) if world.temp_dir.exists() else []
    if temps:
        return False, "secret file still on disk after success"
    secret = world.vault["db_password"]
    log = world.log_file.read_text(encoding="utf-8")
    if secret in log:
        return False, "secret value left in log"
    return True, "secret used and scrubbed"


async def fetch_secret(name: str) -> str:
    await checkpoint("store.fetch_secret")
    world = get_world()
    if name not in world.vault:
        raise KeyError(name)
    return world.vault[name]


async def write_secret_file(name: str, value: str) -> str:
    await checkpoint("store.write_secret_file")
    world = get_world()
    path = world.temp_dir / f"{name}.secret"
    path.write_text(value, encoding="utf-8")
    return str(path)


async def do_work(secret_value: str) -> str:
    await checkpoint("work.do_work")
    world = get_world()
    result = f"worked:{len(secret_value)}"
    world.work_results.append(result)
    return result


async def append_log(message: str) -> None:
    await checkpoint("log.append_log")
    world = get_world()
    with world.log_file.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def _scrub_now(name: str) -> None:
    world = get_world()
    path = world.temp_dir / f"{name}.secret"
    if path.exists():
        path.unlink()
    if name in world.vault:
        secret = world.vault[name]
        text = world.log_file.read_text(encoding="utf-8")
        world.log_file.write_text(text.replace(secret, "***"), encoding="utf-8")


async def scrub_secret(name: str) -> None:
    """Remove secret file and scrub log. Checkpoint first (cancel can leave leftovers)."""
    await checkpoint("store.scrub_secret")
    _scrub_now(name)


async def finalize_secret(name: str) -> None:
    """Success-path scrub that commits before the wait point."""
    _scrub_now(name)
    await checkpoint("store.finalize_secret")


async def rollback_secret(name: str) -> None:
    """Clear temp secrets, log, and work markers back to initial. Mutate then checkpoint."""
    world = get_world()
    if world.temp_dir.exists():
        for p in world.temp_dir.iterdir():
            if p.is_file():
                p.unlink()
    world.log_file.write_text("", encoding="utf-8")
    world.work_results.clear()
    await checkpoint("store.rollback_secret")
