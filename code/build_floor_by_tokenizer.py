"""Tokenize the canonical human solutions with EACH provider's own tokenizer.

WHY THIS EXISTS. Model trace lengths `L` come from the provider's own usage counter,
so they are in that provider's token units. The floor `C_j` was tokenized for every
model with tiktoken `o200k_base` — OpenAI units. For Anthropic models that makes
`L / C_j` and `L - C_j` a ratio and a difference between two different units.

It is not a small effect, and it is not constant across the Anthropic series, because
**Anthropic changed tokenizer at Claude Opus 4.7** (their docs: 1M tokens is ~555k
words on the current tokenizer, ~750k words on the earlier one). Measured against
o200k_base on this benchmark's own solution text, with message framing removed:

    Opus 4.5, 4.6                        1.14x o200k
    Opus 4.7, 4.8, Opus 5, Fable 5.1     1.34x o200k

So a floor of 316 o200k tokens is really ~360 tokens to Opus 4.5 and ~424 to Fable
5.1. Using 316 for all of them understates the floor for Anthropic, which inflates
every Anthropic `L / C_j` and overstates the excess `L - C_j`.

This script counts each canonical solution with every tokenizer and writes
`code/canonical_floors_by_tokenizer.json`, so the figures can pick the right floor per
model and nobody needs an API key to reproduce them.

    ANTHROPIC_API_KEY=... ./venv/bin/python code/build_floor_by_tokenizer.py

Counting is done through `client.messages.count_tokens`, which is free but wraps the
text in a message, so a fixed framing cost is measured per model and subtracted.

WHAT IS NOT COVERED. gpt-oss, GLM and DeepSeek report their own tokenizers too, and
those are not queryable here. Their figures keep the o200k floor and inherit the same
caveat -- see README run-hygiene item 16.
"""
import json
import os
import sys

import numpy as np
import tiktoken
from datasets import load_dataset

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "canonical_floors_by_tokenizer.json")
HF_DATASET = "tyrtleli/thinking-benchmark-90"

# One representative model per distinct tokenizer. Opus 4.5 and 4.6 share one; 4.7
# onward share another. Verified by counting the same probe text through all six.
ANTHROPIC_TOKENIZERS = {
    "anthropic_pre_4_7": "claude-opus-4-5",
    "anthropic_4_7_plus": "claude-opus-5",
}
# The open-weight families tokenize themselves. Pulled from the Hub as raw
# tokenizer.json (no `transformers` needed -- just `tokenizers` + `huggingface_hub`).
HF_TOKENIZERS = {
    "deepseek": "deepseek-ai/DeepSeek-V3",   # R1 and V3 share this tokenizer
    "glm": "zai-org/GLM-4.5",
}
# gpt-oss uses o200k_harmony. Verified identical to o200k_base on all 122 canonical
# solutions -- harmony only adds special tokens, the ordinary-text vocabulary is the
# same -- so it gets its own column only to make that check reproducible.
TIKTOKEN_EXTRA = {"o200k_harmony": "o200k_harmony"}
# Which tokenizer each model's reported counts are in. EVERY spelling a figure
# might pass must appear: Figure 5 uses the API id, the tables use the display
# name, and an unmapped Anthropic label silently means an OpenAI floor.
MODEL_TOKENIZER = {
    'claude-opus-4-5': 'anthropic_pre_4_7',
    'claude-opus-4-6': 'anthropic_pre_4_7',
    'claude-opus-4-7': 'anthropic_4_7_plus',
    'claude-opus-4-8': 'anthropic_4_7_plus',
    'claude-opus-5': 'anthropic_4_7_plus',
    'claude-fable-5-1': 'anthropic_4_7_plus',
    'Opus 4.5': 'anthropic_pre_4_7',
    'Opus 4.6': 'anthropic_pre_4_7',
    'Opus 4.7': 'anthropic_4_7_plus',
    'Opus 4.8': 'anthropic_4_7_plus',
    'Opus 5': 'anthropic_4_7_plus',
    'Fable 5.1': 'anthropic_4_7_plus',
    'fable5.1': 'anthropic_4_7_plus',
    # open-weight families, each on its own tokenizer
    'deepseek_r1_0528': 'deepseek', 'deepseek_v3_2': 'deepseek',
    'deepseek_v4_pro': 'deepseek', 'R1-0528': 'deepseek', 'V3.2': 'deepseek',
    'V4 Pro': 'deepseek', 'V4 high': 'deepseek', 'V4 max': 'deepseek',
    'glm_5_2': 'glm', 'glm_5_3': 'glm', 'GLM 5.2': 'glm', 'GLM 5.3': 'glm',
    'gpt-oss-20b': 'o200k_harmony', 'gpt-oss-120b': 'o200k_harmony',
    '20B': 'o200k_harmony', '120B': 'o200k_harmony',
}


def main():
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")
    key = os.environ.get("ANTHROPIC_API_KEY") or next(
        (os.environ[k] for k in os.environ
         if "ANTHROPIC" in k.upper() and str(os.environ[k]).startswith("sk-")), None)
    if not key:
        sys.exit("no Anthropic API key in the environment")
    client = anthropic.Anthropic(api_key=key)

    def count(model, text):
        return client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": text}]).input_tokens

    # fixed per-model framing cost, so we bill only the solution text
    overhead = {k: count(m, "x") - 1 for k, m in ANTHROPIC_TOKENIZERS.items()}
    print("message framing overhead:", overhead)

    enc = tiktoken.get_encoding("o200k_base")
    _extra = {k: tiktoken.get_encoding(v) for k, v in TIKTOKEN_EXTRA.items()}
    _hf = {}
    try:
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        for k, repo in HF_TOKENIZERS.items():
            _hf[k] = Tokenizer.from_file(
                hf_hub_download(repo_id=repo, filename="tokenizer.json"))
            print(f"  loaded {k} tokenizer from {repo}")
    except Exception as e:       # the Anthropic correction still works without these
        print(f"  WARNING: open-weight tokenizers unavailable ({type(e).__name__}); "
              f"those models fall back to o200k")
    ds = load_dataset(HF_DATASET, split="test")
    out = {}
    for i, r in enumerate(ds):
        sc = r.get("solution_count")
        if sc is None or (isinstance(sc, float) and np.isnan(sc)) or sc == 0:
            continue
        sols = json.loads(r["solutions"])
        per = {"o200k": [len(enc.encode(s)) for s in sols]}
        for key_, model in ANTHROPIC_TOKENIZERS.items():
            per[key_] = [count(model, s) - overhead[key_] for s in sols]
        for key_, enc2 in _extra.items():
            per[key_] = [len(enc2.encode(s)) for s in sols]
        for key_, tk in _hf.items():
            per[key_] = [len(tk.encode(s).ids) for s in sols]
        # store the RAW per-solution counts as well, so min / median / mean (and any
        # future statistic, e.g. the floor-robustness table's rows) are derivable
        # without re-querying the API
        out[str(r["id"])] = {k: {"min": float(min(v)), "median": float(np.median(v)),
                                 "mean": float(np.mean(v)), "counts": [int(x) for x in v]}
                             for k, v in per.items()}
        print(f"  [{i:3d}] {r['id']}  " +
              "  ".join(f"{k}: min={min(v)}" for k, v in per.items()))

    json.dump({"models": MODEL_TOKENIZER, "floors": out}, open(OUT, "w"), indent=2)

    comp = [t for t in out if not str(t).startswith("math_500")]
    print(f"\nwrote {OUT}  ({len(out)} problems)")
    print("\nmean shortest solution over the 40 competition problems:")
    base = np.mean([out[t]["o200k"]["min"] for t in comp])
    for k in ("o200k",) + tuple(ANTHROPIC_TOKENIZERS) + tuple(_extra) + tuple(_hf):
        v = np.mean([out[t][k]["min"] for t in comp])
        print(f"  {k:<20s} {v:7.1f} tok   ({v / base:.3f}x o200k)")


if __name__ == "__main__":
    main()
