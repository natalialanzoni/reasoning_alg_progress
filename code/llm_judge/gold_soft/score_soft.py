"""Merge the two blind annotations into a soft gold, then score v6 against it.

  python3 score_soft.py [prompt] [judge]      # default v6 google/gemini-3.1-pro-preview
"""
import sys, json, os, glob, random
sys.path.insert(0, '/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress/code/llm_judge')
import pilot as P, pilot_v4 as p

D = os.path.dirname(os.path.abspath(__file__))
PR = sys.argv[1] if len(sys.argv) > 1 else 'v6'
J = sys.argv[2] if len(sys.argv) > 2 else 'google/gemini-3.1-pro-preview'
SL = 5
model_of = {r.split(',')[0][:2]: r.split(',')[1] for r in open(p.VERDICTS).read().splitlines()[1:]}


def load(a):
    out = {}
    for f in glob.glob(os.path.join(D, 'annotations', f'{a}_*.json')):
        try:
            d = json.load(open(f))
        except ValueError:
            print(f'SKIP {os.path.basename(f)}: not valid JSON (write was cut off)'); continue
        out[d['trace']] = d
    return out


def spans(i):
    v = [tuple(x) for x in i.get('visits') or []]
    return v or [(i['abandon_line'], i['abandon_line'])]


def near(a, b):
    """Two instances refer to the same episode: any visit spans overlap (with slack)."""
    return any(s1 - SL <= e2 and s2 - SL <= e1 for s1, e1 in spans(a) for s2, e2 in spans(b))


def pair_up(A, B):
    m, used = {}, set()
    for i, x in enumerate(A):
        for j, y in enumerate(B):
            if j not in used and near(x, y):
                m[i] = j; used.add(j); break
    return m


A1, A2 = load('a1'), load('a2')
both = sorted(set(A1) & set(A2))
traces = sorted(set(A1) | set(A2))
print(f'traces annotated by both: {len(both)}  (a1 only {sorted(set(A1)-set(A2))}, a2 only {sorted(set(A2)-set(A1))})')
EMPTY = {'instances': [], 'rejected': []}

# ---- soft gold: union of both annotators; 'agreed' if both found it
gold = []
for t in traces:
    a, b = A1.get(t, EMPTY)['instances'], A2.get(t, EMPTY)['instances']
    m = pair_up(a, b)
    for i, x in enumerate(a):
        y = b[m[i]] if i in m else None
        vis = sorted(set(spans(x)) | (set(spans(y)) if y else set()))
        gold.append({'trace': t, 'id': f'{t}s{len(gold)}', 'spans': [list(v) for v in vis],
                     'anchors': [x['abandon_line']] + ([y['abandon_line']] if y else []),
                     'agreed': y is not None, 'tiers': [x['tier']] + ([y['tier']] if y else []),
                     'by': ['a1', 'a2'] if y else ['a1'], 'approach': x['approach']})
    for j, y in enumerate(b):
        if j not in m.values():
            gold.append({'trace': t, 'id': f'{t}s{len(gold)}', 'spans': [list(v) for v in spans(y)],
                         'anchors': [y['abandon_line']], 'agreed': False, 'tiers': [y['tier']],
                         'by': ['a2'], 'approach': y['approach']})
json.dump({'note': 'Soft backtracking gold: "tries an approach and gives it up to do something different". '
                   'Two blind Claude annotators; union, agreed=both found it. NOT RA-checked.',
           'instances': gold}, open(os.path.join(D, 'gold_soft.json'), 'w'), indent=1)

# ---- judge
recs = {}
for d in map(json.loads, open(P.out_path(PR, J))):
    recs[d['trace']] = d
rows = []
cats = {}
print(f"\n{'tr':3} {'model':13} a1(f/b) a2(f/b) agree | v6 TP dup unm | unmatched v6 by annotator rejection")
for t in traces:
    r = recs[t]; lines = open(os.path.join(p.TRACES, r['file'])).read().split('\n')
    ver = [d for d in p.parse(r.get('raw'), lines) if d['verified']]
    g = [x for x in gold if x['trace'] == t]
    m, dup = p.match(ver, g)
    rej = A1.get(t, EMPTY).get('rejected', []) + A2.get(t, EMPTY).get('rejected', [])
    un = []
    for i, d in enumerate(ver):
        if i in m or i in dup:
            continue
        a = d['abandon_found']; s = d['adopt_found'] or a
        why = next((x['why_not'].split(':')[0].strip() for x in rej
                    if x['lines'][0] - SL <= a <= x['lines'][-1] + SL), None)
        why = why or 'not flagged'
        cats[why] = cats.get(why, 0) + 1
        un.append((s, a, why, d['approach']))
    cnt = lambda A, tier: sum(x['tier'] == tier for x in A[t]['instances']) if t in A else -1
    ag = sum(x['agreed'] for x in g)
    rows.append({'t': t, 'model': model_of[t], 'both': t in both,
                 'a1': len(A1[t]['instances']) if t in A1 else None, 'a2': len(A2[t]['instances']) if t in A2 else None,
                 'firm': sum(all(tt == 'firm' for tt in x['tiers']) for x in g),
                 'gold': len(g), 'agreed': ag, 'v6': len(ver), 'tp': len(m), 'dup': len(dup),
                 'agreed_hit': sum(x['agreed'] for x in g if x['id'] in m.values()), 'un': un})
    print(f"{t:3} {model_of[t]:13} {cnt(A1,'firm'):3}/{cnt(A1,'borderline'):<3} {cnt(A2,'firm'):3}/{cnt(A2,'borderline'):<3} {ag:5} |"
          f" {len(ver):3} {len(m):3} {len(dup):3} {len(un):3} | " + ', '.join(f'{w}' for *_, w, _ in un))

tot = lambda k: sum(x[k] or 0 for x in rows)
print(f"\nannotators: a1 {tot('a1')}, a2 {tot('a2')}, agreed {tot('agreed')}, union {tot('gold')}")
print(f"v6: {tot('v6')} entries -> {tot('tp')} match gold, {tot('dup')} duplicates of a matched gold, "
      f"{sum(len(x['un']) for x in rows)} match nothing")
print(f"recall: union {tot('tp')}/{tot('gold')} = {tot('tp')/tot('gold'):.0%}; "
      f"agreed-only {tot('agreed_hit')}/{tot('agreed')} = {tot('agreed_hit')/max(1,tot('agreed')):.0%}")
print('unmatched v6 entries by what the annotators said about that spot:', cats)


def spear(a, b): return P.spearman(a, b)


for ref in ('gold', 'agreed', 'firm'):
    print(f"spearman v6 vs {ref:6}: {spear([x['v6'] for x in rows], [x[ref] for x in rows]):.2f}   "
          f"MAE {sum(abs(x['v6']-x[ref]) for x in rows)/len(rows):.1f}")
B2 = [x for x in rows if x['both']]
print(f"on the {len(B2)} double-counted traces:")
for ref in ('a1', 'a2'):
    print(f"  spearman v6 vs {ref}: {spear([x['v6'] for x in B2], [x[ref] for x in B2]):.2f}   "
          f"MAE {sum(abs(x['v6']-x[ref]) for x in B2)/len(B2):.1f}")
print(f"  spearman a1 vs a2: {spear([x['a1'] for x in B2], [x['a2'] for x in B2]):.2f}   "
      f"MAE {sum(abs(x['a1']-x['a2']) for x in B2)/len(B2):.1f}   <- how well two careful annotators agree")

print('\nper model totals (19 traces):  v6 union agreed firm')
for mdl in sorted({x['model'] for x in rows}):
    R = [x for x in rows if x['model'] == mdl]
    print(f"  {mdl:13} " + ' '.join(f"{sum(x[k] for x in R):4}" for k in ('v6', 'gold', 'agreed', 'firm')))
# CAUTION: the union gold gives double-counted traces more instances than single-counted ones, and
# the mix differs by model, so these ratios are confounded. fair.py compares one annotator at a time.
rng = random.Random(0)
for old, new in [('GLM 5.2', 'GLM 5.3'), ('gpt-oss-20b', 'gpt-oss-120b')]:
    A = [x for x in rows if x['model'] == old]; B = [x for x in rows if x['model'] == new]
    rat = lambda A, B, k: sum(x[k] for x in B) / sum(x[k] for x in A) if sum(x[k] for x in A) else float('nan')
    line = f"  {new}/{old}: " + '  '.join(f"{k} {rat(A, B, k):.2f}" for k in ('v6', 'gold', 'agreed', 'firm'))
    bs = []
    for _ in range(4000):
        a = [rng.choice(A) for _ in A]; b = [rng.choice(B) for _ in B]
        x, y = rat(a, b, 'v6'), rat(a, b, 'gold')
        if x == x and y == y and y: bs.append(x / y)
    bs.sort()
    print(line + f"   | v6/gold bias {rat(A,B,'v6')/rat(A,B,'gold'):.2f}  boot90 [{bs[int(.05*len(bs))]:.2f}, {bs[int(.95*len(bs))]:.2f}]")

json.dump(rows, open(os.path.join(D, f'rows_{PR}.json'), 'w'), indent=1, default=list)
