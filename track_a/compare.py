"""Track A - paired per-problem difference test between two runs (bootstrap CI)."""
import argparse, json, random, statistics
from pathlib import Path

PASS_FIELDS = {"agent_pass", "gold_pass"}

def _audit(row):
    a = row.get("audit")
    if isinstance(a, str):
        a = json.loads(a)
    return a or {}

def load(path):
    d = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        d[(r["problem_id"], r["policy"], r["granularity"])] = r
    return d

def get_metric(row, field):
    if field in PASS_FIELDS:
        v = row.get(field)
        return (1.0 if v else 0.0) if isinstance(v, bool) else None
    mc = _audit(row).get("metric_card", {}) or {}
    v = mc.get(field)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

def boot_diff_ci(deltas, B=5000, alpha=0.05, seed=0):
    rng = random.Random(seed); n = len(deltas); ms = []
    for _ in range(B):
        ms.append(sum(deltas[rng.randrange(n)] for _ in range(n)) / n)
    ms.sort()
    return ms[int(alpha / 2 * B)], ms[int((1 - alpha / 2) * B) - 1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="baseline run file")
    ap.add_argument("--b", required=True, help="comparison run file")
    ap.add_argument("--field", default="scope_violation_rate")
    ap.add_argument("--policy", default="P4")
    ap.add_argument("--gran", default="unit")
    ap.add_argument("--boot", type=int, default=5000)
    args = ap.parse_args()

    A, B = load(args.a), load(args.b)
    deltas, a_vals, b_vals = [], [], []
    for (pid, pol, gran), ra in A.items():
        if pol != args.policy or gran != args.gran:
            continue
        rb = B.get((pid, pol, gran))
        if rb is None:
            continue
        va, vb = get_metric(ra, args.field), get_metric(rb, args.field)
        if va is None or vb is None:
            continue
        a_vals.append(va); b_vals.append(vb); deltas.append(vb - va)

    n = len(deltas)
    if n < 2:
        print("not enough paired observations"); return
    md = statistics.mean(deltas)
    lo, hi = boot_diff_ci(deltas, B=args.boot)
    sig = "SIGNIFICANT (CI excludes 0)" if (lo > 0 or hi < 0) else "not significant (CI includes 0)"
    print(f"field={args.field}  policy={args.policy}  gran={args.gran}  paired n={n}")
    print(f"  A mean = {round(statistics.mean(a_vals), 4)}   ({Path(args.a).name})")
    print(f"  B mean = {round(statistics.mean(b_vals), 4)}   ({Path(args.b).name})")
    print(f"  mean paired diff (B - A) = {round(md, 4)}   95% CI [{round(lo, 4)}, {round(hi, 4)}]")
    print(f"  -> {sig}")

if __name__ == "__main__":
    main()
