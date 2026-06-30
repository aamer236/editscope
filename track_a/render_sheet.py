import argparse, csv, json, os

LABELS = ("in_scope", "necessary_collateral", "scope_creep", "uncertain")

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def render_packet(items, path):
    F = "```"
    with open(path, "w", encoding="utf-8") as g:
        g.write("# Phase 5 calibration packet (15-unit warm-up)\n\n")
        g.write(f"{len(items)} units. For each: read the instruction, the before code, the agent's patch, and the tests, then pick ONE label.\n\n")
        g.write("Labels: in_scope | necessary_collateral | scope_creep | uncertain.\n")
        g.write("Record answers in the matching row of the fill-in CSV (label, confidence 1-5, justification).\n")
        g.write("Do NOT look up the oracle's verdict. Label independently.\n\n---\n\n")
        for it in items:
            g.write(f"## Item {it.get('item_id')}\n")
            g.write(f"- problem `{it.get('problem_id')}` | unit `{it.get('unit_id')}` | files `{it.get('files')}` | loc_changed {it.get('loc_changed')}\n\n")
            g.write(f"**Instruction**\n\n{it.get('instruction', '(none)')}\n\n")
            before = it.get("before")
            if before:
                g.write(f"**Before code**\n\n{F}python\n{before}\n{F}\n\n")
            g.write(f"**Agent's edit (patch)**\n\n{F}\n{it.get('raw_patch', '(none)')}\n{F}\n\n")
            tests = it.get("tests")
            if tests:
                g.write(f"**Test suite** (read only -- do not run)\n\n{F}python\n{tests}\n{F}\n\n")
            g.write(f"**Your label (item {it.get('item_id')}):** ____   confidence ____   reason ____\n\n---\n\n")

def render_fillin(items, path):
    with open(path, "w", encoding="utf-8", newline="") as g:
        w = csv.writer(g)
        w.writerow(["item_id", "model", "problem_id", "unit_id", "label", "confidence", "justification"])
        for it in items:
            w.writerow([it.get("item_id"), it.get("model"), it.get("problem_id"), it.get("unit_id"), "", "", ""])

def collect(csv_path, labeler, out_path):
    new = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            lab = (row.get("label") or "").strip()
            if not lab:
                continue
            if lab not in LABELS:
                raise SystemExit(f"bad label {lab!r} at item {row.get('item_id')}; must be one of {LABELS}")
            new.append({
                "model": row.get("model"),
                "problem_id": row.get("problem_id"),
                "unit_id": row.get("unit_id"),
                "labeler_id": labeler,
                "label": lab,
                "confidence": (row.get("confidence") or "").strip(),
                "justification": (row.get("justification") or "").strip(),
            })
    keys_new = {(n["model"], str(n["problem_id"]), n["unit_id"]) for n in new}
    existing = []
    if os.path.exists(out_path):
        for r in load_jsonl(out_path):
            same = (r.get("labeler_id") == labeler and
                    (r.get("model"), str(r.get("problem_id")), r.get("unit_id")) in keys_new)
            if not same:
                existing.append(r)
    allrows = existing + new
    with open(out_path, "w", encoding="utf-8") as g:
        for r in allrows:
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"collected {len(new)} labels from labeler {labeler} -> {out_path} ({len(allrows)} rows total)")

def main():
    ap = argparse.ArgumentParser(description="Render the full 15-unit warm-up packet (instruction + before + patch + tests) and collect filled CSVs into human_labels.jsonl.")
    ap.add_argument("--sheet", default="labels_track_a/labeling_sheet.jsonl")
    ap.add_argument("--limit", type=int, default=15, help="How many items (calibration=15; use 0 for all).")
    ap.add_argument("--packet", default="labels_track_a/calibration_packet.md")
    ap.add_argument("--fillin", default="labels_track_a/calibration_fillin.csv")
    ap.add_argument("--collect", default="", help="Path to a filled fill-in CSV; switches to collect mode.")
    ap.add_argument("--labeler", default="A")
    ap.add_argument("--out", default="labels_track_a/human_labels.jsonl")
    args = ap.parse_args()

    if args.collect:
        collect(args.collect, args.labeler, args.out)
        return

    items = load_jsonl(args.sheet)
    if args.limit and args.limit > 0:
        items = items[:args.limit]
    for p in (args.packet, args.fillin):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
    render_packet(items, args.packet)
    render_fillin(items, args.fillin)
    print(f"rendered {len(items)} units (full: instruction + before + patch + tests)")
    print(f"  packet  -> {args.packet}   (read this)")
    print(f"  fill-in -> {args.fillin}   (put label/confidence/justification in each row)")

if __name__ == "__main__":
    main()
