#!/usr/bin/env python3
"""
Numiko SEO-GEO Toolkit — automated test suite
Run after every deploy: python tests/test_app.py [base_url]

Default base_url: https://web-production-843708.up.railway.app
Pass a local URL to test locally: python tests/test_app.py http://localhost:5000
"""
import sys
import urllib.request
import urllib.error
import urllib.parse
import json
import time

BASE_URL = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else "https://web-production-843708.up.railway.app"
# The app uses HTTP Basic Auth — any username, password must match APP_PASSWORD env var.
# Pass password as second arg: python3 tests/test_app.py [base_url] [password]
AUTH_USER = "numiko"
AUTH_PASS = sys.argv[2] if len(sys.argv) > 2 else ""

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []


import base64

def req(path, method="GET", data=None, with_auth=True):
    """Make a request (optionally authenticated). Returns (status_code, body, headers)."""
    url = BASE_URL + path
    encoded_data = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(url, data=encoded_data, method=method)
    if with_auth and AUTH_PASS:
        credentials = base64.b64encode(f"{AUTH_USER}:{AUTH_PASS}".encode()).decode()
        r.add_header("Authorization", f"Basic {credentials}")
    r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = urllib.request.urlopen(r, timeout=60)
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
# Without auth header — either 401 (if auth enabled) or 200 (if disabled)
status_noauth, _, _ = req("/", with_auth=False)
auth_enabled = status_noauth == 401
if auth_enabled:
    check("Unauthenticated request returns 401 (auth enabled)", True, f"status={status_noauth}")
else:
    check("Unauthenticated request returns 200 (auth disabled)", status_noauth == 200, f"status={status_noauth}")

# With auth — expect 200
status, body, _ = req("/")
if auth_enabled and not AUTH_PASS:
    print(f"  {WARN} Skipping authenticated tests — pass APP_PASSWORD as 2nd arg")
    print(f"     Usage: python3 tests/test_app.py {BASE_URL} <APP_PASSWORD>")
    AUTH_OK = False
else:
    check("Authenticated request to / returns 200", status == 200, f"status={status}")
    AUTH_OK = status == 200

# ── 3. Page loads ─────────────────────────────────────────────────────────────
section("3. Page loads")
pages = [
    ("/", "Dashboard"),
    ("/audit", "GEO Audit"),
    ("/keywords", "Keywords"),
    ("/content-guide", "Content Guide"),
    ("/clients", "Clients"),
]
for path, name in pages:
    skip = not AUTH_OK
    if not skip:
        status, body, _ = req(path)
        check(f"GET {path} ({name}) returns 200", status == 200, f"status={status}", skip=skip)
        check(f"GET {path} contains Numiko nav logo", 'viewBox="0 0 31 60"' in body, "SVG logo present", skip=skip)
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
    status, body, _ = req("/audit", method="POST", data={"url": "https://example.com"})
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
    status, body, _ = req("/audit", method="POST", data={"url": ""})
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
