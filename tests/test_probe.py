"""Self-check for scripts/probe.py. Makes NO network requests.

Network entry points (urlopen, socket connect, the module's own fetchers) are
replaced with functions that fail the run if anything touches them. The
classifier, robots logic, throttle and log writer are tested on in-memory
samples. Prints PASS or FAIL per case and exits 1 if any case fails.

    python tests/test_probe.py
"""
import json
import socket
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import probe  # noqa: E402

FAILS = []
NETWORK_TOUCHED = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


def _no_network(*a, **kw):
    NETWORK_TOUCHED.append(a[:1])
    raise AssertionError("test_probe must not touch the network")


urllib.request.urlopen = _no_network
socket.create_connection = _no_network
socket.socket.connect = _no_network
probe.fetch = _no_network
probe.fetch_robots = _no_network

HTML = {"Content-Type": "text/html; charset=utf-8"}
PROSE = "<p>" + ("Fresh price for SKU 1234 is Rs 99 and it is in stock. " * 40) + "</p>"

# ---------------------------------------------------------------- samples

CRA_SHELL = """<!doctype html><html><head><title>Shop</title>
<script defer src="/static/js/main.3f2a.js"></script></head>
<body><noscript>You need to enable JavaScript to run this app.</noscript>
<div id="root"></div></body></html>"""

NEXT_SSR = f"""<!doctype html><html><head><title>Shop</title></head><body>
<div id="__next">{PROSE}</div>
<script id="__NEXT_DATA__" type="application/json">{{"props":{{}}}}</script>
<script src="https://example.com/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>
</body></html>"""

ANGULAR_SHELL = """<html><head><title>App</title></head>
<body><app-root></app-root><script src="main.js"></script></body></html>"""

BARE_SCRIPTS = """<html><body><script src="/a.js"></script><script src="/b.js"></script></body></html>"""

JS_NOTICE_THIN = """<html><body><h1>Please enable JavaScript to continue.</h1>
<script src="/app.js"></script></body></html>"""

JS_NOTICE_RICH = f"""<html><body><noscript>Please enable JavaScript for the best
experience.</noscript><main>{PROSE}</main></body></html>"""

CF_CHALLENGE = """<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>
<meta http-equiv="refresh" content="390"></head><body>
<noscript>Enable JavaScript and cookies to continue</noscript>
<script>(function(){window._cf_chl_opt={cvId: '3',cZone:'example.com'};})();</script>
</body></html>"""

CF_ATTENTION = """<html><head><title>Attention Required! | Cloudflare</title></head>
<body><h1>Sorry, you have been blocked</h1></body></html>"""

DATADOME = """<html><head><title>example.com</title></head><body>
<iframe src="https://geo.captcha-delivery.com/captcha/?initialCid=abc"></iframe></body></html>"""

PERIMETERX = """<html><body><div id="px-captcha"></div>
<p>Press and hold to confirm you are a human.</p></body></html>"""

AKAMAI = """<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>
<H1>Access Denied</H1>You don't have permission to access this server.
Reference #18.abcd https://errors.edgesuite.net/18.abcd</BODY></HTML>"""

RECAPTCHA_THIN = """<html><body><form><div class="g-recaptcha" data-sitekey="x"></div>
<p>Verify you are human</p></form></body></html>"""

RECAPTCHA_RICH_LOGIN = f"""<html><body><main>{PROSE}</main>
<form><div class="g-recaptcha" data-sitekey="x"></div></form></body></html>"""

JSON_BODY = '{"jobs": [{"id": 1, "title": "Data Engineer"}]}'

# ---------------------------------------------------------------- cases


def classifier_cases():
    v = probe.classify
    check("CRA shell -> js_rendered",
          v(200, HTML, CRA_SHELL) == ("js_rendered", "empty_mount_point"), v(200, HTML, CRA_SHELL))
    check("Next.js SSR with prose -> usable (challenge-platform script ignored)",
          v(200, HTML, NEXT_SSR) == ("usable", "content_present"), v(200, HTML, NEXT_SSR))
    check("Angular app-root shell -> js_rendered",
          v(200, HTML, ANGULAR_SHELL)[0] == "js_rendered", v(200, HTML, ANGULAR_SHELL))
    check("scripts and no text -> js_rendered",
          v(200, HTML, BARE_SCRIPTS) == ("js_rendered", "scripts_no_text"), v(200, HTML, BARE_SCRIPTS))
    check("'enable JavaScript' on thin page -> js_rendered",
          v(200, HTML, JS_NOTICE_THIN) == ("js_rendered", "enable_javascript_notice"),
          v(200, HTML, JS_NOTICE_THIN))
    check("'enable JavaScript' in noscript on rich page -> usable",
          v(200, HTML, JS_NOTICE_RICH)[0] == "usable", v(200, HTML, JS_NOTICE_RICH))

    check("Cloudflare 'Just a moment' 403 -> blocked, cloudflare reason",
          v(403, HTML, CF_CHALLENGE) == ("blocked", "cloudflare_challenge"), v(403, HTML, CF_CHALLENGE))
    check("Cloudflare challenge served as 200 still blocked",
          v(200, HTML, CF_CHALLENGE)[0] == "blocked", v(200, HTML, CF_CHALLENGE))
    check("cf-mitigated: challenge header -> blocked on any body",
          v(200, {"CF-Mitigated": "challenge", **HTML}, NEXT_SSR)
          == ("blocked", "cloudflare_challenge_header"))
    check("Cloudflare 'Attention Required' -> blocked",
          v(403, HTML, CF_ATTENTION) == ("blocked", "cloudflare_interstitial"), v(403, HTML, CF_ATTENTION))
    check("DataDome captcha -> blocked",
          v(403, HTML, DATADOME) == ("blocked", "datadome_captcha"), v(403, HTML, DATADOME))
    check("PerimeterX press-and-hold -> blocked",
          v(403, HTML, PERIMETERX) == ("blocked", "perimeterx_captcha"), v(403, HTML, PERIMETERX))
    check("Akamai Access Denied -> blocked",
          v(403, HTML, AKAMAI) == ("blocked", "akamai_access_denied"), v(403, HTML, AKAMAI))
    check("plain 403 -> blocked forbidden",
          v(403, HTML, "<html><body>Forbidden</body></html>") == ("blocked", "forbidden"))
    check("429 with empty body -> blocked rate_limited",
          v(429, {"Retry-After": "30"}, "") == ("blocked", "rate_limited"))
    check("reCAPTCHA on thin 200 page -> blocked",
          v(200, HTML, RECAPTCHA_THIN) == ("blocked", "captcha_or_challenge_page"),
          v(200, HTML, RECAPTCHA_THIN))
    check("reCAPTCHA on rich login page -> usable",
          v(200, HTML, RECAPTCHA_RICH_LOGIN)[0] == "usable", v(200, HTML, RECAPTCHA_RICH_LOGIN))

    check("JSON 200 -> usable",
          v(200, {"Content-Type": "application/json"}, JSON_BODY) == ("usable", "content_present"))
    check("404 -> error http_404",
          v(404, HTML, "<html><body>Not found</body></html>") == ("error", "http_404"))
    check("500 -> error http_500", v(500, HTML, "oops") == ("error", "http_500"))
    check("200 empty body -> error empty_body", v(200, HTML, "  \n") == ("error", "empty_body"))
    check("exception -> error with class name",
          v(None, {}, "", error="TimeoutError") == ("error", "TimeoutError"))
    check("header lookup is case-insensitive",
          probe.js_shell_reason(CRA_SHELL, "TEXT/HTML") == "empty_mount_point")
    check("non-HTML content type is never a shell",
          probe.js_shell_reason(CRA_SHELL, "text/plain") == "")


def robots_cases():
    url = "https://shop.example/p/123"
    rd = probe.robots_decision
    check("robots allows", rd(200, "User-agent: *\nDisallow: /admin\n", url)[:2]
          == (True, "robots_allows"))
    check("robots disallows all", rd(200, "User-agent: *\nDisallow: /\n", url)[:2]
          == (False, "robots_disallows"))
    check("robots disallows our agent by name",
          rd(200, "User-agent: signal-engine-probe\nDisallow: /p/\n\nUser-agent: *\nAllow: /\n", url)[:2]
          == (False, "robots_disallows"))
    check("crawl-delay read", rd(200, "User-agent: *\nCrawl-delay: 5\n", url) == (True, "robots_allows", 5.0))
    check("404 robots -> allowed", rd(404, "", url)[:2] == (True, "no_robots_txt"))
    check("403 robots -> skip", rd(403, "", url)[:2] == (False, "robots_http_403"))
    check("503 robots -> skip", rd(503, "", url)[:2] == (False, "robots_http_503"))
    check("unreachable robots -> skip", rd(None, "", url)[:2] == (False, "robots_unreachable"))
    check("empty 200 robots -> allowed", rd(200, "", url)[:2] == (True, "robots_allows"))


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def throttle_cases():
    c = FakeClock()
    th = probe.HostThrottle(1.5, clock=c.clock, sleep=c.sleep)
    check("first request to a host does not wait", th.wait("a.com") == 0.0)
    th.done("a.com")
    c.t += 0.5
    check("second request to same host waits the remainder", round(th.wait("a.com"), 3) == 1.0, c.slept)
    th.done("a.com")
    check("other host does not wait", th.wait("b.com") == 0.0)
    th.set_host_delay("a.com", 5)
    c.t += 2.0
    check("robots crawl-delay above --delay wins", round(th.wait("a.com"), 3) == 3.0, c.slept)
    th.set_host_delay("c.com", 9999)
    check("crawl-delay is capped", th.gap("c.com") == probe.MAX_CRAWL_DELAY)


def fake_fetch(status, body, headers=None, error=None, final=None):
    def f(url, timeout):
        return {"status": status, "headers": headers or HTML, "final_url": final or url,
                "error": error, "elapsed_ms": 120, "body_bytes": len(body.encode()),
                "body_truncated": False, "body": body}
    return f


def run_cases():
    c = FakeClock()
    calls = []

    def robots(origin, timeout):
        calls.append(("robots", origin))
        return (200, "User-agent: *\nDisallow: /private\n")

    def fetcher(url, timeout):
        calls.append(("get", url))
        return fake_fetch(200, NEXT_SSR, final=url.replace("http://", "https://"))(url, timeout)

    th = probe.HostThrottle(1.5, clock=c.clock, sleep=c.sleep)
    recs = probe.probe_all(
        ["http://s.example/a", "http://s.example/private/x", "http://s.example/b", "ftp://x/y"],
        1.5, 10, quiet=True, throttle=th, fetcher=fetcher, robots_fetcher=robots, allowlist={})
    verdicts = [r["verdict"] for r in recs]
    check("run verdicts", verdicts == ["usable", "skipped_robots", "usable", "error"], verdicts)
    check("disallowed URL never requested",
          ("get", "http://s.example/private/x") not in calls, calls)
    check("robots fetched once per origin", sum(1 for k, _ in calls if k == "robots") == 1, calls)
    check("same-host requests were spaced", len(c.slept) == 2 and all(s >= 1.5 for s in c.slept), c.slept)
    r = recs[0]
    check("redirect recorded", r["redirected"] is True and r["redirected_cross_host"] is False, r)
    check("no body in record", "body" not in r and all("Fresh price" not in str(x) for x in r.values()), r)
    check("record has all measurements",
          {"url", "probed_at", "status", "elapsed_ms", "final_url", "content_type",
           "content_length", "body_bytes", "js_shell", "blocked", "verdict"} <= set(r), sorted(r))


def allowlist_cases():
    al = {"api.ats.example": {"reason": "documented public API", "doc_url": "https://docs.example/api"}}
    rd = probe.robots_decision
    got = rd(401, "", "https://api.ats.example/board/x", allowlist=al)
    check("allowlisted host, robots 401 -> proceeds as allowlisted", got[:2] == (True, "allowlisted"), got)
    got = rd(403, "", "https://API.ats.example/board/x", allowlist=al)
    check("allowlisted host, robots 403, case-insensitive -> allowlisted", got[:2] == (True, "allowlisted"), got)
    got = rd(401, "", "https://other.example/board/x", allowlist=al)
    check("non-allowlisted host, robots 401 -> skips", got[:2] == (False, "robots_http_401"), got)
    got = rd(200, "User-agent: *\nDisallow: /board/\n", "https://api.ats.example/board/x", allowlist=al)
    check("allowlisted host whose robots loads and disallows -> skips",
          got[:2] == (False, "robots_disallows"), got)
    got = rd(503, "", "https://api.ats.example/board/x", allowlist=al)
    check("allowlist does not cover robots 5xx", got[:2] == (False, "robots_http_503"), got)

    c = FakeClock()
    th = probe.HostThrottle(1.5, clock=c.clock, sleep=c.sleep)
    recs = probe.probe_all(["https://api.ats.example/board/x", "https://other.example/y"], 1.5, 10,
                           quiet=True, throttle=th, allowlist=al,
                           fetcher=fake_fetch(200, JSON_BODY, {"Content-Type": "application/json"}),
                           robots_fetcher=lambda o, t: (401, ""))
    check("allowlisted record carries status, reason and doc",
          recs[0]["verdict"] == "usable" and recs[0]["robots_status"] == "allowlisted"
          and recs[0]["robots_allowlist_reason"] == "documented public API"
          and recs[0]["robots_allowlist_doc"] == "https://docs.example/api", recs[0])
    check("non-allowlisted record skipped in same run",
          recs[1]["verdict"] == "skipped_robots" and recs[1]["robots_status"] == "robots_http_401"
          and recs[1]["robots_allowlist_reason"] is None, recs[1])

    real = probe.load_allowlist()
    check("seed allowlist loads api.ashbyhq.com with reason and doc",
          "api.ashbyhq.com" in real and real["api.ashbyhq.com"]["doc_url"].startswith("https://")
          and "401" in real["api.ashbyhq.com"]["reason"], real)
    with tempfile.TemporaryDirectory() as d:
        check("missing allowlist file -> empty", probe.load_allowlist(Path(d) / "nope.csv") == {})


def redirect_cases():
    h = probe.SameHostRedirectHandler()
    req = urllib.request.Request("https://jobs.example/a")
    got = h.redirect_request(req, None, 301, "Moved", {}, "https://jobs.example/b")
    check("same-host redirect is followed",
          got is not None and got.full_url == "https://jobs.example/b", got)
    try:
        h.redirect_request(req, None, 302, "Found", {}, "https://other.example/b")
        check("cross-host redirect refused", False, "no exception")
    except probe.CrossHostRedirect as e:
        check("cross-host redirect refused", e.target == "https://other.example/b" and e.code == 302)
    try:
        h.redirect_request(req, None, 301, "Moved", {}, "https://www.jobs.example/a")
        check("www. subdomain counts as a different host", False, "no exception")
    except probe.CrossHostRedirect:
        check("www. subdomain counts as a different host", True)

    f = fake_fetch(302, "")("https://jobs.example/a", 10)
    f["redirect_target"] = "https://other.example/b"
    r = probe.build_record("https://jobs.example/a", "t", "robots_allows", f)
    check("cross-host record is skipped_redirect with target and note",
          r["verdict"] == "skipped_redirect" and r["redirect_target"] == "https://other.example/b"
          and "--url" in r["note"] and r["status"] == 302, r)
    f = fake_fetch(200, NEXT_SSR, final="https://jobs.example/b")("https://jobs.example/a", 10)
    r = probe.build_record("https://jobs.example/a", "t", "robots_allows", f)
    check("same-host redirect record is classified normally",
          r["verdict"] == "usable" and r["redirected"] and not r["redirected_cross_host"]
          and r["redirect_target"] is None, r)


def log_cases():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "out" / "probe_log.json"
        probe.append_log(p, [{"verdict": "usable", "elapsed_ms": 10}])
        n = probe.append_log(p, [{"verdict": "blocked", "elapsed_ms": 30}])
        data = json.loads(p.read_text(encoding="utf-8"))
        check("log appends to existing list", n == 2 and [x["verdict"] for x in data] == ["usable", "blocked"])
        p.write_text('{"not": "a list"}', encoding="utf-8")
        try:
            probe.append_log(p, [{}])
            check("refuses to overwrite non-list log", False)
        except SystemExit:
            check("refuses to overwrite non-list log",
                  json.loads(p.read_text(encoding="utf-8")) == {"not": "a list"})

        f = Path(d) / "urls.txt"
        f.write_text("# list\nhttps://a.example/\n\nhttps://a.example/\nhttps://b.example/\n", encoding="utf-8")
        got = probe.load_urls(str(f), ["https://b.example/", "https://c.example/"])
        check("load_urls dedupes and skips comments",
              got == ["https://a.example/", "https://b.example/", "https://c.example/"], got)

    s = probe.summarize([{"verdict": "usable", "elapsed_ms": 100},
                         {"verdict": "blocked", "elapsed_ms": 300},
                         {"verdict": "error", "elapsed_ms": 200},
                         {"verdict": "skipped_robots", "elapsed_ms": None}])
    check("summary median ignores skipped", "median elapsed   200 ms" in s, s)
    check("summary counts every verdict", all(v in s for v in probe.VERDICTS), s)


def main():
    classifier_cases()
    robots_cases()
    throttle_cases()
    run_cases()
    redirect_cases()
    allowlist_cases()
    log_cases()
    check("no network touched", not NETWORK_TOUCHED, NETWORK_TOUCHED)
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'ALL PASSED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
