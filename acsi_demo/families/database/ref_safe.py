"""Known-safe: draft then atomic publish; rollback on cancel."""

from __future__ import annotations

from typing import Any

from acsi_demo.families.database.services import (
    begin_txn,
    commit_txn,
    publish_row,
    rollback_txn,
    write_draft,
)


async def handle_publish_row(row_id: str, data: dict[str, Any]) -> str:
    done = False
    try:
        await begin_txn()
        await write_draft(row_id, data)
        await publish_row(row_id)
        await commit_txn()
        done = True
        return row_id
    finally:
        if not done:
            await rollback_txn()
