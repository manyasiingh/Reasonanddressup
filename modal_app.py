"""Modal GPU backend (vLLM) for the dress-up creativity experiment.

Usage:
  python -m modal run modal_app.py --gpu L40S --smoke       # tiny end-to-end check
  python -m modal run modal_app.py --gpu L40S               # full run
"""

import time
from pathlib import Path

import modal

app = modal.App("llm-dressup-creativity")

image = (
    modal.Image.debian_slim(python_version="3.12")
    # pin transformers/hub: unpinned pip pulls transformers 5.x, which breaks vLLM 0.9.2 at import
    .pip_install("vllm==0.9.2", "transformers==4.53.2", "huggingface_hub[hf_transfer]==0.33.4")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_LOGGING_LEVEL": "WARNING"})
)
hf_cache = modal.Volume.from_name("dressup-hf-cache", create_if_missing=True)

MAX_LEN = {"allenai/OLMo-2-1124-7B-Instruct": 4096}


@app.cls(image=image, gpu="L40S", volumes={"/root/.cache/huggingface": hf_cache},
         timeout=3600, scaledown_window=600)
class Generator:
    model_id: str = modal.parameter()

    @modal.enter()
    def load(self):
        from vllm import LLM
        self.max_len = MAX_LEN.get(self.model_id, 8192)
        self.llm = LLM(model=self.model_id, max_model_len=self.max_len, dtype="bfloat16",
                       gpu_memory_utilization=0.90, seed=0)
        self.tok = self.llm.get_tokenizer()
        hf_cache.commit()

    @modal.method()
    def generate(self, requests: list[dict]) -> list[str]:
        from vllm import SamplingParams
        out = [None] * len(requests)
        for thinking in (False, True):
            idx = [i for i, r in enumerate(requests) if bool(r.get("thinking")) == thinking]
            if not idx:
                continue
            convs, params = [], []
            for i in idx:
                r = requests[i]
                n_prompt = len(self.tok.apply_chat_template(
                    r["messages"], add_generation_prompt=True, tokenize=True, enable_thinking=thinking))
                max_tokens = max(16, min(r["max_tokens"], self.max_len - n_prompt - 8))
                convs.append(r["messages"])
                params.append(SamplingParams(temperature=r["temperature"], top_p=1.0, seed=r["seed"],
                                             max_tokens=max_tokens))
            t0 = time.time()
            res = self.llm.chat(convs, params, use_tqdm=False,
                                chat_template_kwargs={"enable_thinking": thinking})
            print(f"{self.model_id} thinking={thinking}: {len(idx)} reqs in {time.time()-t0:.0f}s")
            for i, o in zip(idx, res):
                text = o.outputs[0].text
                if thinking and "<think>" not in text and "</think>" in text:
                    text = "<think>" + text
                out[i] = text
        return out  # type: ignore


@app.function(image=image, timeout=600)
def check_image():
    """CPU-only sanity check: vLLM imports and every tokenizer/chat template loads."""
    import transformers
    import vllm  # noqa: F401
    from transformers import AutoTokenizer
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    for m in ["Qwen/Qwen3-8B", "Qwen/Qwen2.5-7B-Instruct", "microsoft/Phi-4-mini-instruct",
              "allenai/OLMo-2-1124-7B-Instruct", "ibm-granite/granite-3.3-8b-instruct"]:
        tok = AutoTokenizer.from_pretrained(m)
        n = len(tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, enable_thinking=False))
        print(f"ok {m}: {n} prompt tokens")
    return f"vllm {vllm.__version__}, transformers {transformers.__version__}"


@app.local_entrypoint()
def main(gpu: str = "L40S", smoke: bool = False, samples: int = 8, name: str = ""):
    import pipeline
    from wardrobe import BRIEFS

    print("[check]", check_image.remote())

    handles = {}

    def generate_fn(model_id, requests):
        if model_id not in handles:
            handles[model_id] = Generator.with_options(gpu=gpu)(model_id=model_id)
        return handles[model_id].generate.remote(requests)

    if smoke:
        kw = dict(briefs=[BRIEFS[0], BRIEFS[8]], temps=[0.7], samples=2)
    else:
        kw = dict(samples=samples)
    out = Path("results") / (name or ("smoke" if smoke else time.strftime("run_%Y%m%d_%H%M")))
    t0 = time.time()
    pipeline.run(generate_fn, out, **kw)
    print(f"total wall time {time.time()-t0:.0f}s on {gpu}")


@app.local_entrypoint()
def judge2(gpu: str = "L40S", run: str = "results/full"):
    """Re-score an existing run with a second, non-Qwen judge."""
    import pipeline

    print("[check]", check_image.remote())
    gen = Generator.with_options(gpu=gpu)(model_id=pipeline.JUDGE2_MODEL)
    t0 = time.time()
    pipeline.rejudge(lambda m, reqs: gen.generate.remote(reqs), Path(run))
    print(f"total wall time {time.time()-t0:.0f}s on {gpu}")
