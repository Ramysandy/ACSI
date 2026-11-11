"""Known-safe: never log the raw secret; scrub/rollback in finally."""

from __future__ import annotations

from acsi_demo.families.secret.services import (
    append_log,
    do_work,
    fetch_secret,
    finalize_secret,
    rollback_secret,
    write_secret_file,
)


async def handle_secret(name: str) -> str:
    done = False
    try:
        value = await fetch_secret(name)
        await write_secret_file(name, value)
        await append_log("using secret ***")
        result = await do_work(value)
        done = True
        return result
    finally:
        if done:
            await finalize_secret(name)
        else:
            await rollback_secret(name)
