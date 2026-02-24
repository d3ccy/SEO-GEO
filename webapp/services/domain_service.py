import logging
import re
from urllib.parse import urlparse

from dataforseo_api import api_post, get_result, format_count

logger = logging.getLogger(__name__)


def _clean_domain(domain: str) -> str:
    """Strip protocol/path from domain input and validate."""
    domain = domain.strip().lower()
    if not domain:
        raise ValueError('Domain must not be empty.')
    # Reject shell metacharacters, spaces, and other dangerous input
    if re.search(r'[;&|`$\s]', domain):
        raise ValueError(f'Invalid domain: {domain!r}')
    if domain.startswith('http'):
        parsed = urlparse(domain)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f'Unsupported URL scheme: {parsed.scheme}')
        domain = parsed.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    if not domain:
        raise ValueError('Could not extract a valid domain.')
    return domain


def run_domain_overview(domain: str, location_code: int = 2826) -> dict:
    """Run a full domain overview: rank metrics, top keywords, competitors, backlinks.

    Each section is individually try/excepted — partial results are returned
    if any API call fails.
    """
    domain = _clean_domain(domain)
    result = {
        'domain': domain,
        'location_code': location_code,
        'rank_overview': None,
        'keywords': [],
        'competitors': [],
        'backlinks': None,
        'errors': [],
    }

    # ── Section 1: Domain Rank Overview ───────────────────────────────────
    try:
        resp = api_post('dataforseo_labs/google/domain_rank_overview/live', [{
            'target': domain,
            'location_code': location_code,
            'language_code': 'en',
        }])
        ro_results = get_result(resp)
        if ro_results:
            item = ro_results[0]
            metrics = item.get('metrics', {}).get('organic', {})
            result['rank_overview'] = {
                'rank': item.get('domain_rank'),
                'etv': format_count(metrics.get('etv')),
                'keywords_count': format_count(metrics.get('count')),
                'pos_1_3': metrics.get('pos_1_3', 0),
                'pos_4_10': metrics.get('pos_4_10', 0),
            }
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Domain Rank Overview failed: %s', exc)
        result['errors'].append(f'Domain Rank Overview: {exc}')

    # ── Section 2: Top Ranking Keywords ───────────────────────────────────
    try:
        resp = api_post('dataforseo_labs/google/ranked_keywords/live', [{
            'target': domain,
            'location_code': location_code,
            'language_code': 'en',
            'limit': 20,
            'order_by': ['keyword_data.keyword_info.search_volume,desc'],
        }])
        kw_results = get_result(resp)
        if kw_results:
            raw = kw_results[0] if isinstance(kw_results, list) else kw_results
            items = raw.get('items') or kw_results
            for item in (items if isinstance(items, list) else []):
                kd = item.get('keyword_data', {})
                ki = kd.get('keyword_info', {})
                sr = item.get('ranked_serp_element', {}).get('serp_item', {})
                result['keywords'].append({
                    'keyword': kd.get('keyword', ''),
                    'position': sr.get('rank_absolute', sr.get('rank_group', '—')),
                    'volume': format_count(ki.get('search_volume', 0)),
                    'volume_raw': ki.get('search_volume', 0) or 0,
                    'url': sr.get('relative_url', '') or sr.get('url', ''),
                })
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Ranked Keywords fetch failed: %s', exc)
        result['errors'].append(f'Ranked Keywords: {exc}')

    # ── Section 3: Top Competitors ─────────────────────────────────────────
    try:
        resp = api_post('dataforseo_labs/google/competitors_domain/live', [{
            'target': domain,
            'location_code': location_code,
            'language_code': 'en',
            'limit': 10,
        }])
        comp_results = get_result(resp)
        if comp_results:
            raw = comp_results[0] if isinstance(comp_results, list) else comp_results
            items = raw.get('items') or comp_results
            for item in (items if isinstance(items, list) else []):
                result['competitors'].append({
                    'domain': item.get('domain', ''),
                    'common_keywords': item.get('intersections', 0),
                    'relevance': round(item.get('relevance', 0), 3),
                    'domain_rank': item.get('domain_rank'),
                })
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Competitors fetch failed: %s', exc)
        result['errors'].append(f'Competitors: {exc}')

    # ── Section 4: Backlinks Summary ──────────────────────────────────────
    try:
        resp = api_post('backlinks/summary/live', [{
            'target': domain,
            'include_subdomains': True,
        }])
        bl_results = get_result(resp)
        if bl_results:
            item = bl_results[0]
            result['backlinks'] = {
                'rank': item.get('rank'),
                'referring_domains': item.get('referring_domains', 0),
                'backlinks': item.get('backlinks', 0),
                'nofollow': item.get('nofollow', 0),
                'dofollow': (item.get('backlinks') or 0) - (item.get('nofollow') or 0),
            }
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Backlinks fetch failed: %s', exc)
        result['errors'].append(f'Backlinks: {exc}')

    return result
