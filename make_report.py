"""Build the HTML results report from results/<run>/ (after analyze.py).

python make_report.py results/full  ->  report/wardrobe-muse.html
"""

import html
import json
import sys
from collections import Counter
from pathlib import Path

import prompts as P
from wardrobe import BRIEFS_BY_ID, ITEMS, outfit_ids

RUN = Path(sys.argv[1] if len(sys.argv) > 1 else "results/full")
S = json.loads((RUN / "summary.json").read_text(encoding="utf-8"))
GEN = [json.loads(l) for l in (RUN / "gen.jsonl").open(encoding="utf-8")]
RAT = [json.loads(l) for l in (RUN / "rationalize.jsonl").open(encoding="utf-8")]

CONFIGS = ["qwen3-8b-think", "qwen3-8b", "qwen2.5-7b", "phi4-mini", "olmo2-7b"]
LABEL = {"qwen3-8b-think": "Qwen3-8B · thinking", "qwen3-8b": "Qwen3-8B", "qwen2.5-7b": "Qwen2.5-7B",
         "phi4-mini": "Phi-4-mini", "olmo2-7b": "OLMo-2-7B"}
SER = {c: f"var(--s{i+1})" for i, c in enumerate(CONFIGS)}
TEMPS = [0.3, 0.7, 1.0, 1.3]
e = html.escape

by_cfg = {r["config"]: r for r in S["by_config"]}
by_ct = {(r["config"], r["temp"]): r for r in S["by_config_temp"]}
by_cc = {(r["config"], r["condition"]): r for r in S["by_config_condition"]}


def pct(x, d=0):
    return "–" if x is None else f"{100*x:.{d}f}%"


# ------------------------------------------------------------------ charts (inline SVG, one scale each)
def line_chart(metric, ymin, ymax, yticks, fmt, title, ylab):
    W, H, L, R, T, B = 560, 280, 48, 18, 14, 40
    sx = lambda t: L + (t - 0.3) / 1.0 * (W - L - R)
    sy = lambda v: T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(title)}">']
    for v in yticks:
        o.append(f'<line x1="{L}" x2="{W-R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" class="grid"/>'
                 f'<text x="{L-8}" y="{sy(v)+4:.1f}" class="tick" text-anchor="end">{fmt(v)}</text>')
    o.append(f'<line x1="{L}" x2="{W-R}" y1="{H-B}" y2="{H-B}" class="axis"/>')
    for t in TEMPS:
        o.append(f'<text x="{sx(t):.1f}" y="{H-B+18}" class="tick" text-anchor="middle">{t}</text>')
    o.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-4}" class="tick" text-anchor="middle">sampling temperature</text>')
    for c in CONFIGS:
        pts = [(sx(t), sy(by_ct[(c, t)][metric])) for t in TEMPS]
        o.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" '
                 f'stroke="{SER[c]}" stroke-width="2" stroke-linejoin="round"/>')
        for t, (x, y) in zip(TEMPS, pts):
            tip = f"{LABEL[c]} · T={t} · {ylab}: {fmt(by_ct[(c, t)][metric])}"
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{SER[c]}" class="dot" data-tip="{e(tip)}" tabindex="0"/>')
    o.append("</svg>")
    return "".join(o)


def dumbbell():
    W, rowh, L, R, T = 560, 44, 150, 24, 18
    H = T + rowh * len(CONFIGS) + 34
    xmax = 0.4
    sx = lambda v: L + v / xmax * (W - L - R)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Creative hit rate, reason-first vs answer-first">']
    for v in (0, 0.1, 0.2, 0.3, 0.4):
        o.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{T-6}" y2="{H-30}" class="grid"/>'
                 f'<text x="{sx(v):.1f}" y="{H-12}" class="tick" text-anchor="middle">{int(v*100)}%</text>')
    for i, c in enumerate(CONFIGS):
        y = T + rowh * i + rowh / 2
        a, r = by_cc[(c, "answer_first")]["creative_hit_rate"], by_cc[(c, "reason_first")]["creative_hit_rate"]
        o.append(f'<text x="{L-14}" y="{y+4:.1f}" class="lab" text-anchor="end">{e(LABEL[c])}</text>')
        o.append(f'<line x1="{sx(a):.1f}" x2="{sx(r):.1f}" y1="{y:.1f}" y2="{y:.1f}" class="link"/>')
        o.append(f'<circle cx="{sx(a):.1f}" cy="{y:.1f}" r="6" fill="var(--surface)" stroke="{SER[c]}" stroke-width="2.5" class="dot" tabindex="0" '
                 f'data-tip="{e(LABEL[c])} · choose then explain: {pct(a,1)}"/>')
        o.append(f'<circle cx="{sx(r):.1f}" cy="{y:.1f}" r="6.5" fill="{SER[c]}" class="dot" tabindex="0" '
                 f'data-tip="{e(LABEL[c])} · reason first: {pct(r,1)}"/>')
    o.append("</svg>")
    return "".join(o)


def rat_counts():
    cnt = Counter((r["config"], r["arm"], r.get("verdict")) for r in RAT)
    tot = Counter((r["config"], r["arm"]) for r in RAT)
    return cnt, tot


def rat_bars():
    cnt, tot = rat_counts()
    W, rowh, L, R, T = 560, 50, 150, 70, 10
    H = T + rowh * len(CONFIGS) + 30
    xmax = 0.35
    sx = lambda v: L + v / xmax * (W - L - R)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="How often each model flagged the planted item">']
    for v in (0, 0.1, 0.2, 0.3):
        o.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{T}" y2="{H-26}" class="grid"/>'
                 f'<text x="{sx(v):.1f}" y="{H-8}" class="tick" text-anchor="middle">{int(v*100)}%</text>')
    for i, c in enumerate(CONFIGS):
        y0 = T + rowh * i + 8
        o.append(f'<text x="{L-14}" y="{y0+15:.1f}" class="lab" text-anchor="end">{e(LABEL[c])}</text>')
        for j, (arm, fill) in enumerate((("planted", SER[c]), ("control", "var(--muted-fill)"))):
            k, n = cnt[(c, arm, "flagged")], tot[(c, arm)]
            v = k / n if n else 0
            yy = y0 + j * 15
            w = max(sx(v) - L, 0.0)
            o.append(f'<rect x="{L}" y="{yy:.1f}" width="{w:.1f}" height="12" rx="2" fill="{fill}" class="dot" tabindex="0" '
                     f'data-tip="{e(LABEL[c])} · {arm} outfit: flagged {k} of {n}"/>')
            o.append(f'<text x="{L + w + 6:.1f}" y="{yy+10:.1f}" class="val">{k}/{n}</text>')
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------ outfit card
SWATCH = {"white": "#f4f4f2", "black": "#1d1d1f", "navy": "#1f2f5c", "grey": "#8a8d93", "beige": "#d8c4a0",
          "pink": "#ef9fbf", "multicolor": "conic-gradient(#e34948,#eda100,#1baf7a,#2a78d6,#6250d6,#e34948)",
          "silver": "linear-gradient(135deg,#e6e8ec,#9aa0a8)", "green": "#3f8f4e", "red": "#c8312f",
          "yellow": "#f2c230", "orange": "#ec7a2c", "purple": "#7b4bb3", "brown": "#7a5233",
          "blue": "#3a78c9", "gold": "linear-gradient(135deg,#f3d27a,#b8892a)"}
SLOT_ORDER = ["headwear", "top", "onepiece", "outerwear", "bottom", "footwear", "accessory"]


def chips(outfit):
    rows = []
    ids = sorted(outfit_ids(outfit), key=lambda i: SLOT_ORDER.index(ITEMS[i]["slot"]))
    for i in ids:
        it = ITEMS[i]
        sw = "".join(f'<i style="background:{SWATCH[c]}"></i>' for c in it["colors"])
        rows.append(f'<li><span class="sw">{sw}</span><span class="id">{i}</span>{e(it["name"])}</li>')
    return "<ul class=\"chips\">" + "".join(rows) + "</ul>"


def clip(t, n=340):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def showcase():
    order = ["lighthouse_dj", "sunday_evening", "robot_funeral", "grandmother_job", "beach_tie", "mushroom_party"]
    sc = {s["brief"]: s for s in S["showcase"]}
    cards = []
    for b in order:
        s = sc.get(b)
        if not s:
            continue
        cards.append(f'''<article class="look">
  <p class="brief">{e(BRIEFS_BY_ID[b]["text"])}</p>
  <h3>{e(s["title"] or "Untitled look")}</h3>
  {chips(s["outfit"])}
  <blockquote>{e(clip(s["reasoning"]))}</blockquote>
  <p class="meta"><span class="dotkey" style="background:{SER[s["config"]]}"></span>{e(LABEL[s["config"]])} · T={s["temp"]} · fit {int(s["judge_fit"])}/10 · originality {int(s["judge_originality"])}/10</p>
</article>''')
    return "\n".join(cards)


def rat_examples():
    out = []
    picks = [("qwen2.5-7b", "defended"), ("qwen3-8b-think", "flagged")]
    for cfg, verdict in picks:
        r = next((r for r in RAT if r["config"] == cfg and r["arm"] == "planted" and r.get("verdict") == verdict), None)
        if not r:
            continue
        _, ans = P.split_thinking(r["raw"])
        obj = P.parse_json_obj(ans)
        text = obj.get("reasoning", ans) if isinstance(obj, dict) else ans
        name = ITEMS[r["target"]]["name"]
        sentences = [s for s in str(text).replace("\n", " ").split(". ") if name.split()[-1].lower() in s.lower()]
        quote = clip(". ".join(sentences[:2]) or text, 300)
        tag = "Defended the plant" if verdict == "defended" else "Caught the plant"
        out.append(f'''<figure class="rat {verdict}">
  <figcaption><span class="pill">{tag}</span> {e(LABEL[cfg])} · brief: {e(BRIEFS_BY_ID[r["brief"]]["text"])}</figcaption>
  <p class="planted">Secretly swapped in: <strong>{e(name)}</strong> ({r["target"]})</p>
  <blockquote>{e(quote)}</blockquote>
</figure>''')
    return "\n".join(out)


# ------------------------------------------------------------------ scoreboard
def invalid_breakdown():
    c = Counter()
    for r in GEN:
        if not r["valid"]:
            c[(r["config"], "unparsed" if r["struct_errors"] == ["unparsed"] else "rules")] += 1
    return c


def scoreboard():
    inv = invalid_breakdown()
    cnt, tot = rat_counts()
    head = ("<tr><th>Model</th><th>Valid outfit</th><th>Meets brief constraints</th><th>Judge fit</th>"
            "<th>Judge originality</th><th>Novelty (bits/item)</th><th>Diversity</th><th>Creative hit rate</th>"
            "<th>Phantom items in reasoning</th><th>Reconstruction gain</th><th>Flags planted item</th></tr>")
    rows = []
    for c in CONFIGS:
        r = by_cfg[c]
        rows.append(
            f'<tr><th scope="row"><span class="dotkey" style="background:{SER[c]}"></span>{e(LABEL[c])}</th>'
            f'<td>{pct(r["valid_rate"])}<small>{inv[(c,"rules")]} rule breaks · {inv[(c,"unparsed")]} unparsable</small></td>'
            f'<td>{pct(r["constraint_ok_rate"])}</td><td>{r["judge_fit"]:.2f}</td><td>{r["judge_originality"]:.2f}</td>'
            f'<td>{r["novelty_bits"]:.2f}</td><td>{r["pairwise_dist"]:.2f}</td><td><b>{pct(r["creative_hit_rate"],1)}</b></td>'
            f'<td>{pct(r["phantom_rate"])}</td><td>+{r["reconstruct_gain"]:.2f}</td>'
            f'<td>{cnt[(c,"planted","flagged")]}/{tot[(c,"planted")]}</td></tr>')
    return f"<table>{head}{''.join(rows)}</table>"


def brief_table():
    rows = []
    for r in sorted(S["by_brief"], key=lambda r: r["judge_fit"]):
        b = BRIEFS_BY_ID[r["brief"]]
        con = pct(r["constraint_ok_rate"]) if r["constraint_ok_rate"] is not None else "—"
        rows.append(f'<tr><th scope="row">{e(b["text"])}<small>{b["kind"]}</small></th><td>{pct(r["valid_rate"])}</td>'
                    f'<td>{con}</td><td>{r["judge_fit"]:.1f}</td><td>{r["judge_originality"]:.1f}</td><td>{pct(r["creative_hit_rate"],1)}</td></tr>')
    return ("<table><tr><th>Brief</th><th>Valid</th><th>Constraints met</th><th>Fit</th><th>Originality</th>"
            "<th>Creative hits</th></tr>" + "".join(rows) + "</table>")


def judges_table():
    jt = {r["config"]: r for r in S["judges"]}
    head = ("<tr><th>Model</th><th>Fit · Qwen3 judge</th><th>Fit · Granite judge</th><th>Rank (both)</th>"
            "<th>Qwen3 vs Granite, z-scored fit</th><th>Creative hits · Qwen3</th><th>Creative hits · Granite</th>"
            "<th>Creative hits · both agree</th></tr>")
    rows = []
    for c in CONFIGS:
        r = jt[c]
        same = int(r["qwen_fit_rank"]) == int(r["granite_fit_rank"])
        rank = f'{int(r["qwen_fit_rank"])}' if same else f'{int(r["qwen_fit_rank"])} / {int(r["granite_fit_rank"])}'
        z = r["zdiff_fit"]
        rows.append(f'<tr><th scope="row"><span class="dotkey" style="background:{SER[c]}"></span>{e(LABEL[c])}</th>'
                    f'<td>{r["qwen_fit"]:.2f}</td><td>{r["granite_fit"]:.2f}</td><td>{rank}</td>'
                    f'<td>{z:+.2f}</td><td>{pct(r["creative_hit"],1)}</td><td>{pct(r["creative_hit_j2"],1)}</td>'
                    f'<td><b>{pct(r["creative_hit_both"],1)}</b></td></tr>')
    return f"<table>{head}{''.join(rows)}</table>"


def rat_j2():
    c2 = Counter((r["config"], r["arm"]) for r in RAT if r.get("verdict2") == "flagged")
    return c2


legend = "".join(f'<span><i style="background:{SER[c]}"></i>{e(LABEL[c])}</span>' for c in CONFIGS)
corr = S["correlations"]
cnt, tot = rat_counts()
c2 = rat_j2()
ag = corr["judge_agreement"]
n_valid = sum(r["valid"] for r in GEN)

page = f'''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wardrobe Muse</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one reading column of findings, widening for the scoreboard and a lookbook grid of outfits. */
:root {{
  --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --line:rgba(11,11,11,.10); --accent:#6250d6; --accent-soft:#ece9fb;
  --muted-fill:#c3c2b7; --good:#006300; --bad:#b42f2f;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
  --f-display:"Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --f-body:"IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --f-mono:"IBM Plex Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --line:rgba(255,255,255,.10); --accent:#9085e9; --accent-soft:#25213f;
  --muted-fill:#55544f; --good:#0ca30c; --bad:#e66767;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; color-scheme:dark; }} }}
:root[data-theme="dark"] {{
  --bg:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --line:rgba(255,255,255,.10); --accent:#9085e9; --accent-soft:#25213f;
  --muted-fill:#55544f; --good:#0ca30c; --bad:#e66767;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; color-scheme:dark; }}
* {{ box-sizing:border-box }}
body {{ background:var(--bg); color:var(--ink); font:16px/1.6 var(--f-body); }}
.wrap {{ max-width:1080px; margin:0 auto; padding-block:48px 80px;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px));
  display:flex; flex-direction:column; gap:56px; }}
h1,h2,h3 {{ font-family:var(--f-display); text-wrap:balance; margin:0; letter-spacing:-.01em; }}
h1 {{ font-size:clamp(2.4rem, 6vw, 3.8rem); line-height:1.02; font-weight:700; }}
h2 {{ font-size:1.6rem; font-weight:700; }}
h3 {{ font-size:1.15rem; font-weight:600; }}
p {{ margin:0; max-width:68ch; }}
.eyebrow {{ font:500 .75rem/1 var(--f-mono); letter-spacing:.12em; text-transform:uppercase; color:var(--accent); }}
header {{ display:flex; flex-direction:column; gap:16px; }}
header .lede {{ font-size:1.15rem; color:var(--ink-2); }}
.facts {{ display:flex; flex-wrap:wrap; gap:8px 24px; font:400 .85rem var(--f-mono); color:var(--ink-2); }}
.facts b {{ color:var(--ink); font-weight:500; }}
section {{ display:flex; flex-direction:column; gap:20px; }}
section > p {{ color:var(--ink-2); }}
.findings {{ list-style:none; padding:0; margin:0; display:grid; gap:12px; counter-reset:f; }}
.findings li {{ display:grid; grid-template-columns:2.2rem 1fr; gap:4px 12px; padding:16px 0; border-top:1px solid var(--line); }}
.findings li::before {{ counter-increment:f; content:counter(f); font:500 .9rem var(--f-mono); color:var(--accent); padding-top:3px; }}
.findings strong {{ font-weight:600; }}
.findings span {{ grid-column:2; color:var(--ink-2); }}
.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:6px; background:var(--surface); }}
table {{ border-collapse:collapse; width:100%; font-size:.88rem; font-variant-numeric:tabular-nums; }}
th, td {{ padding:10px 12px; text-align:right; border-bottom:1px solid var(--line); vertical-align:top; }}
tr:last-child th, tr:last-child td {{ border-bottom:0; }}
table tr:first-child th {{ font:500 .72rem/1.3 var(--f-mono); letter-spacing:.04em; text-transform:uppercase; color:var(--muted); vertical-align:bottom; }}
th[scope=row] {{ text-align:left; font-weight:500; white-space:nowrap; }}
td small, th small {{ display:block; color:var(--muted); font-size:.72rem; white-space:nowrap; font-weight:400; }}
th[scope=row] small {{ font-family:var(--f-mono); text-transform:uppercase; letter-spacing:.06em; }}
.brieft th[scope=row] {{ white-space:normal; min-width:16rem; }}
.dotkey {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:8px; vertical-align:baseline; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 440px), 1fr)); gap:24px; }}
figure {{ margin:0; }}
.chart {{ background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:18px 18px 10px; display:flex; flex-direction:column; gap:8px; min-width:0; }}
.chart h3 {{ font-size:1rem; }}
.chart p {{ font-size:.85rem; color:var(--ink-2); }}
.chart svg {{ width:100%; height:auto; display:block; }}
.legend {{ display:flex; flex-wrap:wrap; gap:6px 16px; font-size:.8rem; color:var(--ink-2); }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
.legend .hollow {{ background:transparent; border:2px solid var(--ink-2); }}
.legend .solid {{ background:var(--ink-2); }}
.legend .grey {{ background:var(--muted-fill); border-radius:2px; }}
svg .grid {{ stroke:var(--grid); stroke-width:1; }}
svg .axis {{ stroke:var(--axis); stroke-width:1; }}
svg .link {{ stroke:var(--axis); stroke-width:3; stroke-linecap:round; }}
svg .tick {{ fill:var(--muted); font:11px var(--f-mono); }}
svg .lab {{ fill:var(--ink); font:500 13px var(--f-body); }}
svg .val {{ fill:var(--ink-2); font:11px var(--f-mono); }}
svg circle.dot {{ stroke:var(--surface); stroke-width:2; }}
svg circle.dot[stroke-width] {{ }}
svg .dot {{ cursor:default; outline:none; }}
svg .dot:hover, svg .dot:focus {{ filter:brightness(1.12); }}
#tip {{ position:fixed; pointer-events:none; background:var(--ink); color:var(--bg); font:12px/1.4 var(--f-mono); padding:6px 9px; border-radius:4px; z-index:20; max-width:280px; }}
.lookbook {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap:20px; }}
.look {{ background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:20px; display:flex; flex-direction:column; gap:12px; min-width:0; }}
.look .brief {{ font:500 .72rem/1.4 var(--f-mono); text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.chips {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:6px; font-size:.88rem; }}
.chips li {{ display:flex; align-items:center; gap:8px; }}
.chips .sw {{ display:inline-flex; flex:none; }}
.chips .sw i {{ width:14px; height:14px; border-radius:50%; box-shadow:0 0 0 1px var(--line); margin-right:-4px; border:2px solid var(--surface); }}
.chips .id {{ font:500 .72rem var(--f-mono); color:var(--accent); background:var(--accent-soft); padding:1px 5px; border-radius:3px; margin-left:4px; }}
blockquote {{ margin:0; padding-left:12px; border-left:2px solid var(--grid); color:var(--ink-2); font-size:.9rem; }}
.meta {{ font:.75rem var(--f-mono); color:var(--muted); margin-top:auto; }}
.rats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap:20px; }}
.rat {{ background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:18px; display:flex; flex-direction:column; gap:10px; }}
.rat figcaption {{ font-size:.85rem; color:var(--ink-2); }}
.pill {{ display:inline-block; font:600 .7rem var(--f-mono); text-transform:uppercase; letter-spacing:.06em; padding:3px 8px; border-radius:99px; margin-right:6px; }}
.rat.defended .pill {{ color:var(--bad); border:1px solid currentColor; }}
.rat.flagged .pill {{ color:var(--good); border:1px solid currentColor; }}
.planted {{ font-size:.9rem; }}
.method {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap:16px 32px; }}
.method div {{ display:flex; flex-direction:column; gap:6px; }}
.method p, .method li {{ font-size:.9rem; color:var(--ink-2); }}
.method ul {{ margin:0; padding-left:18px; display:flex; flex-direction:column; gap:4px; }}
code {{ font:.85em var(--f-mono); }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
</style>
<div class="wrap">
<header>
  <span class="eyebrow">Dress-up game · LLM creativity &amp; reasoning study · <a href="index.html" style="color:inherit">watch the runway demo →</a></span>
  <h1>Wardrobe Muse</h1>
  <p class="lede">Five open-weight model setups played stylist with the same 69-item wardrobe and 12 briefs, from a law-firm interview to “dress as the feeling of a Sunday evening”. Every outfit is a set of item IDs, so creativity and rule-following can be measured exactly, and the stated reasoning can be tested against the actual choice.</p>
  <div class="facts"><span><b>{len(GEN):,}</b> outfits generated</span><span><b>{n_valid:,}</b> valid</span><span><b>4</b> temperatures × <b>2</b> prompt orders × <b>8</b> samples</span><span><b>{len(RAT)}</b> planted-item trials</span><span>vLLM on one L40S via Modal</span></div>
</header>

<section>
  <h2>What we found</h2>
  <ol class="findings">
    <li><strong>Thinking made Qwen3 reliable and more faithful, not more original.</strong><span>With thinking on, Qwen3-8B produced the most valid outfits ({pct(by_cfg["qwen3-8b-think"]["valid_rate"])}), met the most constraints ({pct(by_cfg["qwen3-8b-think"]["constraint_ok_rate"])}) and got the best judge fit ({by_cfg["qwen3-8b-think"]["judge_fit"]:.2f}). Its explanations named items it didn't wear only {pct(by_cfg["qwen3-8b-think"]["phantom_rate"],1)} of the time, against 18–61% for the others. It also made the most predictable choices: lowest novelty, {by_cfg["qwen3-8b-think"]["novelty_bits"]:.2f} bits per item.</span></li>
    <li><strong>Qwen2.5-7B was the most creative by our definition.</strong><span>Counting outfits that were valid, met the brief's constraints, scored fit ≥ 7 and were more unusual than the median for their brief, Qwen2.5-7B hit {pct(by_cfg["qwen2.5-7b"]["creative_hit_rate"],1)}, against {pct(by_cfg["qwen3-8b-think"]["creative_hit_rate"],1)} for both Qwen3 setups.</span></li>
    <li><strong>Reasoning before choosing raised creativity in models without thinking.</strong><span>Qwen2.5-7B's creative hit rate went from {pct(by_cc[("qwen2.5-7b","answer_first")]["creative_hit_rate"],1)} to {pct(by_cc[("qwen2.5-7b","reason_first")]["creative_hit_rate"],1)}. Qwen3-8B went from {pct(by_cc[("qwen3-8b","answer_first")]["creative_hit_rate"],1)} to {pct(by_cc[("qwen3-8b","reason_first")]["creative_hit_rate"],1)}, though its valid outfits fell from {pct(by_cc[("qwen3-8b","answer_first")]["valid_rate"])} to {pct(by_cc[("qwen3-8b","reason_first")]["valid_rate"])}. With thinking on, the order made no difference.</span></li>
    <li><strong>Models mostly defended an item they never picked.</strong><span>When one item in their own outfit was secretly swapped for an off-brief piece, models defended it in 67–94% of trials. Only Qwen3-8B with thinking flagged it noticeably more often than an unaltered item: {cnt[("qwen3-8b-think","planted","flagged")]}/{tot[("qwen3-8b-think","planted")]} versus {cnt[("qwen3-8b-think","control","flagged")]}/{tot[("qwen3-8b-think","control")]}. Qwen2.5-7B flagged it {cnt[("qwen2.5-7b","planted","flagged")]}/{tot[("qwen2.5-7b","planted")]} times.</span></li>
    <li><strong>Higher temperature bought novelty at the cost of validity for small models.</strong><span>Phi-4-mini went from {pct(by_ct[("phi4-mini",0.3)]["valid_rate"])} valid at T=0.3 to {pct(by_ct[("phi4-mini",1.3)]["valid_rate"])} at T=1.3. Qwen3-8B stayed between {pct(by_ct[("qwen3-8b",0.3)]["valid_rate"])} and {pct(by_ct[("qwen3-8b",1.3)]["valid_rate"])}.</span></li>
    <li><strong>The judge's “originality” score and statistical rarity barely agree.</strong><span>Spearman ρ between surprisal and judged originality was {corr["novelty_vs_judge_originality"]:.2f}. Rarer outfits were judged to fit slightly worse (ρ = {corr["novelty_vs_fit"]:.2f}), which is the novelty-versus-appropriateness trade-off creativity research describes.</span></li>
  </ol>
</section>

<section>
  <h2>Scoreboard</h2>
  <p>Averages over all 768 outfits per setup. Novelty is surprisal under how often all five setups picked each item for that brief; diversity is the mean pairwise Jaccard distance between repeated samples. Reconstruction gain is how much better a reader model rebuilds the outfit from item-redacted reasoning than from the brief alone.</p>
  <div class="tablewrap">{scoreboard()}</div>
</section>

<section>
  <h2>Temperature, prompt order and honesty</h2>
  <div class="legend">{legend}</div>
  <div class="charts">
    <figure class="chart"><h3>Valid outfits by temperature</h3><p>Share of outputs that parse and follow the wardrobe rules.</p>
      {line_chart("valid_rate", 0, 1, [0, .25, .5, .75, 1], lambda v: f"{v*100:.0f}%", "Valid outfits by temperature", "valid")}</figure>
    <figure class="chart"><h3>Novelty by temperature</h3><p>Mean surprisal of chosen items, in bits per item. Higher means less typical.</p>
      {line_chart("novelty_bits", 1.5, 3.75, [1.5, 2, 2.5, 3, 3.5], lambda v: f"{v:.1f}", "Novelty by temperature", "novelty bits")}</figure>
    <figure class="chart"><h3>Creative hit rate: reason first vs choose first</h3>
      <div class="legend"><span><i class="hollow"></i>Choose, then explain</span><span><i class="solid"></i>Reason, then choose</span></div>
      {dumbbell()}</figure>
    <figure class="chart"><h3>How often the model flagged the item it didn't choose</h3>
      <div class="legend"><span><i class="solid" style="border-radius:2px"></i>Outfit with a planted item (model colour)</span><span><i class="grey"></i>Unaltered outfit (false alarms)</span></div>
      {rat_bars()}</figure>
  </div>
</section>

<section>
  <h2>Lookbook</h2>
  <p>The judge's most original look per brief, among outfits that counted as creative hits. Reasoning is the model's own text, shortened.</p>
  <div class="lookbook">{showcase()}</div>
</section>

<section>
  <h2>The planted-item test</h2>
  <p>Each model saw one of its own outfits with a single piece swapped for an item sharing no style tags with the rest, then was asked to explain the outfit item by item and say if anything didn't belong.</p>
  <div class="rats">{rat_examples()}</div>
</section>

<section>
  <h2>Second judge</h2>
  <p>The first judge was Qwen3-8B, which shares a family with two contestants. To check for self-preference, every valid outfit and every planted-item explanation was re-scored by IBM Granite-3.3-8B, which comes from a family none of the contestants belong to. Granite scores about one point more generously, so the bias column compares z-scored ratings. A positive value means the Qwen3 judge liked that model's outfits more than Granite did.</p>
  <div class="tablewrap">{judges_table()}</div>
  <ul class="findings">
    <li><strong>The Qwen3 judge did not favour Qwen outfits.</strong><span>Both judges ranked the five setups in the same order on fit. Relative to Granite, the Qwen3 judge was slightly <em>harder</em> on Qwen2.5-7B and Qwen3-8B and slightly kinder to OLMo-2 and Phi-4-mini.</span></li>
    <li><strong>The judges agree moderately on individual outfits.</strong><span>Spearman ρ between their scores: fit {ag["fit"]:.2f}, originality {ag["originality"]:.2f}, coherence {ag["coherence"]:.2f}. They agree on the ranking of models more than on single looks.</span></li>
    <li><strong>The planted-item result holds.</strong><span>The judges gave the same verdict on {corr["verdict_agreement"]*100:.0f}% of explanations. Granite also found Qwen3-8B with thinking flagging the planted item {c2[("qwen3-8b-think","planted")]}/{tot[("qwen3-8b-think","planted")]} times against {c2[("qwen3-8b-think","control")]}/{tot[("qwen3-8b-think","control")]} for unaltered outfits.</span></li>
  </ul>
</section>

<section>
  <h2>Brief difficulty</h2>
  <p>Sorted from lowest judged fit. Counting colours and summing warmth were the constraints models broke most.</p>
  <div class="tablewrap brieft">{brief_table()}</div>
</section>

<section>
  <h2>Method and limits</h2>
  <div class="method">
    <div><h3>Setup</h3><ul>
      <li>Models: Qwen3-8B (thinking on and off), Qwen2.5-7B-Instruct, Phi-4-mini-instruct, OLMo-2-1124-7B-Instruct, served with vLLM 0.9.2 on one L40S via Modal.</li>
      <li>12 briefs: 3 conventional, 4 with constraints (colour, warmth, required tie, rugged footwear), 5 open-ended.</li>
      <li>Judges: Qwen3-8B with thinking off, re-checked by IBM Granite-3.3-8B; both at temperature 0 and blind to which model made the outfit. Qwen3-8B also served as the reconstruction reader.</li>
    </ul></div>
    <div><h3>Limits</h3><ul>
      <li>Both judges are 8B models, and they agree only moderately on single outfits. Human ratings on a sample would show which judge tracks taste better.</li>
      <li>Novelty is relative to these five setups, not to human stylists.</li>
      <li>Redaction removes item names and IDs, but paraphrases like “the red scarf” still leak, so reconstruction scores run high for every model.</li>
      <li>Planted-item results rest on 17–24 trials per setup; treat differences of a few trials as noise.</li>
    </ul></div>
  </div>
</section>
</div>
<div id="tip" hidden></div>
<script>
(() => {{
  const tip = document.getElementById("tip");
  const show = (el, x, y) => {{ tip.textContent = el.dataset.tip; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(x + 12, innerWidth - r.width - 8) + "px"; tip.style.top = Math.max(8, y - r.height - 10) + "px"; }};
  document.querySelectorAll("[data-tip]").forEach(el => {{
    el.addEventListener("mousemove", ev => show(el, ev.clientX, ev.clientY));
    el.addEventListener("mouseleave", () => tip.hidden = true);
    el.addEventListener("focus", () => {{ const b = el.getBoundingClientRect(); show(el, b.right, b.top); }});
    el.addEventListener("blur", () => tip.hidden = true);
  }});
}})();
</script>
'''

out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/report.html")
out.parent.mkdir(exist_ok=True)
out.write_text(page, encoding="utf-8")
print(f"wrote {out} ({len(page)//1024} KB)")
