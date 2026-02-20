import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

# dataforseo_api imports credential.py which must be on path too
import dataforseo_api as _dfs_api
from dataforseo_api import api_post, get_result, format_count


def run_keyword_research(keyword: str, location_code: int = 2826, limit: int = 20) -> dict:
    """Run keyword research via DataForSEO. Returns structured dict."""
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
        items = results[0].get('items', []) if results else []
        for item in items[:limit]:
            keywords.append({
                'keyword': item.get('keyword', ''),
                'volume': format_count(item.get('search_volume', 0)),
                'volume_raw': item.get('search_volume', 0) or 0,
                'difficulty': item.get('keyword_difficulty', 'N/A'),
                'competition': item.get('competition_level', 'N/A'),
            })

    return {
        'seed_keyword': keyword,
        'location_code': location_code,
        'keywords': keywords,
        'count': len(keywords),
    }
