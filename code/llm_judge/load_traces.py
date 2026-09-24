"""Load the CoT traces behind fig_mechanism, normalised so the four models are
directly comparable.

THE FOUR MODELS are exactly fig_mechanism's (paper_figs/, code/figure_mechanism_ft.py):
    Scale      gpt-oss-20b  -> gpt-oss-120b   (re-medium runs)
    Algorithm  GLM 5.2      -> GLM 5.3        (HIGH effort; the medium runs were
                                               silently remapped and are archived)

COT ONLY, on both sides. The two families store traces differently and this is the
whole reason a loader exists:

  GLM       `reasoning_texts` in a parallel *_reasoning_traces.json (joined by
            task_id) is the thinking block; `response_texts` is a separate clean
            write-up of the answer. Nothing is missing -- we take reasoning_texts.

  gpt-oss   one `text` field holds both, in Harmony channel format as literal
            text: "analysis" + CoT + "assistantfinal" + the answer. We take
            everything before "assistantfinal" and drop the leading "analysis".
            Measured 2026-09-21: 338/360 (20b) and 360/360 (120b) completions
            contain the separator; all 720 start with "analysis"; no split
            produces an empty CoT. The 22 without a separator were truncated
            before reaching the final channel, so the whole text is CoT already.

Counting backtracking over "CoT" for one family and "CoT + answer write-up" for
the other would not be a matched comparison, which is why this normalisation is
not optional.

SAMPLE inherited from figure1_grid_ft.py, as fig_mechanism does: the 40
competition problems (AIME 2026 I/II + HMMT Feb 2026), MATH-500 excluded, and a
trial is valid at tok >= 50.
"""
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CODE = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RESULTS = os.path.join(CODE, "results")

_spec = importlib.util.spec_from_file_location("fs", os.path.join(CODE, "figures_sept.py"))
fs = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fs)
pf = fs.pf

# the paper's sample: 40 competition problems
KEYS = {str(t) for t in pf.CANON_KEYS if not str(t).startswith("math_500")}

GLM = {
    "GLM 5.2": ("glm_5_2", "glm_5_2_thinking_benchmark_90_high"),
    "GLM 5.3": ("glm_5_3", "glm_5_3_thinking_benchmark_90_high"),
}
OSS = {
    "gpt-oss-20b": ("gpt_oss20B_shallow_pass", "gpt-oss-20b_re-medium.json"),
    "gpt-oss-120b": ("gpt_oss120B_shallow_pass", "gpt-oss-120b_re-medium.json"),
}
MODEL_ORDER = ["gpt-oss-20b", "gpt-oss-120b", "GLM 5.2", "GLM 5.3"]

SEPARATOR = "assistantfinal"
MIN_TOK = 50


def _strip_oss(text):
    """gpt-oss text -> CoT only. See module docstring for the format."""
    cot = (text or "").split(SEPARATOR)[0]
    s = cot.lstrip()
    if s.startswith("analysis"):
        s = s[len("analysis"):]
    return s.strip()


def _load_glm(label):
    slug, stem = GLM[label]
    res = json.load(open(os.path.join(DATA, f"{slug}_shallow_pass", f"{stem}.json")))
    # GLM's CoT is a separate traces file. The committed copy is gzipped under data/
    # (code/results/ is gitignored, so an uncompressed copy exists only on the machine
    # that ran the sweep). Prefer the committed one so a fresh checkout works.
    gz = os.path.join(DATA, f"{slug}_shallow_pass", f"{stem}_reasoning_traces.json.gz")
    raw = os.path.join(RESULTS, f"{slug}_shallow_pass", f"{stem}_reasoning_traces.json")
    if os.path.exists(gz):
        import gzip
        with gzip.open(gz, "rt") as fh:
            traces = json.load(fh)
    elif os.path.exists(raw):
        traces = json.load(open(raw))
    else:
        raise SystemExit(
            f"{label}: traces not found.\n"
            f"  looked for {gz}\n  and       {raw}\n"
            "  Without the CoT there is nothing to judge.")
    tmap = {str(t["task_id"]): t["reasoning_texts"] for t in traces}
    out = []
    for r in res:
        tid = str(r["task_id"])
        if tid not in KEYS:
            continue
        traces = tmap.get(tid) or []
        for i, tok in enumerate(r["total_completion_tokens"]):
            if tok < MIN_TOK or i >= len(traces):
                continue
            cot = (traces[i] or "").strip()
            if not cot:
                continue
            # Behaviours are counted in the CoT, so a per-token rate must divide by
            # CoT tokens, not by the whole completion. GLM logs thinking_tokens, so
            # this is exact. (thinking + answer = total, checked.)
            out.append({"model": label, "task_id": tid, "sample": i, "cot": cot,
                        "tokens": tok, "cot_tokens": r["thinking_tokens"][i],
                        "cot_tokens_exact": True,
                        "correct": bool(r["correct"][i])})
    return out


def _load_oss(label):
    folder, fname = OSS[label]
    d = json.load(open(os.path.join(DATA, folder, fname)))
    out = []
    for e in d["results"]:
        tid = str(e["id"])
        if tid not in KEYS:
            continue
        for i, c in enumerate(e.get("completions", [])):
            tok = c.get("n_tokens", 0)
            if tok < MIN_TOK:
                continue
            cot = _strip_oss(c.get("text"))
            if not cot:
                continue
            # gpt-oss logs only n_tokens for the whole completion -- there is no
            # reasoning-token field -- so the CoT share is ESTIMATED by character
            # proportion. Median CoT share is 0.84, and the answer is ordinary prose
            # plus a boxed result, so it tokenises at much the same rate as the CoT.
            # Treat this column as approximate; the GLM columns are exact.
            full = c.get("text") or ""
            frac = (len(cot) / len(full)) if full else 1.0
            out.append({"model": label, "task_id": tid, "sample": i, "cot": cot,
                        "tokens": tok, "cot_tokens": tok * frac,
                        "cot_tokens_exact": False,
                        "correct": bool(c.get("is_correct"))})
    return out


def load_all(models=None):
    out = []
    for label in (models or MODEL_ORDER):
        out.extend(_load_glm(label) if label in GLM else _load_oss(label))
    return out


if __name__ == "__main__":
    import statistics as st
    rows = load_all()
    print(f"sample: {len(KEYS)} competition problems, validity tok >= {MIN_TOK}\n")
    print(f"  {'model':<15}{'traces':>8}{'median CoT chars':>18}{'median tokens':>15}")
    for m in MODEL_ORDER:
        r = [x for x in rows if x["model"] == m]
        print(f"  {m:<15}{len(r):>8}{st.median(len(x['cot']) for x in r):>18,.0f}"
              f"{st.median(x['tokens'] for x in r):>15,.0f}")
    print(f"\n  TOTAL {len(rows)} traces")
