# Numiko SEO-GEO Toolkit

> Internal tool for Generative Engine Optimization (GEO) and SEO workflows — built for the Numiko digital agency team.

**Live:** https://web-production-843708.up.railway.app
**GitHub:** https://github.com/d3ccy/SEO-GEO
**Stack:** Flask · Python 3 · DataForSEO API · Gunicorn · Railway

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [Architecture Overview](#2-architecture-overview)
3. [File Reference](#3-file-reference)
4. [Routes Reference](#4-routes-reference)
5. [Services & Return Types](#5-services--return-types)
6. [DataForSEO Endpoints](#6-dataforseo-endpoints)
7. [Environment Variables](#7-environment-variables)
8. [Local Development Setup](#8-local-development-setup)
9. [Deployment](#9-deployment)
10. [Testing](#10-testing)
11. [How to Extend: Adding a New Tool](#11-how-to-extend-adding-a-new-tool)
12. [GEO Scoring Algorithm](#12-geo-scoring-algorithm)
13. [Key Design Decisions](#13-key-design-decisions)

---

## 1. What This Is

The SEO-GEO Toolkit is a Flask web application used internally by Numiko. It provides six tools:

| Tool | API Required | Purpose |
|------|-------------|---------|
| **GEO Audit** | No | Audit any URL for technical SEO/GEO readiness. Returns 0–100 score. |
| **Keyword Research** | DataForSEO | Keyword suggestions with volume, difficulty, intent, CPC, AI search volume. |
| **AI Visibility** | DataForSEO (AI Optimization plan) | Check if a domain/brand is mentioned by ChatGPT, Claude, Gemini, Perplexity. |
| **Domain Overview** | DataForSEO | Domain rank, top keywords, organic competitors, backlink metrics. |
| **Content Guide** | No | Generate a branded DOCX writing guide (based on Princeton GEO research). |
| **Client Profiles** | No | Save client details; profiles auto-fill forms across all tools. |

**Audience:** Numiko strategists and the developers maintaining the app.

---

## 2. Architecture Overview

```
Browser
  │
  ▼
Flask app  (webapp/app.py)
  ├── auth.py              HTTP Basic Auth decorator (@requires_auth)
  ├── config.py            All env var reads → Config class
  ├── client_store.py      CRUD on webapp/data/clients.json
  │
  ├── services/
  │     ├── audit_service.py         run_audit()         → scripts/seo_audit.py
  │     ├── keyword_service.py       run_keyword_research() → DataForSEO API
  │     ├── ai_visibility_service.py run_ai_visibility() → DataForSEO AI API
  │     ├── domain_service.py        run_domain_overview() → DataForSEO API
  │     └── report_service.py        generate_*_docx()   → report_generators/
  │
  ├── report_generators/
  │     ├── geo_audit_report.py      GEO Audit DOCX (python-docx)
  │     ├── content_guide.py         Content Guide DOCX (python-docx)
  │     └── docx_helpers.py          Shared colour constants + paragraph helpers
  │
  ├── templates/  (Jinja2, 9 files + 6 partials)
  └── static/     (CSS + JS + Numiko fonts)
  │
  ▼
DataForSEO REST API   (Basic Auth, JSON over HTTPS)
  https://api.dataforseo.com/v3/

Persistence
  webapp/data/clients.json   (flat JSON array, gitignored)
  /tmp/seo-geo-reports/      (generated DOCX files, ephemeral)
  webapp/uploads/            (logo uploads, ephemeral)
```

**Key architectural rules:**
- `scripts/` contains standalone CLI-runnable tools. Services add them to `sys.path` at import time.
- Every DataForSEO call in a service is individually wrapped in `try/except` — partial failures return whatever data was retrieved.
- `scripts/dataforseo_api.py` raises `RuntimeError` on any failure; it never calls `sys.exit()`.

---

## 3. File Reference

```
webapp/
├── app.py                   Flask routes + request handling + flash messages (356 lines)
├── config.py                Reads all env vars; sets paths, constants, upload limits
├── auth.py                  requires_auth() decorator factory for HTTP Basic Auth
├── client_store.py          CRUD: load_clients(), save_client(), get_client(), delete_client()
│
├── services/
│   ├── audit_service.py     run_audit(url) → dict  (no API needed for core audit)
│   ├── keyword_service.py   run_keyword_research(keyword, location_code, limit) → dict
│   ├── ai_visibility_service.py  run_ai_visibility(domain, brand_query) → dict
│   ├── domain_service.py    run_domain_overview(domain, location_code) → dict
│   └── report_service.py    generate_content_guide_docx() / generate_geo_audit_docx()
│
├── report_generators/
│   ├── geo_audit_report.py  Branded GEO audit report; score colour-coded; Section 5 = backlinks
│   ├── content_guide.py     100+ page GEO/SEO content writing guide
│   └── docx_helpers.py      Numiko colour constants + shared table/paragraph builders
│
├── templates/
│   ├── base.html            Nav, container, flash messages, JS include
│   ├── index.html           Dashboard — 6 tool cards
│   ├── audit.html           GEO Audit form + results table + DOCX download form
│   ├── keywords.html        Keyword Research form + sortable table + CSV export
│   ├── ai_visibility.html   3-panel AI visibility results (mentions, ChatGPT, multi-LLM)
│   ├── domain.html          4-section domain overview
│   ├── content_guide.html   Content Guide form
│   ├── clients.html         Client list table
│   ├── client_form.html     Create/edit client form
│   └── partials/
│       ├── how_to_audit.html
│       ├── how_to_keywords.html
│       ├── how_to_ai_visibility.html
│       ├── how_to_domain.html
│       ├── how_to_content_guide.html
│       └── how_to_clients.html
│
├── static/
│   ├── css/style.css        All styles — Numiko brand tokens, component classes
│   └── js/main.js           Tab switching, client auto-fill, table sorting, loading states
│
├── data/clients.json        Saved client profiles (gitignored — ephemeral on free hosting)
└── uploads/                 Temporary logo uploads (gitignored)

scripts/
├── seo_audit.py             Core audit: fetch_url(), extract_meta(), check_robots(), check_sitemap()
├── dataforseo_api.py        DataForSEO HTTP wrapper: api_post(), get_result(), format_count()
└── credential.py            get_dataforseo_credentials() — reads DATAFORSEO_* env vars

fonts/
└── numiko_logo.png          Default agency logo for DOCX reports

tests/
└── test_app.py              Integration test suite (stdlib only — no pytest needed)

Procfile                     gunicorn webapp.app:app (Railway/Render)
requirements.txt             Python dependencies
.env.example                 Environment variable template
DEPLOY.md                    Full Railway + Render deployment guide
```

---

## 4. Routes Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✓ | Dashboard (6 tool cards, saved client list) |
| GET/POST | `/audit` | ✓ | GEO Audit — form + results |
| POST | `/audit-report` | ✓ | Generate + stream GEO Audit DOCX |
| GET/POST | `/keywords` | ✓ | Keyword Research — form + sortable results |
| GET | `/keywords/export` | ✓ | CSV export (query params: `keyword`, `location`) |
| GET/POST | `/ai-visibility` | ✓ | AI Visibility — LLM mentions + ChatGPT + multi-LLM |
| GET/POST | `/domain` | ✓ | Domain Overview — rank, keywords, competitors, backlinks |
| GET/POST | `/content-guide` | ✓ | Generate Content Guide DOCX |
| GET | `/clients` | ✓ | List saved client profiles |
| GET/POST | `/clients/new` | ✓ | Create client profile |
| GET/POST | `/clients/<id>/edit` | ✓ | Edit client profile |
| POST | `/clients/<id>/delete` | ✓ | Delete client profile |
| GET | `/download/<filename>` | ✓ | Serve generated DOCX from OUTPUT_DIR (path traversal blocked) |
| GET | `/health` | ✗ | `{"status": "ok"}` — used by Railway health checks |

**Auth column:** ✓ = protected by `@requires_auth` when `APP_PASSWORD` env var is set.

---

## 5. Services & Return Types

### `audit_service.run_audit(url: str) → dict`

No DataForSEO credentials needed for the core audit. Backlinks data (optional) is fetched if credentials are present but **does not affect the score**.

```python
{
    'url': str,
    'page_blocked': bool,          # True if WAF/Cloudflare blocked the main page
    'block_reason': str | None,    # Error string if blocked, else None
    'title': str,
    'title_length': int,
    'title_ok': bool,              # 0 < length ≤ 60
    'description': str,
    'description_length': int,
    'description_ok': bool,        # 0 < length ≤ 155
    'og_tags': bool,
    'h1': str | None,
    'jsonld_count': int,
    'load_time': float | None,     # seconds; None if page blocked
    'load_time_ok': bool,          # load_time < 3s
    'robots_exists': bool,
    'ai_bots': list[str],          # bots EXPLICITLY allowed in robots.txt
    'ai_bots_blocked': list[str],  # bots EXPLICITLY disallowed in robots.txt
    'has_sitemap': bool,
    'sitemap_url': str | None,     # URL where sitemap was found
    'backlinks_rank': int | None,
    'referring_domains': int | None,
    'total_backlinks': int | None,
    'score': int,                  # 0–100 GEO readiness score
}
```

### `keyword_service.run_keyword_research(keyword, location_code=2826, limit=20) → dict`

```python
{
    'seed_keyword': str,
    'location_code': int,
    'count': int,
    'keywords': [{
        'keyword': str,
        'volume': str,          # formatted: "1.2M"
        'volume_raw': int,
        'difficulty': int | str,  # 0–100 or "N/A"
        'competition': str,     # "LOW" / "MEDIUM" / "HIGH"
        'cpc': str,             # formatted: "1.23" or "—"
        'cpc_raw': float,
        'intent': str | None,   # "informational" / "navigational" / "commercial" / "transactional"
        'ai_volume': str | None,  # formatted: "50K" or None
        'ai_volume_raw': int,
    }]
}
```

DataForSEO calls (sequential, each individually try/excepted):
1. `keywords_data/google_ads/keywords_for_keywords/live` — seed keywords + volume + CPC
2. `dataforseo_labs/google/bulk_keyword_difficulty/live` — KD scores
3. `dataforseo_labs/google/search_intent/live` — intent classification
4. `ai_optimization/ai_keyword_data/keywords_search_volume/live` — AI search volume

### `ai_visibility_service.run_ai_visibility(domain, brand_query, location_code=2826) → dict`

```python
{
    'domain': str,
    'brand_query': str,
    'mentions': list | None,   # None = API call failed; [] = no mentions found
    'chatgpt': dict | None,
    'llm_responses': list,
    'errors': list[str],       # one entry per failed API call
}

# mentions items:
{
    'question': str,           # the AI-generated question where domain was cited
    'answer_snippet': str,     # first 300 chars of the answer
    'ai_search_volume': int,
    'platform': str,
    'source_domains': list[str],
}

# chatgpt dict:
{
    'answer': str | None,
    'sources': [{'title': str, 'url': str, 'domain': str}],
    'domain_mentioned': bool,
}

# llm_responses items:
{
    'platform': str,           # "ChatGPT" / "Claude" / "Gemini" / "Perplexity"
    'response': str,
    'domain_mentioned': bool,
}
```

DataForSEO calls (each individually try/excepted):
1. `ai_optimization/llm_mentions/search/live` — LLM mention search
2. `ai_optimization/chat_gpt/llm_scraper/live/advanced` — ChatGPT search scrape
3. `ai_optimization/{platform}/llm_responses/live` × 4 — one call per LLM platform

### `domain_service.run_domain_overview(domain, location_code=2826) → dict`

```python
{
    'domain': str,
    'location_code': int,
    'rank_overview': {
        'rank': int,
        'etv': str,            # formatted: "1.2M"
        'keywords_count': str,
        'pos_1_3': int,
        'pos_4_10': int,
    } | None,
    'keywords': [{
        'keyword': str,
        'position': int,
        'volume': str,
        'volume_raw': int,
        'url': str,
    }],
    'competitors': [{
        'domain': str,
        'common_keywords': int,
        'relevance': float,
        'domain_rank': int,
    }],
    'backlinks': {
        'rank': int,
        'referring_domains': int,
        'backlinks': int,
        'nofollow': int,
        'dofollow': int,
    } | None,
    'errors': list[str],
}
```

DataForSEO calls (sequential, each individually try/excepted):
1. `dataforseo_labs/google/domain_rank_overview/live`
2. `dataforseo_labs/google/ranked_keywords/live` (top 20 by volume)
3. `dataforseo_labs/google/competitors_domain/live` (top 10)
4. `backlinks/summary/live`

---

## 6. DataForSEO Endpoints

Base URL: `https://api.dataforseo.com/v3/`
Auth: HTTP Basic (base64 `login:password` header)
All requests: POST with JSON array body `[{...task...}]`
Success status: `tasks[0].status_code == 20000`

| Endpoint | Service | Purpose |
|----------|---------|---------|
| `keywords_data/google_ads/keywords_for_keywords/live` | keyword_service | Related keywords, volume, CPC |
| `dataforseo_labs/google/bulk_keyword_difficulty/live` | keyword_service | Difficulty scores (0–100) for keyword list |
| `dataforseo_labs/google/search_intent/live` | keyword_service | Intent classification per keyword |
| `ai_optimization/ai_keyword_data/keywords_search_volume/live` | keyword_service | AI search volume (ChatGPT/Perplexity queries) |
| `ai_optimization/llm_mentions/search/live` | ai_visibility_service | Questions where domain is cited in LLM answers |
| `ai_optimization/chat_gpt/llm_scraper/live/advanced` | ai_visibility_service | Live ChatGPT search result + cited sources |
| `ai_optimization/chat_gpt/llm_responses/live` | ai_visibility_service | ChatGPT response to brand query |
| `ai_optimization/claude/llm_responses/live` | ai_visibility_service | Claude response to brand query |
| `ai_optimization/gemini/llm_responses/live` | ai_visibility_service | Gemini response to brand query |
| `ai_optimization/perplexity/llm_responses/live` | ai_visibility_service | Perplexity response to brand query |
| `dataforseo_labs/google/domain_rank_overview/live` | domain_service | Domain authority rank + traffic estimate |
| `dataforseo_labs/google/ranked_keywords/live` | domain_service | Top 20 keywords by volume |
| `dataforseo_labs/google/competitors_domain/live` | domain_service | Top 10 organic competitors |
| `backlinks/summary/live` | domain_service + audit_service | Referring domains, total backlinks, rank |

**Important:** The AI Optimization endpoints (`ai_optimization/`) require the DataForSEO AI Optimization API plan (separate from the standard plan). LLM Responses endpoints also require per-platform plan access.

---

## 7. Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATAFORSEO_LOGIN` | For API tools | — | DataForSEO account email |
| `DATAFORSEO_PASSWORD` | For API tools | — | DataForSEO account password |
| `SECRET_KEY` | Yes (production) | `dev-secret-change-in-prod` | Flask session secret — use `openssl rand -hex 32` |
| `APP_PASSWORD` | No | `""` (disabled) | Enables HTTP Basic Auth on all routes. Any username accepted. |
| `OUTPUT_DIR` | No | `/tmp/seo-geo-reports` | Where DOCX files are written |
| `PORT` | Auto | `5000` | Set automatically by Railway; Gunicorn binds `$PORT` |

**GEO Audit** and **Content Guide** work without DataForSEO credentials.
**Keywords**, **AI Visibility**, and **Domain Overview** all require credentials.
**AI Visibility** additionally requires the AI Optimization API plan.

---

## 8. Local Development Setup

**Prerequisites:** Python 3.10+

```bash
# 1. Clone
git clone https://github.com/d3ccy/SEO-GEO.git
cd SEO-GEO

# 2. Virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, SECRET_KEY

# 5. Run
flask --app webapp/app run --debug
# or from repo root:
gunicorn webapp.app:app --bind 0.0.0.0:5000 --workers 1 --timeout 120

# 6. Verify
curl http://localhost:5000/health
# → {"status": "ok"}
```

**Note:** `webapp/data/clients.json` is created automatically on first save. `webapp/uploads/` and `OUTPUT_DIR` are created by the app on startup.

---

## 9. Deployment

Full guide: see `DEPLOY.md`. Summary:

```
1. Push code to GitHub (main branch)
2. Railway: New Project → Deploy from GitHub repo
   - Auto-detects Procfile: gunicorn webapp.app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
3. Set env vars in Railway Variables tab (see Section 7)
4. Optional: add custom domain in Railway Settings → Domains
   - Add CNAME in Cloudflare DNS pointing to Railway URL
   - Set Cloudflare SSL/TLS mode to "Full" (not "Full Strict")
```

**File persistence caveat:** `clients.json` and generated DOCX files are **ephemeral** on Railway's free tier (reset on redeploy). To persist clients, add a Railway Volume mounted at `/data` and point the app at it (requires a code change to `config.py`).

**Gunicorn timeout is 120s** because AI Visibility checks make up to 6 sequential API calls that can take 20–60 seconds total.

---

## 10. Testing

The test suite uses Python stdlib only (no pytest required):

```bash
# Test against production
python tests/test_app.py

# Test against local server
python tests/test_app.py http://localhost:5000

# Test with auth enabled
python tests/test_app.py http://localhost:5000 mypassword
```

**Test sections:**

| # | Section | What's checked |
|---|---------|---------------|
| 1 | Health & availability | `GET /health` → 200, `{"status":"ok"}` |
| 2 | Authentication | 401 without auth (if enabled), 200 with auth |
| 3 | Page loads | All 7 pages return 200, contain Numiko logo SVG, have AI Visibility + Domain nav links |
| 4 | Branding | No GCHQ/NCSC/placeholder text; CSS has Numiko orange + font |
| 5 | GEO Audit | POST with `example.com` → score, checks, DOCX download section |
| 6 | Error handling | Empty URL → error message |
| 7 | Clients CRUD | List page + new form |
| 8 | Content Guide | Page loads, no placeholders |
| 9 | Security | Path traversal blocked on `/download`, 404 for missing file |
| 10 | New pages | AI Visibility + Domain pages load, have correct form fields |
| 11 | CSV export | `/keywords/export` responds (200 or 503 if no credentials) |
| 12 | Audit new fields | Sitemap URL detail, AI Visibility nav in results |
| 13 | Module safety | `dataforseo_api.api_post` has no `sys.exit` calls |

---

## 11. How to Extend: Adding a New Tool

Follow this sequence when adding a new tool page:

**1. Create `webapp/services/mytool_service.py`**
```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')))
from dataforseo_api import api_post, get_result, format_count

def run_mytool(domain: str, ...) -> dict:
    result = {'domain': domain, 'data': None, 'errors': []}
    try:
        resp = api_post('some/endpoint/live', [{...}])
        results = get_result(resp)
        if results:
            result['data'] = results[0]
    except Exception as e:
        result['errors'].append(str(e))
    return result
```

**2. Create `webapp/templates/mytool.html`**
```html
{% extends "base.html" %}
{% block title %}My Tool — SEO-GEO Toolkit{% endblock %}
{% block content %}
<div class="page-header">
  <h1>My Tool</h1>
  <p class="subtitle">Description here</p>
</div>
{% include 'partials/how_to_mytool.html' %}
<form method="POST" class="form-card">
  ...
</form>
{% if result %}
<div class="results-section">...</div>
{% endif %}
{% endblock %}
```

**3. Add route to `webapp/app.py`**
```python
from services.mytool_service import run_mytool

@app.route('/mytool', methods=['GET', 'POST'])
@requires_auth(_get_password)
def mytool():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {'domain': request.form.get('domain', '').strip()}
        if form['domain']:
            try:
                result = run_mytool(form['domain'])
            except (Exception, SystemExit) as e:
                error = str(e)
        else:
            error = 'Please enter a domain.'
    return render_template('mytool.html', result=result, error=error,
                           clients=clients, form=form)
```

**4. Add nav link to `webapp/templates/base.html`**
```html
<li><a href="{{ url_for('mytool') }}" {% if request.endpoint == 'mytool' %}class="active"{% endif %}>My Tool</a></li>
```

**5. Add tool card to `webapp/templates/index.html`**
```html
<a href="{{ url_for('mytool') }}" class="tool-card">
  <div class="tool-icon">🔧</div>
  <h2>My Tool</h2>
  <p>Description for the dashboard card.</p>
  <span class="card-cta">Use Tool &rarr;</span>
</a>
```

**6. Create `webapp/templates/partials/how_to_mytool.html`** — follow the `<details>/<summary>` pattern from existing partials.

**7. Add tests to `tests/test_app.py`** — add a new numbered section following existing pattern.

---

## 12. GEO Scoring Algorithm

Implemented in `webapp/services/audit_service.py` → `_calculate_score()`.

| Check | Points | Source |
|-------|--------|--------|
| Page title present | +15 | `<title>` tag |
| Meta description present | +10 | `<meta name="description">` |
| Open Graph tags present | +5 | `<meta property="og:title">` |
| H1 heading present | +10 | `<h1>` tag |
| JSON-LD schema present | +20 | `<script type="application/ld+json">` count > 0 |
| AI bots **explicitly allowed** | +15 | `Allow: /` for GPTBot, PerplexityBot, ClaudeBot, anthropic-ai, ChatGPT-User in robots.txt |
| XML sitemap found | +10 | robots.txt `Sitemap:` directive, `/sitemap.xml`, or `/sitemap_index.xml` |
| Page load time < 3s | +15 | HTTP request timer |
| **Total** | **100** | |

**Score thresholds:**
- 71–100 → 🟢 Green — "GEO Ready"
- 41–70 → 🟡 Amber — "Needs Work"
- 0–40 → 🔴 Red — "Poor"

**Important notes:**
- AI bots only earn points if they have an **explicit** `Allow: /` rule — being absent from robots.txt does NOT award points.
- Backlinks data (if DataForSEO credentials are set) is shown as informational cards but **does not affect the score**.
- If the page is blocked by a WAF, blocked checks score 0 (not penalised further — the score is simply lower due to missing data).

---

## 13. Key Design Decisions

**Scripts in `/scripts/`, not in `webapp/`**
`seo_audit.py` and `dataforseo_api.py` were originally CLI tools. Keeping them in `/scripts/` means they can be run directly for debugging (`python scripts/seo_audit.py https://example.com`) without Flask. Services add them to `sys.path` at import time.

**All DataForSEO calls individually try/excepted in services**
API calls cost money and can fail independently (wrong plan, rate limits, API downtime). If bulk keyword difficulty fails, the keyword list is still returned with N/A difficulties. This makes the app resilient to partial plan access.

**`scripts/dataforseo_api.py` raises `RuntimeError`, never `sys.exit()`**
Original code used `sys.exit(1)` on API errors, which silently kills a Gunicorn worker. All exits are now `raise RuntimeError(...)` so Flask can catch and display the error to the user.

**Flat JSON file for client storage**
No database dependency — Railway and Render free tiers work without any database addon. Trade-off: clients are ephemeral on free tiers (reset on redeploy). A future enhancement could use Railway Postgres.

**HTTP Basic Auth via a decorator factory, not Flask-Login**
Simplicity. The app is an internal team tool. Any username + the shared `APP_PASSWORD` grants access. Disabling auth (empty `APP_PASSWORD`) makes local development frictionless.

**Gunicorn with 2 workers, 120s timeout**
AI Visibility checks make up to 6 sequential LLM API calls; each can take 10–15s. 120s timeout prevents Gunicorn from killing slow but legitimate requests.

**No JavaScript framework**
`main.js` is ~130 lines of vanilla JS (tabs, table sorting, form auto-fill, loading states). No build toolchain needed. How-to guides use `<details>/<summary>` — pure HTML, no JS required.

**AI Optimization endpoint paths (as of Feb 2025)**
The DataForSEO AI Optimization API uses nested paths that differ from the Labs/Keywords APIs. The correct paths are documented in Section 6. If panels show "not available", check the error strings in `result['errors']` — wrong endpoint names return HTTP 404 which is caught as a `RuntimeError`.
