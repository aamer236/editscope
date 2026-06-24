import argparse
import csv
import json
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

from .grounding import extract
from .mutate import make as make_mutants
from .partitioner import Unit, changed_units, restore_unit, touched_names
from .resolver import check, newly_broken

POLICIES = ["P1 naive_target_only", "P2 revert_only_w1", "P3 w2_only_strict", "P4 w2_plus_w1_router", "P5 w2_plus_w1_and_resolve_router"]


def _git_rev(path: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "not_available"


def _load_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def load_cases(root: Path):
    files = list(root.rglob("*.jsonl")) + list(root.rglob("*.json"))
    for f in files:
        try:
            rows = list(_load_jsonl(f)) if f.suffix == ".jsonl" else json.loads(f.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("examples") or []
            for i, row in enumerate(rows):
                keys = {k.lower(): k for k in row}
                b = keys.get("before") or keys.get("before_code") or keys.get("original_code")
                a = keys.get("after") or keys.get("after_code") or keys.get("gold")
                d = keys.get("descriptive") or keys.get("descriptive_instruction") or keys.get("instruction")
                lazy = keys.get("lazy") or keys.get("lazy_instruction")
                tests = keys.get("tests") or keys.get("test") or keys.get("hidden_tests")
                if b and a and d:
                    yield {"problem_id": row.get("id", f"{f.name}:{i}"), "before": row[b], "after": row[a], "prompt": row[d], "lazy": row.get(lazy, "") if lazy else "", "tests": row.get(tests, "") if tests else ""}
        except Exception:
            continue


def run_tests(src: str, tests: str, stem: str) -> bool:
    if not tests:
        return True
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="cie_test_"))
    mod = d / "candidate.py"
    mod.write_text(src, encoding="utf-8")
    t = d / "test_candidate.py"
    t.write_text("from candidate import *\n" + tests, encoding="utf-8")
    env = os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", str(t)], cwd=str(d), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    return p.returncode == 0


def outcome(policy: str, is_seed: bool, w2: bool, w1: bool, resolvable: bool) -> str:
    if policy.startswith("P1"):
        return "Authorized" if is_seed else "Violation"
    if policy.startswith("P2"):
        return "Authorized" if (is_seed or w1) else "Violation"
    if policy.startswith("P3"):
        return "Authorized" if (is_seed or w2) else "Violation"
    if policy.startswith("P4"):
        if is_seed or w2: return "Authorized"
        return "Uncertain" if w1 else "Violation"
    if policy.startswith("P5"):
        if is_seed or w2: return "Authorized"
        return "Uncertain" if (w1 or not resolvable) else "Violation"
    raise ValueError(policy)


def ci(vals):
    if not vals:
        return [None, None]
    rng = random.Random(20260617)
    boots = [statistics.mean(rng.choice(vals) for _ in vals) for _ in range(1000)]
    boots.sort()
    return [boots[24], boots[974]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("CANITEDIT_DIR", "/tmp/CanItEdit"))
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()
    root = Path(args.data)
    rows = []
    skips = []
    attempted = 0; gold_ok = 0
    loaded_any = False
    if not root.exists():
        skips.append({"problem_id":"dataset", "reason":"dataset path not found"})
    for case in load_cases(root):
        loaded_any = True
        if gold_ok >= args.limit: break
        attempted += 1
        pid = str(case["problem_id"])
        if not run_tests(case["after"], case.get("tests", ""), pid):
            skips.append({"problem_id": pid, "reason": "gold tests did not pass here"}); continue
        gold_ok += 1
        g = extract(case["prompt"], case["before"])
        base_res = check(case["after"], f"base_{gold_ok}")
        units = changed_units(case["before"], case["after"])
        named = touched_names(units) | g.names
        audit_items = []
        for u in units:
            # Real unit: audited program is the full edit; reverting restores the before-text.
            audit_items.append((u, "collateral" if u.name not in g.names else "seed", u.family, case["after"], restore_unit(case["after"], u)))
        for m in make_mutants(case["after"], named):
            u = Unit(f"mut_{m.family}_{len(audit_items)}", m.family, m.start, m.end, "", "", m.name)
            # FIX (kill-gate): audit the MUTATED source (m.src). Reverting the
            # injected violation yields the clean gold (case["after"]).
            # Previously m.src was discarded and the clean gold was audited,
            # which made every policy trivially return "Violation" and tested nothing.
            audit_items.append((u, m.label, m.family, m.src, case["after"]))
        for u, true_label, family, audited_src, reverted_src in audit_items:
            base_for_unit = check(audited_src, f"base_{gold_ok}_{u.unit_id}")
            var_res = check(reverted_src, f"var_{gold_ok}_{u.unit_id}")
            # W2 = removing THIS unit newly breaks the audited program (forced closure).
            w2 = newly_broken(base_for_unit, var_res)
            # W1 = reverting the unit flips a task test (behavioral, UNSOUND -> router only):
            #   audited passes AND reverted fails.
            if case.get("tests"):
                audited_pass = run_tests(audited_src, case["tests"], f"au_{gold_ok}_{u.unit_id}")
                reverted_pass = run_tests(reverted_src, case["tests"], f"rv_{gold_ok}_{u.unit_id}")
                w1 = bool(audited_pass and not reverted_pass)
            else:
                w1 = False
            is_seed = u.name in g.names or true_label == "seed"
            resolvable = var_res.get("compile_ok") and var_res.get("pyflakes_ok")
            for pol in POLICIES:
                out = outcome(pol, is_seed, w2, w1, resolvable)
                rows.append({"problem_id": pid, "policy": pol.split()[0], "policy_name": pol, "unit_id": u.unit_id, "family": family, "true_label": true_label, "outcome": out, "w2": w2, "w1": w1, "seed": is_seed, "grounding_confidence": g.confidence, "grounding_missed": g.missed, "resolver_disagreement": (var_res.get("mypy_ok") is not None and var_res.get("mypy_ok") != var_res.get("pyflakes_ok"))})
    if root.exists() and not loaded_any:
        skips.append({"problem_id":"dataset", "reason":"no benchmark records found in local checkout; HuggingFace download blocked in this environment"})
    Path("results").mkdir(exist_ok=True)
    with open("results/per_unit_real.csv", "w", newline="", encoding="utf-8") as f:
        fields = ["problem_id","policy","policy_name","unit_id","family","true_label","outcome","w2","w1","seed","grounding_confidence","grounding_missed","resolver_disagreement"]
        wr = csv.DictWriter(f, fieldnames=fields); wr.writeheader(); wr.writerows(rows)
    metrics = {"data_revision": _git_rev(root), "coverage": {"attempted": attempted, "passed_gold": gold_ok, "skipped": skips}}
    byp = {}
    for pol in {r["policy"] for r in rows}:
        rr = [r for r in rows if r["policy"] == pol]
        coll = [r["outcome"] == "Violation" for r in rr if r["true_label"] in {"collateral", "seed"}]
        vio = [r["outcome"] == "Violation" for r in rr if r["true_label"] == "violation"]
        wrong_allow = sum(1 for r in rr if r["true_label"] == "violation" and r["outcome"] == "Authorized")
        third = [r["outcome"] == "Uncertain" for r in rr]
        byp[pol] = {"collateral_fpr": statistics.mean(coll) if coll else None, "collateral_fpr_ci": ci(coll), "violation_recall": statistics.mean(vio) if vio else None, "violation_recall_ci": ci(vio), "wrongly_allowed_count": wrong_allow, "third_outcome_rate": statistics.mean(third) if third else None}
    metrics["policies"] = byp
    Path("results/metrics_real.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
