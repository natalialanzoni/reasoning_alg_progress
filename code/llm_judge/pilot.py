"""Compare backtracking prompts and judges on the 20 review traces, against the strict
gold set, on two measures:

  count        number of abandoned approaches (quote-verified)
  share        fraction of the trace (characters) inside abandoned-approach spans --
               the trial-and-error part of the excess over the MHD

  python code/llm_judge/pilot.py --prompt v5 --judge google/gemini-2.5-pro --send
  python code/llm_judge/pilot.py --prompt v5 --judge google/gemini-2.5-pro   # score only
  python code/llm_judge/pilot.py --compare                                   # all runs

Parsing, quote verification and gold matching are shared with pilot_v4.py. Output:
out/pilot_<prompt>_<judge>.jsonl, one record per trace.
"""
import argparse
import glob
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pilot_v4 as p

HERE = p.HERE
URL = p.URL


def out_path(prompt, judge, tag=""):
    return os.path.join(HERE, "out", f"pilot_{prompt}_{judge.split('/')[-1]}{tag}.jsonl")


def call(key, model, content, max_out, reasoning=None):
    req_body = {"model": model, "temperature": 0, "max_tokens": max_out,
                "messages": [{"role": "user", "content": content}]}
    if reasoning:
        # Anthropic models do not reason on OpenRouter unless asked; Gemini 2.5 does by
        # default. Without this, sonnet-4.5 answered in ~100 tokens, one lumped instance.
        req_body["reasoning"] = {"max_tokens": reasoning}
        req_body.pop("temperature")      # extended thinking does not accept temperature
    body = json.dumps(req_body).encode()
    err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL, body, {"Authorization": f"Bearer {key}",
                                                     "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.load(r)
            ch = d["choices"][0]
            return {"raw": ch["message"]["content"] or "", "finish": ch.get("finish_reason"),
                    "in_tok": d["usage"]["prompt_tokens"],
                    "out_tok": d["usage"]["completion_tokens"]}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            time.sleep(5 * (attempt + 1))
    return {"error": err}


def send(prompt, judge, workers, max_out, reasoning=None, tag=""):
    key = os.environ.get("ERA_OPENROUTER_V2") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("no OpenRouter key (ERA_OPENROUTER_V2 / OPENROUTER_API_KEY)")
    tmpl = open(os.path.join(HERE, f"backtracking_{prompt}.txt")).read()
    out = out_path(prompt, judge, tag)
    # a record with empty output (provider error) is retried, and superseded on scoring
    done = {d["trace"] for d in map(json.loads, open(out))
            if (d.get("raw") or "").strip() and d.get("finish") != "error"} \
        if os.path.exists(out) else set()
    jobs = [(t, f) for t, f in p.traces() if t not in done]
    print(f"sending {len(jobs)} calls: prompt {prompt}, judge {judge}")

    def one(job):
        t, f = job
        _, numbered = p.number_lines(open(f).read())
        rec = {"trace": t, "rep": 0, "file": os.path.basename(f), "judge_model": judge,
               "prompt_version": prompt, "temperature": None if reasoning else 0,
               "reasoning_max_tokens": reasoning}
        rec.update(call(key, judge, tmpl.replace("{response}", numbered), max_out, reasoning))
        return rec

    with open(out, "a") as fh, ThreadPoolExecutor(workers) as ex:
        for rec in ex.map(one, jobs):
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"  {rec['trace']}  " + (f"ERROR {rec['error']}" if "error" in rec else
                  f"ok  out_tok={rec['out_tok']} finish={rec['finish']}"), flush=True)


def covered(spans, lines):
    """Characters of `lines` inside the union of 1-based inclusive line spans."""
    on = set()
    for s, e in spans:
        on.update(range(max(1, min(s, e)), min(len(lines), max(s, e)) + 1))
    return on, sum(len(lines[i - 1]) for i in on)


def score(prompt, judge, verbose=True, tag=""):
    gold_all = json.load(open(p.GOLD))["instances"]
    model_of = {r.split(",")[0][:2]: r.split(",")[1]
                for r in open(p.VERDICTS).read().splitlines()[1:]}
    recs = {}
    for d in map(json.loads, open(out_path(prompt, judge, tag))):
        good = lambda x: ((x.get("raw") or "").strip() != "") + (x.get("finish") != "error")
        if d["trace"] not in recs or good(d) >= good(recs[d["trace"]]):
            recs[d["trace"]] = d                 # the last cleanest record wins
    recs = list(recs.values())
    rows = []
    for r in sorted(recs, key=lambda r: r["trace"]):
        lines = open(os.path.join(p.TRACES, r["file"])).read().split("\n")
        total = sum(len(l) for l in lines)
        inst = p.parse(r.get("raw"), lines)
        ver = [d for d in inst if d["verified"]]
        gold = [g for g in gold_all if g["trace"] == r["trace"]]
        m, dup = p.match(ver, gold)
        firm = {g["id"] for g in gold if g["tier"] == "firm"}
        jspans = []
        for d in ver:
            e = d["abandon_found"]
            s = d["adopt_found"] or d["adopt_line"] or e
            jspans.append((s, e) if s <= e else (e, e))
        jon, jc = covered(jspans, lines)
        gon, gc = covered([s for g in gold for s in g["spans"]], lines)
        fon, fc = covered([s for g in gold if g["tier"] == "firm" for s in g["spans"]], lines)
        inter = sum(len(lines[i - 1]) for i in jon & gon)
        c = p.COUNT_RE.search(r.get("raw") or "")
        rows.append({"trace": r["trace"], "model": model_of.get(r["trace"], "?"),
                     "err": r.get("error") or ("TRUNCATED" if r.get("finish") == "length" else None),
                     "judge_count": int(c.group(1)) if c else None,
                     "listed": len(inst), "verified": len(ver), "tp": len(m), "dups": len(dup),
                     "tp_firm": sum(v in firm for v in m.values()), "firm": len(firm),
                     "gold": len(gold), "hit": set(m.values()),
                     "share_j": jc / total, "share_g": gc / total, "share_f": fc / total,
                     "span_prec": inter / jc if jc else None,
                     "span_rec": inter / gc if gc else None, "nlines": len(lines)})
    if verbose:
        print(f"\n=== prompt {prompt}  judge {judge} ===")
        print(f"{'tr':3} {'model':13} {'gold':>4} {'firm':>4} | {'cnt':>3} {'lst':>3} {'ver':>3}"
              f" {'TP':>3} {'dup':>3} | share: judge  gold")
        for x in rows:
            print(f"{x['trace']:3} {x['model']:13} {x['gold']:>4} {x['firm']:>4} | "
                  f"{x['judge_count'] if x['judge_count'] is not None else '-':>3} "
                  f"{x['listed']:>3} {x['verified']:>3} {x['tp']:>3} {x['dups']:>3} | "
                  f"{x['share_j']:>11.0%} {x['share_g']:>5.0%}  {x['err'] or ''}")
    return rows


def rank(x):
    s = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and x[s[j + 1]] == x[s[i]]:
            j += 1
        for k in range(i, j + 1):
            r[s[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    a, b = rank(a), rank(b); n = len(a); ma, mb = sum(a) / n, sum(b) / n
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** .5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else float("nan")


def summary(rows):
    gold_all = json.load(open(p.GOLD))["instances"]
    by = {x["trace"]: x for x in rows}
    ver = sum(x["verified"] for x in rows); lst = sum(x["listed"] for x in rows)
    tp = sum(x["tp"] for x in rows); tpf = sum(x["tp_firm"] for x in rows)
    nf = sum(g["tier"] == "firm" for g in gold_all)
    pos = [[0, 0] for _ in range(3)]
    for g in gold_all:
        x = by.get(g["trace"])
        if x and g["tier"] == "firm":
            b = pos[min(2, int(3 * g["anchors"][0] / x["nlines"]))]
            b[1] += 1; b[0] += g["id"] in x["hit"]
    sp = [x["span_prec"] for x in rows if x["span_prec"] is not None]
    sr = [x["span_rec"] for x in rows if x["span_rec"] is not None]
    models = sorted({x["model"] for x in rows})
    return {
        "errors": sum(bool(x["err"]) for x in rows),
        "listed": lst, "verified": ver, "quote_ok": ver / max(lst, 1),
        "match_rate": tp / max(ver, 1), "dups": sum(x["dups"] for x in rows),
        "recall_firm": tpf / nf, "recall_all": tp / len(gold_all),
        "recall_by_third": "/".join(f"{a}/{b}" for a, b in pos),
        "rho_count": spearman([x["verified"] for x in rows], [x["gold"] for x in rows]),
        "mae_count": sum(abs(x["verified"] - x["gold"]) for x in rows) / len(rows),
        "rho_share": spearman([x["share_j"] for x in rows], [x["share_g"] for x in rows]),
        "mae_share": sum(abs(x["share_j"] - x["share_g"]) for x in rows) / len(rows),
        "span_prec": sum(sp) / len(sp) if sp else float("nan"),
        "span_rec": sum(sr) / len(sr) if sr else float("nan"),
        "per_model": {m: (sum(x["verified"] for x in rows if x["model"] == m),
                          sum(x["gold"] for x in rows if x["model"] == m),
                          sum(x["share_j"] for x in rows if x["model"] == m) / 5,
                          sum(x["share_g"] for x in rows if x["model"] == m) / 5)
                      for m in models}}


def compare():
    """One row per (prompt, judge) run. The paper compares WITHIN matched pairs, so the
    bias that matters is judge/gold differing between the two models of a pair:
    pair bias = (judge/gold for the newer model) / (judge/gold for the older model).
    1.00 = the judge's error cancels in that pair's ratio."""
    runs = []
    for f in sorted(glob.glob(os.path.join(HERE, "out", "pilot_v*_*.jsonl"))):
        m = re.match(r"pilot_(v\d+)_(.+?)(_think)?\.jsonl", os.path.basename(f))
        if m:
            runs.append((m.group(1), m.group(2), m.group(3) or ""))
    pairs = [("GLM 5.2", "GLM 5.3"), ("gpt-oss-20b", "gpt-oss-120b")]
    print(f"{'run':34} {'ver':>4} {'match':>5} {'dup':>3} {'recF':>4} {'recA':>4} "
          f"{'firm by third':>15} {'rhoC':>5} {'maeC':>4} {'rhoS':>5} | pair bias count (share)")
    for pr, j, t in runs:
        v = summary(score(pr, j, verbose=False, tag=t))
        pm = v["per_model"]
        pb = []
        for old, new in pairs:
            (ja, ga, sja, sga), (jb, gb, sjb, sgb) = pm[old], pm[new]
            c = (jb / gb) / (ja / ga) if ja and ga and gb else float("nan")
            sh = (sjb / sgb) / (sja / sga) if sja and sga and sgb else float("nan")
            pb.append(f"{new.split()[0][:3]} {c:4.2f} ({sh:4.2f})")
        err = f" [{v['errors']} err]" if v["errors"] else ""
        print(f"{pr + ' ' + j + t + err:34} {v['verified']:>4} {v['match_rate']:>5.0%} "
              f"{v['dups']:>3} {v['recall_firm']:>4.0%} {v['recall_all']:>4.0%} "
              f"{v['recall_by_third']:>15} {v['rho_count']:>5.2f} {v['mae_count']:>4.1f} "
              f"{v['rho_share']:>5.2f} | " + "   ".join(pb))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="v5")
    ap.add_argument("--judge", default="google/gemini-2.5-flash")
    ap.add_argument("--send", action="store_true", help="REQUIRED to contact OpenRouter")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-out", type=int, default=16000)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--reasoning", type=int, default=None,
                    help="reasoning token budget (needed for Anthropic judges); "
                         "writes to a separate _think output file")
    a = ap.parse_args()
    if a.compare:
        compare()
    else:
        tag = "_think" if a.reasoning else ""
        if a.send:
            send(a.prompt, a.judge, a.workers, a.max_out, a.reasoning, tag)
        score(a.prompt, a.judge, tag=tag)
