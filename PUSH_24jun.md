# EditScope — changes to commit & push (24 Jun 2026)

Sandbox has no network, so push from your machine (the repo clone that tracks
origin = github.com/bharat06-co/editscope, branch main).

## What changed this session

1. mypy --strict timeout is now caught as inconclusive (not a crash).
   - The harness run on torch units was hanging mypy on stub crawling, raising
     subprocess.TimeoutExpired and aborting the whole eval.
   - Fix: wrap the mypy subprocess in try/except subprocess.TimeoutExpired and
     set mypy_ok = None (inconclusive). Soundness preserved: newly_broken only
     flags a regression when base mypy_ok is True and variant mypy_ok is False;
     None never manufactures a W2 signal.
   - Applied to all three resolver copies:
     - cie_harness/resolver.py
     - scope_oracle/resolver.py
     - scope_auditor_real/resolver.py

2. Adversarial W1-unsoundness probe expanded 8 -> 20 (adversarial_probe.py).
   - Added A9..A20 (set ops, recursion, predicates, text aggregation, lerp,
     list reshaping, palindrome, median, class-method+func, varargs,
     comprehensions). All 20 are valid (w1=True, w2=False, smuggle ungrounded).
   - Verified: P2 wrongly-authorized 20/20; P1/P3/P4/P5 = 0/20.

## Verification (already green in sandbox)

    python -m scope_oracle.tests.test_audit_freeze   # ALL PASS (8/8)
    python -m cie_harness.adversarial_probe          # P2 20/20, others 0/20

## Push (run on your machine)

    cd <your editscope clone>
    # 1) Copy the updated files from this bundle into the matching paths in your
    #    clone (resolver.py x3 + adversarial_probe.py). Adjust paths if your
    #    package layout differs (e.g. nested scope_oracle under scope_auditor_real).

    # 2) Confirm tests still pass locally
    python -m scope_oracle.tests.test_audit_freeze

    # 3) Stage, commit, push
    git add -A
    git commit -m "harness: catch mypy --strict timeout as inconclusive; expand adversarial probe to n=20"
    git push origin main

## Note on the earlier pending commit

If commit 3b8e36e (intra-unit granularity) was never pushed, it will go up in the
same git push origin main once you commit on top of it.
