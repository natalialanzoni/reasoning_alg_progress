"""Thinking-only robustness table (tab:thinking) -- is the decline just shorter ANSWERS?

Motivation. The headline DV is L = thinking + answer, and two things happen in the
answer that have nothing to do with reasoning:

  * gpt-5.1 writes 3.1x longer answers than gpt-5 while its thinking is FLAT
    (7,798 vs 7,829 tokens), which reads as an efficiency regression on L.
  * the whole series switches output format at gpt-5.1, from plain-text math to LaTeX
    display blocks. LaTeX control sequences go from ~0.3-2% of answer characters
    (o1, o3, gpt-5) to ~20-25% for every model after. That inflates L for the RECENT
    models, i.e. against the paper's own claim.

Refitting on thinking tokens alone retires both objections at once, since neither
touches the reasoning block.

SPEC. Thinking-only takes NO floor:

    log(thinking_ijt) = alpha_j + beta * Month_i + eps        (problem FE)

The floor is the shortest human-written derivation -- exposition, the analogue of the
model's ANSWER, not of its hidden scratch work -- so subtracting it from thinking is
not meaningful. It is also unusable empirically: log(thinking - MHD_j) would censor
38.4% of gpt-6-astra's traces and 26.2% of Fable 5.1's, the same defect that
disqualified MATH-500 as a contamination panel.

ONE CAVEAT, and it runs in the safe direction. log(thinking) is undefined for a
zero-thinking trace, so those necessarily drop out: N falls 1,815 -> 1,734 for
Anthropic, and all 81 of them are Fable 5.1 -- the NEWEST model, answering correctly
with no thinking block on a quarter of problems, which are its SHORTEST traces.
Removing the newest model's shortest traces understates the decline, so the
thinking-only rate reported here is conservative.

So the table reports THREE specs per family. log(L) is the one to compare thinking
against: it holds functional form fixed and varies only the DV. The headline excess
spec is included for reference, but its rate is not directly comparable to the other
two because subtracting the floor steepens the implied decay.

    ./venv/bin/python code/table_thinking_only.py            # print
    ./venv/bin/python code/table_thinking_only.py OUT.tex    # and write LaTeX
"""
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("td", os.path.join(HERE, "table_decay.py"))
# table_decay runs its own report at import; silence it, we only want fit/rows_for.
_stdout = sys.stdout
sys.stdout = open(os.devnull, "w")
td = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(td)
sys.stdout.close(); sys.stdout = _stdout

SPECS = [("logthink", r"$\log(\text{thinking})$", "thinking only  (NO floor)"),
         ("logL",     r"$\log L$",                "L = think+answer, no floor"),
         ("excess",   r"$\log(L - \mathrm{MHD}_j)$", "headline excess spec")]

res = {}
for fam, mf in td.FAMILIES:
    for dv, _, _ in SPECS:
        res[(fam, dv)] = td.fit(td.rows_for(mf, dv=dv))

print(f"{'family':<26s} {'spec':<28s} {'beta':>9s} {'SE':>7s} {'%/qtr':>7s} "
      f"{'half-life':>10s} {'WCR p':>7s} {'N':>6s}")
for fam, _ in td.FAMILIES:
    for dv, _, desc in SPECS:
        r = res[(fam, dv)]
        print(f"  {fam:<24s} {desc:<28s} {r['b']:>+9.4f} {r['se']:>7.4f} "
              f"{r['q']:>6.1f}% {r['hl']:>10.1f} {r['p']:>7.4f}{r['star']:<3s} {r['n']:>6d}")

# the headline comparison, stated once
# zero-thinking traces cannot enter log(thinking); report how many and from where
print("\n  Zero-thinking traces dropped by log(thinking) (they are the NEWEST model's")
print("  shortest, so their loss makes the thinking-only rate conservative):")
for fam, mf in td.FAMILIES:
    n_l = len(td.rows_for(mf, dv="logL")); n_t = len(td.rows_for(mf, dv="logthink"))
    print(f"    {fam:<26s} {n_l - n_t:>4d} of {n_l}")

print("\n  Holding functional form fixed (no floor in either), thinking vs L:")
for fam, _ in td.FAMILIES:
    a, b = res[(fam, "logthink")], res[(fam, "logL")]
    print(f"    {fam:<26s} thinking {a['q']:.1f}%/qtr  vs  L {b['q']:.1f}%/qtr "
          f"({a['q'] - b['q']:+.1f}pp)")

tex = [r"\begin{tabular}{llccccc}", r"\toprule",
       r"Family & Dependent variable & $\beta$ & (SE) & \%/quarter & Half-life & $N$ \\",
       r"\midrule"]
for fi, (fam, _) in enumerate(td.FAMILIES):
    for si, (dv, lbl, _) in enumerate(SPECS):
        r = res[(fam, dv)]
        name = fam if si == 0 else ""
        tex.append(f"{name} & {lbl} & ${r['b']:.3f}^{{{r['star']}}}$ & $({r['se']:.3f})$ & "
                   f"${r['q']:.1f}\\%$ & ${r['hl']:.1f}$ & "
                   f"${r['n']:,}$".replace(",", "{,}") + r" \\")
    if fi == 0:
        tex.append(r"\addlinespace")
tex += [r"\bottomrule", r"\end{tabular}"]
tex = "\n".join(tex)
print("\n% ---------------- tab:thinking ----------------\n" + tex)
if len(sys.argv) > 1:
    with open(sys.argv[1], "w") as fh:
        fh.write(tex + "\n")
    print(f"\nwrote {sys.argv[1]}")
