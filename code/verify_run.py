#!/usr/bin/env python3
"""Verify a completed sweep file against what the run claimed to do.

OpenRouter silently substitutes providers, remaps effort levels, serves a
different snapshot than the slug asked for, and lets providers ignore or
under-cut max_tokens. None of that raises an error -- the run completes and the
numbers look plausible. This checks the things that fail silently:

  zero-token trials   a failed request stored as a wrong answer (see README)
  reasoning on        hybrid models return 0 reasoning tokens if the toggle
                      did not take; the trace-length study is meaningless then
  cap respected       over-cap needs censoring; under-cap means the provider
                      imposed a lower ceiling and the model is not comparable
  pin held            every attempt served by the pinned provider
  snapshot stable     one resolved model id across the whole run
  effort as sent      runconfig agrees with what went on the wire

Usage:  verify_run.py code/results/<slug>_shallow_pass/<slug>_<tag>.json [--cap N]
        verify_run.py --all [--cap N]
"""
import argparse, glob, json, os, sys
from collections import Counter


def verify(path, cap):
    rows = json.load(open(path))
    name = os.path.basename(path)
    runcfg = path.replace(".json", "_runconfig.json")
    cfg = json.load(open(runcfg)) if os.path.exists(runcfg) else None

    tok = [v for r in rows for v in r.get("total_completion_tokens", [])]
    # The results schema calls this thinking_tokens (reasoning_tokens is the
    # per-attempt field inside one_request, not what lands in the file).
    rsn = [v for r in rows for v in r.get("thinking_tokens", [])] if any(
        "thinking_tokens" in r for r in rows) else []
    provs = Counter(p for r in rows for p in (r.get("providers_used") or []) if p)
    served = Counter(m for r in rows for m in (r.get("models_served") or []) if m)
    finish = Counter(f for r in rows for f in (r.get("finish_reasons") or []) if f)
    sent = Counter(json.dumps(s, sort_keys=True)
                   for r in rows for s in (r.get("reasoning_sent") or []) if s)
    errs = [e for r in rows for e in (r.get("errors") or []) if e]

    zeros = sum(1 for v in tok if v == 0)
    over = sum(1 for v in tok if v > cap)
    nonzero = [v for v in tok if v > 0]
    fails = []

    print(f"\n=== {name} ===")
    print(f"  tasks {len(rows)}   trials {len(tok)}   errors {len(errs)}")
    if cfg:
        print(f"  runconfig: reasoning_sent={cfg.get('reasoning_sent')} "
              f"cap={cfg.get('cap_applied')} n_problems={cfg.get('n_problems')} "
              f"key_env={cfg.get('key_env')}")
        if cfg.get("n_problems") != len(rows):
            fails.append(f"runconfig says {cfg['n_problems']} problems, file has {len(rows)}")
        if cfg.get("cap_applied") != cap:
            print(f"  NOTE: runconfig cap {cfg.get('cap_applied')} != --cap {cap}")
    else:
        fails.append("no _runconfig.json beside this file")

    print(f"  zero-token trials: {zeros}")
    if zeros:
        fails.append(f"{zeros} zero-token trials (failed requests graded as wrong)")

    # Empty content is the failure this gate originally missed. A model whose
    # <think> block is never closed has ALL its output labelled reasoning and
    # returns content="" -- no error, no zero-token trial, reasoning tokens
    # present, cap respected, and every trial graded wrong. Check it explicitly.
    texts = [t for r in rows for t in (r.get("response_texts") or [])]
    if texts:
        blank = sum(1 for t in texts if not (t or "").strip())
        print(f"  empty answer content: {blank} of {len(texts)} trials")
        if blank:
            fails.append(f"{blank} trials returned no answer content -- see "
                         f"recover_trace_answers.py (answer may be inside the trace)")

    if rsn:
        zr = sum(1 for v in rsn if v == 0)
        print(f"  reasoning tokens: {zr} of {len(rsn)} trials are zero"
              f"   median {sorted(v for v in rsn if v > 0)[len(nonzero)//2] if any(rsn) else 0:,}")
        if zr:
            fails.append(f"{zr} trials with 0 reasoning tokens -- reasoning may be off")
    else:
        print("  reasoning tokens: FIELD ABSENT")
        fails.append("no reasoning_tokens recorded")

    if nonzero:
        mx = max(nonzero)
        at_cap = sum(1 for v in nonzero if v >= cap)
        print(f"  output tokens: max {mx:,}  at/over cap {at_cap}  over cap {over}")
        if over:
            fails.append(f"{over} trials over the {cap:,} cap -- needs censor_over_cap.py")
        # A provider that caps BELOW the request pins a suspicious share of trials
        # at its own ceiling; that model is not comparable to the rest.
        ceil = Counter(v for v in nonzero if v > cap * 0.2)
        top, n = ceil.most_common(1)[0] if ceil else (0, 0)
        if n >= max(3, 0.1 * len(nonzero)) and top < cap * 0.95:
            fails.append(f"{n} trials pinned at exactly {top:,} (< cap) -- provider ceiling")

    print(f"  providers: {dict(provs)}")
    if len(provs) > 1:
        fails.append(f"more than one provider served this run: {dict(provs)}")
    print(f"  models served: {dict(served)}")
    if len(served) > 1:
        fails.append(f"snapshot drifted mid-run: {dict(served)}")
    print(f"  finish reasons: {dict(finish)}")
    print(f"  reasoning_sent on the wire: {[json.loads(k) for k in sent]}")
    if len(sent) > 1:
        fails.append(f"inconsistent reasoning payloads: {[json.loads(k) for k in sent]}")
    if cfg and sent:
        want = json.dumps(cfg.get("reasoning_sent"), sort_keys=True)
        if want not in sent:
            fails.append(f"runconfig says {cfg.get('reasoning_sent')} but wire shows "
                         f"{[json.loads(k) for k in sent]}")

    print("  PASS" if not fails else "  FAIL")
    for f in fails:
        print(f"    - {f}")
    return not fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--all", action="store_true", help="every results file under code/results/")
    ap.add_argument("--cap", type=int, default=40000)
    a = ap.parse_args()
    paths = a.paths
    if a.all:
        paths = sorted(p for p in glob.glob("code/results/*_shallow_pass/*.json")
                       if not p.endswith(("_runconfig.json", "_reasoning_traces.json")))
    if not paths:
        sys.exit("nothing to verify")
    ok = all(verify(p, a.cap) for p in paths)
    print(f"\n{'ALL PASS' if ok else 'FAILURES ABOVE'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
