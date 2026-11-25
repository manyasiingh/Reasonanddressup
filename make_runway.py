"""Build the animated paper-doll runway page from a finished run.

python make_runway.py results/full   ->  report/runway.html

Picks real looks (two top-scored per brief plus the best from the smaller models)
and planted-item swap tests where both judges agree, then fills web/runway_template.html.
"""

import json
import re
import sys
from pathlib import Path

import prompts as P
from wardrobe import BRIEFS, ITEMS, outfit_ids

RUN = Path(sys.argv[1] if len(sys.argv) > 1 else "results/full")
CONFIGS = ["qwen3-8b-think", "qwen3-8b", "qwen2.5-7b", "phi4-mini", "olmo2-7b"]
SMALL = ("qwen2.5-7b", "phi4-mini", "olmo2-7b")

gen = [json.loads(l) for l in (RUN / "gen.jsonl").open(encoding="utf-8")]
rat = [json.loads(l) for l in (RUN / "rationalize.jsonl").open(encoding="utf-8")]
summary = json.loads((RUN / "summary.json").read_text(encoding="utf-8"))


def clean(t, n=360):
    t = " ".join(str(t).replace("**", "").split())
    t = re.sub(r"[^\x20-\x7E‘-”–—…°]", "", t)
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def ok_title(t):
    return bool(t) and re.fullmatch(r"[A-Za-z0-9 ,'&:\-!.]{3,48}", t.strip()) is not None


def score(r):
    return r["judge_originality"] + r["judge2_originality"] + 0.5 * (r["judge_fit"] + r["judge2_fit"])


def look(r):
    return {"brief": r["brief"], "config": r["config"], "temp": r["temp"], "title": r["title"].strip(),
            "outfit": sorted(outfit_ids(r["outfit"])), "reasoning": clean(r["reasoning"]),
            "fit": [r["judge_fit"], r["judge2_fit"]], "orig": [r["judge_originality"], r["judge2_originality"]]}


def good(r):
    return (r["valid"] and r["constraints_ok"] and ok_title(r["title"]) and r.get("judge_fit")
            and r.get("judge2_fit") and len(r["reasoning"]) > 120 and r["mention_coverage"] >= 0.6)


looks = []
for b in BRIEFS:
    cands = sorted((r for r in gen if r["brief"] == b["id"] and good(r)), key=score, reverse=True)
    used = set()
    for r in cands:  # two best looks from different setups
        if r["config"] not in used:
            used.add(r["config"])
            looks.append(look(r))
            if len(used) == 2:
                break
    small = [r for r in cands if r["config"] in SMALL and r["config"] not in used]
    if small:  # plus the best look from a smaller model
        looks.append(look(small[0]))

# swap tests where both judges gave the same verdict, with a quote about the planted piece
swaps, seen = [], set()
want = [("qwen2.5-7b", "defended"), ("qwen3-8b", "defended"), ("phi4-mini", "defended"),
        ("qwen3-8b-think", "flagged"), ("phi4-mini", "flagged"), ("qwen3-8b-think", "flagged")]
for cfg, verdict in want:
    for r in rat:
        if not (r["config"] == cfg and r["arm"] == "planted" and r.get("verdict") == verdict
                and r.get("verdict2") == verdict and (cfg, r["brief"]) not in seen):
            continue
        _, ans = P.split_thinking(r["raw"])
        obj = P.parse_json_obj(ans)
        text = str(obj.get("reasoning", ans) if isinstance(obj, dict) else ans).replace("**", "")
        short = " ".join(ITEMS[r["target"]]["name"].lower().split()[-2:])
        sents = [s for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
                 if (short in s.lower() or r["target"] in s) and 40 < len(s) < 320 and '":' not in s]
        if not sents or "/5" in sents[0]:
            continue
        ctrl = next(x for x in rat if x["config"] == cfg and x["brief"] == r["brief"]
                    and x["src_sample"] == r["src_sample"] and x["arm"] == "control")
        seen.add((cfg, r["brief"]))
        swaps.append({"config": cfg, "brief": r["brief"], "verdict": verdict, "slot": r["slot"],
                      "original": ctrl["target"], "planted": r["target"],
                      "outfit": sorted(outfit_ids(r["outfit"])), "quote": clean(" ".join(sents[:2]), 300)})
        break

by_cfg = {r["config"]: r for r in summary["by_config"]}
flag = {}
for r in rat:
    k = (r["config"], r["arm"])
    flag.setdefault(k, [0, 0])
    flag[k][1] += 1
    flag[k][0] += r.get("verdict") == "flagged"
stats = {c: {"valid": by_cfg[c]["valid_rate"], "hit": by_cfg[c]["creative_hit_rate"],
             "novelty": by_cfg[c]["novelty_bits"], "phantom": by_cfg[c]["phantom_rate"],
             "flagP": flag[(c, "planted")], "flagC": flag[(c, "control")]} for c in CONFIGS}

data = {"items": {i: {"slot": it["slot"], "name": it["name"], "colors": it["colors"]} for i, it in ITEMS.items()},
        "briefs": {b["id"]: {"text": b["text"], "kind": b["kind"]} for b in BRIEFS},
        "looks": looks, "swaps": swaps, "stats": stats}

template = Path("web/runway_template.html").read_text(encoding="utf-8")
out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/index.html")
out.parent.mkdir(exist_ok=True)
payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # safe inside a <script> block
out.write_text(template.replace("__DATA__", payload, 1), encoding="utf-8")
print(f"wrote {out}: {len(looks)} looks, {len(swaps)} swap tests")
