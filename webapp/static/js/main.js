// ── Tab switching (multi-LLM comparison) ────────────────────────────────────

document.querySelectorAll('.tab-nav').forEach((nav) => {
  // Set ARIA role on the tab list
  nav.setAttribute('role', 'tablist');

  const buttons = nav.querySelectorAll('.tab-btn');

  buttons.forEach((btn) => {
    const tabId = btn.dataset.tab;

    // Set ARIA attributes on each tab button
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-controls', tabId);
    btn.setAttribute('aria-selected', btn.classList.contains('active') ? 'true' : 'false');
    btn.setAttribute('tabindex', btn.classList.contains('active') ? '0' : '-1');

    // Set ARIA attributes on the corresponding panel
    const panel = nav.parentElement.querySelector('#' + tabId);
    if (panel) {
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', btn.id || tabId + '-tab');
      // Ensure the button has an id for aria-labelledby
      if (!btn.id) {
        btn.id = tabId + '-tab';
      }
    }

    btn.addEventListener('click', () => {
      activateTab(nav, btn);
    });

    // Keyboard navigation for tabs
    btn.addEventListener('keydown', (e) => {
      const currentButtons = Array.from(nav.querySelectorAll('.tab-btn'));
      const index = currentButtons.indexOf(btn);
      let targetIndex = -1;

      switch (e.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          e.preventDefault();
          targetIndex = (index + 1) % currentButtons.length;
          break;
        case 'ArrowLeft':
        case 'ArrowUp':
          e.preventDefault();
          targetIndex = (index - 1 + currentButtons.length) % currentButtons.length;
          break;
        case 'Home':
          e.preventDefault();
          targetIndex = 0;
          break;
        case 'End':
          e.preventDefault();
          targetIndex = currentButtons.length - 1;
          break;
        default:
          return;
      }

      if (targetIndex >= 0) {
        currentButtons[targetIndex].focus();
        activateTab(nav, currentButtons[targetIndex]);
      }
    });
  });
});

/**
 * Activate a tab button and its corresponding panel within a tab nav.
 */
function activateTab(nav, btn) {
  const tabId = btn.dataset.tab;
  const container = nav.parentElement;

  // Deactivate all tabs and panels in this container
  nav.querySelectorAll('.tab-btn').forEach((b) => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
    b.setAttribute('tabindex', '-1');
  });
  container.querySelectorAll('.tab-panel').forEach((p) => {
    p.classList.remove('active');
  });

  // Activate selected
  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
  btn.setAttribute('tabindex', '0');

  const panel = container.querySelector('#' + tabId);
  if (panel) {
    panel.classList.add('active');
  }
}

// ── Competitor domain quick-fill (event delegation) ─────────────────────────

document.addEventListener('click', (e) => {
  const btn = e.target.closest('.competitor-analyse-btn');
  if (!btn) return;

  e.preventDefault();
  const targetDomain = btn.dataset.domain;
  const domainField = document.getElementById('domain');
  if (domainField && targetDomain) {
    domainField.value = targetDomain;
    domainField.scrollIntoView({ behavior: 'smooth' });
    const form = document.getElementById('domain-form');
    if (form) {
      form.submit();
    }
  }
});

// ── Client profile auto-fill ────────────────────────────────────────────────

document.querySelectorAll('#client-select').forEach((select) => {
  select.addEventListener('change', function () {
    const selected = this.options[this.selectedIndex];
    const domain = selected.dataset.domain || '';
    const name = selected.dataset.name || '';
    const project = selected.dataset.project || '';
    const cms = selected.dataset.cms || '';
    const location = selected.dataset.location || '';

    // Audit page: fill URL
    // Strip any protocol from domain before prepending https:// so we never
    // produce a double-protocol value (e.g. if the stored domain includes https://)
    const urlField = document.getElementById('url');
    if (urlField && domain) {
      const cleanDomain = domain.replace(/^https?:\/\//, '');
      urlField.value = 'https://' + cleanDomain;
    }

    // Keywords page: fill keyword (domain as seed), location
    const keywordField = document.getElementById('keyword');
    if (keywordField && domain) {
      keywordField.value = domain;
    }
    const locationField = document.getElementById('location');
    if (locationField && location) {
      locationField.value = location;
    }

    // AI Visibility + Domain Overview pages: fill domain field
    const domainField = document.getElementById('domain');
    if (domainField && domain) {
      domainField.value = domain;
    }
    const brandQueryField = document.getElementById('brand_query');
    if (brandQueryField && name) {
      brandQueryField.value = name;
    }

    // Content guide page: fill all fields
    const nameField = document.getElementById('client_name');
    if (nameField && name) nameField.value = name;
    const clientDomainField = document.getElementById('client_domain');
    if (clientDomainField && domain) clientDomainField.value = domain;
    const projectField = document.getElementById('project_name');
    if (projectField && project) projectField.value = project;
    const cmsField = document.getElementById('cms');
    if (cmsField && cms) cmsField.value = cms;
  });
});

// ── Loading state on form submit ────────────────────────────────────────────

document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', () => {
    const btn = form.querySelector('button[type=submit]');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('loading');
    }
  });
});

// Re-enable submit buttons when navigating back to the page (e.g. after a
// server error). The pageshow event fires when a page is restored from the
// bfcache, which the unload/load pair does not reliably cover.
window.addEventListener('pageshow', () => {
  document.querySelectorAll('button[type=submit].loading').forEach((btn) => {
    btn.disabled = false;
    btn.classList.remove('loading');
  });
});

// ── Delete confirmation (clients + users) ───────────────────────────────────

document.addEventListener('submit', (e) => {
  const clientForm = e.target.closest('.delete-client-form');
  const userForm = e.target.closest('.delete-user-form');
  const form = clientForm || userForm;
  if (!form) return;

  const name = form.dataset.confirmName || 'this item';
  if (!confirm('Delete "' + name + '"? This cannot be undone.')) {
    e.preventDefault();
  }
});

// ── Sortable table ───────────────────────────────────────────────────────────

document.querySelectorAll('.sortable-table').forEach((table) => {
  const headers = table.querySelectorAll('th.sortable');

  headers.forEach((th) => {
    // Make sortable headers keyboard-focusable
    th.setAttribute('tabindex', '0');
    th.setAttribute('aria-sort', 'none');

    const sortColumn = () => {
      const col = parseInt(th.dataset.col, 10);
      const isNum = th.dataset.type === 'number';
      const asc = !th.classList.contains('asc');

      headers.forEach((h) => {
        h.classList.remove('asc', 'desc');
        h.setAttribute('aria-sort', 'none');
      });
      th.classList.add(asc ? 'asc' : 'desc');
      th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');

      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));

      rows.sort((a, b) => {
        const cellA = a.cells[col];
        const cellB = b.cells[col];
        let va = (cellA.dataset.sort !== undefined ? cellA.dataset.sort : cellA.textContent).trim();
        let vb = (cellB.dataset.sort !== undefined ? cellB.dataset.sort : cellB.textContent).trim();

        if (isNum) {
          va = parseFloat(va) || 0;
          vb = parseFloat(vb) || 0;
          return asc ? va - vb : vb - va;
        }
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      });

      rows.forEach((r) => { tbody.appendChild(r); });
    };

    th.addEventListener('click', sortColumn);

    // Allow sorting via keyboard (Enter or Space)
    th.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        sortColumn();
      }
    });
  });
});

// ── Quick-create client modal ────────────────────────────────────────────────

(function () {
  const modal = document.getElementById('add-client-modal');
  const form  = document.getElementById('add-client-form');
  if (!modal || !form) return;

  const errorDiv  = modal.querySelector('.modal-error');
  const submitBtn = form.querySelector('button[type=submit]');

  // ── Inject "+ New client" button next to every #client-select ────────────
  document.querySelectorAll('#client-select').forEach((select) => {
    // Wrap the select in a flex row so button sits alongside it
    const row = document.createElement('div');
    row.className = 'client-select-row';
    select.parentNode.insertBefore(row, select);
    row.appendChild(select);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-secondary btn-small';
    btn.textContent = '+ New client';
    row.appendChild(btn);

    btn.addEventListener('click', openModal);
  });

  // ── Open / close helpers ──────────────────────────────────────────────────
  function openModal() {
    modal.removeAttribute('hidden');
    form.reset();
    if (errorDiv) errorDiv.textContent = '';
    const nameInput = form.querySelector('#new-client-name');
    if (nameInput) nameInput.focus();
  }

  function closeModal() {
    modal.setAttribute('hidden', '');
  }

  // Close via × button or Cancel button
  modal.querySelectorAll('.modal-close, .modal-cancel').forEach((el) => {
    el.addEventListener('click', closeModal);
  });

  // Close by clicking the overlay backdrop (but not the dialog itself)
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hasAttribute('hidden')) closeModal();
  });

  // ── Form submit via fetch ─────────────────────────────────────────────────
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); // stop the page-level loading-state handler acting on this form

    const csrfToken = document.querySelector('meta[name=csrf-token]');
    const formData  = new FormData(form);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving…';
    if (errorDiv) errorDiv.textContent = '';

    try {
      const resp = await fetch('/api/clients/quick-create', {
        method: 'POST',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken.content } : {},
        body: formData,
      });

      const data = await resp.json();

      if (!resp.ok) {
        if (errorDiv) errorDiv.textContent = data.error || 'Failed to create client.';
        return;
      }

      const client = data.client;

      // Add the new client as an option in every #client-select on the page
      // and immediately select it, triggering the auto-fill change handler.
      document.querySelectorAll('#client-select').forEach((select) => {
        const opt = document.createElement('option');
        opt.value            = client.id;
        opt.dataset.domain   = client.domain        || '';
        opt.dataset.name     = client.name          || '';
        opt.dataset.project  = client.project_name  || '';
        opt.dataset.cms      = client.cms            || '';
        opt.dataset.location = String(client.location_code || '');
        opt.textContent      = client.name + (client.domain ? ` (${client.domain})` : '');
        select.appendChild(opt);

        // Select the new client and trigger the auto-fill handler
        select.value = client.id;
        select.dispatchEvent(new Event('change'));
      });

      closeModal();

    } catch (err) {
      if (errorDiv) errorDiv.textContent = 'Network error — please try again.';
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('loading');
      submitBtn.textContent = 'Create Client';
    }
  });
}());
