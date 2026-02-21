// ── Tab switching (multi-LLM comparison) ────────────────────────────────────

document.querySelectorAll('.tab-nav').forEach(function(nav) {
  nav.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var tabId = btn.dataset.tab;
      var container = nav.parentElement;
      // Deactivate all tabs and panels in this container
      nav.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
      container.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
      // Activate selected
      btn.classList.add('active');
      var panel = container.querySelector('#' + tabId);
      if (panel) panel.classList.add('active');
    });
  });
});

// ── Competitor domain quick-fill ─────────────────────────────────────────────

document.querySelectorAll('.competitor-analyse-btn').forEach(function(btn) {
  btn.addEventListener('click', function(e) {
    e.preventDefault();
    var targetDomain = btn.dataset.domain;
    var domainField = document.getElementById('domain');
    if (domainField && targetDomain) {
      domainField.value = targetDomain;
      domainField.scrollIntoView({ behavior: 'smooth' });
      document.getElementById('domain-form').submit();
    }
  });
});

// ── Client profile auto-fill ────────────────────────────────────────────────

document.querySelectorAll('#client-select').forEach(function(select) {
  select.addEventListener('change', function() {
    var selected = this.options[this.selectedIndex];
    var domain = selected.dataset.domain || '';
    var name = selected.dataset.name || '';
    var project = selected.dataset.project || '';
    var cms = selected.dataset.cms || '';
    var location = selected.dataset.location || '';

    // Audit page: fill URL
    var urlField = document.getElementById('url');
    if (urlField && domain) {
      urlField.value = 'https://' + domain;
    }

    // Keywords page: fill keyword (domain as seed), location
    var keywordField = document.getElementById('keyword');
    if (keywordField && domain) {
      keywordField.value = domain;
    }
    var locationField = document.getElementById('location');
    if (locationField && location) {
      locationField.value = location;
    }

    // AI Visibility + Domain Overview pages: fill domain field
    var domainField = document.getElementById('domain');
    if (domainField && domain) {
      domainField.value = domain;
    }
    var brandQueryField = document.getElementById('brand_query');
    if (brandQueryField && name) {
      brandQueryField.value = name;
    }

    // Content guide page: fill all fields
    var nameField = document.getElementById('client_name');
    if (nameField && name) nameField.value = name;
    var domainField = document.getElementById('client_domain');
    if (domainField && domain) domainField.value = domain;
    var projectField = document.getElementById('project_name');
    if (projectField && project) projectField.value = project;
    var cmsField = document.getElementById('cms');
    if (cmsField && cms) cmsField.value = cms;
  });
});

// ── Loading state on form submit ────────────────────────────────────────────

document.querySelectorAll('form').forEach(function(form) {
  form.addEventListener('submit', function() {
    var btn = form.querySelector('button[type=submit]');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('loading');
    }
  });
});

// ── Sortable table ───────────────────────────────────────────────────────────

document.querySelectorAll('.sortable-table').forEach(function(table) {
  var headers = table.querySelectorAll('th.sortable');
  headers.forEach(function(th) {
    th.addEventListener('click', function() {
      var col = parseInt(th.dataset.col);
      var isNum = th.dataset.type === 'number';
      var asc = th.classList.contains('asc') ? false : true;

      headers.forEach(function(h) { h.classList.remove('asc', 'desc'); });
      th.classList.add(asc ? 'asc' : 'desc');

      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));

      rows.sort(function(a, b) {
        var cellA = a.cells[col];
        var cellB = b.cells[col];
        var va = (cellA.dataset.sort !== undefined ? cellA.dataset.sort : cellA.textContent).trim();
        var vb = (cellB.dataset.sort !== undefined ? cellB.dataset.sort : cellB.textContent).trim();

        if (isNum) {
          va = parseFloat(va) || 0;
          vb = parseFloat(vb) || 0;
          return asc ? va - vb : vb - va;
        }
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      });

      rows.forEach(function(r) { tbody.appendChild(r); });
    });
  });
});
