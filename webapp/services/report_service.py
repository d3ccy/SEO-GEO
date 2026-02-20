import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from report_generators.content_guide import build_content_guide


def generate_content_guide_docx(params: dict, output_path: str):
    """Generate a Content Guide DOCX and save to output_path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = build_content_guide(params)
    doc.save(output_path)
