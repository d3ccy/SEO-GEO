import logging
import re

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


def _clean_answer_snippet(raw: str, max_chars: int = 200) -> str:
    """
    Strip raw DataForSEO bracket-URL markdown from LLM mention answer text.
    Converts: [[Title](https://url)] → '' and trims whitespace.
    Returns a clean plain-text snippet truncated to max_chars.
    """
    if not raw:
        return ''
    # Remove [[text](url)] and [text](url) patterns
    cleaned = re.sub(r'\[\[?[^\]]*\]\([^)]*\)\]?', '', raw)
    # Remove bare URLs
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:max_chars]


_UGC_DOMAINS = {
    'reddit.com', 'quora.com', 'stackoverflow.com', 'stackexchange.com',
    'tripadvisor.co.uk', 'tripadvisor.com', 'trustpilot.com', 'yelp.com',
    'mumsnet.com', 'netmums.com', 'forums.', 'community.',
}
_AUTHORITY_DOMAINS = {
    'gov.uk', '.gov', 'wikipedia.org', 'w3.org', 'bbc.co.uk', 'bbc.com',
    'nhs.uk', 'ico.org.uk', 'nominet.uk', 'ofcom.org.uk',
}
_DIRECTORY_DOMAINS = {
    'clutch.co', 'g2.com', 'capterra.com', 'whatcms.org', 'builtwith.com',
    'crunchbase.com', 'companieshouse.gov.uk',
}


def _classify_domain_type(domain: str) -> str:
    """Return a source type label for a domain: UGC, Authority, Directory, or Editorial."""
    d = domain.lower()
    if any(u in d for u in _UGC_DOMAINS):
        return 'UGC'
    if any(a in d for a in _AUTHORITY_DOMAINS):
        return 'Authority'
    if any(di in d for di in _DIRECTORY_DOMAINS):
        return 'Directory'
    return 'Editorial'


def _classify_sentiment(text: str, domain: str, brand_query: str = '') -> str:
    """
    Basic sentiment classification for an LLM response about a brand.
    Returns 'positive', 'negative', or 'neutral'.
    Uses keyword matching — no external API needed.
    """
    if not text:
        return 'neutral'
    t = text.lower()
    positive_words = [
        'excellent', 'outstanding', 'highly recommend', 'award-winning',
        'trusted', 'leading', 'expertise', 'specialist', 'renowned',
        'well-regarded', 'strong reputation', 'quality', 'impressive',
        'best', 'top', 'great', 'positive', 'effective', 'successful',
    ]
    negative_words = [
        'poor', 'disappointing', 'complaint', 'issue', 'problem', 'bad',
        'avoid', 'warning', 'negative', 'failed', 'lawsuit', 'scandal',
        'controversy', 'misleading', 'overpriced', 'unreliable',
    ]
    pos = sum(1 for w in positive_words if w in t)
    neg = sum(1 for w in negative_words if w in t)
    if pos > neg + 1:
        return 'positive'
    elif neg > pos:
        return 'negative'
    return 'neutral'


def _calculate_visibility_score(
    mentions: list | None,
    llm_responses: list | None,
    chatgpt: dict | None,
    aggregated_metrics: list | None,
) -> dict:
    """
    Calculate a 0–100 AI visibility score from already-collected data.
    No new API calls.

    Scoring formula:
      mention_score   = min(len(mentions), 20) / 20 * 40   → 0–40 pts
      llm_score       = (platforms_mentioned / 5) * 30      → 0–30 pts
      citation_score  = 20 if any mentions else 0            → 0–20 pts
      chatgpt_score   = 10 if chatgpt domain_mentioned else 0 → 0–10 pts
      Total: 0–100

    Returns dict with keys: score (int), grade (str), colour (str),
    platforms_mentioned (int), platforms_total (int).
    """
    mention_count = len(mentions) if mentions else 0
    mention_score = min(mention_count, 20) / 20 * 40

    platforms_mentioned = 0
    platforms_total = len(llm_responses) if llm_responses else 0
    if llm_responses:
        platforms_mentioned = sum(1 for r in llm_responses if r.get('domain_mentioned'))
    if chatgpt and chatgpt.get('domain_mentioned'):
        platforms_mentioned += 1
        platforms_total += 1
    llm_score = (platforms_mentioned / max(platforms_total, 1)) * 30

    citation_score = 20 if mention_count > 0 else 0

    chatgpt_score = 10 if (chatgpt and chatgpt.get('domain_mentioned')) else 0

    total = int(mention_score + llm_score + citation_score + chatgpt_score)
    total = max(0, min(100, total))

    if total >= 70:
        grade, colour = 'Strong', 'green'
    elif total >= 40:
        grade, colour = 'Needs work', 'amber'
    else:
        grade, colour = 'Low visibility', 'red'

    return {
        'score': total,
        'grade': grade,
        'colour': colour,
        'platforms_mentioned': platforms_mentioned,
        'platforms_total': platforms_total,
    }


def _generate_recommendations(result: dict) -> list[dict]:
    """
    Generate prioritised, actionable recommendations from collected data.
    Returns a list of dicts: {priority, title, finding, action, link_text, link_route}.
    priority: 'high', 'medium', 'low'
    No API calls — derived from already-collected data.
    """
    recs = []
    domain = result.get('domain', '')
    mentions = result.get('mentions') or []
    llm_responses = result.get('llm_responses') or []
    top_domains = result.get('top_domains') or []
    ai_overview = result.get('ai_overview') or {}
    chatgpt = result.get('chatgpt') or {}
    vs = result.get('visibility_score') or {}

    # 1. Not in Google AI Overviews
    if not ai_overview.get('domain_mentioned'):
        recs.append({
            'priority': 'high',
            'title': 'Not appearing in Google AI Overviews',
            'finding': f'{domain} was not cited in Google\'s AI Overview for this query.',
            'action': 'Run the GEO Audit to check for missing schema markup (Organization, FAQPage). '
                      'Adding structured data is the highest-impact change for Google AI visibility.',
            'link_text': 'Run GEO Audit →',
            'link_route': 'audit',
        })

    # 2. Not in ChatGPT
    if chatgpt and not chatgpt.get('domain_mentioned'):
        recs.append({
            'priority': 'high',
            'title': 'Not appearing in ChatGPT search results',
            'finding': f'{domain} was not mentioned in ChatGPT\'s answer or cited sources.',
            'action': 'Ensure your site has clear, crawlable content about your core services. '
                      'Check robots.txt allows GPTBot. Consider earning coverage on '
                      'editorial sites that ChatGPT tends to cite.',
            'link_text': None, 'link_route': None,
        })

    # 3. Low mention count
    if len(mentions) < 3:
        recs.append({
            'priority': 'medium',
            'title': 'Low citation volume across LLMs',
            'finding': f'Only {len(mentions)} LLM mention{"s" if len(mentions) != 1 else ""} found. '
                       'Competitors typically have 10+ to rank consistently.',
            'action': 'Create content targeting high-volume AI search queries in your sector. '
                      'Focus on long-form, factual content that AI platforms tend to cite.',
            'link_text': None, 'link_route': None,
        })

    # 4. Competitor gap — if competitors were checked and any outperform
    comp = result.get('competitor_comparison') or []
    if comp:
        leaders = [c for c in comp if not c.get('is_target') and c.get('mentions', 0) > len(mentions)]
        if leaders:
            top_comp = max(leaders, key=lambda x: x['mentions'])
            recs.append({
                'priority': 'medium',
                'title': f'Competitor {top_comp["domain"]} has higher AI visibility',
                'finding': f'{top_comp["domain"]} has {top_comp["mentions"]} mentions vs your {len(mentions)}.',
                'action': f'Review what content {top_comp["domain"]} publishes that drives AI citations. '
                          'Focus on matching or exceeding their coverage of shared topic areas.',
                'link_text': None, 'link_route': None,
            })

    # 5. Source diversity — check if UGC dominates
    if top_domains:
        ugc_count = sum(1 for d in top_domains if d.get('domain_type') == 'UGC')
        if ugc_count > len(top_domains) // 2:
            recs.append({
                'priority': 'medium',
                'title': 'Citations dominated by UGC sources',
                'finding': f'{ugc_count} of {len(top_domains)} citation sources are UGC (Reddit, forums etc.). '
                           'AI platforms weight editorial and authority sources more heavily.',
                'action': 'Pursue coverage on editorial publications, sector directories, and authority '
                          'sites in your space. These are weighted more highly by AI citation algorithms.',
                'link_text': None, 'link_route': None,
            })

    # 6. Good visibility — positive reinforcement
    if vs.get('score', 0) >= 70:
        recs.append({
            'priority': 'low',
            'title': 'Strong AI visibility — monitor monthly',
            'finding': f'Visibility score of {vs.get("score")} is in the strong range. '
                       'No immediate action required.',
            'action': 'Continue monitoring monthly. Set a reminder to re-run this audit after any '
                      'major content or technical changes to the site.',
            'link_text': None, 'link_route': None,
        })

    # Sort: high → medium → low
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    recs.sort(key=lambda r: priority_order.get(r['priority'], 3))

    return recs


def run_ai_visibility(domain: str, brand_query: str, location_code: int = 2826,
                      competitor_domains: list | None = None) -> dict:
    """Check AI visibility for a domain/brand across LLM platforms.

    Returns a dict with:
      - aggregated_metrics: per-platform totals (mentions, ai_search_volume, impressions)
      - top_domains: domains most co-cited alongside the target
      - mentions: Search Mentions items (questions where domain is cited)
      - ai_overview: Google SERP AI Overview for the brand query
      - chatgpt: ChatGPT scraper result
      - llm_responses: per-platform LLM response dicts
      - competitor_comparison: cross-comparison data (if competitor_domains provided)
      - visibility_score: calculated score dict
      - recommendations: prioritised action list
      - errors: list of error strings for any failed calls

    DataForSEO endpoints used:
      - ai_optimization/llm_mentions/aggregated_metrics/live
      - ai_optimization/llm_mentions/top_domains/live
      - ai_optimization/llm_mentions/search/live
      - serp/google/organic/live/advanced  (for ai_overview)
      - ai_optimization/chat_gpt/llm_scraper/live/advanced
      - ai_optimization/{platform}/llm_responses/live  (per platform)
      - ai_optimization/llm_mentions/cross_aggregated_metrics/live  (if competitors)
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
        'competitor_comparison': None,
        'visibility_score': None,
        'recommendations': [],
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
                    'domain_type': _classify_domain_type(item.get('domain', '')),
                }
                for item in items
            ]
        else:
            result['top_domains'] = []
    except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
        logger.warning('Top Domains fetch failed: %s', exc)
        result['errors'].append(f'Top Domains: {exc}')

    # ── Competitor Cross-Comparison ──────────────────────────────────────
    # Uses cross_aggregated_metrics to compare target against competitors.
    # Only runs if competitor_domains were provided.
    if competitor_domains:
        try:
            targets = [{'domain': clean_domain, 'search_filter': 'include'}]
            for cd in competitor_domains[:3]:
                cd_clean = _clean_domain(cd)
                if cd_clean:
                    targets.append({'domain': cd_clean, 'search_filter': 'include'})

            resp = api_post('ai_optimization/llm_mentions/cross_aggregated_metrics/live', [{
                'target': targets,
                'location_code': location_code,
                'language_code': 'en',
            }])
            comp_results = get_result(resp)
            if comp_results:
                raw = comp_results[0] if isinstance(comp_results, list) else comp_results
                items = raw.get('items') or []
                comp_data = []
                for item in items:
                    d = item.get('domain', '')
                    mentions = item.get('mentions', 0)
                    ai_vol = item.get('ai_search_volume', 0)
                    comp_data.append({
                        'domain': d,
                        'mentions': mentions,
                        'ai_search_volume': ai_vol,
                        'is_target': d.lower() == clean_domain.lower(),
                    })
                # Sort: target first, then by mentions desc
                comp_data.sort(key=lambda x: (not x['is_target'], -x['mentions']))
                result['competitor_comparison'] = comp_data
            else:
                result['competitor_comparison'] = []
        except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
            logger.warning('Competitor Cross-Comparison fetch failed: %s', exc)
            result['errors'].append(f'Competitor Comparison: {exc}')

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
                    'answer_snippet': _clean_answer_snippet(item.get('answer') or '', max_chars=200),
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
                        'sentiment': _classify_sentiment(response_text, clean_domain, brand_query),
                    })
        except (RuntimeError, KeyError, TypeError, ConnectionError) as exc:
            logger.warning('%s LLM response fetch failed: %s', platform_name, exc)
            result['errors'].append(f'{platform_name}: {exc}')

    result['llm_responses'] = llm_data if llm_data else []

    # ── Visibility Score ─────────────────────────────────────────────────
    # Calculated from already-collected data — no new API calls.
    result['visibility_score'] = _calculate_visibility_score(
        mentions=result.get('mentions'),
        llm_responses=result.get('llm_responses'),
        chatgpt=result.get('chatgpt'),
        aggregated_metrics=result.get('aggregated_metrics'),
    )

    result['recommendations'] = _generate_recommendations(result)

    return result
