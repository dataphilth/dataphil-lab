"""Independent recomputation of every published figure. Deliberately does NOT import
reproduce.py -- a check that shares code with the thing it checks is not a check."""
import numpy as np, pandas as pd, math

d = pd.read_csv('data/shadow_log.csv', parse_dates=['date_placed'])
d['e'] = d.edge_pct/100 if d.edge_pct.abs().max() > 1.5 else d.edge_pct
s = d[d.result.isin(['win','loss'])].copy()
s['y'] = (s.result == 'win').astype(int)

FAIL = []
def check(label, got, want, tol):
    ok = abs(got-want) <= tol
    if not ok: FAIL.append(label)
    print(f"{'PASS' if ok else 'FAIL':4}  {label:44s} got {got:>10.4f}   published {want}")

# counts
check("rows logged",        len(d), 11950, 0)
check("settled",            len(s), 10928, 0)
check("void",               (d.result=='void').sum(), 877, 0)
check("open",               len(d)-len(s)-(d.result=='void').sum(), 145, 0)
check("H_over_0.5 legs",    (s.prop_type=='H_over_0.5').sum(), 10821, 0)

# aggregate
check("aggregate predicted", s.p_model.mean(), 0.623, 0.0005)
check("aggregate observed",  s.y.mean(),       0.596, 0.0005)
check("brier model",         ((s.p_model-s.y)**2).mean(), 0.2392, 0.0001)
m = s[s.p_market_devig.between(0.01,0.99)]
check("brier market",        ((m.p_market_devig-m.y)**2).mean(), 0.2371, 0.0001)

# deciles -- rank manually rather than qcut
s = s.sort_values(['e','date_placed']).reset_index(drop=True)
s['dec'] = (np.arange(len(s)) * 10 // len(s)) + 1
def flat_roi(g):
    o = g.american_odds_at_bet.to_numpy(float)
    prof = np.where(o>0, o/100, 100/-o)
    return np.where(g.y==1, prof, -1.0)
for dnum, pred, obs, roiv in [(1,.568,.608,-7.9),(3,.610,.617,-5.9),(5,.626,.615,-4.8),
                              (7,.638,.606,-4.3),(9,.645,.590,-3.7),(10,.647,.540,-3.9)]:
    g = s[s.dec==dnum]
    check(f"decile {dnum} predicted", g.p_model.mean(), pred, 0.0015)
    check(f"decile {dnum} observed",  g.y.mean(),       obs,  0.0015)
    check(f"decile {dnum} roi",       flat_roi(g).mean()*100, roiv, 0.25)
g10, g1 = s[s.dec==10], s[s.dec==1]
check("decile-10 pred-obs gap (pts)", (g10.p_model.mean()-g10.y.mean())*100, 10.7, 0.15)

# gate cohort
gate = s[(s.date_placed>='2026-06-16') & (s.e>=0.05)]
p = flat_roi(gate)
check("gate n",   len(gate), 2749, 0)
check("gate roi", p.mean()*100, -3.69, 0.02)
check("gate se",  p.std(ddof=1)/math.sqrt(len(p))*100, 1.59, 0.02)

# monthly
for mo, n, r in [('2026-06',384,2.2),('2026-07',1233,-3.4),('2026-08',1132,-6.1)]:
    g = gate[gate.date_placed.dt.to_period('M').astype(str)==mo]
    check(f"{mo} n",   len(g), n, 0)
    check(f"{mo} roi", flat_roi(g).mean()*100, r, 0.05)

# the July-8 interim window quoted in the writeup
interim = s[(s.date_placed>='2026-06-16') & (s.date_placed<'2026-07-08') & (s.e>=0.05)]
pi = flat_roi(interim)
check("interim (as of 7/08) n",   len(interim), 552, 0)
check("interim (as of 7/08) roi", pi.mean()*100, 2.5, 0.1)
check("interim se (0.7 SE claim)", pi.mean()/ (pi.std(ddof=1)/math.sqrt(len(pi))), 0.7, 0.05)

# clv
c = s[s.clv_pct.fillna(0)!=0]
check("clv nonzero n",      len(c), 964, 0)
check("clv mean %",         c.clv_pct.mean(), 0.002, 0.0006)
ch = c[c.e>=0.05]
check("clv high-edge n",    len(ch), 289, 0)
check("clv high-edge mean", ch.clv_pct.mean(), 0.009, 0.0006)

# horse race -- IRLS written independently
lg = lambda p: np.log(p/(1-p))
q = s[(s.p_market_devig.between(0.01,0.99)) & (s.p_model.between(0.01,0.99))]
X = np.column_stack([np.ones(len(q)), lg(q.p_model.to_numpy()), lg(q.p_market_devig.to_numpy())])
y = q.y.to_numpy(float)
b = np.zeros(3)
for _ in range(200):
    eta = X@b; mu = 1/(1+np.exp(-eta)); W = np.clip(mu*(1-mu), 1e-10, None)
    z = eta + (y-mu)/W
    b_new = np.linalg.lstsq(X*np.sqrt(W)[:,None], z*np.sqrt(W), rcond=None)[0]
    if np.max(np.abs(b_new-b)) < 1e-12: b = b_new; break
    b = b_new
cov = np.linalg.inv((X*W[:,None]).T@X); se = np.sqrt(np.diag(cov))
check("beta model",  b[1], 0.231, 0.001)
check("se model",    se[1], 0.105, 0.001)
check("z model",     b[1]/se[1], 2.20, 0.02)
check("beta market", b[2], 0.820, 0.001)
check("se market",   se[2], 0.103, 0.001)
check("z market",    b[2]/se[2], 7.98, 0.02)
check("model weight share %", b[1]/(b[1]+b[2])*100, 22.0, 0.3)
check("leverage ratio (0.5/w)", 0.5/(b[1]/(b[1]+b[2])), 2.3, 0.05)

print("\n" + ("ALL CHECKS PASSED" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
