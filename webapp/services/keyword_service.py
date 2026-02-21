import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

# dataforseo_api imports credential.py which must be on path too
import dataforseo_api as _dfs_api
from dataforseo_api import api_post, get_result, format_count


def run_keyword_research(keyword: str, location_code: int = 2826, limit: int = 20) -> dict:
    """Run keyword research via DataForSEO. Returns structured dict with intent,
    difficulty, CPC and AI volume enrichment."""
    data = [{
        'keywords': [keyword],
        'location_code': location_code,
        'language_code': 'en',
        'limit': limit,
    }]

    response = api_post('keywords_data/google_ads/keywords_for_keywords/live', data)
    results = get_result(response)

    keywords = []
    if results:
        # keywords_for_keywords returns a flat list of keyword objects directly in result[]
        for item in results[:limit]:
            cpc_raw = item.get('cpc') or 0
            keywords.append({
                'keyword': item.get('keyword', ''),
                'volume': format_count(item.get('search_volume', 0)),
                'volume_raw': item.get('search_volume', 0) or 0,
                'difficulty': item.get('keyword_difficulty'),  # may be None; replaced by bulk call
                'competition': item.get('competition', 'N/A'),
                'cpc': f'{cpc_raw:.2f}' if cpc_raw else '—',
                'cpc_raw': float(cpc_raw),
                'intent': None,      # populated below
                'ai_volume': None,   # populated below
            })

    if not keywords:
        return {
            'seed_keyword': keyword,
            'location_code': location_code,
            'keywords': keywords,
            'count': 0,
        }

    kw_list = [k['keyword'] for k in keywords]

    # ── Bulk keyword difficulty ───────────────────────────────────────────────
    try:
        diff_resp = api_post('dataforseo_labs/google/bulk_keyword_difficulty/live', [{
            'keywords': kw_list,
            'location_code': location_code,
            'language_code': 'en',
        }])
        diff_results = get_result(diff_resp)
        if diff_results:
            diff_map = {item.get('keyword'): item.get('keyword_difficulty')
                        for item in diff_results}
            for kw in keywords:
                kd = diff_map.get(kw['keyword'])
                if kd is not None:
                    kw['difficulty'] = kd
    except Exception:
        pass  # gracefully keep existing difficulty values

    # ── Search intent ─────────────────────────────────────────────────────────
    try:
        intent_resp = api_post('dataforseo_labs/google/search_intent/live', [{
            'keywords': kw_list,
            'language_code': 'en',
        }])
        intent_results = get_result(intent_resp)
        if intent_results:
            # result[] contains one item per keyword with 'keyword' and 'keyword_intent' keys
            intent_map = {}
            for item in intent_results:
                kw_text = item.get('keyword', '')
                ki = item.get('keyword_intent', {})
                # Main intent is the type with highest probability
                main_intent = ki.get('main_intent') if ki else None
                if main_intent:
                    intent_map[kw_text] = main_intent
            for kw in keywords:
                kw['intent'] = intent_map.get(kw['keyword'])
    except Exception:
        pass  # gracefully leave intent as None

    # ── AI search volume ──────────────────────────────────────────────────────
    try:
        ai_resp = api_post('ai_optimization/ai_keyword_data/keywords_search_volume/live', [{
            'keywords': kw_list,
            'location_code': location_code,
            'language_code': 'en',
        }])
        ai_results = get_result(ai_resp)
        if ai_results:
            ai_map = {item.get('keyword'): item.get('ai_search_volume')
                      for item in ai_results}
            for kw in keywords:
                av = ai_map.get(kw['keyword'])
                kw['ai_volume'] = format_count(av) if av else None
                kw['ai_volume_raw'] = av or 0
    except Exception:
        pass  # AI volume not available on all plans

    # Normalise difficulty display
    for kw in keywords:
        if kw['difficulty'] is None:
            kw['difficulty'] = 'N/A'

    return {
        'seed_keyword': keyword,
        'location_code': location_code,
        'keywords': keywords,
        'count': len(keywords),
    }
