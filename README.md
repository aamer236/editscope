# EditScope — Scope-Faithful Coding Agents (canonical repo)

**Owner:** P1 (Oracle / Codebase Lead). This is the *one* canonical repo. Branch hygiene, pinned deps, reproducible configs.

EditScope is a **sound, abstaining, instruction-conditioned scope oracle** for AI coding agents.
Given `(instruction, repo_before, patch)` it labels every change unit **Authorized**, **Violation**, or **Closure-uncertain**.

- **Authorization = seed ∪ W2.** W2 = forced closure verified by a *symbolic* resolver (no LLM inside).
- **W1 is unsound** → demoted to a *risk router* that sends non-seed/non-W2 units to **Closure-uncertain**, never to Authorized.
- **Guarantee:** soundness (never wrongly authorize), not completeness. Abstain instead of guessing.
- **Default policy P4** (W2 + W1 router). **Baseline P1** (naive: every non-seed = Violation).

## Quickstart (reproducibility gate — Phase 0 acceptance)
```bash
git clone <this-repo> && cd editscope
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pytest -q                      # unit + invariant tests
python -m scope_auditor_real.run_real --dataset canitedit --policy P4   # CanItEdit slice
```

**Phase 0 acceptance:** a teammate can clone and run the CanItEdit demo end-to-end from this README alone; zero unverified citation IDs in shared docs.

**Phase 1 acceptance gate:** reproduce collateral FP **0.53 → 0.007 @ recall 1.00**, **0 wrongly-authorized** on CanItEdit (n≈102); soundness invariant holds on the adversarial n=20 (W1-alone is 20/20 unsound and correctly routed to Uncertain).

## Package layout
```
scope_auditor_real/
  grounding.py     # seed extraction from instruction  [MIGRATE]
  mutate.py        # revert/mutation harness            [MIGRATE]
  partitioner.py   # minimal compilable change units    [MIGRATE]
  resolver.py      # symbolic closure: pyflakes+mypy+callgraph  [MIGRATE + HARDEN]
  policy.py        # P1/P4 classification orchestration  [WRITTEN]
  audit.py         # frozen audit() API entrypoint       [WRITTEN]
  metric_card.py   # metric-card aggregation             [WRITTEN]
  schema.py        # frozen dataclasses for JSON output   [WRITTEN]
  run_real.py      # dataset runner (CanItEdit, agents)  [WRITTEN/stub]
```
`[MIGRATE]` = port from existing `scope_auditor_real/`; do not reinvent (it already passes the gate).

## Hard constraints (non-negotiable)
- No circular eval — human slice + Cohen's κ before claiming numbers.
- API-first, GPU-later (QLoRA 7B).
- Checker stays **symbolic** — no LLM inside the oracle.
- Sandbox network OFF when auditing patches.
- Honest claims only — soundness not completeness; never report an unmeasured number.
