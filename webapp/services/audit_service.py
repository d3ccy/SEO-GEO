import logging
from urllib.parse import urlparse

from seo_audit import fetch_url, extract_meta, check_robots, check_sitemap

logger = logging.getLogger(__name__)


def run_audit(url: str, use_stealth: bool = False) -> dict:
    """Run full SEO/GEO audit, return structured dict for template rendering.

    use_stealth=True enables curl_cffi Chrome TLS impersonation — this defeats
    Cloudflare's JA3/JA4 fingerprinting which standard httpx cannot bypass.

    If the main page is blocked (WAF/Cloudflare), returns partial results
    with a warning rather than failing completely. robots.txt and sitemap
    checks are attempted regardless of whether the main page is accessible.
    """
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ('http', 'https'):
        raise ValueError(f'Unsupported URL scheme: {parsed.scheme}. Only http and https are allowed.')

    if not url.startswith('http'):
        url = f'https://{url}'

    content, headers, load_time = fetch_url(url, use_stealth=use_stealth)

    page_blocked = content is None
    block_reason = None
    if page_blocked:
        block_reason = load_time if isinstance(load_time, str) else (
            'Site may be unreachable or blocking automated requests'
        )
        # Still run robots and sitemap — these often work even when the main page is blocked
        meta = {'title': None, 'description': None, 'og_tags': False,
                'h1': None, 'jsonld_count': 0}
        load_time = None
    else:
        meta = extract_meta(content)

    robots = check_robots(url, use_stealth=use_stealth)
    robots_content = robots.get('content')
    has_sitemap, sitemap_url = check_sitemap(url, robots_content=robots_content, use_stealth=use_stealth)

    title = meta.get('title') or ''
    description = meta.get('description') or ''

    # Optional: fetch backlinks summary from DataForSEO if credentials are available
    backlinks_data = _fetch_backlinks(url)

    return {
        'url': url,
        'use_stealth': use_stealth,
        'page_blocked': page_blocked,
        'block_reason': block_reason,
        'title': title,
        'title_length': len(title),
        'title_ok': 0 < len(title) <= 60,
        'description': description,
        'description_length': len(description),
        'description_ok': 0 < len(description) <= 155,
        'og_tags': meta.get('og_tags', False),
        'h1': meta.get('h1'),
        'jsonld_count': meta.get('jsonld_count', 0),
        'load_time': round(load_time, 2) if isinstance(load_time, (int, float)) else None,
        'load_time_ok': isinstance(load_time, (int, float)) and load_time < 3,
        'robots_exists': robots.get('exists', False),
        'ai_bots': robots.get('ai_bots', []),
        'ai_bots_blocked': robots.get('ai_bots_blocked', []),
        'has_sitemap': has_sitemap,
        'sitemap_url': sitemap_url,
        'backlinks_rank': backlinks_data.get('rank'),
        'referring_domains': backlinks_data.get('referring_domains'),
        'total_backlinks': backlinks_data.get('backlinks'),
        'score': _calculate_score(meta, robots, has_sitemap, load_time, page_blocked),
    }


def _fetch_backlinks(url: str) -> dict:
    """Fetch backlinks summary from DataForSEO. Returns empty dict on any failure."""
    try:
        import dataforseo_api as _dfs
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        data = [{'target': domain, 'include_subdomains': True}]
        response = _dfs.api_post('backlinks/summary/live', data)
        results = _dfs.get_result(response)
        if results:
            item = results[0]
            return {
                'rank': item.get('rank'),
                'referring_domains': item.get('referring_domains'),
                'backlinks': item.get('backlinks'),
            }
    except (RuntimeError, ImportError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Backlinks fetch failed: %s', exc)
    return {}


def _calculate_score(meta, robots, has_sitemap, load_time, page_blocked=False) -> int:
    """Simple 0–100 GEO readiness score."""
    score = 0
    title = meta.get('title') or ''
    desc = meta.get('description') or ''
    if title:
        score += 15
    if desc:
        score += 10
    if meta.get('og_tags'):
        score += 5
    if meta.get('h1'):
        score += 10
    if meta.get('jsonld_count', 0) > 0:
        score += 20
    # Score AI bots correctly: only award points for explicitly ALLOWED bots
    if robots.get('ai_bots'):
        score += 15
    if has_sitemap:
        score += 10
    if isinstance(load_time, (int, float)) and load_time < 3:
        score += 15
    return score
