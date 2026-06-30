import json, sys
INV = {"Authorized": "necessary_collateral", "Violation": "scope_creep", "Closure-uncertain": "uncertain"}
src = sys.argv[1] if len(sys.argv) > 1 else "labels_track_a/sample_units.jsonl"
out = sys.argv[2] if len(sys.argv) > 2 else "labels_track_a/human_labels.smoke.jsonl"
n = 0
with open(src, encoding="utf-8") as f, open(out, "w", encoding="utf-8") as g:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        lab = INV.get(d.get("oracle_classification"), "uncertain")
        for lid in ("A", "B"):
            r = {"model": d["model"], "problem_id": d["problem_id"], "unit_id": d["unit_id"],
                 "labeler_id": lid, "label": lab, "confidence": 4, "justification": "smoke"}
            g.write(json.dumps(r) + "\n")
        n += 1
print(f"wrote smoke labels for {n} units -> {out}")
