import sys
import os

# Put scripts/ on path so seo_audit.py and dataforseo_api.py can be imported
_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
_SCRIPTS_DIR = os.path.abspath(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
