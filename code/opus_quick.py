"""Quick look: Claude Opus 4.5 -> Opus 5 per-problem trace length vs the
canonical floor (medium effort, k=8). Reuses CANON/load_rows from paper_figures."""
import importlib.util, os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import seaborn as sns

sns.set_theme(style="whitegrid")
_s = importlib.util.spec_from_file_location("pf", os.path.join(os.path.dirname(__file__), "paper_figures_71226.py"))
pf = importlib.util.module_from_spec(_s); _s.loader.exec_module(pf)

MODELS = [("Opus 4.5", "data/opus4.5_shallow_pass/claude-opus-4-5_medium_thinking_benchmark_90.json"),
          ("Opus 5",   "data/opus5_shallow_pass/claude-opus-5_medium_thinking_benchmark.json")]

per_model, accs = [], []
for lbl, p in MODELS:
    by_id = {}
    nc = nt = 0
    for r in pf.load_rows(pf.ROOT.parent / p):
        tid = str(r["task_id"])
        tt = r.get("thinking_tokens", [1] * len(r["correct"]))
        toks = [t for t, th in zip(r["total_completion_tokens"], tt) if th > 0]
        if tid in pf.CANON_KEYS and toks:
            by_id[tid] = float(np.mean(toks))
        nc += sum(r["correct"]); nt += len(r["correct"])
    per_model.append(by_id); accs.append(nc / nt)

common = sorted(set(per_model[0]) & set(per_model[1]))
canon = float(np.mean([pf.CANON[t]["mean"] for t in common]))
x = [0, 1]

fig, ax = plt.subplots(figsize=(8, 7))
for tid in common:
    ax.plot(x, [per_model[0][tid], per_model[1][tid]], "-", color="#6A1B9A",
            lw=1.0, alpha=0.25, zorder=2)
macro = [float(np.mean([pm[t] for t in common])) for pm in per_model]
ax.plot(x, macro, "o-", color="#4A148C", lw=3, ms=13, zorder=5, label="Mean across problems")
for xi, mv, a in zip(x, macro, accs):
    ax.annotate(f"{mv:,.0f} tok\nacc {a:.0%}", (xi, mv), textcoords="offset points",
                xytext=(0, 16), ha="center", fontsize=11, fontweight="bold", color="#4A148C")
ax.axhline(canon, color="#FFB300", lw=2.4, zorder=4, label=f"Canonical solution ({canon:.0f} tok)")
ax.axhspan(0, canon, color="#FFB300", alpha=0.06, zorder=0)
ax.text(0.5, 0.6, f"{macro[0]/macro[1]:.1f}x shorter\n(Opus 4.5 -> 5)", transform=ax.transAxes,
        ha="center", fontsize=12, fontweight="bold", color="#4A148C",
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#999", alpha=0.92))

ax.set_xticks(x); ax.set_xticklabels([m for m, _ in MODELS], fontsize=12, fontweight="bold")
ax.set_xlim(-0.3, 1.3); ax.set_ylim(bottom=0)
ax.set_ylabel("Per-problem mean trace length (output tokens)", fontsize=11)
ax.set_title(f"Claude Opus reasoning length falls toward the floor\n"
             f"({len(common)} canonical-key problems, k=8, medium effort)", fontsize=12.5)
prob = mlines.Line2D([], [], color="#6A1B9A", lw=1, alpha=0.6, label=f"Individual problems (n={len(common)})")
h, l = ax.get_legend_handles_labels()
ax.legend([prob] + h, [prob.get_label()] + l, loc="upper right", fontsize=9, framealpha=0.95)
plt.tight_layout()
out = pf.ROOT.parent / "figures" / "fig_opus_quick.png"
fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
print(f"wrote {out}  (Opus4.5 mean={macro[0]:,.0f} -> Opus5 mean={macro[1]:,.0f} tok; "
      f"{macro[0]/macro[1]:.1f}x)")
