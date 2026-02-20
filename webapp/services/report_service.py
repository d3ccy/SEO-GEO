import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from report_generators.content_guide import build_content_guide
from report_generators.geo_audit_report import build_geo_audit_report


def generate_content_guide_docx(params: dict, output_path: str):
    """Generate a Content Guide DOCX and save to output_path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = build_content_guide(params)
    doc.save(output_path)


def generate_geo_audit_docx(params: dict, audit: dict, output_path: str):
    """Generate a full GEO Audit Report DOCX and save to output_path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = build_geo_audit_report(params, audit)
    doc.save(output_path)
