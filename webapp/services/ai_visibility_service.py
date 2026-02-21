import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

from dataforseo_api import api_post, get_result, format_count


def run_ai_visibility(domain: str, brand_query: str, location_code: int = 2826) -> dict:
    """Check AI visibility for a domain/brand across LLM platforms.

    Returns a dict with:
      - mentions: list of LLM mention items (questions where domain is cited) or None
      - chatgpt: ChatGPT scraper result dict or None
      - llm_responses: list of per-platform LLM response dicts or None
      - errors: list of error strings for any failed calls

    DataForSEO endpoints used (correct paths as of 2025):
      - ai_optimization/llm_mentions/search/live
      - ai_optimization/chat_gpt/llm_scraper/live/advanced
      - ai_optimization/{platform}/llm_responses/live  (per platform)
    """
    result = {
        'domain': domain,
        'brand_query': brand_query,
        'mentions': None,
        'chatgpt': None,
        'llm_responses': None,
        'errors': [],
    }

    # Strip protocol/www prefix — API expects bare domain e.g. numiko.com
    clean_domain = domain.replace('https://', '').replace('http://', '')
    if clean_domain.startswith('www.'):
        clean_domain = clean_domain[4:]
    clean_domain = clean_domain.rstrip('/')

    # ── Panel 1: LLM Mentions ──────────────────────────────────────────────
    # Correct endpoint: ai_optimization/llm_mentions/search/live
    # 'target' must be a list of entity objects (not a plain string)
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
            # Each item = a question/answer where the domain was cited as a source
            mentions_list = []
            for item in items:
                sources = item.get('sources') or []
                mentions_list.append({
                    'question': item.get('question', ''),
                    'answer_snippet': (item.get('answer') or '')[:300],
                    'ai_search_volume': item.get('ai_search_volume', 0),
                    'platform': item.get('platform', 'google'),
                    'source_domains': [s.get('domain', '') for s in sources[:3]],
                })
            result['mentions'] = mentions_list
        else:
            result['mentions'] = []
    except Exception as e:
        result['errors'].append(f'LLM Mentions: {e}')

    # ── Panel 2: ChatGPT Search Scraper ────────────────────────────────────
    # Correct endpoint: ai_optimization/chat_gpt/llm_scraper/live/advanced
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
            # Check if domain appears in cited sources or answer text
            domain_clean = clean_domain.lower()
            domain_mentioned = any(
                domain_clean in (s.get('url', '') + s.get('domain', '')).lower()
                for s in sources
            )
            if not domain_mentioned and answer_text:
                domain_mentioned = domain_clean in answer_text.lower()
            result['chatgpt'] = {
                'answer': answer_text,
                'sources': sources[:10],
                'domain_mentioned': domain_mentioned,
            }
    except Exception as e:
        result['errors'].append(f'ChatGPT Search: {e}')

    # ── Panel 3: Multi-LLM Responses ───────────────────────────────────────
    # Each platform has its own endpoint; request uses 'user_prompt' + 'model_name'
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
                        # Rich format uses sections[]; plain format uses text
                        sections = item.get('sections') or []
                        if sections:
                            response_text = '\n\n'.join(
                                s.get('text', '') for s in sections if s.get('text')
                            )
                        else:
                            response_text = item.get('text') or item.get('description')
                        break
                if response_text:
                    domain_clean = clean_domain.lower()
                    mentioned = domain_clean in response_text.lower()
                    llm_data.append({
                        'platform': platform_name,
                        'response': response_text,
                        'domain_mentioned': mentioned,
                    })
        except Exception as e:
            result['errors'].append(f'{platform_name}: {e}')

    result['llm_responses'] = llm_data if llm_data else []

    return result
