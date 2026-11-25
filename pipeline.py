"""Experiment orchestration. Backend-agnostic: pass a generate_fn(model_id, requests) -> list[str].

Stages
  1. gen        : every config x brief x temperature x condition x sample -> stylist output
  2. rationalize: show each model its own outfit with one item swapped for an off-brief item
                  (or unchanged, as control) and ask it to explain -> does it defend the plant?
  3. judge      : fixed judge model scores fit/originality/coherence; a fixed reader model tries
                  to reconstruct the outfit from item-redacted reasoning; brief-only baseline;
                  rationalization verdicts.
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import prompts as P
from wardrobe import BRIEFS, ITEMS, check_constraints, check_structure, normalize_outfit, outfit_ids

CONFIGS = {
    "qwen3-8b-think": {"model": "Qwen/Qwen3-8B", "thinking": True},
    "qwen3-8b": {"model": "Qwen/Qwen3-8B", "thinking": False},
    "qwen2.5-7b": {"model": "Qwen/Qwen2.5-7B-Instruct", "thinking": False},
    "phi4-mini": {"model": "microsoft/Phi-4-mini-instruct", "thinking": False},
    "olmo2-7b": {"model": "allenai/OLMo-2-1124-7B-Instruct", "thinking": False},
}
JUDGE_MODEL = "Qwen/Qwen3-8B"  # used with thinking off, temperature 0
TEMPS = [0.3, 0.7, 1.0, 1.3]
CONDITIONS = ["reason_first", "answer_first"]


def _seed(*parts) -> int:
    import hashlib
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def run_by_model(generate_fn, requests: list[dict]) -> list[str]:
    """Group requests by model, run each model's batch in parallel, return texts in order."""
    by_model: dict[str, list[int]] = {}
    for i, r in enumerate(requests):
        by_model.setdefault(r["model"], []).append(i)
    out: list[str | None] = [None] * len(requests)

    def work(model):
        idx = by_model[model]
        texts = generate_fn(model, [requests[i] for i in idx])
        for i, t in zip(idx, texts):
            out[i] = t

    with ThreadPoolExecutor(max_workers=len(by_model)) as ex:
        list(ex.map(work, by_model))
    return out  # type: ignore


def _req(model, messages, temperature, seed, thinking, max_tokens=None):
    return {"model": model, "messages": messages, "temperature": temperature, "seed": seed,
            "thinking": thinking, "max_tokens": max_tokens or (4096 if thinking else 1024)}


# ---------------------------------------------------------------- stage 1
def build_gen_requests(configs, briefs, temps, samples):
    meta, reqs = [], []
    for cname in configs:
        cfg = CONFIGS[cname]
        for b in briefs:
            for t in temps:
                for cond in CONDITIONS:
                    for k in range(samples):
                        m = {"config": cname, "brief": b["id"], "kind": b["kind"], "temp": t,
                             "condition": cond, "sample": k}
                        meta.append(m)
                        reqs.append(_req(cfg["model"], P.stylist_messages(b["id"], cond), t,
                                         _seed(cname, b["id"], t, cond, k), cfg["thinking"]))
    return meta, reqs


def analyze_record(m: dict, text: str) -> dict:
    r = dict(m)
    r["raw"] = text
    p = P.parse_stylist(text)
    r.update({k: p.get(k) for k in ("thinking", "parsed", "reasoning", "title", "key_order")})
    outfit = normalize_outfit(p["outfit_raw"]) if p["parsed"] else None
    r["format_repaired"] = False
    if outfit is not None:
        from wardrobe import repair_outfit
        outfit, r["format_repaired"] = repair_outfit(outfit)
    r["outfit"] = outfit
    r["struct_errors"] = check_structure(outfit) if outfit is not None else ["unparsed"]
    r["valid"] = not r["struct_errors"]
    from wardrobe import BRIEFS_BY_ID
    r["constraint_errors"] = check_constraints(outfit, BRIEFS_BY_ID[m["brief"]]) if r["valid"] else None
    r["constraints_ok"] = r["valid"] and not r["constraint_errors"]
    if r["valid"]:
        chosen = set(outfit_ids(outfit))
        mentioned = P.items_mentioned(r["reasoning"] or "")
        r["n_items"] = len(chosen)
        r["mention_coverage"] = len(chosen & mentioned) / len(chosen)
        r["phantom_mentions"] = sorted(mentioned - chosen)
    return r


# ---------------------------------------------------------------- stage 2
def _plant(outfit: dict, rng: random.Random):
    """Swap one clothing item for a same-slot item sharing no tags with the rest of the outfit."""
    slots = [s for s in outfit if s != "accessory"]
    rng.shuffle(slots)
    for slot in slots:
        orig = outfit[slot]
        rest_tags = {t for i in outfit_ids(outfit) if i != orig for t in ITEMS[i]["tags"]}
        cands = [i for i, it in ITEMS.items()
                 if it["slot"] == slot and i != orig and not (set(it["tags"]) & rest_tags)]
        if cands:
            new = rng.choice(sorted(cands))
            planted = dict(outfit)
            planted[slot] = new
            return planted, slot, new
    return None


def build_rationalize_requests(records, per_brief=2):
    meta, reqs = [], []
    for cname in sorted({r["config"] for r in records}):
        cfg = CONFIGS[cname]
        for b in sorted({r["brief"] for r in records}):
            pool = [r for r in records if r["config"] == cname and r["brief"] == b and r["valid"]
                    and r["condition"] == "reason_first" and r["temp"] in (0.7, 0.3)]
            pool.sort(key=lambda r: (r["temp"] != 0.7, r["sample"]))
            for src in pool[:per_brief]:
                rng = random.Random(_seed("plant", cname, b, src["sample"]))
                res = _plant(src["outfit"], rng)
                if res is None:
                    continue
                planted, slot, new = res
                for arm, outfit, target in (("planted", planted, new), ("control", src["outfit"], src["outfit"][slot])):
                    meta.append({"config": cname, "brief": b, "arm": arm, "slot": slot,
                                 "target": target, "outfit": outfit, "src_sample": src["sample"]})
                    reqs.append(_req(cfg["model"], P.rationalize_messages(b, outfit, "reason_first"), 0.7,
                                     _seed("rat", cname, b, src["sample"], arm), cfg["thinking"]))
    return meta, reqs


# ---------------------------------------------------------------- stage 3
def build_judge_requests(records, rat_records, baseline_samples=8):
    jobs = []  # (kind, key, request)
    for i, r in enumerate(records):
        if not r["valid"]:
            continue
        jobs.append(("score", i, _req(JUDGE_MODEL, P.judge_messages(r["brief"], r["outfit"], r["title"]), 0.0, 0, False, 200)))
        if r["reasoning"]:
            red = P.redact_items(r["reasoning"])
            jobs.append(("reconstruct", i, _req(JUDGE_MODEL, P.reader_messages(r["brief"], red), 0.0, 0, False, 300)))
    for b in BRIEFS:
        for k in range(baseline_samples):
            jobs.append(("baseline", (b["id"], k), _req(JUDGE_MODEL, P.reader_messages(b["id"], None), 0.7,
                                                        _seed("base", b["id"], k), False, 300)))
    for i, rr in enumerate(rat_records):
        _, expl = P.split_thinking(rr["raw"])
        jobs.append(("rat_verdict", i, _req(JUDGE_MODEL, P.rationalize_judge_messages(
            rr["brief"], rr["outfit"], rr["target"], expl), 0.0, 0, False, 60)))
    return jobs


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def apply_judgements(records, rat_records, jobs, texts):
    baseline = {}
    for (kind, key, _), text in zip(jobs, texts):
        _, ans = P.split_thinking(text)
        obj = P.parse_json_obj(ans) or {}
        if kind == "score":
            for f in ("fit", "originality", "coherence"):
                try:
                    records[key][f"judge_{f}"] = max(1, min(10, int(obj.get(f))))
                except (TypeError, ValueError):
                    records[key][f"judge_{f}"] = None
            records[key]["judge_comment"] = obj.get("comment")
        elif kind == "reconstruct":
            o = normalize_outfit(obj.get("outfit")) or {}
            records[key]["reconstructed"] = sorted(outfit_ids(o))
            records[key]["reconstruct_jaccard"] = jaccard(outfit_ids(o), outfit_ids(records[key]["outfit"]))
        elif kind == "baseline":
            o = normalize_outfit(obj.get("outfit")) or {}
            baseline.setdefault(key[0], []).append(outfit_ids(o))
        elif kind == "rat_verdict":
            v = str(obj.get("verdict", "")).strip().lower()
            rat_records[key]["verdict"] = v if v in ("defended", "flagged", "not_mentioned") else "unparsed"
    # brief-only baseline overlap: what you'd get guessing the outfit without the reasoning
    for r in records:
        if r.get("reconstruct_jaccard") is not None:
            preds = baseline.get(r["brief"], [])
            base = sum(jaccard(p, outfit_ids(r["outfit"])) for p in preds) / max(1, len(preds))
            r["baseline_jaccard"] = base
            r["reconstruct_gain"] = r["reconstruct_jaccard"] - base
    return baseline


# ---------------------------------------------------------------- second judge
# A judge from a family none of the contestants belong to, to measure Qwen3-judge self-preference.
JUDGE2_MODEL = "ibm-granite/granite-3.3-8b-instruct"


def rejudge(generate_fn, run_dir: Path, model: str = JUDGE2_MODEL, log=print):
    records = _read_jsonl(run_dir / "gen.jsonl")
    rat_records = _read_jsonl(run_dir / "rationalize.jsonl")
    jobs = []
    for i, r in enumerate(records):
        if r["valid"]:
            jobs.append(("score", i, _req(model, P.judge_messages(r["brief"], r["outfit"], r["title"]), 0.0, 0, False, 200)))
    for i, rr in enumerate(rat_records):
        _, expl = P.split_thinking(rr["raw"])
        jobs.append(("rat_verdict", i, _req(model, P.rationalize_judge_messages(
            rr["brief"], rr["outfit"], rr["target"], expl), 0.0, 0, False, 60)))
    log(f"[judge2] {len(jobs)} calls on {model}")
    texts = generate_fn(model, [j[2] for j in jobs])
    for (kind, key, _), text in zip(jobs, texts):
        obj = P.parse_json_obj(P.split_thinking(text)[1]) or {}
        if kind == "score":
            for f in ("fit", "originality", "coherence"):
                try:
                    records[key][f"judge2_{f}"] = max(1, min(10, int(obj.get(f))))
                except (TypeError, ValueError):
                    records[key][f"judge2_{f}"] = None
        else:
            v = str(obj.get("verdict", "")).strip().lower()
            rat_records[key]["verdict2"] = v if v in ("defended", "flagged", "not_mentioned") else "unparsed"
    _write_jsonl(run_dir / "gen.jsonl", records)
    _write_jsonl(run_dir / "rationalize.jsonl", rat_records)
    ok = sum(r.get("judge2_fit") is not None for r in records if r["valid"])
    log(f"[judge2] parsed scores for {ok}/{sum(r['valid'] for r in records)} outfits")


# ---------------------------------------------------------------- driver
def run(generate_fn, out_dir: Path, configs=None, briefs=None, temps=None, samples=8, log=print):
    configs = configs or list(CONFIGS)
    briefs = briefs or BRIEFS
    temps = temps or TEMPS
    out_dir.mkdir(parents=True, exist_ok=True)

    meta, reqs = build_gen_requests(configs, briefs, temps, samples)
    log(f"[gen] {len(reqs)} stylist generations across {len(configs)} configs")
    texts = run_by_model(generate_fn, reqs)
    records = [analyze_record(m, t) for m, t in zip(meta, texts)]
    _write_jsonl(out_dir / "gen.jsonl", records)
    log(f"[gen] valid outfits: {sum(r['valid'] for r in records)}/{len(records)}")

    rmeta, rreqs = build_rationalize_requests(records)
    log(f"[rationalize] {len(rreqs)} explanation requests")
    rtexts = run_by_model(generate_fn, rreqs)
    rat_records = [dict(m, raw=t) for m, t in zip(rmeta, rtexts)]

    jobs = build_judge_requests(records, rat_records)
    log(f"[judge] {len(jobs)} judge/reader calls on {JUDGE_MODEL}")
    jtexts = generate_fn(JUDGE_MODEL, [j[2] for j in jobs])
    baseline = apply_judgements(records, rat_records, jobs, jtexts)

    _write_jsonl(out_dir / "gen.jsonl", records)
    _write_jsonl(out_dir / "rationalize.jsonl", rat_records)
    (out_dir / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    log(f"[done] wrote {out_dir}")
    return records, rat_records
