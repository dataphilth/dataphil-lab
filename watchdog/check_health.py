#!/usr/bin/env python3
"""Cloud-side freshness watchdog.

Polls /api/health on the live site and mails Phil only when something is
actually wrong. Runs in GitHub Actions rather than on the laptop, because
the laptop watchdog could only ever see the local half of the chain:

    Task Scheduler -> refresh_and_push.bat -> GitHub -> Actions -> Render

Everything from "GitHub" rightward was unmonitored. This closes that.

Stdlib only, on purpose - no pip install step means one less thing that can
fail between a real outage and the alert about it.

One alert per incident per day (2026-09-25). Two independent watchdogs poll
this - the GitHub Actions cron and the cron-job.org pinger via Render - and
before this change a single stuck index mailed Phil 9 times in 3 days, plus
a GitHub "Run failed" mail per red run. Now:
  - mail() first asks Gmail (IMAP, same app password) whether an alert with
    this exact subject already went out today (ET). If so it stays quiet.
    Any IMAP trouble fails OPEN - a duplicate beats a missed outage.
  - main() exits 0 once the alert is delivered or already delivered, so
    GitHub does not send its own duplicate. It exits 1 only when mail
    could not be sent, which makes GitHub's run-failed email the backup.
The subject names the broken layer(s), so a NEW problem on the same day
still mails.

Local use:
    python scripts/check_health.py --dry-run     # print the verdict, never mail
    python scripts/check_health.py --url http://localhost:5000
"""
import argparse, imaplib, json, os, smtplib, ssl, sys, time, urllib.error, urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DEFAULT_URL = os.environ.get("SITE_URL", "https://dataphil.com").rstrip("/")

# Render's free tier spins down when idle, so the first request of the day
# pays a cold start, and /api/health calls Yahoo on top of that. Retry
# patiently: a slow wake is not an outage, and crying wolf trains you to
# ignore the alert that matters.
ATTEMPTS = 4
TIMEOUT = 90
BACKOFF = 20


def fetch(url):
    """Return (payload, error). Cache-busted; never raises."""
    last = None
    for i in range(1, ATTEMPTS + 1):
        bust = "%s%scb=%d" % (url, "&" if "?" in url else "?", int(time.time()))
        try:
            req = urllib.request.Request(bust, headers={
                "User-Agent": "dataphil-watchdog/1.0",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace")
            if r.status != 200:
                last = "HTTP %s" % r.status
            else:
                try:
                    return json.loads(body), None
                except ValueError:
                    # HTML where JSON belongs usually means a Render error
                    # page or a route that did not deploy.
                    last = "non-JSON response (%d bytes): %s" % (
                        len(body), body[:200].replace("\n", " "))
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        if i < ATTEMPTS:
            print("  attempt %d/%d failed (%s), retrying in %ds"
                  % (i, ATTEMPTS, last, BACKOFF), flush=True)
            time.sleep(BACKOFF)
    return None, last


# ── alert tiers (build 059, 2026-10-16) ─────────────────────────────────────
# Every complaint line gets one tier, judged by its text, not just its layer:
# "street calls" can be housekeeping (a call waiting for its first price bar)
# or a real failure (the scorer stopped). Order = severity; the worst tier
# present sets the subject.
TIER_ORDER = ("wrong", "stale", "verify", "blind", "notice")
TIER_LEAD = {"wrong": "dataphil WRONG", "stale": "dataphil stale",
             "verify": "dataphil verify", "blind": "dataphil watchdog blind",
             "notice": "dataphil notice"}

# (layer, phrase in the complaint) -> tier. First match wins; anything not
# listed is "stale", and any "check failed" stays stale - a broken check is
# never housekeeping.
_TIER_RULES = (
    ("content", "", "wrong"),
    ("numbers", "", "wrong"),
    ("outside check", "", "blind"),
    ("quote data", "verify against the real close", "verify"),
    ("street calls", "have no price at call yet", "notice"),
    ("reported calls", "link to the publisher", "notice"),
    ("clip tags", "tagger misfire", "notice"),
)


def tier_of(complaint):
    """'wrong' | 'stale' | 'verify' | 'blind' | 'notice' for one complaint line."""
    c = str(complaint or "")
    layer = c.split(":", 1)[0].strip()
    if layer in ("content", "numbers") and not ("check failed" in c or "could not run" in c
                                                or "failed to run" in c):
        return "wrong"
    if "check failed" in c or "failed to run" in c or "could not run" in c:
        return "stale"
    for lay, phrase, tier in _TIER_RULES:
        if layer == lay and phrase in c:
            return tier
    return "stale"


def compose(url, payload, error):
    """Return (subject, body). Written to be readable on a phone lock screen:
    the subject alone should say which layer broke."""
    stamp = datetime.now(ET).strftime("%a %b %d, %H:%M ET")

    if error:
        return ("dataphil DOWN - /api/health unreachable",
                "The watchdog could not read %s\n\n"
                "Last error: %s\nAfter %d attempts.\nChecked %s\n\n"
                "Most likely: Render deploy failed, the service is asleep and "
                "not waking, or /api/health has not shipped yet.\n"
                "Check https://dashboard.render.com first, then the latest "
                "commit's deploy log.\n" % (url, error, ATTEMPTS, stamp))

    complaints = payload.get("complaints") or []
    by_tier = {t: [] for t in TIER_ORDER}
    for c in complaints:
        by_tier[tier_of(c)].append(c)
    # Build 069 (L28): /api/health's own notices (e.g. an index the site already holds
    # back) never set ok:false, so they never start a mail; when something else does,
    # they ride along in the NOTICE section so nothing is silent.
    top = next((t for t in TIER_ORDER if by_tier[t]), "stale")   # from complaints only
    by_tier["notice"].extend(str(n) for n in (payload.get("notices") or []))

    def _layers(items):
        out = []
        for c in items:
            layer = c.split(":", 1)[0].strip()
            if layer not in out:
                out.append(layer)
        return out

    # Tiers (build 059). The subject names only the layers that need action;
    # housekeeping (NOTICE) rides along in the body. A NOTICE-only mail has a
    # fixed subject, so the once-a-day dedupe in mail() caps it at one a day
    # however the notice list changes. "WRONG" = a published sentence failed
    # the truth audit (build 029) or a figure disagreed with CNBC on two checks
    # (build 039). "verify" = a big one-day move nobody has confirmed yet.
    act = [c for t in TIER_ORDER if t != "notice" for c in by_tier[t]]
    act_layers = _layers(act)
    layers = _layers(complaints)          # every layer, for the WHERE TO LOOK sections
    if top == "notice":
        subject = "dataphil notice - daily housekeeping (nothing broken)"
    elif top == "blind" and act_layers == ["outside check"]:
        subject = "dataphil watchdog blind - outside check"   # about the check, not the site
    else:
        subject = "%s - %s" % (TIER_LEAD[top], ", ".join(act_layers) or "unknown layer")

    lines = ["Checked %s against site date %s\n"
             % (stamp, payload.get("checked_at_et", "?"))]
    heads = {"wrong": "WRONG ON THE SITE NOW", "stale": "STALE OR BROKEN",
             "verify": "VERIFY", "blind": "WATCHDOG BLIND",
             "notice": "NOTICE - no action needed, listed so nothing is silent"}
    for t in TIER_ORDER:
        if by_tier[t]:
            lines.append(heads[t])
            for c in by_tier[t]:
                lines.append("  - %s" % c)
            lines.append("")

    # The outside comparison's own view, so a first sighting (not yet a
    # complaint) still shows WHICH figures were off.
    oc = payload.get("outside") or {}
    if oc.get("out_of_limit") and "numbers" not in layers:
        lines.append("OUTSIDE CHECK (%s, %s compared, not yet confirmed - not a complaint)"
                     % (oc.get("status"), oc.get("compared")))
        for t in oc["out_of_limit"][:10]:
            lines.append("  ~ %s" % t)
        lines.append("")

    lines.append("\nWHERE TO LOOK")
    if "clips" in layers:
        lines.append("  Clips come from the LAPTOP:")
        lines.append("    Task Scheduler -> refresh_and_push.bat -> git push -> Render")
        lines.append("    Check refresh_last_success.txt, then refresh_auto.log for FAILED.")
    if any(l in ("morning read", "am take", "brief") for l in layers):
        lines.append("  The morning read, the AM take and the brief are cloud jobs the")
        lines.append("  cron-job.org pinger dispatches - the laptop is NOT involved:")
        lines.append("    /api/tasks/refresh -> daily-refresh.yml  (morning read + AM take, from 05:05 ET)")
        lines.append("    /api/tasks/brief   -> daily-brief.yml    ('Before the open', from 06:30 ET)")
        lines.append("    Fastest fix: github.com/dataphilth/dataphil/actions -> the workflow")
        lines.append("    -> Run workflow. If neither ran, the Render GITHUB_TOKEN may have")
        lines.append("    expired (every dispatch dies with it).")
    if "pulse" in layers or "options" in layers:
        lines.append("  Pulse and options captures run from the cron-job.org pinger")
        lines.append("    -> https://dataphil.com/api/tasks/<pulse|options> (X-Task-Key)")
        lines.append("    https://dataphil.com/api/tasks/status shows whether the last run")
        lines.append("    finished ok (its error/log need the X-Task-Key header); then check")
        lines.append("    cron-job.org's execution history. GitHub Actions")
        lines.append("    (pulse-refresh.yml / options-refresh.yml) is the fallback, not the primary.")
    if "content" in layers:
        lines.append("  CONTENT means something published today failed the truth audit:")
        lines.append("    a take or Morning Read sentence its own stored facts do not back, a")
        lines.append("    docket or rating fact the calendar seed no longer shows, or a Street")
        lines.append("    Call that breaks a rule. It is on the site right now.")
        lines.append("    1. Read content.failures in the payload below (each names the surface).")
        lines.append("    2. Takes / Morning Read: github.com/dataphilth/dataphil/actions ->")
        lines.append("       the narrative workflow -> Run workflow with force = true rewrites it")
        lines.append("       from current data. Street Calls: the next news refresh corrects it;")
        lines.append("       if it persists, claim_extractor.revalidate_street_calls is not running.")
        lines.append("    3. If it was live long enough to matter, add an entry to corrections.json")
        lines.append("       (it then shows as corrected here and on /corrections).")
    if "outside check" in layers:
        lines.append("  OUTSIDE CHECK means the watchdog could not reach CNBC's quote service, so")
        lines.append("    today the site's numbers have not been compared with anyone else's.")
        lines.append("    Nothing on the site is being called wrong by this line.")
        lines.append("    Render's address may be refused by CNBC, or the service changed its")
        lines.append("    response. scripts/outside_check.py can be run by hand; the GitHub")
        lines.append("    'Freshness watchdog' run log prints the same check from GitHub's network.")
    if "numbers" in layers:
        lines.append("  NUMBERS means a figure the site is serving disagreed with CNBC's quote")
        lines.append("    service by more than its limit on two checks in a row (about 30 minutes).")
        lines.append("    Each line above gives the site's value, CNBC's and the gap.")
        lines.append("    1. Open the page and CNBC for that instrument and see who is right.")
        lines.append("    2. A whole session apart = the site is serving an old bar (Yahoo).")
        lines.append("       A constant gap on one instrument = wrong symbol or contract.")
        lines.append("    3. The check itself: scripts/outside_check.py, state on /api/health")
        lines.append("       under 'outside'. If CNBC was wrong, widen that row's limit there.")
    if "quote data" in layers:
        lines.append("  Quote data is fetched live by Render from Yahoo:")
        lines.append("    A stuck data_date means Yahoo is serving old bars or")
        lines.append("    the fetch is erroring into a cache. The laptop is NOT")
        lines.append("    involved - do not go looking at Task Scheduler for this.")
        if any(c.startswith("quote data") and tier_of(c) == "verify" for c in complaints):
            lines.append("    A VERIFY line is a big one-day move: check the index on CNBC or the")
            lines.append("    exchange. Real move = nothing to do. Wrong = Yahoo served a bad bar.")
    if "market data" in layers:
        lines.append("  MARKET DATA is the docket (econ calendar, earnings, analyst moves) the brief,")
        lines.append("    the Desk and the takes read. It is fetched by the cloud daily-refresh and the")
        lines.append("    laptop refresh (data_fetcher.run_data_fetch): econ from ForexFactory, earnings")
        lines.append("    and analyst moves from Yahoo. 'came back empty' = that source answered with")
        lines.append("    nothing (throttled or down) and yesterday's rows are being shown; the next")
        lines.append("    refresh retries. 'is empty' = nothing recent to keep: the docket is blank,")
        lines.append("    so the brief and takes will say nothing is scheduled. Re-run daily-refresh")
        lines.append("    from github.com/dataphilth/dataphil/actions once the source answers.")
    if "street calls" in layers:
        lines.append("  STREET CALLS live in the newsletter_claims table on Render.")
        lines.append("    'no price at call yet' is pending, not broken: the daily reprice pass")
        lines.append("    retries and withdraws a call after 3 days without bars. Act only if")
        lines.append("    the same calls are still listed after that, or a call is 'overdue'")
        lines.append("    (= the scorer is not running or its price lookups fail).")
    if "reported calls" in layers:
        lines.append("  REPORTED CALLS come from the news wire via the daily refresh")
        lines.append("    (scripts/refresh_reported_calls.py). A low publisher-link rate means")
        lines.append("    the Google link resolver is failing - rows keep the Google link, so")
        lines.append("    nothing on the site is wrong; few rows stored means the wire, the")
        lines.append("    extractor or the daily refresh stalled.")
    if "scorecard" in layers:
        lines.append("  SCORECARD seeds are written by the daily refresh workflow:")
        lines.append("    github.com/dataphilth/dataphil/actions -> daily-refresh.yml. Check its")
        lines.append("    newest run's TIME (not just its green check), then scorecard_seed.json")
        lines.append("    / basket_history_seed.json on main.")
    if any(l in ("clip archive", "clip tags") for l in layers):
        lines.append("  CLIP ARCHIVE / TAGS come from the LAPTOP refresh (YouTube blocks cloud IPs).")
        lines.append("    A gap day = the laptop refresh did not run that day. A tag misfire is a")
        lines.append("    tagger quality hint only - nothing is stale.")

    # The push-recovery recipe only applies to the laptop leg (clips). It used
    # to be on every mail, including ones where nothing had failed to push.
    if any(l in ("clips", "clip archive") for l in layers):
        lines.append("\nIf the laptop push failed, the known-good recovery is:")
        lines.append("  git rebase --abort")
        lines.append("  git status          # confirm no modified TRACKED files")
        lines.append("  git fetch origin")
        lines.append("  git reset --hard origin/main")
        lines.append("  re-run refresh_and_push.bat")
        lines.append("\nNever resolve a seed-JSON conflict by rebasing - .gitattributes")
        lines.append("marks them -merge, so a rebase is guaranteed to hard-conflict.")

    lines.append("\nFULL PAYLOAD\n%s" % json.dumps(payload, indent=2))
    return subject, "\n".join(lines)


def already_sent_today(user, pw, subject):
    """True only when Gmail positively shows a watchdog alert with this exact
    subject sent since midnight ET. Looks in All Mail AND Trash (Phil trashes
    these). Anything unexpected -> False, i.e. send anyway."""
    since = datetime.now(ET).strftime("%d-%b-%Y")
    try:
        im = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
    except TypeError:  # Python < 3.9 has no timeout kwarg
        im = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        im.login(user, pw)
        typ, boxes = im.list()
        folders = []
        for raw in boxes or []:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            if "\\All" in line or "\\Trash" in line:
                folders.append(line.rsplit(' "/" ', 1)[-1].strip())
        for box in folders:
            if im.select(box, readonly=True)[0] != "OK":
                continue
            typ, data = im.search(None, "SINCE", since,
                                  "HEADER", "X-Dataphil-Watchdog", "1",
                                  "SUBJECT", '"%s"' % subject.replace('"', ""))
            if typ != "OK" or not data or not data[0]:
                continue
            # IMAP SUBJECT is a substring match; insist on the exact subject.
            for num in data[0].split():
                typ, hdr = im.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                for part in hdr or []:
                    if isinstance(part, tuple):
                        got = part[1].decode("utf-8", "replace").split(":", 1)[-1].strip()
                        if got == subject:
                            print("already alerted today in %s - not mailing again" % box)
                            return True
        return False
    finally:
        try:
            im.logout()
        except Exception:
            pass


def mail(subject, body):
    """Send the alert unless it already went out today. Returns True when
    Phil has the alert (sent now or earlier today), False when he doesn't."""
    user = os.environ.get("GMAIL_ADDRESS")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("WATCHDOG_TO") or user
    if not (user and pw):
        print("!! GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set - cannot mail")
        return False
    try:
        if already_sent_today(user, pw, subject):
            return True
    except Exception as e:
        print("  dedupe check skipped (%s: %s) - mailing anyway" % (type(e).__name__, e))
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("dataphil watchdog", user))
    msg["To"] = to
    msg["X-Dataphil-Watchdog"] = "1"
    msg.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ctx) as s:
        s.login(user, pw)
        s.send_message(msg)
    print("alert mailed to %s" % to)
    return True


RECHECK_S = int(os.environ.get("WATCHDOG_RECHECK_S") or 360)


def _layer_set(payload):
    return {c.split(":", 1)[0].strip() for c in ((payload or {}).get("complaints") or [])}


def confirm_looks(p1, e1, p2, e2):
    """(payload, error, confirmed) from two looks, by the Render watchdog's
    rules: mail only what both looks agree on - the site unreachable twice,
    or the same layer complaining twice. A "numbers" complaint counts on the
    second look alone (outside_check already demands two sightings). A
    complaint text-less not-ok payload both times is odd, not a blip: mail."""
    if p2 is not None and p2.get("ok"):
        return p2, None, False
    if p2 is None:
        return None, e2, p1 is None
    if p1 is None:
        return p2, None, False            # down, then stale: changed shape, next poll decides
    first = _layer_set(p1)
    seen = p2.get("complaints") or []
    kept = [c for c in seen if c.split(":", 1)[0].strip() in first or c.startswith("numbers:")]
    if kept:
        p2 = dict(p2, complaints=kept)
        return p2, None, True
    return p2, None, (not first and not seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL,
                    help="site base URL (default $SITE_URL or dataphil.com)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the verdict, never send mail")
    ap.add_argument("--no-recheck", action="store_true",
                    help="judge on one look (skip the %ds second look)" % RECHECK_S)
    a = ap.parse_args()

    endpoint = a.url.rstrip("/") + "/api/health"
    print("checking %s" % endpoint, flush=True)

    payload, error = fetch(endpoint)

    # The outside comparison (build 039), printed for the run log only. From
    # here it has no memory of the last run, so it cannot confirm anything
    # and never mails; the Render watchdog task is the one that alarms.
    try:
        import outside_check
        oc = outside_check.run(a.url, save=False)
        print("outside check: %s - %s instruments compared, %s inside limits"
              % (str(oc.get("status")).upper(), oc.get("compared"), oc.get("matched")))
        for g in oc.get("gross") or []:
            print("  OUT OF LIMIT  %s" % g.get("text"))
        for n in oc.get("notes") or []:
            print("  note          %s" % n)
        for e in oc.get("errors") or []:
            print("  error         %s" % e)
    except Exception as e:
        print("outside check could not run: %s: %s" % (type(e).__name__, e))

    if payload and payload.get("ok"):
        print("OK - everything fresh as of %s" % payload.get("checked_at_et"))
        for n in payload.get("notices") or []:      # build 069: held-back rows etc., no action
            print("  notice        %s" % n)
        for k in ("clips", "morning_read", "takes", "world_markets", "pulse", "options", "market_data", "content", "outside"):
            print("  %-14s %s" % (k, json.dumps(payload.get(k, {}))))
        return 0

    # Second look (build 060) - same rule as the Render watchdog (build 024):
    # this job used to mail on one look, which is how a six-hours-late cron
    # run mailed a passing after-hours quote blip on 2026-10-13 19:14 ET.
    if not a.no_recheck:
        print("not ok on the first look - looking again in %ds" % RECHECK_S, flush=True)
        time.sleep(RECHECK_S)
        p2, e2 = fetch(endpoint)
        payload, error, confirmed = confirm_looks(payload, error, p2, e2)
        if not confirmed:
            print("second look: %s - not mailing" % (
                "ok" if (p2 and p2.get("ok")) else "not the same problem twice"))
            return 0

    subject, body = compose(a.url, payload, error)
    print("\n" + "=" * 70)
    print(subject)
    print("=" * 70)
    print(body)

    if a.dry_run:
        print("\n[dry-run] not mailing")
        return 1
    delivered = False
    try:
        delivered = mail(subject, body)
    except Exception as e:
        print("!! mail failed: %s: %s" % (type(e).__name__, e))
    if delivered:
        # Phil has the alert. A red run would only add GitHub's duplicate.
        print("::warning::%s (alert delivered by mail)" % subject)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
