from __future__ import annotations

import asyncio

from acsi_demo.families.secret import ref_safe, ref_unsafe
from acsi_demo.harness.runner import load_family, run_success


def test_ref_safe_functional():
    bundle = load_family("secret")
    outcome, world = asyncio.run(run_success(bundle, ref_safe.handle_secret))
    assert outcome.ok, outcome.exception
    ok, reason = bundle.functional_check(outcome.result, world)
    assert ok, reason


def test_ref_unsafe_functional():
    bundle = load_family("secret")
    outcome, world = asyncio.run(run_success(bundle, ref_unsafe.handle_secret))
    assert outcome.ok, outcome.exception
    ok, reason = bundle.functional_check(outcome.result, world)
    assert ok, reason
