"""Pilot backtracking v4 (strict, quoted instances) on the 20 review traces and
score it against the strict gold set.

  python code/llm_judge/pilot_v4.py --send --reps 2     # judge the 20 traces
  python code/llm_judge/pilot_v4.py                     # score what is in out/

v4 differs from v0-v3 in what the judge returns: not just a count, but each
instance with the line it was adopted on and the line it was abandoned on, each
with a verbatim quote. The count we use is the number of instances whose quotes
are found in the trace near the lines claimed -- the judge's own <count> is
recorded but not trusted (v3 showed it drifting from its own list).

Input traces are for_RA_review/review_traces/traces/*.txt (exactly the CoT the
earlier judges saw), prefixed with line numbers so instances can be located and
matched to gold. Blank lines are skipped but keep their numbers.

Gold: gold_strict.json (now in data/archive/llm_judge_superseded/), strict instances
(firm / borderline) adjudicated by Claude
reviewers on these 20 traces, 2026-09-24. NOT yet checked by the RA.
"""
import argparse
import glob
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
# The 20 review traces and their index (file, model, task, sample) are what the v6 run,
# its RA pack and gold_soft/ are scored on. The strict key and the v4 prompt were
# superseded and live in the archive; they are only read by this module's own pilot.
TRACES = os.path.join(HERE, "for_RA_review", "review_traces", "traces")
VERDICTS = os.path.join(HERE, "for_RA_review", "review_traces", "index.csv")
ARCHIVE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "data", "archive", "llm_judge_superseded")
GOLD = os.path.join(ARCHIVE, "gold_strict.json")
PROMPT = os.path.join(ARCHIVE, "prompts", "backtracking_v4.txt")
OUT = os.path.join(HERE, "out", "pilot_v4.jsonl")

JUDGE_MODEL = "google/gemini-2.5-flash"   # same judge as v0-v3
TEMPERATURE = 0
MAX_OUT = 12000
URL = "https://openrouter.ai/api/v1/chat/completions"
QUOTE_SLACK = 3      # a quote may sit this many lines from the line claimed
MATCH_SLACK = 5      # judge abandon_line may sit this far outside a gold span

INST_RE = re.compile(r"<instance>(.*?)</instance>", re.S)
COUNT_RE = re.compile(r"<count>\s*(\d+)\s*</count>", re.I)


def number_lines(text):
    lines = text.split("\n")
    return lines, "\n".join(f"L{i}: {l}" for i, l in enumerate(lines, 1) if l.strip())


def norm(s):
    s = s.lower().replace("\\", "").replace("$", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def find_quote(lines, q, near):
    """Line number where quote q occurs, nearest to `near`; None if absent. A short
    quote ("So not.") is accepted only within QUOTE_SLACK of the line claimed, since
    it recurs throughout a trace; a longer one anywhere (the judge sometimes garbles
    line numbers, e.g. 173220 for 173, while quoting correctly)."""
    nq = norm(q)
    if not nq:
        return None
    hits = [i for i, l in enumerate(lines, 1) if nq in norm(l)]
    if near is not None and len(nq) < 12:
        hits = [i for i in hits if abs(i - near) <= QUOTE_SLACK]
    if not hits:
        return None
    return min(hits, key=lambda i: abs(i - near) if near is not None else 0)


def field(block, name):
    m = re.search(rf"^\s*{name}:\s*(.+?)\s*$", block, re.M)
    return m.group(1).strip().strip('"').strip("“”") if m else None


def parse(raw, lines):
    out = []
    for b in INST_RE.findall(raw or ""):
        d = {k: field(b, k) for k in ("approach", "adopt_line", "adopt_quote",
                                      "abandon_line", "abandon_quote", "switched_to")}
        for k in ("adopt", "abandon"):
            # Take the FIRST integer. Judges sometimes write the line's text into the
            # line field ("L29: Let me guess ... radius 9?"); use it as the quote then.
            v = d[f"{k}_line"] or ""
            m = re.match(r"\s*L?(\d+)\s*[:.\-]?\s*(.*)", v)
            d[f"{k}_line"] = int(m.group(1)) if m else None
            if m and not d[f"{k}_quote"] and len(m.group(2)) > 8:
                d[f"{k}_quote"] = m.group(2)[:200]
        # a quote is verified if it appears within QUOTE_SLACK lines of its claim
        for k in ("adopt", "abandon"):
            at = find_quote(lines, d[f"{k}_quote"] or "", d[f"{k}_line"])
            d[f"{k}_found"] = at
            d[f"{k}_ok"] = at is not None and d[f"{k}_line"] is not None \
                and abs(at - d[f"{k}_line"]) <= QUOTE_SLACK
        # The abandonment quote is what must exist: it proves the event is on the page.
        # The adoption quote is often paraphrased; it is recorded, not required.
        d["verified"] = d["abandon_found"] is not None
        out.append(d)
    return out


def traces():
    for p in sorted(glob.glob(os.path.join(TRACES, "*.txt"))):
        yield os.path.basename(p)[:2], p


def call(key, content):
    body = json.dumps({"model": JUDGE_MODEL, "temperature": TEMPERATURE,
                       "max_tokens": MAX_OUT,
                       "messages": [{"role": "user", "content": content}]}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL, body, {"Authorization": f"Bearer {key}",
                                                     "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.load(r)
            return {"raw": d["choices"][0]["message"]["content"] or "",
                    "in_tok": d["usage"]["prompt_tokens"],
                    "out_tok": d["usage"]["completion_tokens"]}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            time.sleep(5 * (attempt + 1))
    return {"error": err}


def send(reps, workers):
    key = os.environ.get("ERA_OPENROUTER_V2") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("no OpenRouter key (ERA_OPENROUTER_V2 / OPENROUTER_API_KEY)")
    tmpl = open(PROMPT).read()
    done = set()
    if os.path.exists(OUT):
        done = {(d["trace"], d["rep"]) for d in map(json.loads, open(OUT))}
    jobs = [(t, p, r) for t, p in traces() for r in range(reps) if (t, r) not in done]
    print(f"sending {len(jobs)} calls to {JUDGE_MODEL}")

    def one(job):
        t, p, r = job
        _, numbered = number_lines(open(p).read())
        rec = {"trace": t, "rep": r, "file": os.path.basename(p), "judge_model": JUDGE_MODEL,
               "prompt_version": "v4", "temperature": TEMPERATURE}
        rec.update(call(key, tmpl.replace("{response}", numbered)))
        return rec

    with open(OUT, "a") as fh, ThreadPoolExecutor(workers) as ex:
        for rec in ex.map(one, jobs):
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"  {rec['trace']} rep{rec['rep']}  "
                  f"{'ERROR ' + rec['error'] if 'error' in rec else 'ok'}", flush=True)


def match(inst, gold):
    """One-to-one: each judge instance to the nearest-anchor gold instance one of whose
    episode spans contains its abandon_line (with slack). Returns {judge index: gold id}."""
    cand = []
    for i, d in enumerate(inst):
        a = d["abandon_found"] or d["abandon_line"]
        if a is None:
            continue
        for g in gold:
            if any(s - MATCH_SLACK <= a <= e + MATCH_SLACK for s, e in g["spans"]):
                cand.append((min(abs(a - x) for x in g["anchors"]), i, g["id"]))
    m, used = {}, set()
    for _, i, gid in sorted(cand):
        if i not in m and gid not in used:
            m[i] = gid; used.add(gid)
    return m, {i: gid for _, i, gid in sorted(cand) if i not in m}


def score():
    gold_all = json.load(open(GOLD))["instances"]
    model_of = {}
    for row in open(VERDICTS).read().splitlines()[1:]:
        f = row.split(",")
        model_of[f[0][:2]] = (f[1], int(f[6]))          # model, v3 count
    recs = [json.loads(l) for l in open(OUT)]
    reps = sorted({r["rep"] for r in recs})
    tr = sorted({r["trace"] for r in recs})
    unmatched = []
    tot = {"listed": 0, "verified": 0, "tp_any": 0, "fp": 0}
    rows = {}
    for r in recs:
        lines = open(os.path.join(TRACES, r["file"])).read().split("\n")
        inst = parse(r.get("raw"), lines)
        ver = [d for d in inst if d["verified"]]
        gold = [g for g in gold_all if g["trace"] == r["trace"]]
        m, dup = match(ver, gold)
        firm = [g["id"] for g in gold if g["tier"] == "firm"]
        c = COUNT_RE.search(r.get("raw") or "")
        rows[(r["trace"], r["rep"])] = {
            "judge_count": int(c.group(1)) if c else None, "listed": len(inst),
            "verified": len(ver), "tp": len(m),
            "tp_firm": sum(m[i] in firm for i in m), "firm": len(firm), "gold": len(gold),
            "error": r.get("error"), "dups": len(dup),
            "hit_ids": set(m.values()), "nlines": len(lines)}
        tot["listed"] += len(inst); tot["verified"] += len(ver); tot["tp_any"] += len(m)
        for i, d in enumerate(ver):
            if i not in m:
                tot["fp"] += 1
                unmatched.append({"trace": r["trace"], "rep": r["rep"], "dup_of": dup.get(i),
                                  "abandon_found": d["abandon_found"], **{k: d[k] for k in (
                    "approach", "adopt_line", "abandon_line", "abandon_quote", "switched_to")}})
        for d in inst:
            if not d["verified"]:
                unmatched.append({"trace": r["trace"], "rep": r["rep"], "UNVERIFIED": True,
                                  **{k: d[k] for k in ("approach", "adopt_line", "adopt_quote",
                                                       "adopt_found", "abandon_line",
                                                       "abandon_quote", "abandon_found")}})

    print(f"{'tr':3} {'model':13} {'v3':>3} {'firm':>4} {'gold':>4} | "
          + " | ".join(f"rep{k}: cnt lst ver TP TPf" for k in reps))
    for t in tr:
        mdl, v3 = model_of.get(t, ("?", -1))
        g = rows[(t, reps[0])]
        cells = []
        for k in reps:
            x = rows.get((t, k))
            cells.append("ERR" if not x or x["error"] else
                         f"{x['judge_count'] if x['judge_count'] is not None else '-':>8} "
                         f"{x['listed']:>3} {x['verified']:>3} {x['tp']:>2} {x['tp_firm']:>3}")
        print(f"{t:3} {mdl:13} {v3:>3} {g['firm']:>4} {g['gold']:>4} | " + " | ".join(cells))

    nf = sum(1 for g in gold_all if g["tier"] == "firm")
    for k in reps:
        R = [rows[(t, k)] for t in tr if (t, k) in rows]
        ver = sum(x["verified"] for x in R); tp = sum(x["tp"] for x in R)
        tpf = sum(x["tp_firm"] for x in R); lst = sum(x["listed"] for x in R)
        dups = sum(x["dups"] for x in R)
        # recall by where the gold instance sits in the trace (first anchor / length)
        pos = {"first third": [0, 0], "middle third": [0, 0], "last third": [0, 0]}
        for g in gold_all:
            x = rows.get((g["trace"], k))
            if not x or g["tier"] != "firm":
                continue
            f = g["anchors"][0] / x["nlines"]
            b = pos["first third" if f < 1/3 else "middle third" if f < 2/3 else "last third"]
            b[1] += 1; b[0] += g["id"] in x["hit_ids"]
        print(f"\nrep{k}: listed {lst}, quotes verified {ver} ({ver/max(lst,1):.0%}); "
              f"matched gold {tp} -> precision {tp/max(ver,1):.0%} (vs gold, before review "
              f"of unmatched); recall firm {tpf}/{nf} = {tpf/max(nf,1):.0%}, "
              f"recall firm+borderline {tp}/{len(gold_all)} = {tp/max(len(gold_all),1):.0%}; "
              f"{dups} verified instances duplicate an already-matched gold instance")
        print("   firm recall by position: " + ", ".join(
            f"{p} {a}/{b}" for p, (a, b) in pos.items()))
        by = {}
        for t in tr:
            mdl = model_of.get(t, ("?",))[0]
            b = by.setdefault(mdl, [0, 0, 0])
            b[0] += rows[(t, k)]["verified"]; b[2] += rows[(t, k)]["firm"]
            b[1] += sum(1 for g in gold_all if g["trace"] == t)
        print("   per model (v4 verified / gold firm+bl / gold firm): "
              + ", ".join(f"{m} {v[0]}/{v[1]}/{v[2]}" for m, v in sorted(by.items())))
    if len(reps) > 1:
        a = [rows[(t, reps[0])]["verified"] for t in tr]
        b = [rows[(t, reps[1])]["verified"] for t in tr]
        print(f"\nrepeatability rep0 vs rep1: identical {sum(x == y for x, y in zip(a, b))}"
              f"/{len(tr)}, totals {sum(a)} vs {sum(b)}")
    path = os.path.join(HERE, "out", "pilot_v4_unmatched.json")
    json.dump(unmatched, open(path, "w"), indent=1)
    print(f"\n{len(unmatched)} unmatched/unverified judge instances -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="REQUIRED to contact OpenRouter")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if a.send:
        send(a.reps, a.workers)
    score()
