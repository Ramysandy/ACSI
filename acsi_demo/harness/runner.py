"""Run a sample against a family: dry-run, cancel-at-each, timeout mode."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from acsi_demo.harness.checkpoint import CheckpointController, set_controller


Handler = Callable[..., Awaitable[Any]]


@dataclass
class RunOutcome:
    ok: bool
    cancelled: bool = False
    timed_out: bool = False
    exception: str | None = None
    result: Any = None
    checkpoint_index: int | None = None
    checkpoint_name: str | None = None
    checkpoints_seen: list[str] = field(default_factory=list)
    traceback: str | None = None


@dataclass
class FamilyBundle:
    name: str
    services: Any
    rules: Any
    handler_name: str
    build_call_args: Callable[[Any], tuple[tuple, dict]]
    # functional check: (handler_result, world) -> (pass, reason)
    functional_check: Callable[[Any, Any], tuple[bool, str]]


def load_family(family: str) -> FamilyBundle:
    services = importlib.import_module(f"acsi_demo.families.{family}.services")
    rules = importlib.import_module(f"acsi_demo.families.{family}.rules")
    meta = services.FAMILY_META
    return FamilyBundle(
        name=family,
        services=services,
        rules=rules,
        handler_name=meta["handler_name"],
        build_call_args=services.build_call_args,
        functional_check=services.functional_check,
    )


def load_handler_from_path(path: Path, handler_name: str) -> Handler:
    """Load an async handler from a .py file without putting it on sys.modules permanently."""
    import importlib.util
    import sys
    import uuid

    mod_name = f"_acsi_sample_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Ensure family services resolve the same way as refs (package imports).
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    handler = getattr(module, handler_name, None)
    if handler is None or not callable(handler):
        sys.modules.pop(mod_name, None)
        raise AttributeError(f"{path} missing async def {handler_name}(...)")
    return handler


def load_handler_from_module(module_path: str, handler_name: str) -> Handler:
    module = importlib.import_module(module_path)
    handler = getattr(module, handler_name, None)
    if handler is None or not callable(handler):
        raise AttributeError(f"{module_path} missing {handler_name}")
    return handler


async def _invoke(handler: Handler, args: tuple, kwargs: dict) -> Any:
    result = handler(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_once(
    bundle: FamilyBundle,
    handler: Handler,
    controller: CheckpointController,
    *,
    timeout: float | None = None,
) -> RunOutcome:
    set_controller(controller)
    controller.install_sleep_patch()
    world = bundle.services.create_world()
    args, kwargs = bundle.build_call_args(world)
    try:
        if timeout is not None:
            try:
                async with asyncio.timeout(timeout):
                    result = await _invoke(handler, args, kwargs)
                return RunOutcome(
                    ok=True,
                    result=result,
                    checkpoints_seen=list(controller.seen),
                )
            except TimeoutError:
                return RunOutcome(
                    ok=False,
                    timed_out=True,
                    exception="TimeoutError",
                    checkpoints_seen=list(controller.seen),
                )
        else:
            result = await _invoke(handler, args, kwargs)
            return RunOutcome(
                ok=True,
                result=result,
                checkpoints_seen=list(controller.seen),
            )
    except asyncio.CancelledError as e:
        name = None
        idx = controller.cancel_at
        if idx and 0 < idx <= len(controller.seen):
            name = controller.seen[idx - 1]
        return RunOutcome(
            ok=False,
            cancelled=True,
            exception=str(e) or "CancelledError",
            checkpoint_index=idx,
            checkpoint_name=name,
            checkpoints_seen=list(controller.seen),
        )
    except Exception as e:
        return RunOutcome(
            ok=False,
            exception=f"{type(e).__name__}: {e}",
            traceback=traceback.format_exc(),
            checkpoints_seen=list(controller.seen),
        )
    finally:
        controller.uninstall_sleep_patch()


async def dry_run_count(bundle: FamilyBundle, handler: Handler) -> tuple[int, list[str], RunOutcome]:
    controller = CheckpointController(mode="count")
    outcome = await run_once(bundle, handler, controller)
    return controller.counter, list(controller.seen), outcome


async def run_cancel_at(
    bundle: FamilyBundle, handler: Handler, index: int
) -> tuple[RunOutcome, Any]:
    controller = CheckpointController(mode="cancel_at", cancel_at=index)
    outcome = await run_once(bundle, handler, controller)
    world = bundle.services.get_world()
    return outcome, world


async def run_timeout_mode(
    bundle: FamilyBundle, handler: Handler, *, timeout: float = 0.05, slow: float = 0.2
) -> tuple[RunOutcome, Any]:
    controller = CheckpointController(mode="slow", slow_seconds=slow)
    outcome = await run_once(bundle, handler, controller, timeout=timeout)
    world = bundle.services.get_world()
    return outcome, world


async def run_success(bundle: FamilyBundle, handler: Handler) -> tuple[RunOutcome, Any]:
    controller = CheckpointController(mode="passthrough")
    outcome = await run_once(bundle, handler, controller)
    world = bundle.services.get_world()
    return outcome, world


def snapshot_world(bundle: FamilyBundle, world: Any) -> Any:
    return bundle.services.snapshot(world)


def initial_world_snapshot(bundle: FamilyBundle) -> Any:
    world = bundle.services.create_world()
    snap = bundle.services.snapshot(world)
    return snap
