# Land the dataset pin (CanItEdit revision 3c07f38)

This package contains the files changed to pin the dataset revision for reproducibility.
Extract it **into the root of your editscope git clone** (the folder with `.git/`),
overwriting the same paths, then commit + push.

## Files in this package
```
scope_oracle/run_real.py        # real pinned loader + dataset_pin() + constants
scope_oracle/parity_real.py     # data_revision: unpinned -> 3c07f38, + dataset_pin block
scope_auditor_real/run_real.py  # identical pinned loader (mirror)
cie_harness/run_real.py         # metric card now records dataset_pin block
README.md                       # new "Dataset pin (reproducibility)" section
make_report.py                  # report wording: pin done
```

## Sanity check before pushing (optional, offline-safe)
```powershell
py -m scope_oracle.tests.test_audit_freeze      # expect ALL PASS (8/8)
py -m scope_oracle.run_real --dataset canitedit --policy P4   # prints the dataset_pin JSON
```

## Commit + push (from the clone root)
```powershell
git add -A
git commit -m "harness: pin CanItEdit dataset revision (HF 3c07f38) for reproducibility" -m "- real pinned loader in scope_oracle/scope_auditor_real run_real.py (revision=3c07f38; abort if num_examples != 105)" -m "- dataset_pin() helper + constants (revision, parquet sha256 9f78b1a2..cc6222)" -m "- record dataset_pin block in cie_harness metric cards" -m "- parity_real data_revision unpinned -> 3c07f38" -m "- README: Dataset pin section; report wording updated"
git push origin main
```

If `git commit` says *nothing to commit*, the files didn't overwrite the right paths —
check you extracted into the clone root. If it complains about identity (the silent-fail
from last time), set it once:
```powershell
git config user.email "bvbhat1975@gmail.com"
git config user.name "bharat06-co"
```
Then re-run the commit + push. Confirm the new commit shows green CI under the Actions tab.

## The pin, for the record
- repo: `nuprl/CanItEdit`  split: `test`
- revision: **3c07f38** (verified, 2024-03-19; parent a90f026)
- test parquet sha256: `9f78b1a2378b96b24d158a6fe83d69aa18e43a360ae3b7d0891c02f660cc6222` (105 examples)
- coverage: 104/105 gold-passing; id 78 (llm_inference) is the GPU-only exclusion
