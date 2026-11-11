"""Generate code samples from LLM_MODELS (Stage 4 — run only after validation sign-off)."""

from __future__ import annotations

import argparse
import os
import re
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
FAMILIES = ["upload", "token", "payment", "secret", "database"]

SECURE_SENTENCE = "Handle cancellation and timeouts securely."


def load_tasks(family: str) -> list[dict]:
    path = ROOT / "families" / family / "tasks.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_prompt(task: dict, *, secure: bool) -> str:
    """Build a model prompt. Must never include rules, probes, or the word probe."""
    body = task["prompt"].rstrip()
    extra = (task.get("extra") or "").strip()
    parts = [body]
    if extra:
        parts.append(f"Extra requirement: {extra}")
    parts.append(
        "Return a single Python code block that defines only the required async function. "
        "Assume the listed helpers are already imported."
    )
    if secure:
        parts.append(SECURE_SENTENCE)
    text = "\n\n".join(parts)
    assert "probe" not in text.lower(), "prompt must not mention probes"
    assert "rules.py" not in text, "prompt must not mention rules.py"
    return text


def extract_python(text: str) -> str:
    fence = re.search(r"```(?:python)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        return textwrap.dedent(fence.group(1)).strip() + "\n"
    return textwrap.dedent(text).strip() + "\n"


def chat_client():
    from openai import OpenAI

    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        raise SystemExit("LLM_API_KEY is required")
    return OpenAI(base_url=base, api_key=key)


def generate_one(client, model: str, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        temperature=0.8,
        messages=[
            {"role": "system", "content": "You write careful async Python functions."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def safe_model_tag(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", model)


def main() -> None:
    parser = argparse.ArgumentParser(description="ACSI sample generator (Stage 4)")
    parser.add_argument("--families", nargs="*", default=FAMILIES)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--plain-only", action="store_true")
    parser.add_argument("--dry-prompt", action="store_true", help="Print prompts only")
    args = parser.parse_args()

    models = [m.strip() for m in os.environ.get("LLM_MODELS", "").split(",") if m.strip()]
    if not models and not args.dry_prompt:
        raise SystemExit("Set LLM_MODELS to a comma-separated list of model names")

    SAMPLES.mkdir(parents=True, exist_ok=True)
    client = None if args.dry_prompt else chat_client()
    conditions = ["plain"] if args.plain_only else ["plain", "secure"]

    for family in args.families:
        for task in load_tasks(family):
            for model in models or ["dry"]:
                for condition in conditions:
                    prompt = build_prompt(task, secure=(condition == "secure"))
                    for k in range(1, args.samples + 1):
                        name = f"{family}_{task['id']}_{safe_model_tag(model)}_{condition}_{k}.py"
                        out = SAMPLES / name
                        if args.dry_prompt:
                            print(f"=== {name} ===\n{prompt}\n")
                            continue
                        assert client is not None
                        raw = generate_one(client, model, prompt)
                        code = extract_python(raw)
                        # Rewrite imports to family services for harness loading
                        header = (
                            f"# auto-generated\n"
                            f"from acsi_demo.families.{family}.services import *  # noqa: F403\n\n"
                        )
                        out.write_text(header + code, encoding="utf-8")
                        print(f"wrote {out}")


if __name__ == "__main__":
    main()
