"""Track A - demo_card: one clean metric card for a single model under a policy.

Counts (Authorized / Violation / Closure-uncertain) come from the per-unit oracle
verdicts, exactly like sample_units.py. The four rates are the mean of each
problem's metric_card, exactly like summarize.py -- so the numbers match the
published tables.
"""
import argparse, json, statistics, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PRETTY = {
    "llama-3.1-8b-instant": "Llama-3.1-8B",
    "llama-3.3-70b-versatile": "Llama-3.3-70B",
    "qwen/qwen3-32b": "Qwen3-32B",
}
CLASSES = ["Authorized", "Violation", "Closure-uncertain"]
POLICY_LABEL = {"P4": "sound oracle", "P1": "naive checker"}

def get_audit(row):
    a = row.get("audit")
    return json.loads(a) if isinstance(a, str) else (a or {})

def load_rows(paths):
    rows = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print(f"(skip missing {pp})")
            continue
        for line in pp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def main():
    ap = argparse.ArgumentParser(description="One clean metric card for a model under a given policy.")
    ap.add_argument("--runs", nargs="+", required=True, help="Run file(s), e.g. the rescored neutral file.")
    ap.add_argument("--model", default=None, help="Model id. Defaults to the only model in the file.")
    ap.add_argument("--policy", default="P4", help="P4 (sound oracle) or P1 (naive checker).")
    ap.add_argument("--gran", default="unit")
    ap.add_argument("--style", default="neutral")
    args = ap.parse_args()

    rows = load_rows(args.runs)
    models = sorted({r.get("model") for r in rows if r.get("model")})
    model = args.model or (models[0] if len(models) == 1 else None)
    if model is None:
        raise SystemExit(f"Multiple models present: {models}. Re-run with --model <id>.")

    sel = [r for r in rows
           if r.get("model") == model
           and r.get("prompt_style", "neutral") == args.style
           and r.get("policy") == args.policy
           and r.get("granularity") == args.gran]
    if not sel:
        raise SystemExit(f"No rows for model={model}, style={args.style}, policy={args.policy}, gran={args.gran}.")

    counts = Counter()
    for r in sel:
        for v in get_audit(r).get("verdicts", []):
            counts[v.get("classification")] += 1

    def card_mean(field):
        vals = []
        for r in sel:
            mc = get_audit(r).get("metric_card") or {}
            v = mc.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(v)
        return statistics.mean(vals) if vals else None

    sv = card_mean("scope_violation_rate")
    ab = card_mean("uncertain_abstention_rate")
    loc = card_mean("extra_edit_loc")
    ap_vals = [1.0 if r.get("agent_pass") else 0.0 for r in sel if isinstance(r.get("agent_pass"), bool)]
    agent_pass = statistics.mean(ap_vals) if ap_vals else None

    def fmt(x, nd):
        return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "-"

    title = PRETTY.get(model, model)
    label = POLICY_LABEL.get(args.policy, args.policy)
    pad = max(len(c) for c in CLASSES) + 2
    print(f"{title} -- {label} ({args.policy}, {args.gran}, n={len(sel)})")
    for c in CLASSES:
        print(f"  {(c + ':'):<{pad}}{counts.get(c, 0)}")
    print(f"  scope-violation rate: {fmt(sv, 3)}   abstention: {fmt(ab, 3)}   extra LOC: {fmt(loc, 2)}   agent_pass: {fmt(agent_pass, 3)}")

if __name__ == "__main__":
    main()
