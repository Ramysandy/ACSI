"""Known-unsafe: cleanup not in finally — cancel after API leaves valid token + temp file."""

from __future__ import annotations

from acsi_demo.families.token.services import (
    call_api,
    clear_temp_token,
    refresh_token,
    revoke_token,
    write_temp_token,
)


async def handle_token_use(user_id: str) -> str:
    token = await refresh_token(user_id)
    await write_temp_token(user_id, token)
    result = await call_api(token)
    # BUG: not in finally — cancel between call_api and these leaves valid token + temp
    await revoke_token(user_id)
    await clear_temp_token(user_id)
    return result
