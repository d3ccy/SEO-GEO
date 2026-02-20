#!/usr/bin/env python3
"""
SEO audit script (no API required)
Usage: python3 scripts/seo_audit.py "https://example.com"
"""
import argparse
import urllib.request
import urllib.error
import urllib.parse
import ssl
import re
import time
import sys
import html as html_module


# ---------------------------------------------------------------------------
# httpx with HTTP/2 support — much better WAF bypass than urllib
# Falls back gracefully to urllib if not installed
# ---------------------------------------------------------------------------
try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# Custom Numiko audit bot UA — whitelist this in Cloudflare for client sites
NUMIKO_UA = "NumikoAuditBot/1.0 (+https://numiko.com/audit-bot)"

# urllib fallback header sets — tried in order when httpx also fails
_HEADER_SETS = [
    # Chrome 122 on macOS
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "identity",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    },
    # Firefox 124 on Windows
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    },
    # Chrome on Windows
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    },
    # Safari on macOS
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    },
    # Googlebot — many sites explicitly allow this
    {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
        "Accept-Encoding": "identity",
    },
    # Custom Numiko UA (whitelist this in Cloudflare for client sites)
    {
        "User-Agent": NUMIKO_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "identity",
    },
]


def _is_bot_challenge(content: str, headers: dict) -> bool:
    """Detect Cloudflare JS challenge interstitial pages."""
    cf_signatures = [
        'just a moment',
        'challenges.cloudflare.com',
        'cf_chl_opt',
    ]
    content_lower = content.lower()
    for sig in cf_signatures:
        if sig.lower() in content_lower:
            return True
    if headers.get('cf-mitigated') == 'challenge':
        return True
    return False


def _url_variants(url):
    """Generate URL variants to try (www/non-www)."""
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc
    variants = [url]
    if netloc.startswith('www.'):
        alt = parsed._replace(netloc=netloc[4:]).geturl()
    else:
        alt = parsed._replace(netloc='www.' + netloc).geturl()
    if alt != url:
        variants.append(alt)
    return variants


def _fetch_httpx(url, timeout):
    """Fetch using httpx with HTTP/2 — passes most WAF fingerprint checks.
    Returns (content, headers_dict, load_time) or raises.
    """
    start = time.time()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    }
    with httpx.Client(
        http2=True,
        follow_redirects=True,
        timeout=timeout,
        verify=False,
        headers=headers,
    ) as client:
        resp = client.get(url)
        content = resp.text
        load_time = time.time() - start
        return content, dict(resp.headers), load_time


def _fetch_urllib(url, headers, timeout):
    """Single urllib fetch attempt."""
    start = time.time()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
        load_time = time.time() - start
        return content, dict(resp.headers), load_time


def fetch_url(url, timeout=30):
    """Fetch URL, trying httpx (HTTP/2) first then urllib fallbacks.
    Returns (content, headers, load_time) on success.
    Returns (None, None, error_string) on total failure.
    """
    last_error = "Unknown error"
    got_cf_challenge = False

    for try_url in _url_variants(url):

        # ── httpx with HTTP/2 (primary — best WAF bypass) ──────────────────
        if _HTTPX_AVAILABLE:
            try:
                content, resp_headers, load_time = _fetch_httpx(try_url, timeout)
                if _is_bot_challenge(content, resp_headers):
                    got_cf_challenge = True
                    # Don't break — try next URL variant or urllib
                elif content and len(content) > 200:
                    return content, resp_headers, load_time
            except Exception as e:
                err_str = str(e)
                # Extract HTTP status if present
                if "403" in err_str or "Client error" in err_str:
                    last_error = "HTTP 403 Forbidden"
                else:
                    last_error = err_str
                # Fall through to urllib

        # ── urllib fallback: multiple header sets ───────────────────────────
        for headers in _HEADER_SETS:
            try:
                content, resp_headers, load_time = _fetch_urllib(try_url, headers, timeout)
                if _is_bot_challenge(content, resp_headers):
                    got_cf_challenge = True
                    continue
                if content and len(content) > 200:
                    return content, resp_headers, load_time
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="ignore")
                    if body and len(body) > 500 and not _is_bot_challenge(body, {}):
                        return body, {}, 0.5
                except Exception:
                    pass
                code = e.code
                last_error = f"HTTP {code} {e.reason}"
                if code in (403, 406, 429, 503):
                    continue
                return None, None, last_error
            except urllib.error.URLError as e:
                last_error = f"Connection error: {e.reason}"
                break
            except Exception as e:
                last_error = str(e)
                continue

    if got_cf_challenge:
        return None, None, (
            "Cloudflare bot protection is blocking this site. "
            "To audit this site, add 'NumikoAuditBot/1.0' to the Cloudflare WAF allowlist, "
            "or temporarily disable Bot Fight Mode."
        )

    return None, None, (
        f"Could not access this site ({last_error}). "
        "The site's firewall is blocking requests from the audit server. "
        "For client sites, add 'NumikoAuditBot/1.0' to their Cloudflare WAF allowlist."
    )


def extract_meta(html):
    """Extract meta tags from HTML"""
    result = {}

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    result["title"] = html_module.unescape(title_match.group(1).strip()) if title_match else None

    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if not desc_match:
        desc_match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', html, re.I)
    result["description"] = html_module.unescape(desc_match.group(1).strip()) if desc_match else None

    og_match = re.search(r'<meta[^>]+property=["\']og:title["\']', html, re.I)
    result["og_tags"] = bool(og_match)

    jsonld_count = len(re.findall(r'application/ld\+json', html, re.I))
    result["jsonld_count"] = jsonld_count

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.DOTALL)
    if h1_match:
        h1_text = re.sub(r"<[^>]+>", " ", h1_match.group(1))
        h1_text = re.sub(r"\s+", " ", h1_text).strip()
        result["h1"] = html_module.unescape(h1_text)[:100]
    else:
        result["h1"] = None

    return result


def check_robots(url):
    """Check robots.txt"""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    content, _, _ = fetch_url(robots_url)

    result = {"exists": False, "ai_bots": []}
    if content:
        result["exists"] = True
        ai_bots = ["GPTBot", "PerplexityBot", "ClaudeBot", "anthropic-ai", "ChatGPT-User"]
        for bot in ai_bots:
            if bot.lower() in content.lower():
                result["ai_bots"].append(bot)
    return result


def check_sitemap(url):
    """Check if sitemap.xml exists"""
    parsed = urllib.parse.urlparse(url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    content, _, _ = fetch_url(sitemap_url)
    if not content:
        return False
    return "<urlset" in content.lower() or "<sitemapindex" in content.lower() or "<?xml" in content.lower()


def main():
    parser = argparse.ArgumentParser(description="SEO audit")
    parser.add_argument("url", help="URL to audit")
    args = parser.parse_args()

    url = args.url
    if not url.startswith("http"):
        url = f"https://{url}"

    print(f"=== SEO Audit: {url} ===")
    print()

    content, headers, load_time = fetch_url(url)
    if not content:
        print(f"error: {load_time}")
        sys.exit(1)

    print("## Meta Tags")
    meta = extract_meta(content)
    title = meta["title"]
    print(f"title: {title[:60] if title else 'MISSING'}{'...' if title and len(title) > 60 else ''}")
    print(f"title_length: {len(title) if title else 0} chars")
    desc = meta["description"]
    print(f"description: {desc[:80] if desc else 'MISSING'}{'...' if desc and len(desc) > 80 else ''}")
    print(f"description_length: {len(desc) if desc else 0} chars")
    print(f"og_tags: {'yes' if meta['og_tags'] else 'no'}")
    print(f"h1: {meta['h1'] if meta['h1'] else 'MISSING'}")
    print()

    print("## Schema Markup")
    print(f"json_ld_blocks: {meta['jsonld_count']}")
    print()

    print("## Performance")
    print(f"load_time: {load_time:.2f}s")
    print(f"status: {'good' if load_time < 3 else 'slow'}")
    print()

    print("## robots.txt")
    robots = check_robots(url)
    print(f"exists: {'yes' if robots['exists'] else 'no'}")
    if robots["ai_bots"]:
        print(f"ai_bots_mentioned: {', '.join(robots['ai_bots'])}")
    else:
        print("ai_bots_mentioned: none")
    print()

    print("## Sitemap")
    has_sitemap = check_sitemap(url)
    print(f"sitemap_xml: {'yes' if has_sitemap else 'no'}")
    print()

    print("=== Audit Complete ===")


if __name__ == "__main__":
    main()
