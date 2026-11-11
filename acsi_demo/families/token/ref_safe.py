"""Known-safe: rollback on cancel; secure_cleanup after successful API use."""

from __future__ import annotations

from acsi_demo.families.token.services import (
    call_api,
    refresh_token,
    rollback_token,
    secure_cleanup,
    write_temp_token,
)


async def handle_token_use(user_id: str) -> str:
    done = False
    try:
        token = await refresh_token(user_id)
        await write_temp_token(user_id, token)
        result = await call_api(token)
        done = True
        return result
    finally:
        if done:
            await secure_cleanup(user_id)
        else:
            await rollback_token(user_id)
