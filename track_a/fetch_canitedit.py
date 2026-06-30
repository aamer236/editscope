"""Fetch CanItEdit -> local ./canitedit/canitedit_test.jsonl (Track A)."""
from datasets import load_dataset
from pathlib import Path
import json

REVISION = None  # TODO: pin to the HF commit hash P1 confirms (reproducibility)

ds = load_dataset("nuprl/CanItEdit", revision=REVISION)
split = "test" if "test" in ds else list(ds.keys())[0]
rows = ds[split]

out = Path("canitedit"); out.mkdir(exist_ok=True)
fp = out / "canitedit_test.jsonl"
with open(fp, "w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(dict(row)) + "\n")
print(f"wrote {len(rows)} rows to {fp}  (split='{split}')")
