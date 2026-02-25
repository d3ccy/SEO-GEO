import logging

from dataforseo_api import api_post, get_result, format_count

logger = logging.getLogger(__name__)

# Location options exposed to the template for the location selector.
# (code, label) — ordered by likely usage for a UK-based agency.
LOCATION_OPTIONS = [
    (2826, "United Kingdom"),
    (2840, "United States"),
    (2036, "Australia"),
    (2124, "Canada"),
    (2276, "Germany"),
    (2250, "France"),
    (2724, "Spain"),
    (2380, "Italy"),
]


def _clean_domain(domain: str) -> str:
    """Strip protocol and trailing slash; remove www prefix."""
    d = domain.replace('https://', '').replace('http://', '')
    if d.startswith('www.'):
        d = d[4:]
    return d.rstrip('/')


def _domain_mentioned(text: str, clean_domain: str, brand_query: str = '') -> bool:
    """Return True if the domain / brand appears to be referenced in *text*.

    Three checks in order of specificity:
    1. Bare domain string  (e.g. "numiko.com")
    2. Domain name without TLD  (e.g. "numiko")  — only if >= 4 chars
    3. First word of brand_query  (e.g. "Numiko")  — only if >= 4 chars

    This prevents false negatives when AI responses mention a brand by name
    without including the full domain URL.
    """
    if not text:
        return False
    text_lower = text.lower()

    # 1. Full domain (e.g. numiko.com)
    if clean_domain.lower() in text_lower:
        return True

    # 2. Name-part only (e.g. "numiko" from "numiko.com")
    if '.' in clean_domain:
        name_only = clean_domain.rsplit('.', 1)[0]
        if len(name_only) >= 4 and name_only.lower() in text_lower:
            return True

    # 3. First word of brand_query (e.g. "Numiko" from "Numiko digital agency")
    if brand_query:
        first_word = brand_query.strip().split()[0]
        if len(first_word) >= 4 and first_word.lower() in text_lower:
            return True

    return False


def run_ai_visibility(domain: str, brand_query: str, location_code: int = 2826) -> dict:
    """Check AI visibility for a domain/brand across LLM platforms.

    Returns a dict with:
      - aggregated_metrics: per-platform totals (mentions, ai_search_volume, impressions)
      - top_domains: domains most co-cited alongside the target
      - mentions: Search Mentions items (questions where domain is cited)
      - ai_overview: Google SERP AI Overview for the brand query
      - chatgpt: ChatGPT scraper result
      - llm_responses: per-platform LLM response dicts
      - errors: list of error strings for any failed calls

    DataForSEO endpoints used:
      - ai_optimization/llm_mentions/aggregated_metrics/live
      - ai_optimization/llm_mentions/top_domains/live
      - ai_optimization/llm_mentions/search/live
      - serp/google/organic/live/advanced  (for ai_overview)
      - ai_optimization/chat_gpt/llm_scraper/live/advanced
      - ai_optimization/{platform}/llm_responses/live  (per platform)
    """
    result = {
        'domain': domain,
        'brand_query': brand_query,
        'location_code': location_code,
        'aggregated_metrics': None,
        'top_domains': None,
        'mentions': None,
        'ai_overview': None,
        'chatgpt': None,
        'llm_responses': None,
        'errors': [],
    }

    clean_domain = _clean_domain(domain)

    # ── Aggregated Metrics ─────────────────────────────────────────────────
    # Returns totals (mentions, ai_search_volume, impressions) per platform.
    try:
        resp = api_post('ai_optimization/llm_mentions/aggregated_metrics/live', [{
            'target': [{'domain': clean_domain, 'search_filter': 'include'}],
            'location_code': location_code,
            'language_code': 'en',
        }])
        agg_results = get_result(resp)
        if agg_results:
            raw = agg_results[0] if isinstance(agg_results, list) else agg_results
            items = raw.get('items') or []
            result['aggregated_metrics'] = [
                {
                    'platform': item.get('platform', ''),
                    'mentions': item.get('mentions', 0),
                    'ai_search_volume': item.get('ai_search_volume', 0),
                    'impressions': item.get('impressions', 0),
                }
                for item in items
            ]
        else:
            result['aggregated_metrics'] = []
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Aggregated Metrics fetch failed: %s', exc)
        result['errors'].append(f'Aggregated Metrics: {exc}')

    # ── Top Domains ────────────────────────────────────────────────────────
    # Domains most cited by LLMs alongside / instead of the target domain.
    try:
        resp = api_post('ai_optimization/llm_mentions/top_domains/live', [{
            'target': [{'domain': clean_domain, 'search_filter': 'include'}],
            'location_code': location_code,
            'language_code': 'en',
            'limit': 10,
        }])
        top_results = get_result(resp)
        if top_results:
            raw = top_results[0] if isinstance(top_results, list) else top_results
            items = raw.get('items') or []
            result['top_domains'] = [
                {
                    'domain': item.get('domain', ''),
                    'mentions': item.get('mentions', 0),
                    'ai_search_volume': item.get('ai_search_volume', 0),
                    'is_target': item.get('domain', '').lower() == clean_domain.lower(),
                }
                for item in items
            ]
        else:
            result['top_domains'] = []
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Top Domains fetch failed: %s', exc)
        result['errors'].append(f'Top Domains: {exc}')

    # ── LLM Mentions — Search Mentions ────────────────────────────────────
    # Questions / AI answers where the domain was cited as a source.
    try:
        resp = api_post('ai_optimization/llm_mentions/search/live', [{
            'target': [{'domain': clean_domain, 'search_filter': 'include'}],
            'location_code': location_code,
            'language_code': 'en',
            'limit': 10,
        }])
        mentions_results = get_result(resp)
        if mentions_results:
            raw = mentions_results[0] if isinstance(mentions_results, list) else mentions_results
            items = raw.get('items') or []
            result['mentions'] = [
                {
                    'question': item.get('question', ''),
                    'answer_snippet': (item.get('answer') or '')[:400],
                    'ai_search_volume': item.get('ai_search_volume', 0),
                    'platform': item.get('platform', 'google'),
                    'source_domains': [
                        s.get('domain', '') for s in (item.get('sources') or [])[:5]
                    ],
                }
                for item in items
            ]
        else:
            result['mentions'] = []
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('LLM Mentions fetch failed: %s', exc)
        result['errors'].append(f'LLM Mentions: {exc}')

    # ── Google SERP AI Overview ────────────────────────────────────────────
    # What Google's AI Overview says about the brand query + which pages it cites.
    try:
        resp = api_post('serp/google/organic/live/advanced', [{
            'keyword': brand_query or clean_domain,
            'location_code': location_code,
            'language_code': 'en',
            'expand_ai_overview': True,
        }])
        serp_results = get_result(resp)
        if serp_results:
            raw = serp_results[0] if isinstance(serp_results, list) else serp_results
            items = raw.get('items') or []
            for item in items:
                if item.get('type') == 'ai_overview':
                    overview_text = item.get('markdown') or item.get('text') or ''
                    refs = item.get('references') or []
                    ref_text = ' '.join(
                        (r.get('domain', '') + ' ' + r.get('url', ''))
                        for r in refs
                    )
                    result['ai_overview'] = {
                        'text': overview_text,
                        'references': [
                            {
                                'title': r.get('title', ''),
                                'url': r.get('url', ''),
                                'domain': r.get('domain', ''),
                            }
                            for r in refs[:10]
                        ],
                        'domain_mentioned': _domain_mentioned(
                            overview_text + ' ' + ref_text,
                            clean_domain,
                            brand_query,
                        ),
                    }
                    break
        if result['ai_overview'] is None:
            result['ai_overview'] = {'text': None, 'references': [], 'domain_mentioned': False}
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('SERP AI Overview fetch failed: %s', exc)
        result['errors'].append(f'Google AI Overview: {exc}')
        if result['ai_overview'] is None:
            result['ai_overview'] = {'text': None, 'references': [], 'domain_mentioned': False}

    # ── ChatGPT Search Scraper ─────────────────────────────────────────────
    try:
        resp = api_post('ai_optimization/chat_gpt/llm_scraper/live/advanced', [{
            'keyword': brand_query,
            'location_code': location_code,
            'language_code': 'en',
        }])
        chatgpt_results = get_result(resp)
        if chatgpt_results:
            raw = chatgpt_results[0] if isinstance(chatgpt_results, list) else chatgpt_results
            items = raw.get('items') or []
            answer_text = None
            sources = []
            for item in items:
                item_type = item.get('type', '')
                if item_type in ('chatgpt_answer', 'message', 'answer'):
                    answer_text = (
                        item.get('text')
                        or item.get('description')
                        or item.get('content')
                    )
                elif item_type in ('source', 'organic', 'link', 'citation'):
                    sources.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', '') or item.get('link', ''),
                        'domain': item.get('domain', ''),
                    })
            source_text = ' '.join(
                (s.get('url', '') + ' ' + s.get('domain', '') + ' ' + s.get('title', ''))
                for s in sources
            )
            result['chatgpt'] = {
                'answer': answer_text,
                'sources': sources[:10],
                'domain_mentioned': _domain_mentioned(
                    (answer_text or '') + ' ' + source_text,
                    clean_domain,
                    brand_query,
                ),
            }
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('ChatGPT Search fetch failed: %s', exc)
        result['errors'].append(f'ChatGPT Search: {exc}')

    # ── Multi-LLM Responses ────────────────────────────────────────────────
    llm_platforms = [
        ('ChatGPT',    'ai_optimization/chat_gpt/llm_responses/live',  'gpt-4.1-mini'),
        ('Claude',     'ai_optimization/claude/llm_responses/live',     'claude-3-5-haiku-20241022'),
        ('Gemini',     'ai_optimization/gemini/llm_responses/live',     'gemini-2.0-flash'),
        ('Perplexity', 'ai_optimization/perplexity/llm_responses/live', 'sonar'),
    ]

    llm_data = []
    for platform_name, endpoint, model_name in llm_platforms:
        try:
            resp = api_post(endpoint, [{
                'user_prompt': brand_query,
                'model_name': model_name,
            }])
            llm_results = get_result(resp)
            if llm_results:
                raw = llm_results[0] if isinstance(llm_results, list) else llm_results
                items = raw.get('items') or []
                response_text = None
                for item in items:
                    if item.get('type') in ('message', 'answer', 'response'):
                        sections = item.get('sections') or []
                        if sections:
                            response_text = '\n\n'.join(
                                s.get('text', '') for s in sections if s.get('text')
                            )
                        else:
                            response_text = item.get('text') or item.get('description')
                        break
                if response_text:
                    llm_data.append({
                        'platform': platform_name,
                        'response': response_text,
                        'domain_mentioned': _domain_mentioned(
                            response_text, clean_domain, brand_query
                        ),
                    })
        except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
            logger.warning('%s LLM response fetch failed: %s', platform_name, exc)
            result['errors'].append(f'{platform_name}: {exc}')

    result['llm_responses'] = llm_data if llm_data else []

    return result
