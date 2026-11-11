"""Known-unsafe: publishes before scan completes; cancel after publish leaves unscanned public file."""

from __future__ import annotations

from pathlib import Path

from acsi_demo.families.upload.services import publish, read_file, save_private, scan_file


async def handle_upload(file_path: str) -> str:
    data = await read_file(file_path)
    name = Path(file_path).name
    await save_private(name, data)
    # BUG: publish before scan — cancel between publish and scan leaves public+unscanned
    published = await publish(name)
    await scan_file(published)
    return published
