"""Render the judge prompts as block-quote IMAGES for the appendix.

The LaTeX version (make_prompt_appendix.py) does not typeset cleanly -- the prompts
are full of #, {}, <> and markdown that fight with LaTeX even after escaping. This
emits the same text as a picture instead, so the appendix can just do:

    \\includegraphics[width=\\textwidth]{paper_figs/fig_judge_prompt_backtracking.pdf}
    \\includegraphics[width=\\textwidth]{paper_figs/fig_judge_prompt_verification.pdf}

Reads the live templates the paper's runs used (PROMPTS below), so the appendix cannot
drift from what was actually sent to the judge. Verification is Gandhi et al.'s template
with one line changed, marked `[edited]` and set in bold. Backtracking v6 was written for
this paper, so nothing in it is marked and its caption says so.

    ./venv/bin/python code/llm_judge/make_prompt_image.py
Output -> paper_figs/fig_judge_prompt_{backtracking,verification}.{pdf,png}
"""
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "paper_figs")

# behaviour -> (prompt version, judge) of the run behind the paper table
PROMPTS = {"verification": ("v0", "gemini-2.5-flash"),
           "backtracking": ("v6", "gemini-3.1-pro-preview")}

OUR_LINE = ("You will be provided with the reasoning trace of a language model "
            "solving a competition mathematics problem.")

WRAP = 104          # characters per line at 8.5pt mono in an 11in figure
LINE_H = 0.145      # inches per rendered line
PAD_TOP = 0.62      # room for the heading
PAD_BOT = 0.22
BG = "#F6F6F4"      # quote background
BAR = "#8A8A8A"     # left quote rule
INK = "#1A1A1A"


def wrapped_lines(behaviour):
    """The prompt as display lines, each tagged with whether it is our edit."""
    raw = open(os.path.join(HERE, f"{behaviour}_{PROMPTS[behaviour][0]}.txt")).read().rstrip()
    out = []
    for line in raw.splitlines():
        if not line.strip():
            out.append(("", False, False))
            continue
        edited = line.strip() == OUR_LINE
        chunks = textwrap.wrap(line, WRAP) or [""]
        for i, ch in enumerate(chunks):
            # continuation lines get a hanging indent so wrapping is visibly wrapping.
            # `edited` marks only the FIRST chunk -- it is a one-per-line annotation,
            # not a property of every wrapped fragment.
            out.append((ch if i == 0 else "    " + ch, edited, edited and i == 0))
    return out


def render(behaviour):
    lines = wrapped_lines(behaviour)
    h = PAD_TOP + PAD_BOT + LINE_H * (len(lines) + 1)
    fig = plt.figure(figsize=(11, h))
    fig.patch.set_facecolor("white")

    # quote block: soft background panel with a rule down the left edge
    x0, x1 = 0.035, 0.995
    y0, y1 = PAD_BOT / h, 1 - (PAD_TOP - 0.18) / h
    fig.patches.append(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0, transform=fig.transFigure,
        boxstyle="round,pad=0.004,rounding_size=0.006",
        fc=BG, ec="#E2E2DE", lw=1.0, zorder=0))
    fig.patches.append(plt.Rectangle(
        (x0, y0), 0.004, y1 - y0, transform=fig.transFigure,
        fc=BAR, ec="none", zorder=1))

    fig.text(x0, 1 - 0.30 / h, behaviour.capitalize(),
             fontsize=13, fontweight="bold", color=INK, va="bottom")
    fig.text(x1, 1 - 0.30 / h,
             f"code/llm_judge/{behaviour}_{PROMPTS[behaviour][0]}.txt   ·   {PROMPTS[behaviour][1]}, "
             f"temperature 0" + ("   ·   written for this paper" if PROMPTS[behaviour][0] != "v0" else ""),
             fontsize=8, color="#777777", va="bottom", ha="right")

    y = y1 - LINE_H / h * 0.9
    for text, edited, mark in lines:
        if text:
            fig.text(x0 + 0.016, y, ("[edited]  " + text) if mark else text,
                     fontsize=8.5, family="monospace", color=INK, va="top",
                     fontweight="bold" if edited else "normal")
        y -= LINE_H / h

    os.makedirs(OUT, exist_ok=True)
    stem = os.path.join(OUT, f"fig_judge_prompt_{behaviour}")
    for ext in ("pdf", "png"):
        fig.savefig(f"{stem}.{ext}", dpi=200, facecolor="white",
                    bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    print(f"  wrote {stem}.pdf / .png   ({len(lines)} lines, {h:.1f} in tall)")


if __name__ == "__main__":
    for b in (sys.argv[1:] or ["backtracking", "verification"]):
        render(b)
