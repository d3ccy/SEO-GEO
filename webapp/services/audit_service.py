import sys
import os

# Put scripts/ on path so seo_audit.py can be imported directly
_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

from seo_audit import fetch_url, extract_meta, check_robots, check_sitemap


def run_audit(url: str) -> dict:
    """Run full SEO/GEO audit, return structured dict for template rendering.

    If the main page is blocked (WAF/Cloudflare), returns partial results
    with a warning rather than failing completely. robots.txt and sitemap
    checks are attempted regardless of whether the main page is accessible.
    """
    if not url.startswith('http'):
        url = f'https://{url}'

    content, headers, load_time = fetch_url(url)

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

    robots = check_robots(url)
    has_sitemap = check_sitemap(url)

    title = meta.get('title') or ''
    description = meta.get('description') or ''

    return {
        'url': url,
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
        'has_sitemap': has_sitemap,
        'score': _calculate_score(meta, robots, has_sitemap, load_time, page_blocked),
    }


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
    if robots.get('ai_bots'):
        score += 15
    if has_sitemap:
        score += 10
    if isinstance(load_time, (int, float)) and load_time < 3:
        score += 15
    return score
