"""Merge short hints (rule / why / terms) from subagent batches into data/explanations.json.

Each input file is a JSON array of {"id", "rule", "why", "terms": [{"t", "d"}], "refs"}.
Usage: python3 merge_hints.py <batches_dir>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWER_LEAK = re.compile(r"правильн\w* відповід|відповід\w* \d", re.I)


def main(src):
    path = ROOT / "data/explanations.json"
    exp = json.loads(path.read_text())
    done, problems = 0, []
    for f in sorted(Path(src).glob("*.json")):
        for item in json.loads(f.read_text()):
            e = exp.get(item.get("id"))
            rule = (item.get("rule") or "").strip()
            if e is None or not rule:
                problems.append(f"{f.name}: bad item {item.get('id')}")
                continue
            if ANSWER_LEAK.search(rule + " " + (item.get("why") or "")):
                problems.append(f"{item['id']}: mentions the answer")
            e["rule"] = rule
            e["why"] = (item.get("why") or "").strip() or None
            e["terms"] = [{"t": t["t"].strip(), "d": t["d"].strip()} for t in item.get("terms") or []
                          if t.get("t") and t.get("d")][:3]
            refs = [r.strip() for r in item.get("refs") or [] if r and r.strip()]
            if refs:
                e["r"] = refs
            done += 1
    path.write_text(json.dumps(exp, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [i for i, e in exp.items() if not e.get("rule")]
    print(f"hints merged: {done}, questions without hint: {len(missing)}")
    for p in problems:
        print("  !", p)
    if missing:
        print("  missing:", " ".join(missing[:40]))


if __name__ == "__main__":
    main(sys.argv[1])
