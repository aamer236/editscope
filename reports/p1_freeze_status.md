# P1 Freeze & Soundness Status

- **Commit:** 528b8ec (main)
- **CI:** run #16 — GREEN (freeze + intra-unit hardening + grounding precision)
- **Toolchain:** Python 3.13.0, pyflakes 3.4.0, mypy 2.1.0
- **Dataset:** nuprl/CanItEdit @ 3c07f38b1f9385f3214fcea94d4664c79df0d36a

## Frozen suite (no dataset/network)
python -m scope_oracle.tests.test_audit_freeze
python -m scope_oracle.tests.test_grounding_precision
python -m scope_oracle.tests.test_intra_unit_hardening

## CanItEdit parity gate (n=102)
python -m scope_oracle.parity_real --data ./canitedit --limit 102

- P1: collateral_fpr 0.532, recall 1.0, wrongly_allowed 0
- P4: collateral_fpr 0.0072, recall 1.0, wrongly_allowed 0, uncertain 0.324
- soundness: PASS

## Adversarial probe (n=20)
python -m cie_harness.adversarial_probe
- P2 (W1-only): 20/20 wrongly-allowed (unsound, as expected)
- P3/P4/P5: 0 wrongly-allowed (P4/P5 route all 20 to Uncertain)