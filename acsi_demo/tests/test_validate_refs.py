"""Acceptance: reference solutions behave as required for Stage 3."""

from __future__ import annotations

import asyncio
import importlib

import pytest

from acsi_demo.harness.scoring import score_all

FAMILIES = ["upload", "token", "payment", "secret", "database"]


@pytest.mark.parametrize("family", FAMILIES)
def test_ref_safe_passes_all_modes(family: str):
    mod = importlib.import_module(f"acsi_demo.families.{family}.ref_safe")
    handler_name = importlib.import_module(
        f"acsi_demo.families.{family}.services"
    ).FAMILY_META["handler_name"]
    handler = getattr(mod, handler_name)
    report = asyncio.run(score_all(family, handler, sample_name="ref_safe"))
    assert report.normal.passed, report.normal.reason
    assert report.crash_only.passed, report.crash_only.reason
    assert report.generic_leftover.passed, report.generic_leftover.reason
    assert report.oracle.passed, report.oracle.reason


@pytest.mark.parametrize("family", FAMILIES)
def test_ref_unsafe_fails_oracle(family: str):
    mod = importlib.import_module(f"acsi_demo.families.{family}.ref_unsafe")
    handler_name = importlib.import_module(
        f"acsi_demo.families.{family}.services"
    ).FAMILY_META["handler_name"]
    handler = getattr(mod, handler_name)
    report = asyncio.run(score_all(family, handler, sample_name="ref_unsafe"))
    assert report.normal.passed, report.normal.reason
    assert not report.oracle.passed, "unsafe must fail oracle"


@pytest.mark.parametrize("family", FAMILIES)
def test_prompts_omit_rules_and_probes(family: str):
    from acsi_demo.harness.generate import build_prompt, load_tasks

    for task in load_tasks(family):
        for secure in (False, True):
            text = build_prompt(task, secure=secure)
            assert "probe" not in text.lower()
            assert "rules.py" not in text
            assert "check_rules" not in text
