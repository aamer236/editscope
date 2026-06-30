import argparse, json, math, random
from collections import defaultdict, Counter

HUMAN_TO_ORACLE = {
    "in_scope": "Authorized",
    "necessary_collateral": "Authorized",
    "scope_creep": "Violation",
    "uncertain": "Closure-uncertain",
}
ADJ_IDS = {"final", "adjudicated", "adj", "gold"}

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def get_audit(row):
    a = row.get("audit")
    return json.loads(a) if isinstance(a, str) else a

def unit_key(r):
    return (r.get("model"), str(r.get("problem_id")), r.get("unit_id"))

def cohen_kappa(pairs):
    pairs = [(a, b) for (a, b) in pairs if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return float("nan"), 0
    cats = set()
    for a, b in pairs:
        cats.add(a); cats.add(b)
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if abs(1 - pe) < 1e-12:
        return (1.0 if po == 1.0 else float("nan")), n
    return (po - pe) / (1 - pe), n

def fleiss_kappa(item_ratings, categories):
    counts = [sum(c.values()) for c in item_ratings]
    if not counts:
        return float("nan"), 0, 0
    R = Counter(counts).most_common(1)[0][0]
    items = [c for c in item_ratings if sum(c.values()) == R]
    N = len(items)
    if N == 0 or R < 2:
        return float("nan"), N, R
    cats = list(categories)
    P_is = []
    col_tot = {c: 0 for c in cats}
    for it in items:
        s = sum(it.get(c, 0) ** 2 for c in cats)
        P_is.append((s - R) / (R * (R - 1)))
        for c in cats:
            col_tot[c] += it.get(c, 0)
    Pbar = sum(P_is) / N
    p_j = {c: col_tot[c] / (N * R) for c in cats}
    Pe = sum(v * v for v in p_j.values())
    if abs(1 - Pe) < 1e-12:
        return float("nan"), N, R
    return (Pbar - Pe) / (1 - Pe), N, R

def resolve_label(labeler_map):
    for lid, lab in labeler_map.items():
        if str(lid).lower() in ADJ_IDS:
            return lab, "adjudicated"
    votes = Counter(labeler_map.values())
    top, n = votes.most_common(1)[0]
    ties = [c for c, v in votes.items() if v == n]
    if len(ties) > 1:
        return "uncertain", "tie->uncertain"
    return top, "majority"

def pct(vals, p):
    if not vals:
        return float("nan")
    vals = sorted(vals)
    k = (len(vals) - 1) * p / 100.0
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] * (c - k) + vals[c] * (k - f)

def main():
    ap = argparse.ArgumentParser(description="Phase 5: reliability (kappa) + true collateral-FPR from human labels.")
    ap.add_argument("--labels", required=True, help="human_labels.jsonl (one row per unit per labeler).")
    ap.add_argument("--sample", required=True, help="sample_units.jsonl (WITH oracle verdicts).")
    ap.add_argument("--runs", nargs="+", default=[], help="Neutral run files: needed for naive P1 verdicts + stratum sizes (true collateral-FPR).")
    ap.add_argument("--naive", default="P1")
    ap.add_argument("--sound", default="P4")
    ap.add_argument("--gran", default="unit")
    ap.add_argument("--style", default="neutral")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260625)
    args = ap.parse_args()

    sample = load_jsonl(args.sample)
    labels = load_jsonl(args.labels)

    oracle_cls = {}
    sample_strata = {}
    for r in sample:
        k = unit_key(r)
        oracle_cls[k] = r.get("oracle_classification")
        sample_strata[k] = (r.get("model"), r.get("oracle_classification"))

    by_unit = defaultdict(dict)
    for r in labels:
        lab = r.get("label")
        if lab:
            by_unit[unit_key(r)][r.get("labeler_id")] = lab

    labelers = sorted({lid for m in by_unit.values() for lid in m if str(lid).lower() not in ADJ_IDS})
    print("Phase 5 reliability report")
    print("=" * 74)
    print(f"labeled units: {len(by_unit)}   independent labelers: {labelers}")

    print("\n-- Inter-human agreement (pairwise Cohen's kappa) --")
    for i in range(len(labelers)):
        for j in range(i + 1, len(labelers)):
            la, lb = labelers[i], labelers[j]
            pairs = [(m[la], m[lb]) for u, m in by_unit.items() if la in m and lb in m]
            k, n = cohen_kappa(pairs)
            print(f"  {la} vs {lb}: kappa={k:.3f}  (n={n} co-labeled)")

    cats4 = ["in_scope", "necessary_collateral", "scope_creep", "uncertain"]
    item_ratings = []
    for u, m in by_unit.items():
        ind = [lab for lid, lab in m.items() if str(lid).lower() not in ADJ_IDS]
        if ind:
            item_ratings.append(Counter(ind))
    fk, fN, fR = fleiss_kappa(item_ratings, cats4)
    print(f"\n-- Fleiss' kappa (4-class): {fk:.3f}  over {fN} items at {fR} raters/item --")

    resolved = {}
    res_mode = Counter()
    for u, m in by_unit.items():
        lab, how = resolve_label(m)
        resolved[u] = lab
        res_mode[how] += 1
    print(f"\nresolved labels via: {dict(res_mode)}")

    pairs = []
    conf = defaultdict(Counter)
    for u, hlab in resolved.items():
        oc = oracle_cls.get(u)
        if oc is None:
            continue
        hc = HUMAN_TO_ORACLE.get(hlab)
        pairs.append((oc, hc))
        conf[oc][hc] += 1
    ok, on = cohen_kappa(pairs)
    print("\n-- Oracle <-> human agreement (collapsed to Authorized/Violation/Closure-uncertain) --")
    print(f"  Cohen's kappa = {ok:.3f}  (n={on})   target >= 0.61")
    classes3 = ["Authorized", "Violation", "Closure-uncertain"]
    print("  confusion matrix (rows = oracle, cols = human):")
    print("    " + "".join(f"{c[:11]:>13}" for c in classes3) + f"{'row tot':>10}")
    for oc in classes3:
        row = conf.get(oc, Counter())
        cells = "".join(f"{row.get(hc, 0):>13}" for hc in classes3)
        print(f"    {oc[:11]:<11}{cells}{sum(row.values()):>10}")
    if on:
        agree = sum(conf[c].get(c, 0) for c in classes3)
        print(f"  raw agreement: {agree}/{on} = {agree/on:.3f}")

    if args.runs:
        naive_cls = {}
        pool_avail = Counter()
        for path in args.runs:
            for r in load_jsonl(path):
                if r.get("prompt_style") != args.style or r.get("granularity") != args.gran:
                    continue
                a = get_audit(r)
                model = r.get("model"); pid = str(r.get("problem_id"))
                if r.get("policy") == args.naive:
                    for v in a.get("verdicts", []):
                        naive_cls[(model, pid, v.get("unit_id"))] = v.get("classification")
                if r.get("policy") == args.sound:
                    for v in a.get("verdicts", []):
                        pool_avail[(model, v.get("classification"))] += 1

        sampled_per_stratum = Counter(sample_strata.values())
        def weight(u):
            st = sample_strata.get(u)
            s = sampled_per_stratum.get(st, 0)
            return (pool_avail.get(st, 0) / s) if s else 0.0

        rows = []
        un_fp = un_tp = 0
        for u, hlab in resolved.items():
            if naive_cls.get(u) != "Violation":
                continue
            if hlab == "uncertain":
                continue
            is_fp = 1 if hlab in ("in_scope", "necessary_collateral") else 0
            is_tp = 1 if hlab == "scope_creep" else 0
            un_fp += is_fp; un_tp += is_tp
            rows.append((u[1], is_fp, is_tp, weight(u)))

        denom = un_fp + un_tp
        print("\n-- TRUE collateral-FPR of the naive checker (human ground truth) --")
        if denom == 0:
            print("  no naive-flagged, human-ruled units in the sample -- cannot estimate.")
        else:
            print(f"  within-sample (UNWEIGHTED): FP={un_fp} TP={un_tp} -> {un_fp/denom:.3f}")
            print("    [caution] sample is P4-stratified; this is NOT a corpus estimate.")
            wfp = sum(w for _, fp, _, w in rows if fp)
            wtp = sum(w for _, _, tp, w in rows if tp)
            if wfp + wtp > 0:
                west = wfp / (wfp + wtp)
                byprob = defaultdict(list)
                for pid, fp, tp, w in rows:
                    byprob[pid].append((fp, tp, w))
                probs = list(byprob.keys())
                rng = random.Random(args.seed)
                est = []
                for _ in range(args.boot):
                    nfp = ntp = 0.0
                    for _ in range(len(probs)):
                        for fp, tp, w in byprob[probs[rng.randrange(len(probs))]]:
                            nfp += w * fp; ntp += w * tp
                    if nfp + ntp > 0:
                        est.append(nfp / (nfp + ntp))
                lo, hi = (pct(est, 2.5), pct(est, 97.5)) if est else (float("nan"), float("nan"))
                print(f"  stratum-reweighted (corpus-projected): {west:.3f}   95% CI [{lo:.3f}, {hi:.3f}]")
                print("    compare vs finding 6 (oracle-referenced): 8B 0.260 / 70B 0.350 / Qwen3 0.043")
    else:
        print("\n(skipping true collateral-FPR: pass --runs with the neutral run files to compute it)")

if __name__ == "__main__":
    main()
