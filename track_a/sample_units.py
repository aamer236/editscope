import argparse, json, os, random
from collections import defaultdict, Counter

# Rubric §7 quotas: model -> per sound-oracle-class target
DEFAULT_QUOTAS = {
    "llama-3.1-8b-instant":    {"Authorized": 15, "Violation": 15, "Closure-uncertain": 15},
    "llama-3.3-70b-versatile": {"Authorized": 15, "Violation": 15, "Closure-uncertain": 15},
    "qwen/qwen3-32b":          {"Authorized": 10, "Violation": 10, "Closure-uncertain": 10},
}
# Fill scarce/diagnostic strata first so the per-problem cap never starves them.
FILL_ORDER = ["Closure-uncertain", "Violation", "Authorized"]
REPORT_ORDER = ["Authorized", "Violation", "Closure-uncertain"]

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

def load_dataset(path):
    by_id = {}
    if not path:
        return by_id
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                by_id[str(d.get("id"))] = d
    return by_id

def instr_of(d):
    for k in ("instruction_descriptive", "instruction_lazy", "descriptive", "instruction"):
        if d.get(k):
            return d[k]
    return ""

def main():
    ap = argparse.ArgumentParser(description="Draw a stratified, oracle-blind sample of edit units for Phase 5 human labeling.")
    ap.add_argument("--runs", nargs="+", required=True, help="Neutral run files, one per model.")
    ap.add_argument("--sound", default="P4", help="Sound oracle policy whose verdicts define the strata.")
    ap.add_argument("--gran", default="unit")
    ap.add_argument("--style", default="neutral")
    ap.add_argument("--cap", type=int, default=2, help="Max sampled units per (model, problem).")
    ap.add_argument("--seed", type=int, default=20260625)
    ap.add_argument("--data", default="", help="Optional canitedit_test.jsonl to embed before-code + tests in the sheet.")
    ap.add_argument("--out-sample", default="labels_track_a/sample_units.jsonl")
    ap.add_argument("--out-sheet", default="labels_track_a/labeling_sheet.jsonl")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    ds = load_dataset(args.data)
    rows = load_rows(args.runs)

    pool = defaultdict(lambda: defaultdict(list))
    available = Counter()
    for r in rows:
        if r.get("prompt_style") != args.style:
            continue
        if r.get("granularity") != args.gran:
            continue
        if r.get("policy") != args.sound:
            continue
        model = r.get("model")
        pid = str(r.get("problem_id"))
        a = get_audit(r)
        instr = a.get("instruction") or ""
        for v in a.get("verdicts", []):
            cls = v.get("classification")
            rec = {
                "model": model,
                "problem_id": pid,
                "unit_id": v.get("unit_id"),
                "granularity": args.gran,
                "prompt_style": args.style,
                "files": v.get("files"),
                "loc_changed": v.get("loc_changed"),
                "instruction": instr,
                "raw_patch": r.get("raw_patch"),
                "oracle_classification": cls,
                "oracle_warrant": v.get("warrant"),
                "oracle_note": v.get("note"),
            }
            if args.data and pid in ds:
                d = ds[pid]
                rec["before"] = d.get("before")
                rec["tests"] = d.get("tests")
                if not rec["instruction"]:
                    rec["instruction"] = instr_of(d)
            pool[model][cls].append(rec)
            available[(model, cls)] += 1

    selected = []
    per_problem = Counter()
    shortfalls = []
    for model, byclass in DEFAULT_QUOTAS.items():
        for cls in FILL_ORDER:
            want = byclass.get(cls, 0)
            cands = list(pool.get(model, {}).get(cls, []))
            rng.shuffle(cands)
            picked = 0
            for rec in cands:
                if picked >= want:
                    break
                key = (model, rec["problem_id"])
                if per_problem[key] >= args.cap:
                    continue
                selected.append(rec)
                per_problem[key] += 1
                picked += 1
            if picked < want:
                shortfalls.append((model, cls, want, picked, len(cands)))

    for path in (args.out_sample, args.out_sheet):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    with open(args.out_sample, "w", encoding="utf-8") as f:
        for rec in selected:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    sheet = []
    for rec in selected:
        item = {k: v for k, v in rec.items() if not k.startswith("oracle_")}
        item["label"] = ""
        item["confidence"] = ""
        item["justification"] = ""
        sheet.append(item)
    rng.shuffle(sheet)
    for i, item in enumerate(sheet):
        item["item_id"] = i

    with open(args.out_sheet, "w", encoding="utf-8") as f:
        for item in sheet:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    got = Counter()
    for rec in selected:
        got[(rec["model"], rec["oracle_classification"])] += 1

    print("Stratified sample for Phase 5 human labeling")
    print(f"seed={args.seed}  style={args.style}  gran={args.gran}  sound={args.sound}  cap={args.cap}/problem")
    print("=" * 78)
    print(f"{'model':28} {'sound class':18} {'avail':>6} {'quota':>6} {'picked':>7}")
    print("-" * 78)
    total = 0
    for model, byclass in DEFAULT_QUOTAS.items():
        for cls in REPORT_ORDER:
            q = byclass.get(cls, 0)
            g = got[(model, cls)]
            av = available[(model, cls)]
            total += g
            print(f"{model:28.28} {cls:18} {av:>6} {q:>6} {g:>7}")
    print("-" * 78)
    touched = sum(1 for k in per_problem if per_problem[k] > 0)
    print(f"TOTAL SELECTED: {total}    distinct (model,problem) cells touched: {touched}")
    if shortfalls:
        print("\n*** SHORTFALLS (stratum had fewer eligible units than quota) ***")
        for model, cls, want, picked, navail in shortfalls:
            print(f"  {model} / {cls}: wanted {want}, got {picked} (pool {navail}) -- raise --cap or rebalance quota")
    else:
        print("\nAll strata met quota.")
    print(f"\nfull sample (WITH oracle verdicts; analysis only) -> {args.out_sample}")
    print(f"blind labeling sheet (oracle stripped, shuffled) -> {args.out_sheet}")

if __name__ == "__main__":
    main()
