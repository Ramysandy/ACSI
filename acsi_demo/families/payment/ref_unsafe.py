"""Known-unsafe: captures then never voids; cancel after authorize leaves open auth."""

from __future__ import annotations

from acsi_demo.families.payment.services import authorize, capture


async def handle_payment(amount: float, order_id: str) -> str:
    auth_id = await authorize(amount, order_id)
    # BUG: if cancelled after authorize, authorization stays open forever
    cap_id = await capture(auth_id, amount)
    return cap_id
