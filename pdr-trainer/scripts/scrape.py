"""Scrape official Ukrainian driving-theory questions (categories B and C) from pdrtest.com.

Each /test/section/<n> page embeds the full question list of that section
(with correct answers) in the Next.js RSC payload, so one request per section
is enough. Images are downloaded from the public bucket.

Usage: python3 scrape.py <out_dir>
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://pdrtest.com"
IMG = "https://bucket.pdrtest.com/pics/{}.webp"
WANTED = {"B", "C"}
UA = {"User-Agent": "pdr-trainer-personal-study/1.0"}


def get(url, binary=False):
    for attempt in range(7):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binary else data.decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == 6:
                raise
            print(f"retry {url}: {e}", file=sys.stderr)
            time.sleep(min(2 ** (attempt + 1), 30))
        except Exception as e:  # noqa: BLE001
            if attempt == 6:
                raise
            print(f"retry {url}: {e}", file=sys.stderr)
            time.sleep(min(2 ** (attempt + 1), 30))


def rsc_payload(html):
    out = []
    for chunk in re.findall(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, flags=re.S):
        arr = json.loads(chunk)
        if len(arr) > 1 and isinstance(arr[1], str):
            out.append(arr[1])
    return "".join(out)


def extract(payload, marker):
    i = payload.find(marker)
    if i < 0:
        raise ValueError(f"marker not found: {marker}")
    obj, _ = json.JSONDecoder().raw_decode(payload[i:])
    return obj


def strip_html(s):
    s = re.sub(r"</p>|<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


def main(out_dir):
    out = Path(out_dir)
    (out / "img").mkdir(parents=True, exist_ok=True)
    index = rsc_payload(get(f"{BASE}/test"))
    meta = extract(index, '{"profile":null,"sectionMeta"')["sectionMeta"]
    sections = extract(index, '{"snapshot":{"sections"')["snapshot"]["sections"]

    result_sections, questions = [], []
    for s in sections:
        cats = meta[s["id"]]["categories"]
        mine = sorted(WANTED & set(cats))
        if not mine:
            continue
        payload = rsc_payload(get(f"{BASE}/test/section/{s['id']}"))
        qs = extract(payload, '{"profile":null,"questions"')["questions"]
        print(f"section {s['sectionId']:>5} {len(qs):>4}/{s['sum']:<4} {s['title'][:60]}")
        result_sections.append({"id": s["sectionId"], "title": s["title"].replace("​", "").strip(),
                                "categories": mine, "count": len(qs)})
        for q in qs:
            answers = [a["answer"].strip() for a in q["answers"]]
            correct = [i for i, a in enumerate(q["answers"]) if a.get("truth")]
            if len(correct) != 1:
                print(f"  ! {q['id']} has {len(correct)} correct answers", file=sys.stderr)
            ref = q.get("reference")
            questions.append({
                "id": q["id"],
                "section": s["sectionId"],
                "categories": mine,
                "text": q["question"].strip(),
                "answers": answers,
                "correct": correct[0] if correct else -1,
                "image": q.get("image") or None,
                "fixed_order": bool(q.get("notrandom")),
                "ref": strip_html(ref) if isinstance(ref, str) and not ref.startswith("$") else None,
            })
        time.sleep(1)

    imgs = sorted({q["image"] for q in questions if q["image"]})
    print(f"{len(questions)} questions, {len(imgs)} images")

    def fetch(name):
        dst = out / "img" / f"{name}.webp"
        if dst.exists():
            return name, True
        try:
            dst.write_bytes(get(IMG.format(name), binary=True))
            return name, True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return name, False
            raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        missing = {name for name, ok in pool.map(fetch, imgs) if not ok}
    print(f"missing images: {len(missing)}")
    for q in questions:
        if q["image"] in missing:
            q["image"] = None

    (out / "questions.json").write_text(json.dumps(
        {"source": BASE, "scraped": time.strftime("%Y-%m-%d"), "sections": result_sections,
         "questions": questions}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
