# Backtracking v6 — review pack

Same 20 traces as the v3 pack. Each sheet links to the trace in `../v3_backtracking/traces/`,
and every line reference opens GitHub with those lines highlighted.

## What we are measuring

The paper counts **abandoned approaches**: places where the writer

> tries an approach and gives it up to do something different.

This definition is deliberately softer than the one used for `gold_strict.json`. The writer
does not have to commit to the approach or say that it failed. An approach can be a method, a
construction, a formula, a guessed answer or candidate value, or an interpretation of the
problem, and it can be tried briefly.

If the writer comes back to the same approach later, or continues it after a pause, that is
**one** entry, not several.

**Do not count:**
- **Verification.** Re-checking or re-deriving a step that was already done, then keeping it.
- **Required cases.** Ruling out a case the solution has to rule out, such as case 1 of a case
  split the argument needs.
- **Error fixes.** Fixing an arithmetic or algebra slip and carrying on with the same method.
  If the slip makes the writer drop the method for a different one, the dropped method does
  count.
- Restating the problem, planning aloud, or summarising.

## Why you are checking this

v6 is an LLM judge (Gemini 3.1 Pro). To show in the paper that it counts correctly, we need a
hand count to compare it against. Two annotators (Claude models) counted each trace
independently, without seeing the judge's output. Their merged lists are the **key**. The
key has not been checked by a person yet, and that is the first thing we need from you.

Coverage is uneven, because an automated filter stopped some annotators partway through:

- **Both annotators:** 01, 05, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17
- **One annotator only:** 02, 03, 06, 15, 18, 19, 20. These need extra care.
- **No annotator:** 04. Please count this one from scratch.

## What to do

### Part 1 — check the key, trace by trace

Do all of Part 1 before looking at any Part 2 section, so the judge's list doesn't influence
you.

For each entry `K1, K2, ...` on a sheet, open the lines, decide, and fill `RA_verdict` in
`key_verdicts.csv` with one of:

| verdict | meaning |
|---|---|
| `yes` | a real abandoned approach, and a separate one |
| `no-verification` / `no-required-case` / `no-error-fix` / `no-other` | not an abandoned approach (say why in `RA_note` for `no-other`) |
| `same-as-Kn` | the same approach as entry Kn, so it should be merged into it |
| `two` | this entry is really two separate approaches |

Then **add anything the annotators missed** as new rows: use `RA1, RA2, ...` in the `entry`
column and give the lines and a short name.

Each sheet has a collapsed list of places the annotators considered and decided *not* to
count, with their reason. It's there to show where they drew the line. If you disagree with
one, add it as a new row.

**Brief ideas.** Entries marked `borderline` are thin. Usually the idea is raised in a line or
two and set aside with no work done ("Could use coordinates? Maybe not needed."). Please judge
them by the same rule as everything else, and add a note if you think this kind should or
should not count in general. We have not decided yet, and your view will help.

### Part 2 — check the judge

For each judge entry `J1, J2, ...`, the sheet shows which key entry it was matched to by line
position, or `none`. Fill `RA_verdict` in `v6_verdicts.csv`:

| verdict | meaning |
|---|---|
| `yes` | a real abandoned approach that the judge listed once |
| `repeat-of-Jn` | the same approach as another judge entry, so the judge listed it twice |
| `no-verification` / `no-required-case` / `no-error-fix` / `no-other` | not an abandoned approach |

We most want to know two things about the judge: **how often it lists one approach more than
once**, and **how often it lists things that are not abandoned approaches**, verifications
above all.

The automatic match is by line position only, so it can be wrong. Something marked
"a second entry for it" may be a genuinely different idea that sits inside a long episode.
Judge by reading the trace, not from the match column.

## Files

- `NN_*.md` — one sheet per trace: the problem, Part 1, Part 2
- `key_verdicts.csv` — your verdicts on the key (Part 1)
- `v6_verdicts.csv` — your verdicts on the judge (Part 2)
- `../../gold_soft/` — the annotators' raw files and the scoring scripts
- `../../backtracking_v6.txt` — the exact prompt the judge was given
