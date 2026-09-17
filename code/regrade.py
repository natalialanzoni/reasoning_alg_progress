"""
Robust re-grader for math-answer correctness.

The original benchmark grader (benchmark_math_dist.is_correct) is brittle: it fails
on answer prefixes ("BC=3+\\sqrt{11}"), work shown inside \\boxed{} ("(20+1)(20+1)=441"),
units ("74^\\circ"), leading zeros ("070" vs "70"), tuples, \\frac32 shorthand, and
algebraically-equivalent radical forms ("2\\sqrt{435}/3" == "\\sqrt{580/3}"). Because the
efficient models write terser answers, they are penalised far more than verbose ones
(gpt-6-astra +9.2 pts on re-grade; verbose models ~+0), biasing the accuracy rows.

This module fixes that with: prefix stripping, RHS-of-work extraction, unit removal,
leading-zero-safe integer compare, tuple/point compare, and symbolic equivalence via
sympy parse_latex (antlr backend). It is deliberately CONSERVATIVE about false
positives — an answer is correct only on a genuine string / integer / numeric /
symbolic match.

    from regrade import is_correct, regrade_rows
"""
import re

from sympy import E, N, pi, simplify, sympify
from sympy.parsing.latex import parse_latex

_CONST = {"pi": pi, "e": E}

# reuse the original boxed extractor for re-extraction from raw text when needed
import importlib.util as _ilu
import os as _os
_spec = _ilu.spec_from_file_location("_bmd", _os.path.join(_os.path.dirname(__file__), "benchmark_math_dist.py"))
_bmd = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bmd)
extract_boxed = _bmd.extract_boxed


def _clean(s):
    """Strip formatting cruft, answer-variable prefixes, shown work, and units."""
    if s is None:
        return None
    s = str(s).strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    s = re.sub(r"\\text\{[^{}]*\}", "", s)
    s = re.sub(r"\\(mathrm|mathbf|operatorname)\{[^{}]*\}", "", s)
    # leading "VAR = " prefix, e.g. BC=, x =, \theta =, AB\cdot CD=
    s = re.sub(r"^\s*[A-Za-z\\][A-Za-z0-9_\\\\\\\s\\cdot]{0,12}?\s*=\s*", "", s)
    # if work is shown (expr = answer), keep the final RHS
    if s.count("=") >= 1:
        s = s.split("=")[-1].strip()
    for t in ("^\\circ", "^{\\circ}", "\\circ", "\\degree", "\\left", "\\right",
              "\\!", "\\,", "\\;", "\\:", "\\ "):
        s = s.replace(t, "")           # note: '%' is left in for _to_num to detect
    s = re.sub(r"\\sqrt\s*(\d|[a-zA-Z])", r"\\sqrt{\1}", s)   # \sqrt2 -> \sqrt{2} (parseable)
    s = s.strip().rstrip(".")
    return s or None


def _norm_str(s):
    s = _clean(s)
    if s is None:
        return None
    s = re.sub(r"\s+", "", s).lower()
    for v in ("\\dfrac", "\\tfrac", "\\cfrac"):
        s = s.replace(v, "\\frac")
    s = re.sub(r"\\sqrt(\d)", r"\\sqrt{\1}", s)
    return s


def _to_num(s):
    """Numeric value of a scalar expression via parse_latex(antlr) then sympify.

    Robust to: \\pi / e left as free symbols by the parser, mixed numbers
    (3\\frac{1}{2}), thousands separators (1,574), percent, and \\cdot/\\times."""
    c = _clean(s)
    if c is None:
        return None
    c = re.sub(r"(\d+)\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1+(\2)/(\3))", c)  # mixed number
    c = c.replace("\\cdot", "*").replace("\\times", "*")
    pct = c.endswith("\\%") or c.endswith("%")
    c = c.replace("\\%", "").replace("%", "").replace(",", "")
    for parse in (lambda x: parse_latex(x, backend="antlr"), sympify):
        try:
            expr = parse(c)
            if getattr(expr, "free_symbols", None):
                expr = expr.subs({sym: _CONST[sym.name] for sym in expr.free_symbols
                                  if sym.name in _CONST})
            if getattr(expr, "free_symbols", set()):     # still has unknown symbols -> not numeric
                continue
            v = complex(N(expr))
            if abs(v.imag) < 1e-9:
                return v.real / 100.0 if pct else v.real
        except Exception:
            continue
    return None


def _split_delim(s):
    """Return (kind, parts) where kind is 'set' for \\{..\\}/{..} (unordered) or
    'seq' for (..)/[..] (ordered), else (None, None)."""
    c = _clean(s)
    if c is None or len(c) < 2:
        return None, None
    c = c.replace("\\{", "{").replace("\\}", "}").replace("\\langle", "(").replace("\\rangle", ")")
    kind = "set" if c[0] == "{" and c[-1] == "}" else ("seq" if c[0] in "([" and c[-1] in ")]" else None)
    if kind is None:
        return None, None
    inner, depth, cur, parts = c[1:-1], 0, "", []
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    parts = [p.strip() for p in parts if p.strip() != ""]
    return (kind, parts) if len(parts) >= 2 else (None, None)


def is_correct(extracted, gold):
    """Robust equivalence. Conservative: True only on a genuine match."""
    if extracted is None or gold is None:
        return False
    # tuples/sequences (ordered) and sets (unordered)
    ka, pa = _split_delim(extracted)
    kb, pb = _split_delim(gold)
    if ka is not None and kb is not None and ka == kb and len(pa) == len(pb):
        if ka == "seq":
            return all(is_correct(a, b) for a, b in zip(pa, pb))
        # set: every gold element matched by some extracted element (bijection-ish)
        used = [False] * len(pa)
        for b in pb:
            hit = False
            for i, a in enumerate(pa):
                if not used[i] and is_correct(a, b):
                    used[i] = True; hit = True; break
            if not hit:
                return False
        return True
    # normalized string
    a, b = _norm_str(extracted), _norm_str(gold)
    if a is not None and a == b:
        return True
    # integers (leading-zero safe, e.g. AIME 070 == 70)
    if a is not None and b is not None and re.fullmatch(r"-?\d+", a) and re.fullmatch(r"-?\d+", b):
        return int(a) == int(b)
    # numeric / symbolic equivalence
    na, nb = _to_num(extracted), _to_num(gold)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-6
    return False


def regrade_rows(rows):
    """Re-grade every trial in a list of result rows (in place is avoided; returns new
    correct-lists). Uses extracted_answers when present, else re-extracts from
    response_texts. Returns (per_row_correct, n_correct, n_total, n_flipped)."""
    out, nc, nt, flip = [], 0, 0, 0
    for r in rows:
        gold = r.get("gold_answer")
        n = len(r["correct"])
        ext = r.get("extracted_answers")
        texts = r.get("response_texts")
        new = []
        for i in range(n):
            e = ext[i] if ext else (extract_boxed(texts[i]) if texts else None)
            old = bool(r["correct"][i])
            ok = old or is_correct(e, gold)     # never demote an already-correct trial
            new.append(ok)
            nt += 1; nc += int(ok); flip += int(ok and not old)
        out.append(new)
    return out, nc, nt, flip
