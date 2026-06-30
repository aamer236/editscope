import argparse, json, math, random
from collections import defaultdict

def load_rows(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows

def get_audit(row):
    a = row.get("audit")
    return json.loads(a) if isinstance(a, str) else a

def unit_verdicts(row):
    a = get_audit(row)
    return {v.get("unit_id"): v.get("classification") for v in a.get("verdicts", [])}

def _pct(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100.0
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

def boot_ci(per_problem, B=2000, seed=12345):
    if not per_problem:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(per_problem)
    est = []
    for _ in range(B):
        fp = tp = 0
        for _ in range(n):
            f, t = per_problem[rng.randrange(n)]
            fp += f; tp += t
        if fp + tp > 0:
            est.append(fp / (fp + tp))
    est.sort()
    return (_pct(est, 2.5), _pct(est, 97.5))

def main():
    ap = argparse.ArgumentParser(description="Corpus collateral FPR of the naive checker, with the sound oracle as reference.")
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--gran", default="unit", help="Granularity to score (default unit; 'all' = every granularity).")
    ap.add_argument("--naive", default="P1")
    ap.add_argument("--sound", default="P4")
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()

    rows = load_rows(args.runs)
    index = {}
    for r in rows:
        if args.gran != "all" and r.get("granularity") != args.gran:
            continue
        index[(r.get("model"), r.get("prompt_style"), r.get("problem_id"),
               r.get("granularity"), r.get("policy"))] = r

    agg = defaultdict(lambda: defaultdict(lambda: {"fp": 0, "tp": 0, "unc": 0, "oth": 0, "nv": 0, "units": 0}))
    seen = set()
    for (model, style, pid, gran, policy) in list(index.keys()):
        base = (model, style, pid, gran)
        if base in seen:
            continue
        seen.add(base)
        rn = index.get((model, style, pid, gran, args.naive))
        rs = index.get((model, style, pid, gran, args.sound))
        if rn is None or rs is None:
            continue
        vn = unit_verdicts(rn); vs = unit_verdicts(rs)
        cell = agg[(model, style)][base]
        for uid, cn in vn.items():
            cs = vs.get(uid)
            if cs is None:
                continue
            cell["units"] += 1
            if cn == "Violation":
                cell["nv"] += 1
                low = cs.lower()
                if cs == "Authorized":
                    cell["fp"] += 1
                elif cs == "Violation":
                    cell["tp"] += 1
                elif "uncertain" in low:
                    cell["unc"] += 1
                else:
                    cell["oth"] += 1

    print(f"Collateral false-positive rate of naive {args.naive} checker (reference = sound {args.sound}); gran={args.gran}")
    print("collFPR = FP / (FP + TP).  FP = naive=Violation & sound=Authorized (necessary collateral cleared by the sound oracle).")
    print("TP = naive & sound both Violation (genuine scope creep).  Unc = sound abstains (closure-uncertain), excluded from denominator.")
    print("Oth = any other sound label (should be 0); CI = cluster bootstrap resampling problems.")
    print("=" * 110)
    print(f"{'model':30} {'style':7} {'probs':>5} {'nViol':>6} {'FP':>5} {'TP':>5} {'Unc':>4} {'Oth':>4} {'collFPR':>8}   95% CI")
    print("-" * 110)
    for (model, style), probs in sorted(agg.items()):
        per_problem = [(c["fp"], c["tp"]) for c in probs.values()]
        FP = sum(c["fp"] for c in probs.values())
        TP = sum(c["tp"] for c in probs.values())
        UNC = sum(c["unc"] for c in probs.values())
        OTH = sum(c["oth"] for c in probs.values())
        NV = sum(c["nv"] for c in probs.values())
        denom = FP + TP
        fpr = FP / denom if denom else float("nan")
        ci = boot_ci(per_problem, B=args.boot) if args.boot > 0 else (float("nan"), float("nan"))
        ci_s = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if args.boot > 0 else ""
        print(f"{model:30.30} {style:7.7} {len(probs):>5} {NV:>6} {FP:>5} {TP:>5} {UNC:>4} {OTH:>4} {fpr:>8.4f}   {ci_s}")

if __name__ == "__main__":
    main()
