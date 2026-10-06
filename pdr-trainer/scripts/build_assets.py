"""Assemble the offline web app (web/ + data/) into the Android assets folder.

Usage: python3 build_assets.py [dest]   (default: android/app/src/main/assets/www)
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(dest):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT / "web", dest)
    (dest / "data").mkdir()

    src = json.loads((ROOT / "data/questions.json").read_text())
    exp_path = ROOT / "data/explanations.json"
    exp = json.loads(exp_path.read_text()) if exp_path.exists() else {}
    questions = []
    for q in src["questions"]:
        e = exp.get(q["id"], {})
        item = {"id": q["id"], "s": q["section"], "c": q["categories"], "t": q["text"], "a": q["answers"],
                "k": q["correct"], "img": q["image"], "fx": q["fixed_order"],
                "e": e.get("e"), "r": e.get("r") or [], "tip": e.get("tip") or None, "flag": e.get("flag")}
        questions.append({k: v for k, v in item.items() if v is not None and v is not False and v != []})
    payload = {"source": src["source"], "scraped": src["scraped"], "sections": src["sections"], "questions": questions}
    (dest / "data/questions.js").write_text(
        "window.PDR_DATA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    rules = json.loads((ROOT / "data/pdr_rules.json").read_text())
    (dest / "data/rules.js").write_text(
        "window.PDR_RULES=" + json.dumps(rules, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    (dest / "img").mkdir()
    for name in sorted({q["image"] for q in src["questions"] if q["image"]}):
        shutil.copy2(ROOT / "data/img" / f"{name}.webp", dest / "img" / f"{name}.webp")
    print(f"{len(questions)} questions ({sum(1 for q in questions if 'e' in q)} explained) -> {dest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "android/app/src/main/assets/www")
