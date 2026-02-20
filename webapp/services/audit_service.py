import sys
import os

# Put scripts/ on path so seo_audit.py can be imported directly
_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

from seo_audit import fetch_url, extract_meta, check_robots, check_sitemap


def run_audit(url: str) -> dict:
    """Run full SEO/GEO audit, return structured dict for template rendering."""
    if not url.startswith('http'):
        url = f'https://{url}'

    content, headers, load_time = fetch_url(url)
    if not content:
        reason = load_time if isinstance(load_time, str) else 'site may be unreachable or blocking automated requests'
        raise ValueError(f'Could not fetch {url} — {reason}')

    meta = extract_meta(content)
    robots = check_robots(url)
    has_sitemap = check_sitemap(url)

    title = meta.get('title') or ''
    description = meta.get('description') or ''

    return {
        'url': url,
        'title': title,
        'title_length': len(title),
        'title_ok': 0 < len(title) <= 60,
        'description': description,
        'description_length': len(description),
        'description_ok': 0 < len(description) <= 155,
        'og_tags': meta.get('og_tags', False),
        'h1': meta.get('h1'),
        'jsonld_count': meta.get('jsonld_count', 0),
        'load_time': round(load_time, 2) if load_time is not None else None,
        'load_time_ok': load_time is not None and load_time < 3,
        'robots_exists': robots.get('exists', False),
        'ai_bots': robots.get('ai_bots', []),
        'has_sitemap': has_sitemap,
        'score': _calculate_score(meta, robots, has_sitemap, load_time),
    }


def _calculate_score(meta, robots, has_sitemap, load_time) -> int:
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
    if load_time is not None and load_time < 3:
        score += 15
    return score
