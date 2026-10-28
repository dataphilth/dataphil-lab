# dataphil.com watchdog

A stdlib-only freshness check for [dataphil.com](https://dataphil.com). Three times each weekday it
reads the site's own verdict at `/api/health`, and if a layer is stale or the site is unreachable,
it looks again six minutes later and mails one alert naming the broken layer. One alert per
incident per day; a duplicate is better than a missed outage, so mail trouble fails open.

Schedule and wiring: `.github/workflows/dataphil-watchdog.yml`.

```
python watchdog/check_health.py --dry-run     # print the verdict, never mail
```
