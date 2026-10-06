"""Merge subagent explanation batches (JSON arrays) into data/explanations.json and validate them.

Usage: python3 merge_explanations.py <batches_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(src):
    questions = {q["id"]: q for q in json.loads((ROOT / "data/questions.json").read_text())["questions"]}
    out_path = ROOT / "data/explanations.json"
    merged = json.loads(out_path.read_text()) if out_path.exists() else {}
    problems = []
    for f in sorted(Path(src).glob("*.json")):
        for item in json.loads(f.read_text()):
            q = questions.get(item.get("id"))
            if not q:
                problems.append(f"{f.name}: unknown id {item.get('id')}")
                continue
            if item.get("correct") != q["correct"] + 1:
                problems.append(f"{q['id']}: explained answer {item.get('correct')} != official {q['correct'] + 1}")
                continue
            if not (item.get("explanation") or "").strip():
                problems.append(f"{q['id']}: empty explanation")
                continue
            merged[q["id"]] = {
                "e": item["explanation"].strip(),
                "r": [r.strip() for r in item.get("rules") or [] if r and r.strip()],
                "tip": (item.get("tip") or "").strip(),
                "flag": (item.get("flag") or "").strip() or None,
            }
    missing = [i for i in questions if i not in merged]
    ordered = {i: merged[i] for i in questions if i in merged}
    out_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"explained {len(ordered)}/{len(questions)}, flagged {sum(1 for v in ordered.values() if v['flag'])}")
    for p in problems:
        print("  !", p)
    if missing:
        print(f"  missing ({len(missing)}): {' '.join(missing[:40])}{' …' if len(missing) > 40 else ''}")


if __name__ == "__main__":
    main(sys.argv[1])
