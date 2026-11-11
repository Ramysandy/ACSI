"""Known-safe: scan while private, publish last; rollback on cancel so state is all-or-nothing."""

from __future__ import annotations

from pathlib import Path

from acsi_demo.families.upload.services import (
    publish,
    read_file,
    rollback_upload,
    save_private,
    scan_file,
)


async def handle_upload(file_path: str) -> str:
    name = Path(file_path).name
    done = False
    try:
        data = await read_file(file_path)
        private_path = await save_private(name, data)
        await scan_file(private_path)
        published = await publish(name)
        done = True
        return published
    finally:
        if not done:
            await rollback_upload(name)
