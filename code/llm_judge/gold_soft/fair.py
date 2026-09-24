import sys, json, os, random
sys.path.insert(0, '/home/nfl234/reasoning_trace_efficiency/reasoning_alg_progress/code/llm_judge')
import pilot as P, pilot_v4 as p
D=os.path.dirname(os.path.abspath(__file__))
rows={r['t']:r for r in json.load(open(f'{D}/rows_v6.json'))}
gold=json.load(open(f'{D}/gold_soft.json'))['instances']
def fa(a,t):
    try: return json.load(open(f'{D}/annotations/{a}_{t}.json'))
    except Exception: return None
# ---- pair ratios, one annotator at a time, same traces for judge and annotator
rng=random.Random(0)
for ann in ('a1','a2'):
    for tier in ('all','firm'):
        out=[]
        for old,new in [('GLM 5.2','GLM 5.3'),('gpt-oss-20b','gpt-oss-120b')]:
            def S(m):
                T=[t for t,r in rows.items() if r['model']==m and fa(ann,t)]
                g=[sum(tier=='all' or i['tier']=='firm' for i in fa(ann,t)['instances']) for t in T]
                j=[rows[t]['v6'] for t in T]
                return T,g,j
            To,go,jo=S(old); Tn,gn,jn=S(new)
            if not sum(go) or not sum(jo): out.append(f'{new}: n/a'); continue
            out.append(f"{new.split('-')[0][:3]} (n={len(To)}+{len(Tn)}): annot {sum(gn)/len(Tn)/(sum(go)/len(To)):.2f} v6 {sum(jn)/len(Tn)/(sum(jo)/len(To)):.2f}")
        print(f'{ann} {tier:4}: '+'   '.join(out))
# ---- missed agreed instances: firm vs borderline, and whether a v6 span covers them
recs={}
for d in map(json.loads, open(P.out_path('v6','google/gemini-3.1-pro-preview'))): recs[d['trace']]=d
miss={'firm':[0,0],'mixed':[0,0],'borderline':[0,0]}; hitt={'firm':0,'mixed':0,'borderline':0}
for t,r in recs.items():
    g=[x for x in gold if x['trace']==t and x['agreed']]
    if not g: continue
    lines=open(os.path.join(p.TRACES,r['file'])).read().split('\n')
    ver=[d for d in p.parse(r.get('raw'),lines) if d['verified']]
    m,_=p.match(ver,[x for x in gold if x['trace']==t]); hit=set(m.values())
    for x in g:
        k='firm' if all(tt=='firm' for tt in x['tiers']) else ('borderline' if all(tt=='borderline' for tt in x['tiers']) else 'mixed')
        if x['id'] in hit: hitt[k]+=1; continue
        cov=any(any(min(d['adopt_found'] or d['abandon_found'],d['abandon_found'])<=b and a<=max(d['adopt_found'] or 0,d['abandon_found']) for a,b in x['spans']) for d in ver)
        miss[k][0 if cov else 1]+=1
print('\nagreed instances: tier -> matched / missed-but-inside-a-v6-span / missed-outright')
for k in hitt: print(f'  {k:10} {hitt[k]:3} / {miss[k][0]:3} / {miss[k][1]:3}')
