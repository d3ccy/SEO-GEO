# SEO-GEO Toolkit — Deployment Guide

This is a Python/Flask web application. It cannot run directly on Cloudflare Workers or Pages (which only support JavaScript). The recommended approach — used by most teams — is to deploy it to **Railway** or **Render** (both have free tiers), then point a **Cloudflare-managed domain** at it via DNS. You get Cloudflare's CDN, SSL, and DDoS protection this way.

---

## What you need before starting

- A [Railway](https://railway.app) or [Render](https://render.com) account (free)
- A [GitHub](https://github.com) account (to host the code)
- Your DataForSEO API credentials (login email + password)
- Optional: a domain managed in Cloudflare

---

## Step 1 — Put the code on GitHub

1. Create a new **private** repository on GitHub (e.g. `seo-geo-toolkit`)
2. Upload all the files from this ZIP into that repository (drag and drop in the GitHub UI, or use git)
3. Make sure the repository root contains `Procfile`, `requirements.txt`, and the `webapp/` folder

---

## Step 2 — Deploy to Railway (recommended)

Railway has a generous free tier and the simplest deploy flow.

### 2a — Create the project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select your `seo-geo-toolkit` repository
4. Railway will detect the `Procfile` automatically and start deploying

### 2b — Set environment variables

In Railway, go to your project → **Variables** tab → add these:

| Variable | Value |
|----------|-------|
| `DATAFORSEO_LOGIN` | Your DataForSEO login email |
| `DATAFORSEO_PASSWORD` | Your DataForSEO password |
| `SECRET_KEY` | Any long random string (e.g. `openssl rand -hex 32`) |
| `APP_PASSWORD` | A password to protect the app (leave blank to disable auth) |
| `OUTPUT_DIR` | `/tmp/seo-geo-reports` |

> **Note:** Railway provides `$PORT` automatically — the `Procfile` already uses it.

### 2c — Verify the deploy

Once deployed, Railway gives you a URL like `https://seo-geo-toolkit-production.up.railway.app`.

Open it in a browser — you should see the SEO-GEO Toolkit dashboard. Test:
- `GET /health` → should return `{"status": "ok"}`
- Run a GEO audit on `https://example.com`
- Generate a Content Guide DOCX

---

## Step 3 — Deploy to Render (alternative)

If you prefer Render:

1. Go to [render.com](https://render.com) and sign in with GitHub
2. Click **New → Web Service**
3. Connect your `seo-geo-toolkit` repository
4. Set:
   - **Environment:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn webapp.app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Under **Environment Variables**, add the same variables as above
6. Click **Deploy**

Render gives you a URL like `https://seo-geo-toolkit.onrender.com`.

> **Free tier note:** Render free services spin down after 15 minutes of inactivity. The first request after a spin-down takes ~30 seconds. Upgrade to the $7/month plan to avoid this.

---

## Step 4 — Point a Cloudflare domain at the app

This step is optional but gives you a clean domain, SSL, and Cloudflare's CDN/DDoS protection.

### 4a — Add a CNAME in Cloudflare

1. Log in to Cloudflare and go to your domain's **DNS** settings
2. Add a new record:
   - **Type:** CNAME
   - **Name:** `tools` (or whatever subdomain you want, e.g. `seo-geo`)
   - **Target:** your Railway/Render URL (without `https://`), e.g. `seo-geo-toolkit-production.up.railway.app`
   - **Proxy status:** Proxied (orange cloud) ✓

3. Save the record

This creates `https://tools.yourdomain.com` pointing to the app.

### 4b — Set the custom domain in Railway/Render

**Railway:**
1. In your Railway project, go to **Settings → Domains**
2. Click **Add Domain** and enter `tools.yourdomain.com`
3. Railway will show a verification record — add it to Cloudflare DNS if prompted

**Render:**
1. In your Render service, go to **Settings → Custom Domains**
2. Click **Add Custom Domain** and enter `tools.yourdomain.com`
3. Render will verify it via the Cloudflare CNAME you already added

### 4c — SSL

Cloudflare handles SSL automatically. Set the Cloudflare SSL/TLS mode to **Full** (not Full Strict) in your domain's **SSL/TLS** settings.

---

## File structure reference

```
/
├── webapp/                 # Flask application
│   ├── app.py              # Routes
│   ├── config.py           # Config (reads env vars)
│   ├── auth.py             # HTTP Basic Auth
│   ├── client_store.py     # Client profile storage
│   ├── services/           # Business logic
│   ├── report_generators/  # DOCX generators
│   ├── templates/          # HTML pages
│   └── static/             # CSS + JS
├── scripts/                # CLI SEO scripts (used by services)
├── fonts/                  # Logo + fonts for reports
├── Procfile                # Gunicorn startup command
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variable reference
```

---

## Environment variables reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATAFORSEO_LOGIN` | Yes (for keywords) | DataForSEO account email |
| `DATAFORSEO_PASSWORD` | Yes (for keywords) | DataForSEO account password |
| `SECRET_KEY` | Yes | Flask session secret — set to any long random string |
| `APP_PASSWORD` | No | If set, protects all pages with HTTP Basic Auth |
| `OUTPUT_DIR` | No | Where generated reports are stored (default: `/tmp/seo-geo-reports`) |
| `PORT` | Auto | Set automatically by Railway/Render |

---

## Persistent client profiles

Client profiles are saved in `webapp/data/clients.json`. On Railway and Render free tiers, the filesystem is ephemeral — profiles will be lost on redeploy.

**To avoid this:**
- **Railway:** Add a Volume in the Railway dashboard, mount it at `/data`, then set `DATA_FILE=/data/clients.json` as an environment variable (requires a small code change — contact the developer)
- **Render:** Upgrade to a paid plan with a Persistent Disk, mount at `/data`, same env var change
- **Simplest option:** Keep a backup of `clients.json` and re-upload when needed

---

## Troubleshooting

**App won't start:**
- Check that `requirements.txt` is in the repository root
- Check that `Procfile` is in the repository root
- Check the deploy logs in Railway/Render for Python errors

**Keyword research returns an error:**
- Verify `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` are set correctly
- Test credentials at [app.dataforseo.com](https://app.dataforseo.com)

**DOCX download fails:**
- Check that `OUTPUT_DIR` is writable (default `/tmp/seo-geo-reports` is always writable)
- Check the app logs for Python tracebacks

**Custom domain not working:**
- Ensure the CNAME in Cloudflare points to the correct Railway/Render URL
- Wait up to 5 minutes for DNS propagation
- Ensure the custom domain is added in Railway/Render settings (Step 4b)

---

## Updating the app

1. Edit the files locally
2. Push changes to GitHub
3. Railway/Render redeploy automatically on every push to `main`
