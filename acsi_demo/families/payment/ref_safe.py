"""Known-safe: void/rollback in finally if capture did not complete."""

from __future__ import annotations

from acsi_demo.families.payment.services import authorize, capture, rollback_payment


async def handle_payment(amount: float, order_id: str) -> str:
    done = False
    try:
        auth_id = await authorize(amount, order_id)
        cap_id = await capture(auth_id, amount)
        done = True
        return cap_id
    finally:
        if not done:
            await rollback_payment()
