import os
import sys
import uuid
from datetime import datetime

# Put webapp/ on path so local imports work regardless of where flask is launched
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, send_file, flash

from config import Config
from auth import requires_auth
from client_store import load_clients, save_client, delete_client, get_client
from services.audit_service import run_audit
from services.keyword_service import run_keyword_research
from services.ai_visibility_service import run_ai_visibility
from services.domain_service import run_domain_overview
from services.report_service import generate_content_guide_docx, generate_geo_audit_docx

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


def _get_password():
    return Config.APP_PASSWORD


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
@requires_auth(_get_password)
def index():
    clients = load_clients()
    return render_template('index.html', clients=clients)


@app.route('/audit', methods=['GET', 'POST'])
@requires_auth(_get_password)
def audit():
    clients = load_clients()
    result = None
    error = None
    url_value = ''
    if request.method == 'POST':
        url_value = request.form.get('url', '').strip()
        if url_value:
            try:
                result = run_audit(url_value)
            except (Exception, SystemExit) as e:
                error = str(e) or 'An unexpected error occurred.'
        else:
            error = 'Please enter a URL.'
    return render_template('audit.html', result=result, error=error,
                           clients=clients, url_value=url_value)


@app.route('/keywords', methods=['GET', 'POST'])
@requires_auth(_get_password)
def keywords():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {
            'keyword': request.form.get('keyword', '').strip(),
            'location': request.form.get('location', '2826'),
            'limit': request.form.get('limit', '20'),
        }
        if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
            error = 'DataForSEO credentials are not configured. Please set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD environment variables.'
        elif form['keyword']:
            try:
                result = run_keyword_research(
                    form['keyword'],
                    location_code=int(form['location']),
                    limit=int(form['limit']),
                )
            except (Exception, SystemExit) as e:
                error = str(e) or 'Keyword research failed. Check your DataForSEO credentials.'
        else:
            error = 'Please enter a keyword.'
    return render_template('keywords.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/content-guide', methods=['GET', 'POST'])
@requires_auth(_get_password)
def content_guide():
    clients = load_clients()
    error = None
    if request.method == 'POST':
        params = {
            'client_name': request.form.get('client_name', '').strip(),
            'client_domain': request.form.get('client_domain', '').strip(),
            'project_name': request.form.get('project_name', '').strip(),
            'date': request.form.get('date', '').strip() or datetime.now().strftime('%B %Y'),
            'cms': request.form.get('cms', 'Drupal').strip(),
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
                generate_content_guide_docx(params, output_path)
                return redirect(url_for('download_file', filename=filename))
            except Exception as e:
                error = f'Failed to generate report: {e}'

    return render_template('content_guide.html', clients=clients, error=error)


@app.route('/audit-report', methods=['POST'])
@requires_auth(_get_password)
def audit_report():
    """Run a GEO audit and download the result as a branded DOCX report."""
    url_value = request.form.get('url', '').strip()
    client_name = request.form.get('client_name', '').strip()
    project_name = request.form.get('project_name', '').strip()

    if not url_value:
        flash('Please enter a URL to generate a report.', 'error')
        return redirect(url_for('audit'))

    try:
        audit_data = run_audit(url_value)
    except (Exception, SystemExit) as e:
        flash(str(e) or 'Could not fetch URL — check the address and try again.', 'error')
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
    except Exception as e:
        flash(f'Failed to generate report: {e}', 'error')
        return redirect(url_for('audit'))

    return send_file(output_path, as_attachment=True, download_name=filename)


@app.route('/download/<path:filename>')
@requires_auth(_get_password)
def download_file(filename):
    # Block path traversal
    if os.sep in filename or '/' in filename or '..' in filename:
        return 'Invalid filename.', 400
    path = os.path.join(Config.OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return 'File not found. It may have expired.', 404
    return send_file(path, as_attachment=True, download_name=filename)


@app.route('/clients')
@requires_auth(_get_password)
def clients():
    all_clients = load_clients()
    return render_template('clients.html', clients=all_clients)


@app.route('/clients/new', methods=['GET', 'POST'])
@requires_auth(_get_password)
def client_new():
    if request.method == 'POST':
        client = {
            'id': uuid.uuid4().hex,
            'name': request.form.get('name', '').strip(),
            'domain': request.form.get('domain', '').strip(),
            'project_name': request.form.get('project_name', '').strip(),
            'cms': request.form.get('cms', '').strip(),
            'location_code': int(request.form.get('location_code', 2826) or 2826),
            'notes': request.form.get('notes', '').strip(),
            'created': datetime.now().isoformat(),
        }
        if not client['name']:
            flash('Client name is required.', 'error')
            return render_template('client_form.html', client=client, action='new')
        save_client(client)
        flash(f'Client \u201c{client["name"]}\u201d saved.')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None, action='new')


@app.route('/clients/<client_id>/edit', methods=['GET', 'POST'])
@requires_auth(_get_password)
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
            'location_code': int(request.form.get('location_code', 2826) or 2826),
            'notes': request.form.get('notes', '').strip(),
        })
        if not client['name']:
            flash('Client name is required.', 'error')
            return render_template('client_form.html', client=client, action='edit')
        save_client(client)
        flash(f'Client \u201c{client["name"]}\u201d updated.')
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=client, action='edit')


@app.route('/clients/<client_id>/delete', methods=['POST'])
@requires_auth(_get_password)
def client_delete(client_id):
    client = get_client(client_id)
    name = client.get('name', 'Unknown')
    delete_client(client_id)
    flash(f'Client \u201c{name}\u201d deleted.')
    return redirect(url_for('clients'))


@app.route('/ai-visibility', methods=['GET', 'POST'])
@requires_auth(_get_password)
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
                result = run_ai_visibility(
                    form['domain'],
                    brand_query=brand_query,
                )
            except (Exception, SystemExit) as e:
                error = str(e) or 'AI Visibility check failed.'
        else:
            error = 'Please enter a domain.'
    return render_template('ai_visibility.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/domain', methods=['GET', 'POST'])
@requires_auth(_get_password)
def domain():
    clients = load_clients()
    result = None
    error = None
    form = {}
    if request.method == 'POST':
        form = {
            'domain': request.form.get('domain', '').strip(),
            'location': request.form.get('location', '2826'),
        }
        if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
            error = 'DataForSEO credentials are not configured.'
        elif form['domain']:
            try:
                result = run_domain_overview(
                    form['domain'],
                    location_code=int(form['location']),
                )
            except (Exception, SystemExit) as e:
                error = str(e) or 'Domain overview failed.'
        else:
            error = 'Please enter a domain.'
    return render_template('domain.html', result=result, error=error,
                           clients=clients, form=form)


@app.route('/keywords/export')
@requires_auth(_get_password)
def keywords_export():
    """Export keyword research as CSV."""
    keyword = request.args.get('keyword', '').strip()
    location = request.args.get('location', '2826')
    if not keyword:
        return 'No keyword specified.', 400
    if not Config.DATAFORSEO_LOGIN or not Config.DATAFORSEO_PASSWORD:
        return 'DataForSEO credentials not configured.', 503

    try:
        data = run_keyword_research(keyword, location_code=int(location), limit=50)
    except Exception as e:
        return str(e), 500

    from flask import Response
    import io
    import csv

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

    safe_keyword = keyword.replace(' ', '-').replace('/', '-')[:40]
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=keywords-{safe_keyword}.csv'},
    )


@app.route('/health')
def health():
    return {'status': 'ok'}, 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
