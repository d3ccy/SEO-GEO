import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

from dataforseo_api import api_post, get_result


def run_ai_visibility(domain: str, brand_query: str, location_code: int = 2826) -> dict:
    """Check AI visibility for a domain/brand across LLM platforms.

    Returns a dict with:
      - mentions: LLM mention data per platform (or None if call failed)
      - chatgpt: ChatGPT search scraper result (or None)
      - llm_responses: multi-LLM responses (or None)
      - errors: list of error strings for any failed calls
    """
    result = {
        'domain': domain,
        'brand_query': brand_query,
        'mentions': None,
        'chatgpt': None,
        'llm_responses': None,
        'errors': [],
    }

    # ── Panel 1: LLM Mentions ──────────────────────────────────────────────
    try:
        resp = api_post('ai_optimization/llm_mentions/live', [{
            'target': domain,
        }])
        mentions_results = get_result(resp)
        if mentions_results:
            raw = mentions_results[0] if isinstance(mentions_results, list) else mentions_results
            # Normalise into a list of platform cards
            platforms = []
            items = raw.get('items') or []
            for item in items:
                platforms.append({
                    'platform': item.get('se_type') or item.get('platform', 'Unknown'),
                    'mentions': item.get('mentions_count', 0),
                    'sentiment': item.get('sentiment', 'neutral'),
                    'sample_citations': item.get('citations', [])[:3],
                })
            result['mentions'] = platforms if platforms else []
    except Exception as e:
        result['errors'].append(f'LLM Mentions: {e}')

    # ── Panel 2: ChatGPT Search Scraper ────────────────────────────────────
    try:
        resp = api_post('ai_optimization/chatgpt_search_scraper/live', [{
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
                if item.get('type') == 'chatgpt_answer':
                    answer_text = item.get('text') or item.get('description')
                elif item.get('type') in ('source', 'organic', 'link'):
                    sources.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', '') or item.get('link', ''),
                        'domain': item.get('domain', ''),
                    })
            # Check if target domain appears in sources
            domain_mentioned = any(
                domain.lower().replace('www.', '') in (s.get('url', '') + s.get('domain', '')).lower()
                for s in sources
            )
            result['chatgpt'] = {
                'answer': answer_text,
                'sources': sources[:10],
                'domain_mentioned': domain_mentioned,
            }
    except Exception as e:
        result['errors'].append(f'ChatGPT Search: {e}')

    # ── Panel 3: Multi-LLM Responses ───────────────────────────────────────
    try:
        resp = api_post('ai_optimization/llm_responses/live', [{
            'keyword': brand_query,
            'language_code': 'en',
        }])
        llm_results = get_result(resp)
        if llm_results:
            raw = llm_results[0] if isinstance(llm_results, list) else llm_results
            items = raw.get('items') or []
            llm_data = []
            for item in items:
                platform = item.get('se_type') or item.get('platform', 'Unknown')
                response_text = item.get('text') or item.get('description') or item.get('response')
                if response_text:
                    domain_clean = domain.lower().replace('www.', '')
                    mentioned = domain_clean in response_text.lower()
                    llm_data.append({
                        'platform': platform,
                        'response': response_text,
                        'domain_mentioned': mentioned,
                    })
            result['llm_responses'] = llm_data if llm_data else []
    except Exception as e:
        result['errors'].append(f'Multi-LLM: {e}')

    return result
