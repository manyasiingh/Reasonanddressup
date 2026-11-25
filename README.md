# Wardrobe Muse

**Measuring creativity and reasoning faithfulness in small LLMs with a dress-up game.**

Five open-weight model setups play stylist. Each gets the same fixed wardrobe of 69 items and a design brief, from *"a job interview at a traditional law firm"* to *"dress as the feeling of a Sunday evening"*, and must pick an outfit by item ID and explain why.

Every outfit is a set of IDs, so creativity, rule-following and diversity are **measured exactly** rather than eyeballed. The stated reasoning can then be **tested against the actual choice**. The pipeline runs end to end on a single cloud GPU through [Modal](https://modal.com) and [vLLM](https://github.com/vllm-project/vllm).

---

## Why a dress-up game?

Creativity benchmarks usually grade free text such as poems or stories, which is hard to score objectively. A wardrobe gives a closed, checkable action space with plenty of room for taste:

- **Valid or not** is exact: real IDs, right slots, at most two accessories, a top and a bottom *or* a one-piece.
- **Brief constraints** are exact too: "no black", "at most two colours", "must wear a necktie at the beach", "total warmth ≥ 6 at −5 °C".
- **Novelty** is measured as surprisal, in bits per item, under how often all the models picked each item for that brief.
- **Appropriateness** is scored by two independent LLM judges, plus an embedding similarity check that doesn't depend on an LLM.

Creativity is defined the way creativity research usually defines it: **novel *and* appropriate**.

## Experiment design

| | |
|---|---|
| **Wardrobe** | 69 items in 7 slots (top, bottom, one-piece, outerwear, footwear, headwear, accessory). Each item has colours, formality 1–5, warmth 0–3 and style tags. |
| **Briefs** | 12 in total: 3 conventional, 4 with a hard constraint, 5 open-ended |
| **Models** | Qwen3-8B (thinking **on** and **off**), Qwen2.5-7B-Instruct, Phi-4-mini-instruct, OLMo-2-1124-7B-Instruct |
| **Conditions** | 4 temperatures (0.3, 0.7, 1.0, 1.3) × 2 prompt orders (*reason, then choose* vs *choose, then explain*) × 8 samples |
| **Scale** | 3,840 outfits, 220 planted-item trials, about 8,000 judge calls |
| **Judges** | Qwen3-8B (thinking off), re-checked by IBM Granite-3.3-8B, which belongs to no contestant's model family. Both run at temperature 0 and don't know which model made the outfit. |

### Creativity metrics

| Metric | What it measures |
|---|---|
| Valid rate | Output parses and follows the wardrobe rules |
| Constraint rate | Meets the brief's hard rule |
| Novelty | Mean surprisal of the chosen items for that brief, in bits per item |
| Diversity | Mean pairwise Jaccard distance between repeated samples |
| Judge fit / originality / coherence | 1–10 scores from each judge |
| **Creative hit rate** | Valid ∧ meets constraints ∧ judge fit ≥ 7 ∧ novelty above the brief's median |

### Reasoning-faithfulness tests

1. **Reconstruction.** Item names are removed from a model's explanation, and a fixed reader model tries to rebuild the outfit from what's left. The *gain* over a brief-only guess shows how much the reasoning actually explains the choice.
2. **Phantom mentions.** Does the explanation name items the model didn't actually pick?
3. **Planted-item (rationalization) test.** The model is shown one of its own outfits with one piece secretly swapped for an off-brief item, then asked to explain each piece. Does it defend the planted item or flag it? Unaltered outfits serve as a false-alarm control.

## Results

| Model | Valid | Meets constraints | Judge fit | Novelty (bits) | Creative hits | Phantom items | Reconstruction gain | Flags planted item |
|---|---|---|---|---|---|---|---|---|
| Qwen3-8B · thinking | **94%** | **80%** | **7.21** | 1.87 | 16.3% | **4.5%** | **+0.26** | **7/24** |
| Qwen3-8B | 84% | 73% | 6.89 | 1.91 | 16.3% | 18% | +0.16 | 3/23 |
| Qwen2.5-7B | 85% | 57% | 6.63 | 2.54 | **27.6%** | 28% | +0.14 | 2/24 |
| Phi-4-mini | 45% | 60% | 6.58 | 2.69 | 12.4% | 42% | +0.11 | 6/22 |
| OLMo-2-7B | 23% | 44% | 6.43 | 2.90 | 6.0% | 61% | +0.12 | 1/17 |

*Judge fit uses the Qwen3 judge. Creative hits use the Qwen3 judge's fit; under Granite or under both judges together, the model ranking is the same.*

### Key findings

1. **Thinking made Qwen3 reliable and faithful, but not original.** It had the highest validity, constraint rate and judge fit. Its explanations almost never named items it wasn't wearing, and they predicted its choices best. It also made the most predictable picks.
2. **Qwen2.5-7B was the most creative by the novel-and-appropriate definition.** It led under either judge: 27.6% (Qwen3 judge), 42.4% (Granite), 27.1% (both agree).
3. **Reasoning before choosing increases creativity in models without thinking.** Qwen2.5-7B's creative hits went from 19.5% to 35.7%, and Qwen3-8B (thinking off) went from 8.9% to 23.7%. For Qwen3-8B this cost validity, which fell from 96% to 71%. With thinking on, the prompt order made no difference.
4. **Models mostly rationalize.** They defended a planted, off-brief item in 67–94% of trials. Only Qwen3-8B with thinking flagged it clearly more often than unaltered outfits: 7/24 versus 1/24, and Granite independently found 6/24 versus 0/24.
5. **Temperature buys novelty at the cost of validity in small models.** Phi-4-mini's validity fell from 69% at T = 0.3 to 7% at T = 1.3. Qwen3-8B held steady at 82–85%.
6. **Novelty trades off against fit.** Spearman ρ between novelty and judged fit was −0.28. The judges' "originality" scores barely track statistical rarity (ρ = 0.07).
7. **No judge self-preference was found.** Both judges ranked the five models identically on fit. After z-scoring, the Qwen3 judge was slightly *harsher* on Qwen outputs than Granite was. The two judges agree moderately on individual outfits (ρ ≈ 0.5) and on 91% of planted-item verdicts.

The hardest constraints were counting colours (the two-colour brief was met only 12% of the time) and summing warmth (46%).

## Visual outputs

The repo builds two self-contained HTML pages from a finished run:

- **`report/wardrobe-muse.html`**: the results report, with a scoreboard, temperature and prompt-order charts, a lookbook of the best outfits, planted-item examples and the judge comparison.
- **`report/runway.html`**: an animated paper-doll runway that replays real looks. The model's notes type out, garments drop onto the doll, both judges raise score paddles, and the swap test is replayed with a *Defended it* / *Caught it* stamp.

## Running it

### 1. Setup

```bash
pip install -r requirements.txt
python -m modal setup          # one-time login to Modal
```

All GPU work happens inside a Modal container built from `modal_app.py`, which pins `vllm==0.9.2`, `transformers==4.53.2` and `huggingface_hub==0.33.4`. An unpinned `transformers` 5.x crashes vLLM 0.9.2 at import. Model weights are cached in a Modal volume. Before any GPU starts, a CPU-only check imports vLLM and loads every model's chat template, so a broken environment fails once instead of repeatedly restarting a GPU container.

### 2. Smoke test (2 briefs, 2 samples, every stage)

```bash
python -m modal run modal_app.py --gpu L40S --smoke
```

### 3. Full experiment

```bash
python -m modal run modal_app.py --gpu L40S --name full        # ~20 min on one L40S
python -m modal run modal_app.py::judge2 --gpu L40S --run results/full   # second judge, ~6 min
```

### 4. Analysis and pages

```bash
python analyze.py results/full          # tables, summary.json, metrics.csv
python make_report.py results/full      # report/wardrobe-muse.html
python make_runway.py results/full      # report/runway.html
```

`analyze.py --no-embed` skips the sentence-transformers fit score if you don't want to download the embedding model.

The full run took about 20 minutes of wall time. Four model containers ran in parallel on L40S GPUs, so the whole thing costs a few dollars of Modal credit including model downloads. `--gpu A100` or `--gpu H100` also work.

## Project structure

```
wardrobe.py          wardrobe catalog, briefs, outfit validation and constraint checks
prompts.py           stylist / judge / reader / rationalization prompts, JSON parsing, item redaction
pipeline.py          backend-agnostic experiment stages: generate → rationalize → judge → second judge
modal_app.py         Modal + vLLM GPU backend and run entry points
analyze.py           metrics: validity, novelty, diversity, creative hits, faithfulness, judge agreement
make_report.py       builds the HTML results report
make_runway.py       builds the animated runway page from web/runway_template.html
web/                 runway page template (vanilla JS + SVG, no build step)
```

`pipeline.py` only needs a `generate_fn(model_id, requests) -> texts` function, so you can swap Modal for a local vLLM server or any other backend.

## Limitations

- Both judges are 8B models. Human ratings on a sample would show which judge better tracks human taste.
- Novelty is measured relative to these five setups, not to human stylists.
- Redaction removes item names and IDs, but paraphrases like "the red scarf" still leak information, so reconstruction scores are inflated for every model by a similar amount.
- The planted-item results rest on 17–24 trials per setup. Treat differences of a few trials as noise.
- OLMo-2's 4,096-token context makes long prompts tight, which adds to its high rate of unparsable outputs.

## Ideas for extending it

- Add human ratings on a stratified sample to calibrate the judges.
- Include larger models, or the same family at several sizes, to see how creativity and faithfulness scale.
- Use constrained decoding (a JSON grammar) to separate *format* failures from *taste* failures.
- Run multi-turn styling, where the model revises its look after judge feedback.
