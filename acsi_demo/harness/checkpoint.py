"""Checkpoint registry for cancellation injection.

Every fake-service awaitable calls ``await checkpoint(name)``.
``asyncio.sleep`` is also patched so agent sleeps are checkpoints.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckpointController:
    """Controls whether checkpoints pass through, are counted, or cancel."""

    mode: str = "passthrough"  # passthrough | count | cancel_at | slow
    cancel_at: int | None = None  # 1-based index
    slow_seconds: float = 0.0
    counter: int = 0
    seen: list[str] = field(default_factory=list)
    _orig_sleep: Any = None

    def reset(self) -> None:
        self.counter = 0
        self.seen = []

    async def checkpoint(self, name: str) -> None:
        self.counter += 1
        idx = self.counter
        self.seen.append(name)
        if self.mode == "cancel_at" and self.cancel_at is not None and idx == self.cancel_at:
            raise asyncio.CancelledError(f"cancelled at checkpoint {idx}:{name}")
        if self.mode == "slow" and self.slow_seconds > 0:
            # Use real sleep so asyncio.timeout can fire; do not recurse into patched sleep.
            await self._real_sleep(self.slow_seconds)
        elif self.slow_seconds > 0 and self.mode == "passthrough":
            pass

    async def _real_sleep(self, delay: float) -> None:
        sleep = self._orig_sleep or asyncio.sleep
        await sleep(delay)

    def install_sleep_patch(self) -> None:
        if self._orig_sleep is not None:
            return
        self._orig_sleep = asyncio.sleep
        controller = self

        async def patched_sleep(delay: float, result: Any = None) -> Any:
            await controller.checkpoint(f"asyncio.sleep({delay})")
            if delay and controller.mode == "passthrough":
                # Skip real delay during normal/cancel runs for speed.
                return result
            if controller.mode == "slow":
                await controller._real_sleep(min(delay, controller.slow_seconds) if delay else 0)
            return result

        asyncio.sleep = patched_sleep  # type: ignore[assignment]

    def uninstall_sleep_patch(self) -> None:
        if self._orig_sleep is not None:
            asyncio.sleep = self._orig_sleep  # type: ignore[assignment]
            self._orig_sleep = None


# Process-wide controller used by services via checkpoint().
_controller = CheckpointController()


def get_controller() -> CheckpointController:
    return _controller


def set_controller(controller: CheckpointController) -> None:
    global _controller
    _controller = controller


async def checkpoint(name: str) -> None:
    await _controller.checkpoint(name)
