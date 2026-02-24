import os
import sys
import io
import csv
import uuid
import logging
from datetime import datetime
from urllib.parse import urlparse

# Put webapp/ on path so local imports work regardless of where flask is launched
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import login_required
from werkzeug.utils import secure_filename

from config import (
    Config,
    DEFAULT_LOCATION_CODE,
    DEFAULT_CMS,
    DEFAULT_KEYWORD_LIMIT,
    MAX_KEYWORD_EXPORT_LIMIT,
)
from extensions import db, login_manager, migrate
from auth import auth_bp
from client_store import load_clients, save_client, delete_client, get_client
from services.audit_service import run_audit
from services.keyword_service import run_keyword_research
from services.ai_visibility_service import run_ai_visibility
from services.domain_service import run_domain_overview
from services.report_service import generate_content_guide_docx, generate_geo_audit_docx

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── App setup ────────────────────────────────────────────────────────────────
Config.validate()
Config.ensure_output_dir()

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['SESSION_COOKIE_HTTPONLY'] = Config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = Config.SESSION_COOKIE_SAMESITE

# ── Extensions ───────────────────────────────────────────────────────────────
csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["120 per minute"],
    storage_uri="memory://",
)

db.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)

# ── Blueprints ───────────────────────────────────────────────────────────────
app.register_blueprint(auth_bp)

# Apply rate limits to auth POST routes
limiter.limit("10 per minute", methods=["POST"])(auth_bp)

# ── Create tables (if not using migrations) ──────────────────────────────────
with app.app_context():
    from models import User  # noqa: F401  ensure model is registered
    db.create_all()

    # ── Seed test user (survives ephemeral Railway redeploys) ─────────────
    _SEED_EMAIL = os.environ.get('SEED_USER_EMAIL', '').strip().lower()
    _SEED_PASS = os.environ.get('SEED_USER_PASSWORD', '')
    if _SEED_EMAIL and _SEED_PASS:
        try:
            _existing_seed = User.query.filter_by(email=_SEED_EMAIL).first()
            if not _existing_seed:
                _seed = User(email=_SEED_EMAIL, name='Seed User',
                             is_active_user=True, is_admin=True)
                _seed.activated_at = datetime.now()
                _seed.set_password(_SEED_PASS)
                db.session.add(_seed)
                db.session.commit()
                print(f'[SEED] Created seed user: {_SEED_EMAIL}')
            elif not _existing_seed.is_admin:
                _existing_seed.is_admin = True
                db.session.commit()
                print(f'[SEED] Promoted to admin: {_SEED_EMAIL}')
            else:
                print(f'[SEED] Seed user already exists: {_SEED_EMAIL}')
        except Exception as exc:
            db.session.rollback()
            print(f'[SEED] Skipped (likely race condition): {exc}')

os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_url(url):
    """Validate that *url* uses an allowed scheme (http or https).

    Returns the cleaned URL string on success, or raises ValueError with a
    safe, user-facing message on failure.
    """
    if not url:
        raise ValueError("Please enter a URL.")
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https', ''):
        raise ValueError("Only http and https URLs are allowed.")
    # If no scheme was provided, default to https
    if not parsed.scheme:
        url = f"https://{url}"
    return url


def _safe_download_path(filename):
    """Resolve *filename* inside OUTPUT_DIR and guard against path traversal.

    Returns the absolute path on success, or ``None`` if the resolved path
    escapes the output directory.
    """
    safe_path = os.path.normpath(os.path.join(Config.OUTPUT_DIR, filename))
    # Ensure the resolved path is still inside OUTPUT_DIR
    if not safe_path.startswith(os.path.normpath(Config.OUTPUT_DIR) + os.sep) and \
       safe_path != os.path.normpath(Config.OUTPUT_DIR):
        return None
    return safe_path


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    clients = load_clients()
    return render_template('index.html', clients=clients)


@app.route('/audit', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per minute", methods=["POST"])
def audit():
    clients = load_clients()
    result = None
    error = None
    url_value = ''
    if request.method == 'POST':
        url_value = request.form.get('url', '').strip()
        try:
            url_value = _validate_url(url_value)
        except ValueError as ve:
            error = str(ve)

        if not error:
            try:
                logger.info("Running audit for URL: %s", url_value)
                result = run_audit(url_value)
                logger.info("Audit completed successfully for URL: %s", url_value)
            except Exception as e:
                logger.exception("Audit failed for URL %s: %s", url_value, e)
                error = 'An unexpected error occurred while running the audit.'
    return render_template('audit.html', result=result, error=error,
                           clients=clients, url_value=url_value)


@app.route('/keywords', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per minute", methods=["POST"])
def keywords():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {
            'keyword': request.form.get('keyword', '').strip(),
            'location': request.form.get('location', str(DEFAULT_LOCATION_CODE)),
            'limit': request.form.get('limit', str(DEFAULT_KEYWORD_LIMIT)),
        }
        if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
            error = 'DataForSEO credentials are not configured. Please set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD environment variables.'
        elif form['keyword']:
            try:
                logger.info("Running keyword research for: %s", form['keyword'])
                result = run_keyword_research(
                    form['keyword'],
                    location_code=int(form['location']),
                    limit=int(form['limit']),
                )
            except Exception as e:
                logger.exception("Keyword research failed for '%s': %s", form['keyword'], e)
                error = 'Keyword research failed. Please check your credentials and try again.'
        else:
            error = 'Please enter a keyword.'
    return render_template('keywords.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/content-guide', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def content_guide():
    clients = load_clients()
    error = None
    if request.method == 'POST':
        params = {
            'client_name': request.form.get('client_name', '').strip(),
            'client_domain': request.form.get('client_domain', '').strip(),
            'project_name': request.form.get('project_name', '').strip(),
            'date': request.form.get('date', '').strip() or datetime.now().strftime('%B %Y'),
            'cms': request.form.get('cms', DEFAULT_CMS).strip(),
        }

        # Handle logo upload
        logo_path = Config.AGENCY_LOGO_PATH
        if 'client_logo' in request.files:
            f = request.files['client_logo']
            if f and f.filename:
                ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
                if ext in Config.ALLOWED_EXTENSIONS:
                    fname = f'{uuid.uuid4().hex}.{ext}'
                    save_path = os.path.join(Config.UPLOAD_FOLDER, fname)
                    f.save(save_path)
                    logo_path = save_path
                else:
                    error = f'Logo must be one of: {", ".join(Config.ALLOWED_EXTENSIONS)}'

        if not error:
            params['logo_path'] = logo_path
            slug = params['client_domain'].replace('.', '-') or 'report'
            filename = f"content-guide-{slug}-{uuid.uuid4().hex[:6]}.docx"
            output_path = os.path.join(Config.OUTPUT_DIR, filename)
            try:
                logger.info("Generating content guide for domain: %s", params['client_domain'])
                generate_content_guide_docx(params, output_path)
                return redirect(url_for('download_file', filename=filename))
            except Exception as e:
                logger.exception("Content guide generation failed: %s", e)
                error = 'Failed to generate the content guide. Please try again.'

    return render_template('content_guide.html', clients=clients, error=error)


@app.route('/audit-report', methods=['POST'])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def audit_report():
    """Run a GEO audit and download the result as a branded DOCX report."""
    url_value = request.form.get('url', '').strip()
    client_name = request.form.get('client_name', '').strip()
    project_name = request.form.get('project_name', '').strip()

    if not url_value:
        flash('Please enter a URL to generate a report.', 'error')
        return redirect(url_for('audit'))

    try:
        url_value = _validate_url(url_value)
    except ValueError:
        flash('Invalid URL. Only http and https URLs are allowed.', 'error')
        return redirect(url_for('audit'))

    try:
        logger.info("Running audit report for URL: %s", url_value)
        audit_data = run_audit(url_value)
    except Exception as e:
        logger.exception("Audit report failed for URL %s: %s", url_value, e)
        flash('Could not fetch URL — check the address and try again.', 'error')
        return redirect(url_for('audit'))

    # Build report params from form + audit data
    domain = audit_data.get('url', url_value).replace('https://', '').replace('http://', '').rstrip('/')
    params = {
        'client_name': client_name or domain,
        'client_domain': domain,
        'project_name': project_name,
        'date': datetime.now().strftime('%B %Y'),
        'logo_path': Config.AGENCY_LOGO_PATH,
    }

    slug = domain.replace('.', '-').replace('/', '-')
    filename = f"geo-audit-{slug}-{uuid.uuid4().hex[:6]}.docx"
    output_path = os.path.join(Config.OUTPUT_DIR, filename)

    try:
        generate_geo_audit_docx(params, audit_data, output_path)
        logger.info("Audit report generated: %s", filename)
    except Exception as e:
        logger.exception("Audit report generation failed: %s", e)
        flash('Failed to generate the audit report. Please try again.', 'error')
        return redirect(url_for('audit'))

    return send_file(output_path, as_attachment=True, download_name=filename)


@app.route('/download/<path:filename>')
@login_required
def download_file(filename):
    path = _safe_download_path(filename)
    if path is None:
        logger.warning("Path traversal attempt blocked for filename: %s", filename)
        return 'Invalid filename.', 400
    if not os.path.exists(path):
        return 'File not found. It may have expired.', 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.route('/clients')
@login_required
def clients():
    all_clients = load_clients()
    return render_template('clients.html', clients=all_clients)


@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per minute", methods=["POST"])
def client_new():
    if request.method == 'POST':
        client = {
            'id': uuid.uuid4().hex,
            'name': request.form.get('name', '').strip(),
            'domain': request.form.get('domain', '').strip(),
            'project_name': request.form.get('project_name', '').strip(),
            'cms': request.form.get('cms', '').strip(),
            'location_code': int(request.form.get('location_code', DEFAULT_LOCATION_CODE) or DEFAULT_LOCATION_CODE),
            'notes': request.form.get('notes', '').strip(),
            'created': datetime.now().isoformat(),
        }
        if not client['name']:
            flash('Client name is required.', 'error')
            return render_template('client_form.html', client=client, action='new')
        save_client(client)
        logger.info("New client created: %s (%s)", client['name'], client['id'])
        flash(f'Client \u201c{client["name"]}\u201d saved.')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None, action='new')


@app.route('/clients/<client_id>/edit', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per minute", methods=["POST"])
def client_edit(client_id):
    client = get_client(client_id)
    if not client:
        flash('Client not found.', 'error')
        return redirect(url_for('clients'))
    if request.method == 'POST':
        client.update({
            'name': request.form.get('name', '').strip(),
            'domain': request.form.get('domain', '').strip(),
            'project_name': request.form.get('project_name', '').strip(),
            'cms': request.form.get('cms', '').strip(),
            'location_code': int(request.form.get('location_code', DEFAULT_LOCATION_CODE) or DEFAULT_LOCATION_CODE),
            'notes': request.form.get('notes', '').strip(),
        })
        if not client['name']:
            flash('Client name is required.', 'error')
            return render_template('client_form.html', client=client, action='edit')
        save_client(client)
        logger.info("Client updated: %s (%s)", client['name'], client_id)
        flash(f'Client \u201c{client["name"]}\u201d updated.')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=client, action='edit')


@app.route('/clients/<client_id>/delete', methods=['POST'])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def client_delete(client_id):
    client = get_client(client_id)
    name = client.get('name', 'Unknown')
    delete_client(client_id)
    logger.info("Client deleted: %s (%s)", name, client_id)
    flash(f'Client \u201c{name}\u201d deleted.')
    return redirect(url_for('clients'))


@app.route('/ai-visibility', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per minute", methods=["POST"])
def ai_visibility():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {
            'domain': request.form.get('domain', '').strip(),
            'brand_query': request.form.get('brand_query', '').strip(),
        }
        if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
            error = 'DataForSEO credentials are not configured.'
        elif form['domain']:
            brand_query = form['brand_query'] or form['domain']
            try:
                logger.info("Running AI visibility for domain: %s", form['domain'])
                result = run_ai_visibility(
                    form['domain'],
                    brand_query=brand_query,
                )
            except Exception as e:
                logger.exception("AI visibility check failed for '%s': %s", form['domain'], e)
                error = 'AI Visibility check failed. Please try again.'
        else:
            error = 'Please enter a domain.'
    return render_template('ai_visibility.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/domain', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per minute", methods=["POST"])
def domain():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {
            'domain': request.form.get('domain', '').strip(),
            'location': request.form.get('location', str(DEFAULT_LOCATION_CODE)),
        }
        if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
            error = 'DataForSEO credentials are not configured.'
        elif form['domain']:
            try:
                logger.info("Running domain overview for: %s", form['domain'])
                result = run_domain_overview(
                    form['domain'],
                    location_code=int(form['location']),
                )
            except Exception as e:
                logger.exception("Domain overview failed for '%s': %s", form['domain'], e)
                error = 'Domain overview failed. Please try again.'
        else:
            error = 'Please enter a domain.'
    return render_template('domain.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/keywords/export')
@login_required
@limiter.limit("10 per minute")
def keywords_export():
    """Export keyword research as CSV."""
    keyword = request.args.get('keyword', '').strip()
    location = request.args.get('location', str(DEFAULT_LOCATION_CODE))
    if not keyword:
        return 'No keyword specified.', 400
    if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
        return 'DataForSEO credentials not configured.', 503

    try:
        logger.info("Exporting keywords CSV for: %s", keyword)
        data = run_keyword_research(keyword, location_code=int(location), limit=MAX_KEYWORD_EXPORT_LIMIT)
    except Exception as e:
        logger.exception("Keyword export failed for '%s': %s", keyword, e)
        return 'Keyword export failed. Please try again.', 500

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Keyword', 'Volume', 'Difficulty', 'CPC', 'Intent', 'AI Volume', 'Competition'])
    for kw in data.get('keywords', []):
        writer.writerow([
            kw.get('keyword', ''),
            kw.get('volume_raw', ''),
            kw.get('difficulty', ''),
            kw.get('cpc', ''),
            kw.get('intent', ''),
            kw.get('ai_volume_raw', ''),
            kw.get('competition', ''),
        ])

    safe_keyword = secure_filename(keyword)[:40] or 'export'
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="keywords-{safe_keyword}.csv"'},
    )


@app.route('/health')
@csrf.exempt
def health():
    return {'status': 'ok'}, 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
