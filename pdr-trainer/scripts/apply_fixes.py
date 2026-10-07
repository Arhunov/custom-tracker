"""Apply corrected explanations from verification passes onto data/explanations.json.

Each input file is a JSON array of {"id", "explanation", "tip", "rules", "why"}.
Usage: python3 apply_fixes.py <fixes_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(src):
    path = ROOT / "data/explanations.json"
    exp = json.loads(path.read_text())
    changed = 0
    for f in sorted(Path(src).glob("*.json")):
        for item in json.loads(f.read_text()):
            e = exp.get(item.get("id"))
            if e is None or not (item.get("explanation") or "").strip():
                print(f"  ! {f.name}: skipped {item.get('id')}")
                continue
            e["e"] = item["explanation"].strip()
            if (item.get("tip") or "").strip():
                e["tip"] = item["tip"].strip()
            if item.get("rules") is not None:
                e["r"] = [r.strip() for r in item["rules"] if r and r.strip()]
            changed += 1
    path.write_text(json.dumps(exp, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"applied {changed} fixes")


if __name__ == "__main__":
    main(sys.argv[1])
