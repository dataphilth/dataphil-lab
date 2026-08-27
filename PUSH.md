# Publish — run on Windows (PowerShell)

Everything is built. This is deploy-only.

## 1. Init and commit

```powershell
cd C:\dev\dataphil-lab
git init -b main
git add -A
git commit -m "dataphil lab: MLB shadow test writeup, explorer, notebook, data"
```

## 2. Create the public repo and push

With GitHub CLI:

```powershell
gh repo create dataphil-lab --public --source=. --push
```

Without it: create an empty **public** repo named `dataphil-lab` at https://github.com/new
(no README, no license), then:

```powershell
git remote add origin https://github.com/dataphilth/dataphil-lab.git
git push -u origin main
```

The repo name matters — the Colab links and the raw-data URL in `notebook.ipynb` are hardcoded
to `dataphilth/dataphil-lab`. If you name it something else, tell me and I'll update them.

## 3. Turn on Pages

Repo → **Settings** → **Pages** → Source: *Deploy from a branch* → Branch `main`, folder
`/docs` → Save.

`docs/CNAME` already contains `lab.dataphil.com`, so Pages will pick the custom domain up
automatically.

## 4. DNS at your registrar

Add one record:

| type | host | value |
|---|---|---|
| CNAME | `lab` | `dataphilth.github.io` |

Then in Settings → Pages, wait for the certificate to provision and tick **Enforce HTTPS**.
Usually a few minutes, occasionally up to an hour.

Check it: **https://lab.dataphil.com**

## 5. One link from the product

In the dataphil repo, add a quiet footer link on `templates/landing.html` — not a nav tab:

```html
<a href="https://lab.dataphil.com">Lab &rarr;</a>
```

That's the only change the product needs. Send me the path to the real dataphil repo and I'll
do it properly.

---

## Refreshing later

The site is a snapshot dated 2026-08-26. To update it:

```powershell
cd C:\dev\dataphil-lab\projects\mlb-shadow-test
copy C:\dev\mlb-model-v2\live\shadow_log.csv data\shadow_log.csv
copy C:\dev\mlb-model-v2\live\shadow_log_totals.csv data\shadow_log_totals.csv
python analysis\reproduce.py             # figures + results.json
python analysis\build_explorer_data.py   # the explorer's compact dataset
python analysis\verify.py                # must print ALL CHECKS PASSED
```

`verify.py` compares against the numbers **currently published**, so after a data refresh it
will fail on anything that moved — that's the point. The prose figures in `docs/` and
`WRITEUP.md` are hand-written; ask me and I'll rewrite them against the fresh `results.json`
and update `verify.py` to match.

## What's deliberately absent

No model source, no methodology document, no API keys, no `.env`. `C:\dev\mlb-model-v2` stays
private.
