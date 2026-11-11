"""Known-unsafe: logs the secret and forgets scrub — cancel leaves file + secret in log."""

from __future__ import annotations

from acsi_demo.families.secret.services import (
    append_log,
    do_work,
    fetch_secret,
    scrub_secret,
    write_secret_file,
)


async def handle_secret(name: str) -> str:
    value = await fetch_secret(name)
    await write_secret_file(name, value)
    await append_log(f"using secret {value}")
    result = await do_work(value)
    # BUG: scrub not in finally — cancel before this leaves file + secret in log
    await scrub_secret(name)
    return result
