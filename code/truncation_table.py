"""
Build a LaTeX table of output-cap truncation on the open-source OpenRouter runs.
A trial is "truncated" if its output piled up at the provider's effective cap;
truncated trials often emit no final answer ("empty"), which depresses accuracy.
Writes figures/figs_sept/truncation_rates.tex.
"""
import importlib.util
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "figures", "figs_sept")
os.makedirs(OUT, exist_ok=True)

# provider per model, from the benchmark config
_s = importlib.util.spec_from_file_location(
    "bm", os.path.join(ROOT, "code", "benchmark_math_open_source.py"))
bm = importlib.util.module_from_spec(_s); _s.loader.exec_module(bm)
PROVIDER = {m["label"]: m["provider"] for m in bm.MODELS}

# (display label, provider-config label, data slug)
MODELS = [
    ("GLM 4.5", "GLM 4.5", "glm_4_5"), ("GLM 4.6", "GLM 4.6", "glm_4_6"),
    ("GLM 4.7", "GLM 4.7", "glm_4_7"), ("GLM 5", "GLM 5", "glm_5"),
    ("GLM 5.1", "GLM 5.1", "glm_5_1"), ("GLM 5.2", "GLM 5.2", "glm_5_2"),
    ("GLM 5.3", "GLM 5.3", "glm_5_3"),
    ("Kimi K2.5", "Kimi K2.5", "kimi_k2_5"), ("Kimi K2.6", "Kimi K2.6", "kimi_k2_6"),
    ("Kimi K2.7 Code", "Kimi K2.7 Code", "kimi_k2_7_code"),
    ("Kimi K2 Thinking", "Kimi K2 Thinking", "kimi_k2_thinking"),
    ("Kimi K3", "Kimi K3", "kimi_k3"),
]

rows = []
for disp, cfg_label, slug in MODELS:
    p = os.path.join(DATA, f"{slug}_shallow_pass", f"{slug}_thinking_benchmark_90.json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    tot = [t for r in d for t in r["total_completion_tokens"]]
    empty = np.mean([1 if not t.strip() else 0 for r in d for t in r["response_texts"]])
    n = len(tot)
    mx = max(tot)
    at_max = sum(1 for t in tot if t >= mx - 2)
    trunc_frac = at_max / n
    # a "cap" only if trials genuinely pile up at the max
    capped = trunc_frac >= 0.03
    rows.append({
        "model": disp,
        "provider": PROVIDER.get(cfg_label, "?"),
        "cap": f"{mx:,}" if capped else "--",
        "n": n, "trunc_n": at_max if capped else 0,
        "trunc": trunc_frac if capped else 0.0,
        "empty": empty,
    })

rows.sort(key=lambda r: r["trunc"], reverse=True)

lines = [
    r"\begin{table}[t]",
    r"\centering",
    r"\caption{Output-cap truncation on the open-source OpenRouter runs "
    r"(requested cap 40{,}000 tokens; $k{=}8$ over 47 problems $=$ 376 trials per model). "
    r"A trial is \emph{truncated} if its output piled up at the provider's effective cap; "
    r"such trials usually emit no final \texttt{\textbackslash boxed\{\}} answer "
    r"(\emph{empty}), which depresses measured accuracy. Providers that honored no cap "
    r"(ran past 40k) and the two naturally-short medium-effort models show ``--''. "
    r"For reference, all GPT and Opus runs stayed far below the cap (0\% truncation).}",
    r"\label{tab:truncation}",
    r"\begin{tabular}{llrrr}",
    r"\toprule",
    r"Model & Provider & Eff.\ cap & Truncated & Empty ans. \\",
    r"\midrule",
]
for r in rows:
    cap = r["cap"].replace(",", "{,}") if r["cap"] != "--" else "--"
    tr = f"{r['trunc_n']}/{r['n']} ({r['trunc']*100:.0f}\\%)" if r["trunc_n"] else "0\\%"
    lines.append(f"{r['model']} & {r['provider']} & {cap} & {tr} & {r['empty']*100:.0f}\\% \\\\")
lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]

tex = "\n".join(lines)
path = os.path.join(OUT, "truncation_rates.tex")
with open(path, "w") as f:
    f.write(tex)
print(tex)
print(f"wrote {path}")
