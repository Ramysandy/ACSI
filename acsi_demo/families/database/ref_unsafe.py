"""Known-unsafe: writes partial published row before commit; cancel leaves txn open + half row."""

from __future__ import annotations

from typing import Any

from acsi_demo.families.database.services import (
    begin_txn,
    commit_txn,
    write_published_partial,
)


async def handle_publish_row(row_id: str, data: dict[str, Any]) -> str:
    await begin_txn()
    # BUG: publish partial fields first; cancel before full write/commit
    await write_published_partial(row_id, {"title": data.get("title")})
    await write_published_partial(row_id, data)
    await commit_txn()
    return row_id
