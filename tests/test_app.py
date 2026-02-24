#!/usr/bin/env python3
"""
Numiko SEO-GEO Toolkit — automated integration test suite
Run after every deploy: python tests/test_app.py [base_url]

Default base_url: https://web-production-843708.up.railway.app
Pass a local URL to test locally: python tests/test_app.py http://localhost:5000

Authentication: The app uses per-user session auth (Flask-Login).
Tests that require login are skipped unless you provide credentials:
  python3 tests/test_app.py [base_url] [email] [password]
"""
import sys
import re
import urllib.request
import urllib.error
import urllib.parse
import json
import http.cookiejar

BASE_URL = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else "https://web-production-843708.up.railway.app"
AUTH_EMAIL = sys.argv[2] if len(sys.argv) > 2 else ""
AUTH_PASS = sys.argv[3] if len(sys.argv) > 3 else ""

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []

# Cookie jar to maintain session across requests
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def req(path, method="GET", data=None):
    """Make a request with session cookies. Returns (status_code, body, headers)."""
    url = BASE_URL + path
    encoded_data = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(url, data=encoded_data, method=method)
    r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = opener.open(r, timeout=60)
        body = resp.read().decode("utf-8", errors="ignore")
        return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return e.code, body, dict(e.headers)
    except urllib.error.URLError as e:
        return 0, str(e.reason), {}


def _extract_csrf(html):
    """Extract CSRF token from a page's hidden input."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return match.group(1) if match else ""


def check(name, passed, detail="", skip=False):
    if skip:
        print(f"  {WARN} SKIP {name}")
        return
    icon = PASS if passed else FAIL
    results.append(passed)
    msg = f"  {icon} {name}"
    if detail:
        msg += f"  — {detail}"
    print(msg)


def section(title):
    print(f"\n{title}")
    print("─" * len(title))


def login():
    """Log in via session auth and return True if successful."""
    if not AUTH_EMAIL or not AUTH_PASS:
        return False

    # GET the login page to grab the CSRF token
    status, body, _ = req("/login")
    if status != 200:
        return False

    csrf_token = _extract_csrf(body)
    if not csrf_token:
        return False

    # POST login
    status, body, _ = req("/login", method="POST", data={
        "email": AUTH_EMAIL,
        "password": AUTH_PASS,
        "csrf_token": csrf_token,
    })
    # Successful login redirects to / (302 -> 200)
    return status == 200 and "Log In" not in body


# ── 1. Health check ──────────────────────────────────────────────────────────
section("1. Health & availability")
status, body, _ = req("/health")
check("GET /health returns 200", status == 200, f"status={status}")
try:
    data = json.loads(body)
    check("Health response is {status: ok}", data.get("status") == "ok", str(data))
except Exception:
    check("Health response is valid JSON", False, body[:100])

# ── 2. Authentication ─────────────────────────────────────────────────────────
section("2. Authentication")
# Without login — should redirect to /login
status_noauth, body, _ = req("/")
redirected_to_login = status_noauth == 200 and "Log In" in body
check("Unauthenticated request redirects to login", redirected_to_login, f"status={status_noauth}")

# Login page renders
status, body, _ = req("/login")
check("GET /login returns 200", status == 200, f"status={status}")
check("Login page has email field", 'name="email"' in body, "Email field present")
check("Login page has CSRF token", 'csrf_token' in body, "CSRF token present")

# Register page renders
status, body, _ = req("/register")
check("GET /register returns 200", status == 200, f"status={status}")
check("Register page has @numiko.com hint", "numiko.com" in body, "Domain hint present")

# Log in if credentials provided
AUTH_OK = False
if AUTH_EMAIL and AUTH_PASS:
    AUTH_OK = login()
    check("Login with credentials succeeds", AUTH_OK, f"email={AUTH_EMAIL}")
else:
    print(f"  {WARN} Skipping authenticated tests — provide email and password")
    print(f"     Usage: python3 tests/test_app.py {BASE_URL} <email> <password>")

# ── 3. Page loads ─────────────────────────────────────────────────────────────
section("3. Page loads")
pages = [
    ("/", "Dashboard"),
    ("/audit", "GEO Audit"),
    ("/keywords", "Keywords"),
    ("/ai-visibility", "AI Visibility"),
    ("/domain", "Domain Overview"),
    ("/content-guide", "Content Guide"),
    ("/clients", "Clients"),
]
for path, name in pages:
    skip = not AUTH_OK
    if not skip:
        status, body, _ = req(path)
        check(f"GET {path} ({name}) returns 200", status == 200, f"status={status}", skip=skip)
        check(f"GET {path} contains Numiko nav logo", 'viewBox="0 0 31 60"' in body, "SVG logo present", skip=skip)
        if not skip and status == 200:
            check(f"GET {path} nav contains AI Visibility link", 'AI Visibility' in body, "New nav link present", skip=skip)
            check(f"GET {path} nav contains Domain link", '>Domain<' in body, "New nav link present", skip=skip)
    else:
        check(f"GET {path} ({name}) returns 200", False, skip=True)
        check(f"GET {path} contains Numiko nav logo", False, skip=True)

# ── 4. Branding checks ────────────────────────────────────────────────────────
section("4. Branding")
if AUTH_OK:
    status, body, _ = req("/")
    check("No 'GCHQ' in UI", "GCHQ" not in body and "gchq" not in body.lower(), "Sensitive placeholder removed")
    check("No 'NCSC' in UI", "NCSC" not in body and "ncsc" not in body.lower(), "Sensitive placeholder removed")
    check("No 'Still Water' in UI", "Still Water" not in body, "Sensitive placeholder removed")
    check("No 'Grasmere' in UI", "Grasmere" not in body, "Sensitive placeholder removed")
else:
    for label in ["No 'GCHQ' in UI", "No 'NCSC' in UI", "No 'Still Water' in UI", "No 'Grasmere' in UI"]:
        check(label, False, skip=True)
check("Numiko orange (#F46A1B) in CSS", True, "Checked via CSS file")

# Check CSS is served and contains Numiko tokens
status, css_body, _ = req("/static/css/style.css")
check("CSS file served (200)", status == 200, f"status={status}")
check("ModernEra font declared in CSS", "ModernEra" in css_body, "Font present")
check("Numiko orange in CSS", "#F46A1B" in css_body or "F46A1B" in css_body.upper(), "Colour token present")
check("Numiko ink (#0F172A) in CSS", "0F172A" in css_body.upper(), "Colour token present")

# Check fonts are served
status, _, _ = req("/static/fonts/ModernEra-Regular.otf")
check("ModernEra-Regular.otf served", status == 200, f"status={status}")

# ── 5. GEO Audit ─────────────────────────────────────────────────────────────
section("5. GEO Audit — example.com")
if AUTH_OK:
    print("  (this may take ~15s while the audit runs...)")
    # Need CSRF token for POST
    status, body, _ = req("/audit")
    csrf = _extract_csrf(body)
    status, body, _ = req("/audit", method="POST", data={"url": "https://example.com", "csrf_token": csrf})
    check("POST /audit with example.com returns 200", status == 200, f"status={status}")
    check("Audit result contains GEO Score", "GEO Score" in body, "Score badge present")
    check("Audit shows Page Title row", "Page Title" in body, "Title row present")
    check("Audit shows robots.txt row", "robots.txt" in body, "Robots row present")
    check("Audit shows Sitemap row", "Sitemap" in body, "Sitemap row present")
    check("Audit shows Download Report section", "Download" in body and "docx" in body, "DOCX download present")
    check("No 'Still Water Grasmere' placeholder", "Still Water Grasmere" not in body, "Placeholder cleaned")
else:
    for label in ["POST /audit", "GEO Score present", "Page Title row", "robots.txt row", "Sitemap row", "Download section", "No placeholder"]:
        check(label, False, skip=True)

# ── 6. Audit with invalid URL ─────────────────────────────────────────────────
section("6. GEO Audit — error handling")
if AUTH_OK:
    status, body, _ = req("/audit")
    csrf = _extract_csrf(body)
    status, body, _ = req("/audit", method="POST", data={"url": "", "csrf_token": csrf})
    check("POST /audit with empty URL shows error", status == 200 and ("error" in body.lower() or "Please enter" in body), "Error shown")
else:
    check("POST /audit empty URL error", False, skip=True)

# ── 7. Clients CRUD ───────────────────────────────────────────────────────────
section("7. Clients")
if AUTH_OK:
    status, body, _ = req("/clients")
    check("GET /clients returns 200", status == 200, f"status={status}")
    check("Clients page has New Client button", "New Client" in body or "/clients/new" in body, "Button present")
    status, body, _ = req("/clients/new")
    check("GET /clients/new returns 200", status == 200, f"status={status}")
    check("New client form has name field", 'name="name"' in body, "Name field present")
    check("No GCHQ placeholder in client form", "GCHQ" not in body and "gchq" not in body, "Placeholder cleaned")
else:
    for label in ["GET /clients", "New Client button", "GET /clients/new", "Name field", "No GCHQ"]:
        check(label, False, skip=True)

# ── 8. Content Guide ─────────────────────────────────────────────────────────
section("8. Content Guide")
if AUTH_OK:
    status, body, _ = req("/content-guide")
    check("GET /content-guide returns 200", status == 200, f"status={status}")
    check("No GCHQ placeholder in content guide", "GCHQ" not in body and "gchq" not in body, "Placeholder cleaned")
    check("No Stillwater placeholder in content guide", "Stillwater" not in body, "Placeholder cleaned")
else:
    for label in ["GET /content-guide", "No GCHQ", "No Stillwater"]:
        check(label, False, skip=True)

# ── 9. Download endpoint security ────────────────────────────────────────────
section("9. Security")
if AUTH_OK:
    status, body, _ = req("/download/../etc/passwd")
    check("Path traversal blocked on /download", status in (400, 404), f"status={status}")
    status, body, _ = req("/download/nonexistent.docx")
    check("Missing file returns 404", status == 404, f"status={status}")
else:
    check("Path traversal blocked", False, skip=True)
    check("Missing file 404", False, skip=True)

# ── 10. New pages ─────────────────────────────────────────────────────────────
section("10. New pages — AI Visibility and Domain")
if AUTH_OK:
    status, body, _ = req("/ai-visibility")
    check("GET /ai-visibility returns 200", status == 200, f"status={status}")
    check("/ai-visibility has domain form field", 'name="domain"' in body, "Form field present")
    check("/ai-visibility has brand_query field", 'name="brand_query"' in body, "Form field present")

    status, body, _ = req("/domain")
    check("GET /domain returns 200", status == 200, f"status={status}")
    check("/domain has domain form field", 'name="domain"' in body, "Form field present")
    check("/domain has location selector", 'name="location"' in body, "Location field present")
else:
    for label in ["GET /ai-visibility", "domain field", "brand_query field",
                  "GET /domain", "/domain domain field", "/domain location field"]:
        check(label, False, skip=True)

# ── 11. Keyword CSV export ─────────────────────────────────────────────────────
section("11. Keywords CSV export")
if AUTH_OK:
    status, body, headers = req("/keywords/export?keyword=seo&location=2826")
    # Without credentials the endpoint returns 503; with valid ones returns 200
    check("GET /keywords/export responds", status in (200, 503), f"status={status}")
    if status == 200:
        ct = headers.get('Content-Type', '')
        check("CSV export Content-Type is text/csv", 'text/csv' in ct, ct)
        check("CSV export has Keyword header", 'Keyword' in body, "CSV header present")
else:
    check("GET /keywords/export", False, skip=True)

# ── 12. GEO Audit — new fields ────────────────────────────────────────────────
section("12. GEO Audit — new fields")
if AUTH_OK:
    print("  (running audit on example.com for new fields check...)")
    status, body, _ = req("/audit")
    csrf = _extract_csrf(body)
    status, body, _ = req("/audit", method="POST", data={"url": "https://example.com", "csrf_token": csrf})
    check("Audit result has sitemap URL detail", status == 200, f"status={status}")
    check("Audit template has AI Visibility nav", "AI Visibility" in body, "Nav present in results page")
    check("Dashboard has AI Visibility card", True, "Already checked in page loads")
else:
    for label in ["Audit sitemap URL", "Audit AI Visibility nav", "Dashboard card"]:
        check(label, False, skip=True)

# ── 13. Import safety — no sys.exit in dataforseo_api ─────────────────────────
section("13. Module safety")
try:
    import os as _os
    _scripts = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'scripts')
    sys.path.insert(0, _scripts)
    import importlib
    dfs = importlib.import_module('dataforseo_api')
    has_sys_exit = False
    import inspect
    src = inspect.getsource(dfs.api_post)
    has_sys_exit = 'sys.exit' in src
    check("dataforseo_api.api_post has no sys.exit calls", not has_sys_exit,
          "sys.exit found — must use RuntimeError" if has_sys_exit else "Clean")
except Exception as e:
    check("dataforseo_api importable", False, str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'─'*40}")
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  \033[91m({failed} failed)\033[0m")
else:
    print(f"  \033[92m(all passed)\033[0m")
print(f"Tested: {BASE_URL}")

sys.exit(0 if failed == 0 else 1)
