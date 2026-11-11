"""Fake database with draft/published tables and a transaction flag."""

from __future__ import annotations

from typing import Any

from acsi_demo.harness.checkpoint import checkpoint

FAMILY_META = {
    "handler_name": "handle_publish_row",
    "description": "Write a draft row then publish it",
}

_world: "DatabaseWorld | None" = None


class DatabaseWorld:
    def __init__(self) -> None:
        self.draft: dict[str, dict[str, Any]] = {}
        self.published: dict[str, dict[str, Any]] = {}
        self.txn_open: bool = False

    def close(self) -> None:
        pass


def create_world() -> DatabaseWorld:
    global _world
    _world = DatabaseWorld()
    return _world


def get_world() -> DatabaseWorld:
    if _world is None:
        raise RuntimeError("world not initialized")
    return _world


def snapshot(world: DatabaseWorld) -> dict[str, Any]:
    return {
        "draft": {k: dict(v) for k, v in sorted(world.draft.items())},
        "published": {k: dict(v) for k, v in sorted(world.published.items())},
        "txn_open": world.txn_open,
    }


def build_call_args(world: DatabaseWorld) -> tuple[tuple, dict]:
    return ("row-1", {"title": "Hello", "body": "World"}), {}


def functional_check(result: Any, world: DatabaseWorld) -> tuple[bool, str]:
    if "row-1" not in world.published:
        return False, "row not in published table"
    if world.txn_open:
        return False, "transaction left open after success"
    if "row-1" in world.draft:
        return False, "draft row should be cleared after publish"
    row = world.published["row-1"]
    if row.get("title") != "Hello" or row.get("body") != "World":
        return False, "published row incomplete"
    return True, "row published"


async def begin_txn() -> None:
    await checkpoint("db.begin_txn")
    world = get_world()
    world.txn_open = True


async def write_draft(row_id: str, data: dict[str, Any]) -> None:
    await checkpoint("db.write_draft")
    world = get_world()
    world.draft[row_id] = dict(data)


async def write_published_partial(row_id: str, data: dict[str, Any]) -> None:
    """Unsafe helper: writes a partial published row (e.g. missing fields)."""
    await checkpoint("db.write_published_partial")
    world = get_world()
    world.published[row_id] = dict(data)


async def publish_row(row_id: str) -> None:
    await checkpoint("db.publish_row")
    world = get_world()
    if row_id not in world.draft:
        raise KeyError(row_id)
    world.published[row_id] = dict(world.draft[row_id])
    del world.draft[row_id]


async def commit_txn() -> None:
    await checkpoint("db.commit_txn")
    world = get_world()
    world.txn_open = False


async def rollback_txn() -> None:
    """Abort txn and clear partial draft/published from this flow. Mutate then checkpoint."""
    world = get_world()
    world.txn_open = False
    world.draft.clear()
    # Remove incomplete published rows (missing required keys)
    for rid in list(world.published.keys()):
        row = world.published[rid]
        if "title" not in row or "body" not in row:
            del world.published[rid]
    await checkpoint("db.rollback_txn")
