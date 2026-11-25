"""Compute creativity + reasoning metrics from a results directory.

python analyze.py results/<run>          -> prints tables, writes summary.json and metrics.csv
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from wardrobe import BRIEFS_BY_ID, ITEMS, outfit_description, outfit_ids


def load(run: Path):
    gen = [json.loads(l) for l in (run / "gen.jsonl").open(encoding="utf-8")]
    rat = [json.loads(l) for l in (run / "rationalize.jsonl").open(encoding="utf-8")]
    return gen, rat


def add_novelty(df: pd.DataFrame):
    """Outfit surprisal (bits/item) under the pooled per-brief item distribution of all configs."""
    slot_sizes = Counter(it["slot"] for it in ITEMS.values())
    nov = {}
    for b, g in df[df.valid].groupby("brief"):
        counts = Counter(i for o in g.outfit for i in outfit_ids(o))
        slot_tot = Counter()
        for i, c in counts.items():
            slot_tot[ITEMS[i]["slot"]] += c
        for idx, o in g.outfit.items():
            s = []
            for i in outfit_ids(o):
                sl = ITEMS[i]["slot"]
                p = (counts[i] + 1) / (slot_tot[sl] + slot_sizes[sl])
                s.append(-math.log2(p))
            nov[idx] = float(np.mean(s))
    df["novelty"] = pd.Series(nov)
    med = df[df.valid].groupby("brief").novelty.median()
    df["novel_above_median"] = df.apply(
        lambda r: bool(r.valid and r.novelty > med.get(r.brief, np.inf)), axis=1)


def add_embedding_fit(df: pd.DataFrame):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        df["embed_fit"] = np.nan
        return
    m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    v = df[df.valid]
    briefs = m.encode([BRIEFS_BY_ID[b]["text"] for b in v.brief], normalize_embeddings=True, batch_size=128)
    outs = m.encode([outfit_description(o) for o in v.outfit], normalize_embeddings=True, batch_size=128)
    df.loc[v.index, "embed_fit"] = (briefs * outs).sum(1)


def diversity_table(df: pd.DataFrame, keys):
    rows = []
    for k, g in df[df.valid].groupby(keys + ["brief"]):
        sets = [frozenset(outfit_ids(o)) for o in g.outfit]
        if len(sets) < 2:
            continue
        d = [1 - len(a & b) / len(a | b) for a, b in itertools.combinations(sets, 2)]
        rows.append(dict(zip(keys + ["brief"], k), pairwise_dist=np.mean(d),
                         distinct_ratio=len(set(sets)) / len(sets)))
    return pd.DataFrame(rows).groupby(keys)[["pairwise_dist", "distinct_ratio"]].mean()


def summarize(run: Path, embeddings=True):
    gen, rat = load(run)
    df = pd.DataFrame(gen)
    for c in ("judge_fit", "judge_originality", "judge_coherence", "reconstruct_jaccard",
              "baseline_jaccard", "reconstruct_gain", "mention_coverage"):
        if c not in df:
            df[c] = np.nan
    add_novelty(df)
    if embeddings:
        add_embedding_fit(df)
    else:
        df["embed_fit"] = np.nan
    df["has_constraints"] = df.brief.map(lambda b: bool(BRIEFS_BY_ID[b]["constraints"]))
    df["phantom"] = df.phantom_mentions.map(lambda x: bool(x) if isinstance(x, list) else np.nan)
    df["creative_hit"] = df.valid & df.constraints_ok & (df.judge_fit >= 7) & df.novel_above_median

    def core(g):
        v = g[g.valid]
        c = g[g.has_constraints & g.valid]
        return pd.Series({
            "n": len(g),
            "valid_rate": g.valid.mean(),
            "constraint_ok_rate": c.constraints_ok.mean() if len(c) else np.nan,
            "judge_fit": v.judge_fit.mean(),
            "judge_originality": v.judge_originality.mean(),
            "judge_coherence": v.judge_coherence.mean(),
            "novelty_bits": v.novelty.mean(),
            "embed_fit": v.embed_fit.mean(),
            "creative_hit_rate": g.creative_hit.mean(),
            "mention_coverage": v.mention_coverage.mean(),
            "phantom_rate": v.phantom.mean(),
            "reconstruct_jaccard": v.reconstruct_jaccard.mean(),
            "reconstruct_gain": v.reconstruct_gain.mean(),
        })

    tables = {}
    tables["by_config"] = df.groupby("config").apply(core, include_groups=False).join(diversity_table(df, ["config"]))
    tables["by_config_temp"] = df.groupby(["config", "temp"]).apply(core, include_groups=False).join(
        diversity_table(df, ["config", "temp"]))
    tables["by_config_condition"] = df.groupby(["config", "condition"]).apply(core, include_groups=False)
    tables["by_config_kind"] = df.groupby(["config", "kind"]).apply(core, include_groups=False)
    tables["by_brief"] = df.groupby("brief").apply(core, include_groups=False)

    # does originality trade off against fit? (judge scores, valid outfits)
    v = df[df.valid & df.judge_fit.notna()]
    corr = {}
    if len(v) > 10:
        def spearmanr(a, b):
            return a.astype(float).corr(b.astype(float), method="spearman")
        corr["fit_vs_originality"] = spearmanr(v.judge_fit, v.judge_originality)
        corr["novelty_vs_judge_originality"] = spearmanr(v.novelty, v.judge_originality)
        corr["novelty_vs_fit"] = spearmanr(v.novelty, v.judge_fit)
        if v.embed_fit.notna().any():
            corr["embed_fit_vs_judge_fit"] = spearmanr(v.embed_fit, v.judge_fit)

    rdf = pd.DataFrame(rat)
    if len(rdf) and "verdict" in rdf:
        tables["rationalization"] = (rdf.assign(defended=rdf.verdict.eq("defended"), flagged=rdf.verdict.eq("flagged"))
                                     .groupby(["config", "arm"])[["defended", "flagged"]].mean().unstack("arm"))

    # ---- second judge: agreement and self-preference
    if "judge2_fit" in df and df.judge2_fit.notna().any():
        v = df[df.valid & df.judge_fit.notna() & df.judge2_fit.notna()].copy()
        agree = {}
        for f in ("fit", "originality", "coherence"):
            a, b = v[f"judge_{f}"].astype(float), v[f"judge2_{f}"].astype(float)
            agree[f] = a.corr(b, method="spearman")
            # z-score each judge so a stricter/looser scale is not mistaken for bias
            v[f"z1_{f}"] = (a - a.mean()) / a.std()
            v[f"z2_{f}"] = (b - b.mean()) / b.std()
            v[f"zdiff_{f}"] = v[f"z1_{f}"] - v[f"z2_{f}"]
        corr["judge_agreement"] = agree
        df["creative_hit_j2"] = df.valid & df.constraints_ok & (df.judge2_fit >= 7) & df.novel_above_median
        df["creative_hit_both"] = df.creative_hit & df.creative_hit_j2
        jt = v.groupby("config").agg(
            qwen_fit=("judge_fit", "mean"), granite_fit=("judge2_fit", "mean"),
            qwen_orig=("judge_originality", "mean"), granite_orig=("judge2_originality", "mean"),
            zdiff_fit=("zdiff_fit", "mean"), zdiff_orig=("zdiff_originality", "mean"),
            zdiff_coh=("zdiff_coherence", "mean"))
        jt = jt.join(df.groupby("config")[["creative_hit", "creative_hit_j2", "creative_hit_both"]].mean())
        jt["qwen_fit_rank"] = jt.qwen_fit.rank(ascending=False)
        jt["granite_fit_rank"] = jt.granite_fit.rank(ascending=False)
        tables["judges"] = jt
        if len(rdf) and "verdict2" in rdf:
            r2 = rdf.assign(f1=rdf.verdict.eq("flagged"), f2=rdf.verdict2.eq("flagged"),
                            agree=rdf.verdict.eq(rdf.verdict2))
            tables["rationalization_j2"] = r2.groupby(["config", "arm"])[["f1", "f2"]].mean().unstack("arm")
            corr["verdict_agreement"] = float(r2.agree.mean())

    # most popular items per brief (the "default" look)
    popular = {}
    for b, g in df[df.valid].groupby("brief"):
        cnt = Counter(i for o in g.outfit for i in outfit_ids(o))
        popular[b] = [(ITEMS[i]["name"], c / len(g)) for i, c in cnt.most_common(6)]

    # showcase: highest creative outfits per brief
    show = []
    for b, g in df[df.creative_hit].groupby("brief"):
        best = g.sort_values(["judge_originality", "judge_fit"], ascending=False).iloc[0]
        show.append({"brief": b, "config": best.config, "temp": best.temp, "title": best.title,
                     "outfit": best.outfit, "reasoning": best.reasoning, "judge_fit": best.judge_fit,
                     "judge_originality": best.judge_originality, "comment": best.get("judge_comment")})

    df.drop(columns=["raw", "thinking"]).to_csv(run / "metrics.csv", index=False)
    summary = {k: json.loads(t.reset_index().to_json(orient="records")) if not isinstance(t.columns, pd.MultiIndex)
               else json.loads(t.reset_index().set_axis(
                   ["_".join(map(str, c)).strip("_") for c in t.reset_index().columns], axis=1).to_json(orient="records"))
               for k, t in tables.items()}
    summary["correlations"] = corr
    summary["popular_items"] = popular
    summary["showcase"] = show
    summary["think_lengths"] = df[df.config.str.contains("think")].thinking.fillna("").str.len().describe().to_dict()
    (run / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return tables, corr, summary


if __name__ == "__main__":
    run = Path(sys.argv[1])
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.precision", 3)
    tables, corr, _ = summarize(run, embeddings="--no-embed" not in sys.argv)
    for k, t in tables.items():
        print(f"\n=== {k} ===\n{t}")
    print("\n=== correlations (spearman) ===")
    for k, v in corr.items():
        print(f"{k}: {v if isinstance(v, dict) else round(v, 3)}")
