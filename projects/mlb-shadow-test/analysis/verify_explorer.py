"""Reference values for the browser explorer. The JS must reproduce these exactly.
Recomputes the blend, deciles and threshold subset in Python from the same
compact dataset the page embeds."""
import numpy as np, pandas as pd, pathlib, json

ROOT = pathlib.Path(__file__).resolve().parents[1]
d = pd.read_csv(ROOT.parents[1] / "docs" / "mlb-shadow-test" / "shadow.csv")
lm = np.log(d.pm / (1 - d.pm)).to_numpy()
lk = np.log(d.pk / (1 - d.pk)).to_numpy()
pk = d.pk.to_numpy(); w = d.w.to_numpy(float)
profit = np.where(d.o > 0, d.o / 100, 100 / -d.o)

def snap(lam, thr):
    p = 1 / (1 + np.exp(-(lam * lm + (1 - lam) * lk)))
    e = p - pk
    order = np.argsort(e, kind="stable")
    n = len(e); dec = []
    for k in range(10):
        idx = order[n * k // 10:n * (k + 1) // 10]
        dec.append((round(float(p[idx].mean()), 4), round(float(w[idx].mean()), 4)))
    q = e >= thr
    out = {"lam": lam, "thr": thr, "n": int(q.sum()), "max_edge": round(float(e.max()), 4),
           "dec_first": dec[0], "dec_last": dec[9]}
    if q.sum() > 1:
        pay = np.where(w[q] == 1, profit[q], -1.0)
        out |= {"pred": round(float(p[q].mean()), 4), "obs": round(float(w[q].mean()), 4),
                "roi": round(float(pay.mean() * 100), 2),
                "se": round(float(pay.std(ddof=1) / np.sqrt(q.sum()) * 100), 2)}
    return out

cases = [(1.00, 0.05), (0.50, 0.05), (0.22, 0.05), (0.22, 0.00), (1.00, 0.10), (0.75, 0.02)]
for lam, thr in cases:
    print(json.dumps(snap(lam, thr)))
