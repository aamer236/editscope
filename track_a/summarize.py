"""Track A - summarize run logs: point-estimate table + bootstrap 95% CIs."""
import argparse, json, random, statistics
from pathlib import Path
from collections import defaultdict

def _audit(r):
    a = r.get("audit")
    if isinstance(a, str):
        a = json.loads(a)
    return a or {}

CARD_FIELDS = ["scope_violation_rate", "necessary_collateral_false_flag_rate",
               "uncertain_abstention_rate", "extra_edit_loc", "extra_edit_blocks"]
PASS_FIELDS = ["agent_pass", "gold_pass"]
CI_FIELDS   = ["agent_pass", "scope_violation_rate", "uncertain_abstention_rate", "extra_edit_loc"]

def bootstrap_ci(values, B=2000, alpha=0.05, seed=0):
    vals = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(vals) < 2:
        return None
    rng = random.Random(seed)
    n = len(vals)
    means = []
    for _ in range(B):
        means.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int((alpha / 2) * B)]
    hi = means[int((1 - alpha / 2) * B) - 1]
    return (round(lo, 4), round(hi, 4))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["results_track_a/runs.jsonl"])
    ap.add_argument("--paired", action="store_true",
                    help="only include problem_ids present in EVERY input file")
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()

    file_id_sets, all_rows = [], []
    for path in args.runs:
        p = Path(path)
        if not p.exists():
            print(f"(skip missing {p})"); continue
        ids, rows = set(), []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line); rows.append(r); ids.add(r["problem_id"])
        file_id_sets.append(ids); all_rows.extend(rows)

    keep = None
    if args.paired and file_id_sets:
        keep = set.intersection(*file_id_sets)
        print(f"[paired] {len(keep)} shared problem_ids across {len(file_id_sets)} files\n")

    vals = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(int)
    for r in all_rows:
        if keep is not None and r["problem_id"] not in keep:
            continue
        key = (r["model"], r.get("prompt_style", "neutral"), r["policy"], r["granularity"])
        counts[key] += 1
        mc = _audit(r).get("metric_card", {}) or {}
        for f in CARD_FIELDS:
            v = mc.get(f)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals[key][f].append(v)
        for f in PASS_FIELDS:
            v = r.get(f)
            if isinstance(v, bool):
                vals[key][f].append(1.0 if v else 0.0)

    # --- point-estimate table ---
    cols = PASS_FIELDS + CARD_FIELDS
    header = f"{'model':<24}{'style':<8}{'pol':<5}{'gran':<11}{'n':<4}" + "".join(f"{c[:16]:<18}" for c in cols)
    print(header); print("-" * len(header))
    for key in sorted(vals.keys()):
        model, style, pol, gran = key
        row = f"{model:<24}{style:<8}{pol:<5}{gran:<11}{counts[key]:<4}"
        for c in cols:
            v = vals[key].get(c)
            cell = round(statistics.mean(v), 4) if v else "-"
            row += f"{str(cell):<18}"
        print(row)

    # --- bootstrap 95% CIs (per granularity) ---
    print("\nBootstrap 95% CIs (per granularity):")
    for key in sorted(vals.keys()):
        model, style, pol, gran = key
        print(f"\n  {model} / {style} / {pol} / {gran}  (n={counts[key]})")
        for f in CI_FIELDS:
            v = vals[key].get(f)
            if not v:
                print(f"    {f:<26} -"); continue
            m = round(statistics.mean(v), 4)
            ci = bootstrap_ci(v, B=args.boot)
            print(f"    {f:<26} {m}  " + (f"[{ci[0]}, {ci[1]}]" if ci else "[n/a]"))

if __name__ == "__main__":
    main()
