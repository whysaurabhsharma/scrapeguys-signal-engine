"""Measure what a naive, unauthenticated HTTP request returns for public URLs.

The fallback for /asset when there is no ScrapeGuys API key. It cannot collect
the data, so it documents, with timestamps, exactly how collection fails.

Never stores a response body. Body bytes are read into memory only to classify
them, then discarded. Only the measurements are appended to out/probe_log.json.

Politeness:
  - robots.txt is fetched and checked BEFORE any URL on that origin. Disallowed,
    401/403 on robots.txt, or robots.txt unreachable: the URL is not requested.
    Sole exception: a 401/403 on robots.txt for a host listed in
    config/robots_allowlist.csv (documented public APIs) proceeds as
    "allowlisted". A robots.txt that loads and disallows always wins.
  - one request at a time (the script is sequential, so never two per host).
  - --delay seconds (default 1.5) between the END of one request and the START
    of the next to the same host, robots.txt fetches included. A larger
    robots.txt Crawl-delay wins, capped at MAX_CRAWL_DELAY.
  - --timeout seconds (default 10). No retries on anything, 403 and 429 included.
  - redirects to a different host are NOT followed: the record is
    "skipped_redirect" with the target, which must be probed explicitly so its
    own robots.txt is checked. Same-host redirects are followed.
  - a descriptive user agent naming the repo.

    python scripts/probe.py --url https://example.com/ --url https://example.org/
    python scripts/probe.py --urls config/probe_urls.txt --quiet
"""
import argparse
import csv
import html
import http.client
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "out" / "probe_log.json"
ALLOWLIST_PATH = ROOT / "config" / "robots_allowlist.csv"

REPO_URL = "https://github.com/whysaurabhsharma/scrapeguys-signal-engine"
USER_AGENT = (f"signal-engine-probe/0.1 (+{REPO_URL}; research probe; "
              "records status and timing only, stores no content)")
DEFAULT_DELAY = 1.5        # seconds between requests to the same host
DEFAULT_TIMEOUT = 10.0     # seconds, connect and read
MAX_CRAWL_DELAY = 60.0     # honour robots Crawl-delay up to this
MAX_BODY_BYTES = 2_000_000  # read at most this to classify; never written

VERDICTS = ("usable", "js_rendered", "blocked", "error", "skipped_robots", "skipped_redirect")
REDIRECT_NOTE = ("redirect to a different host was not followed; probe the target by "
                 "passing it explicitly with --url so its own robots.txt is checked")

# ---------------------------------------------------------------- classifier
# Pure functions. No I/O. tests/test_probe.py calls these directly.

SHELL_TEXT_MAX = 300      # mount point with less visible text than this: shell
NOSCRIPT_TEXT_MAX = 1500  # "enable JavaScript" counts only on a page this thin
THIN_TEXT_MAX = 1500      # weak captcha markers count only on a page this thin
BARE_TEXT_MAX = 100       # scripts and almost nothing else: shell

_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_HIDDEN = re.compile(r"<(script|style|noscript|template|svg|head)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_MOUNT = re.compile(
    r"""<div\b[^>]*\bid\s*=\s*["']?(root|app|__next|__nuxt|svelte|react-root|main-app)\b"""
    r"""|\bdata-reactroot\b|<app-root\b|\bng-version=""", re.I)
_ENABLE_JS = re.compile(
    r"(enable|turn\s+on|activate)\s+javascript"
    r"|javascript\s+(is\s+)?(required|disabled|must\s+be\s+enabled)"
    r"|requires?\s+javascript", re.I)
_SCRIPT = re.compile(r"<script\b", re.I)

BLOCK_STATUSES = {401: "auth_required", 403: "forbidden", 407: "proxy_auth_required",
                  429: "rate_limited"}

# Strong: specific to a challenge or block page, so they count on any page.
_STRONG_BLOCK = [
    (re.compile(r"cf_chl_opt|cf-browser-verification|cf_chl_prog", re.I), "cloudflare_challenge"),
    (re.compile(r"<title>\s*(just a moment\.*|attention required!?\s*\|\s*cloudflare)", re.I),
     "cloudflare_interstitial"),
    (re.compile(r"captcha-delivery\.com", re.I), "datadome_captcha"),
    (re.compile(r"\bpx-captcha\b", re.I), "perimeterx_captcha"),
    (re.compile(r"_Incapsula_Resource|Incapsula incident ID", re.I), "imperva_block"),
    (re.compile(r"errors\.edgesuite\.net", re.I), "akamai_access_denied"),
]
# Weak: also appear on ordinary pages (login forms, Cloudflare's always-on
# challenge-platform script, AWS WAF token script). Count only on a thin page.
_WEAK_BLOCK = re.compile(
    r"g-recaptcha|h-captcha|hcaptcha\.com|recaptcha/api|challenges\.cloudflare\.com/turnstile"
    r"|/cdn-cgi/challenge-platform/|awswaf|\bcaptcha\b|are you a robot"
    r"|verify (that )?you are (a )?human|unusual traffic|<title>\s*access denied", re.I)


def norm_headers(headers):
    """Case-insensitive header lookup without depending on http.client types."""
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def visible_text(body):
    """Text a reader would see without running JavaScript."""
    t = _COMMENTS.sub(" ", body or "")
    t = _HIDDEN.sub(" ", t)
    t = _TAGS.sub(" ", t)
    return _WS.sub(" ", html.unescape(t)).strip()


def looks_html(body, content_type=""):
    ct = (content_type or "").lower()
    if ct:
        return "html" in ct
    return (body or "").lstrip()[:1] == "<"


def js_shell_reason(body, content_type=""):
    """Why this body is a client-rendered shell, or "" if it is not one."""
    if not looks_html(body, content_type):
        return ""
    n = len(visible_text(body))
    if _MOUNT.search(body) and n < SHELL_TEXT_MAX:
        return "empty_mount_point"
    if _ENABLE_JS.search(body) and n < NOSCRIPT_TEXT_MAX:
        return "enable_javascript_notice"
    if _SCRIPT.search(body) and n < BARE_TEXT_MAX:
        return "scripts_no_text"
    return ""


def block_reason(status, headers, body):
    """Why this response looks like a block, or "" if it does not."""
    h = norm_headers(headers)
    if h.get("cf-mitigated", "").strip().lower() == "challenge":
        return "cloudflare_challenge_header"
    body = body or ""
    for rx, reason in _STRONG_BLOCK:
        if rx.search(body):
            return reason
    if status in BLOCK_STATUSES:
        return BLOCK_STATUSES[status]
    if _WEAK_BLOCK.search(body) and len(visible_text(body)) < THIN_TEXT_MAX:
        return "captcha_or_challenge_page"
    return ""


def classify(status, headers, body, error=None):
    """Return (verdict, reason). Precedence: error, blocked, http error, shell, usable."""
    if error:
        return "error", error
    reason = block_reason(status, headers, body)
    if reason:
        return "blocked", reason
    if status is None or not 200 <= status < 300:
        return "error", f"http_{status}"
    if not (body or "").strip():
        return "error", "empty_body"
    reason = js_shell_reason(body, norm_headers(headers).get("content-type", ""))
    if reason:
        return "js_rendered", reason
    return "usable", "content_present"


def robots_decision(status, text, url, user_agent=USER_AGENT, allowlist=None):
    """Return (allowed, reason, crawl_delay). Conservative when unsure.

    status None means robots.txt could not be fetched at all (DNS, timeout,
    TLS). 404 and other 4xx mean no robots.txt: allowed, per RFC 9309.
    401/403 and 5xx mean we cannot know: not allowed, unless the host is in
    the allowlist, which applies to 401/403 only. A robots.txt that loads is
    always obeyed; the allowlist never overrides a disallow rule.
    """
    if status is None:
        return False, "robots_unreachable", None
    if status in (401, 403):
        if (urlsplit(url).hostname or "").lower() in (allowlist or {}):
            return True, "allowlisted", None
        return False, f"robots_http_{status}", None
    if 400 <= status < 500:
        return True, "no_robots_txt", None
    if not 200 <= status < 300:
        return False, f"robots_http_{status}", None
    rp = urllib.robotparser.RobotFileParser()
    rp.parse((text or "").splitlines())
    rp.modified()  # can_fetch refuses everything until this is set
    delay = rp.crawl_delay(user_agent)
    delay = float(delay) if delay is not None else None
    if rp.can_fetch(user_agent, url):
        return True, "robots_allows", delay
    return False, "robots_disallows", delay


def load_allowlist(path=ALLOWLIST_PATH):
    """{host: {"reason", "doc_url"}}. Missing file means an empty allowlist."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["host"].strip().lower(): {"reason": (r.get("reason") or "").strip(),
                                            "doc_url": (r.get("doc_url") or "").strip()}
                for r in csv.DictReader(fh) if (r.get("host") or "").strip()}


# ---------------------------------------------------------------- politeness

class HostThrottle:
    """Enforces a gap between the end of one request and the start of the next
    to the same host. Clock and sleep are injectable so tests never wait."""

    def __init__(self, delay, clock=time.monotonic, sleep=time.sleep):
        self.delay = delay
        self.clock = clock
        self.sleep = sleep
        self._last = {}
        self._extra = {}

    def set_host_delay(self, host, seconds):
        if seconds:
            self._extra[host] = min(float(seconds), MAX_CRAWL_DELAY)

    def gap(self, host):
        return max(self.delay, self._extra.get(host, 0.0))

    def wait(self, host):
        last = self._last.get(host)
        if last is None:
            return 0.0
        remaining = self.gap(host) - (self.clock() - last)
        if remaining > 0:
            self.sleep(remaining)
            return remaining
        return 0.0

    def done(self, host):
        self._last[host] = self.clock()


# ---------------------------------------------------------------- network

class CrossHostRedirect(Exception):
    def __init__(self, code, target):
        super().__init__(f"{code} -> {target}")
        self.code, self.target = code, target


class SameHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only when the target hostname equals the source's."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        src = (urlsplit(req.full_url).hostname or "").lower()
        dst = (urlsplit(newurl).hostname or "").lower()
        if dst != src:
            raise CrossHostRedirect(code, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(SameHostRedirectHandler)


def _decode(raw, content_type):
    m = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    try:
        return raw.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def fetch(url, timeout):
    """One GET. No retries. Returns raw measurements plus the decoded body,
    which the caller classifies and drops."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    })
    status, headers, raw, final, error, target = None, {}, b"", url, None, None
    t0 = time.monotonic()
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            status, final = resp.status, resp.geturl()
            headers = dict(resp.headers.items())
            raw = resp.read(MAX_BODY_BYTES + 1)
    except CrossHostRedirect as e:
        status, target = e.code, e.target
    except urllib.error.HTTPError as e:  # 4xx/5xx: still has headers and a body
        status, final = e.code, (e.geturl() or url)
        headers = dict(e.headers.items()) if e.headers else {}
        try:
            raw = e.read(MAX_BODY_BYTES + 1)
        except (OSError, http.client.HTTPException):
            raw = b""
    except urllib.error.URLError as e:
        r = e.reason
        error = type(r).__name__ if isinstance(r, BaseException) else "URLError"
    except (OSError, http.client.HTTPException, ValueError) as e:
        error = type(e).__name__
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    ct = norm_headers(headers).get("content-type", "")
    return {
        "status": status, "headers": headers, "final_url": final, "error": error,
        "redirect_target": target,
        "elapsed_ms": elapsed_ms, "body_bytes": min(len(raw), MAX_BODY_BYTES),
        "body_truncated": len(raw) > MAX_BODY_BYTES,
        "body": _decode(raw[:MAX_BODY_BYTES], ct),
    }


def fetch_robots(origin, timeout):
    """(status, text). Status None when robots.txt could not be reached."""
    r = fetch(origin + "/robots.txt", timeout)
    return r["status"], (r["body"] if r["status"] and 200 <= r["status"] < 300 else "")


# ---------------------------------------------------------------- record

def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_record(url, probed_at, robots_reason, f=None, skipped=False, allow_entry=None):
    """The only thing written to disk. Never includes the body."""
    rec = {"url": url, "probed_at": probed_at, "user_agent": USER_AGENT,
           "robots_status": robots_reason,
           "robots_allowlist_reason": (allow_entry or {}).get("reason"),
           "robots_allowlist_doc": (allow_entry or {}).get("doc_url")}
    if skipped or f is None:
        rec.update(verdict="skipped_robots", reason=robots_reason, status=None, error=None,
                   redirect_target=None, note=None,
                   elapsed_ms=None, final_url=None, redirected=None, redirected_cross_host=None,
                   content_type=None, content_length=None, body_bytes=None,
                   body_truncated=None, js_shell=None, blocked=None)
        return rec
    h = norm_headers(f["headers"])
    target = f.get("redirect_target")
    if target:
        rec.update(verdict="skipped_redirect", reason=f"http_{f['status']}_cross_host",
                   status=f["status"], error=None, redirect_target=target, note=REDIRECT_NOTE,
                   elapsed_ms=f["elapsed_ms"], final_url=None, redirected=True,
                   redirected_cross_host=True, content_type=None, content_length=None,
                   body_bytes=None, body_truncated=None, js_shell=None, blocked=None)
        return rec
    verdict, reason = classify(f["status"], f["headers"], f["body"], f["error"])
    final = f["final_url"] or url
    rec.update(
        verdict=verdict, reason=reason, status=f["status"], error=f["error"],
        redirect_target=None, note=None,
        elapsed_ms=f["elapsed_ms"], final_url=final, redirected=final != url,
        redirected_cross_host=urlsplit(final).hostname != urlsplit(url).hostname,
        content_type=h.get("content-type"),
        content_length=int(h["content-length"]) if h.get("content-length", "").isdigit() else None,
        body_bytes=f["body_bytes"], body_truncated=f["body_truncated"],
        js_shell=bool(js_shell_reason(f["body"], h.get("content-type", ""))) if not f["error"] else None,
        blocked=bool(block_reason(f["status"], f["headers"], f["body"])) if not f["error"] else None,
    )
    return rec


# ---------------------------------------------------------------- run

def load_urls(url_file, urls):
    out, seen = [], set()
    lines = []
    if url_file:
        lines = Path(url_file).read_text(encoding="utf-8-sig").splitlines()
    for u in lines + list(urls or []):
        u = u.strip()
        if not u or u.startswith("#") or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def probe_all(urls, delay, timeout, quiet=False, throttle=None, fetcher=fetch,
              robots_fetcher=fetch_robots, allowlist=None):
    throttle = throttle or HostThrottle(delay)
    allowlist = load_allowlist() if allowlist is None else allowlist
    robots_cache = {}  # origin -> (status, text)
    records = []
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            rec = build_record(url, now_utc(), "not_checked",
                               {"status": None, "headers": {}, "final_url": url,
                                "error": "unsupported_url", "elapsed_ms": 0,
                                "body_bytes": 0, "body_truncated": False, "body": ""})
            records.append(rec)
            continue
        host = parts.hostname.lower()
        origin = f"{parts.scheme}://{parts.netloc.lower()}"
        if origin not in robots_cache:
            throttle.wait(host)
            robots_cache[origin] = robots_fetcher(origin, timeout)
            throttle.done(host)
        allowed, reason, crawl_delay = robots_decision(*robots_cache[origin], url,
                                                       allowlist=allowlist)
        entry = allowlist.get(host) if reason == "allowlisted" else None
        throttle.set_host_delay(host, crawl_delay)
        if not allowed:
            rec = build_record(url, now_utc(), reason, skipped=True)
        else:
            throttle.wait(host)
            probed_at = now_utc()
            f = fetcher(url, timeout)
            throttle.done(host)
            rec = build_record(url, probed_at, reason, f, allow_entry=entry)
        records.append(rec)
        if not quiet:
            print(f"{rec['verdict']:<15} {str(rec['status'] or '-'):<4} "
                  f"{str(rec['elapsed_ms'] or '-'):>6}ms  {rec['reason']:<28} {url}"
                  + (f"  -> {rec['redirect_target']}" if rec.get("redirect_target") else ""))
    return records


def append_log(path, records):
    """Append to a JSON list. Refuses to overwrite a file that is not one."""
    path = Path(path)
    existing = []
    if path.exists() and path.stat().st_size:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise SystemExit(f"{path} is not a JSON list; refusing to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(existing + records, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return len(existing) + len(records)


def summarize(records):
    counts = {v: 0 for v in VERDICTS}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    timed = [r["elapsed_ms"] for r in records if r.get("elapsed_ms") is not None
             and r["verdict"] != "skipped_robots"]
    med = statistics.median(timed) if timed else None
    lines = ["verdict           count", "----------------  -----"]
    lines += [f"{v:<16}  {counts[v]:>5}" for v in counts]
    lines += ["----------------  -----", f"{'total':<16}  {len(records):>5}",
              f"median elapsed   {'-' if med is None else f'{med:.0f} ms'}"
              f"  (over {len(timed)} requested)"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--urls", help="file with one URL per line; # comments allowed")
    ap.add_argument("--url", action="append", default=[], help="a URL; repeatable")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="JSON list to append to")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help="seconds between requests to one host (min 1.5)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--quiet", action="store_true", help="summary only")
    args = ap.parse_args(argv)

    urls = load_urls(args.urls, args.url)
    if not urls:
        ap.error("no URLs: pass --urls FILE or --url URL")
    delay = max(args.delay, DEFAULT_DELAY)  # never less polite than the default
    records = probe_all(urls, delay, args.timeout, quiet=args.quiet)
    total = append_log(args.out, records)
    print("\n" + summarize(records))
    print(f"\nappended {len(records)} to {args.out} ({total} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
