# ACSI demo

Feasibility demo: security invariants under cancellation and timeout in LLM-written async Python.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Stage 3 validation (references)

```bash
python -m acsi_demo.harness.validate_refs
pytest -q
```

Every `ref_unsafe` must fail the oracle; every `ref_safe` must pass all four scoring modes.

## Stage 4+ (after confirmation)

```bash
export LLM_BASE_URL=...
export LLM_API_KEY=...
export LLM_MODELS=model-a,model-b
python -m acsi_demo.harness.generate
```

## Layout

- `acsi_demo/harness/` — checkpoints, runner, scoring, generate
- `acsi_demo/families/{upload,token,payment,secret,database}/` — services, hidden rules, tasks, refs
- `acsi_demo/samples/` — generated code (gitignored)
- `acsi_demo/results/` — scores and failure writeups (gitignored)
