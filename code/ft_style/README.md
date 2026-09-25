# `code/ft_style/` — the MIT FutureTech house style, vendored

Verbatim copy of the `futuretech-charts` skill's python module, taken from skill
commit **bd72541** on 2026-09-25.

## Why it is in the repo

The figure scripts used to import this from `~/.claude/skills/futuretech-charts/python`,
which is outside the repository. Two problems with that, both of which matter for a
paper:

1. **It is not there on anyone else's machine.** Every figure script raised
   `ModuleNotFoundError` on a fresh clone until a local reconstruction was added as a
   fallback — and a reconstruction is not the house style, it is an approximation of it.
2. **It could change under the paper.** A skill update would silently restyle every
   committed figure, with nothing in the repo's history recording why.

Vendoring pins the style to the repo, so a clone reproduces the figures exactly.

## How the scripts find it

Each figure script puts this directory on `sys.path` and imports
`futuretech_helpers` / `futuretech_palette` from it. `code/_ft_style_local.py`
remains as a last-resort fallback if this directory is ever missing; it reports
`STYLE_SRC = LOCAL RECONSTRUCTION` so an approximated figure is never mistaken for
the real thing.

## Refreshing it

Only deliberately, and never mid-paper:

```bash
cp ~/.claude/skills/futuretech-charts/python/futuretech_{helpers.py,palette.py} \
   ~/.claude/skills/futuretech-charts/python/futuretech.mplstyle code/ft_style/
bash scripts/make_paper_figs.sh        # then check the verification anchors
```

Record the new skill commit above, and expect every figure to change.
