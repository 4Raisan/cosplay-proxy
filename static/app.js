/* ═══════════════════════════════════════════════════════════════════
   Cosplay — Frontend Application Logic
   Provider cards · Modals · API client · Auto-refresh
   ═══════════════════════════════════════════════════════════════════ */

// ── API Client ────────────────────────────────────────────────────
const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
    return res.json();
  },

  async post(path, body = {}) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `POST ${path}: ${res.status}`);
    }
    return res.json();
  },

  async put(path, body = {}) {
    const res = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `PUT ${path}: ${res.status}`);
    }
    return res.json();
  },

  async del(path) {
    const res = await fetch(path, { method: 'DELETE' });
    if (!res.ok) throw new Error(`DELETE ${path}: ${res.status}`);
    return res.json();
  },
};

// ── State ─────────────────────────────────────────────────────────
let providers = [];
let checkingProviders = new Set();

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadProviders();
  autoRefreshModels();
  loadRuntimeSettings();

  // Button handlers
  document.getElementById('btnAddProvider').addEventListener('click', () => openModal('addProviderModal'));
  document.getElementById('btnConnectAccount').addEventListener('click', openConnectAccountModal);

  // Navigation handlers
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const viewId = e.target.getAttribute('data-view');
      if (!viewId) return;

      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      
      document.querySelectorAll('.view-section').forEach(v => v.hidden = true);
      document.getElementById(viewId).hidden = false;

      if (viewId === 'view-routing') {
        loadRoutingSettings();
      } else if (viewId === 'view-thinking') {
        loadThinkingSettings();
      } else if (viewId === 'view-web-voice') {
        loadWebVoiceSettings();
      } else if (viewId === 'view-remote') {
        loadRemoteSettings();
        if (typeof startDaemonPoll === 'function') startDaemonPoll();
      }
      
      if (viewId !== 'view-remote') {
        if (typeof stopDaemonPoll === 'function') stopDaemonPoll();
      }
    });
  });

  // More dropdown menu (native <details> toggle; close on item pick / outside click)
  const moreToggle = document.getElementById('moreToggle');
  const moreMenu = document.getElementById('moreMenu');
  const moreDetails = moreToggle ? moreToggle.closest('.more-details') : null;
  if (moreToggle && moreMenu && moreDetails) {
    moreMenu.querySelectorAll('.more-item').forEach(btn => {
      btn.addEventListener('click', () => { moreDetails.open = false; });
    });
    document.addEventListener('click', (e) => {
      if (moreDetails.open && !e.target.closest('.topbar-more')) {
        moreDetails.open = false;
      }
    });
  }

  // Form submissions
  document.getElementById('addProviderForm').addEventListener('submit', handleAddProvider);
  document.getElementById('configureForm').addEventListener('submit', handleUpdateProvider);
  document.getElementById('runtimeForm').addEventListener('submit', handleSaveRuntime);
  document.getElementById('routingForm').addEventListener('submit', handleSaveRouting);
  document.getElementById('thinkingForm').addEventListener('submit', handleSaveThinking);
  document.getElementById('btnSaveThinking').addEventListener('click', handleSaveThinking);
  document.getElementById('webVoiceForm').addEventListener('submit', handleSaveWebVoice);
  document.getElementById('remoteForm').addEventListener('submit', handleSaveRemote);

  initAutoSave();

  // WebVoice buttons
  document.getElementById('btnConfigureNvidia').addEventListener('click', handleConfigureNvidia);
  document.getElementById('btnRefreshVoiceModels').addEventListener('click', handleRefreshVoiceModels);

  // Remote buttons
  document.getElementById('btnPairTelegram').addEventListener('click', handlePairTelegram);
  document.getElementById('btnTestRemoteConnection').addEventListener('click', handleTestRemoteConnection);
  document.getElementById('btnBrowseFolder')?.addEventListener('click', () => openFolderBrowser());
  document.getElementById('btnSelectFolder')?.addEventListener('click', handleSelectFolder);

  // Monitor port change
  document.getElementById('serverPort').addEventListener('input', () => {
    document.getElementById('portRestartHint').style.display = 'block';
  });

  // API type change updates hints
  document.getElementById('apiType').addEventListener('change', updateApiTypeHints);
  updateApiTypeHints();
});

// ── Load & Render ─────────────────────────────────────────────────
async function loadProviders() {
  try {
    providers = await API.get('/api/providers');
    renderProviders();
  } catch (e) {
    showToast('Failed to load providers', 'error');
  }
}

// Auto-refresh discovered models for every provider when the page loads,
// so the model lists are current without a manual "Refresh Models" button.
async function autoRefreshModels() {
  try {
    const list = await API.get('/api/providers');
    await Promise.all(list.map(async (p) => {
      try {
        await API.post(`/api/providers/${p.id}/refresh-models`);
      } catch (e) {
        console.error(`auto-refresh failed for ${p.id}:`, e.message);
      }
    }));
    providers = await API.get('/api/providers');
    renderProviders();
  } catch (e) {
    console.error('autoRefreshModels failed:', e.message);
  }
}

function renderProviders() {
  const grid = document.getElementById('providerGrid');
  const section = document.getElementById('providerSection');
  const empty = document.getElementById('emptyState');

  if (providers.length === 0) {
    section.hidden = true;
    empty.hidden = false;
    return;
  }

  section.hidden = false;
  empty.hidden = true;
  grid.innerHTML = providers.map((p, i) => renderProviderCard(p, i)).join('');
}

function renderProviderCard(provider, index) {
  const statusClass = {
    connected: 'status-connected',
    error: 'status-error',
    disconnected: 'status-error',
    unknown: 'status-unknown',
  }[provider.connection_status] || 'status-unknown';

  const statusLabel = {
    connected: 'Connected',
    error: 'Error',
    disconnected: 'Disconnected',
    unknown: 'Unknown',
  }[provider.connection_status] || 'Unknown';

  const apiTypeLabel = {
    openai_compatible: 'OpenAI Compatible',
    anthropic: 'Anthropic',
    gemini: 'Gemini API',
    local: 'Local Provider',
  }[provider.api_type] || provider.api_type;

  const updatedAgo = timeAgo(provider.updated_at);
  const isChecking = checkingProviders.has(provider.id);

  // Model count display — working/failed breakdown; unchecked is the badge below
  let modelInfo = `<span class="model-count">${provider.model_count}</span>`;
  const parts = [];
  if (provider.working_model_count > 0) parts.push(`<span class="working-count">${provider.working_model_count} working</span>`);
  if (provider.failed_model_count > 0) parts.push(`<span class="failed-count">${provider.failed_model_count} failed</span>`);
  if (parts.length > 0) modelInfo += ` (${parts.join(', ')})`;
  if (provider.unchecked_model_count > 0) modelInfo += ` <span class="badge badge-unchecked">Unchecked</span>`;

  return `
    <div class="provider-card" style="animation-delay: ${index * 60}ms">
      <div class="card-header">
        <span class="card-name">${escapeHtml(provider.name)}</span>
        <span class="card-status ${statusClass}">
          <span class="status-dot"></span>
          ${statusLabel}
        </span>
      </div>
      <dl class="card-details">
        <dt>Provider Type</dt>
        <dd>${apiTypeLabel}</dd>
        <dt>Models</dt>
        <dd>${modelInfo}</dd>
        <dt>Last Updated</dt>
        <dd>${updatedAgo}</dd>
      </dl>
      ${isChecking ? '<div class="progress-bar"><div class="progress-fill" style="width: 50%"></div></div>' : ''}
      <div class="card-actions">
        <button class="btn btn-secondary btn-sm" onclick="openConfigureModal('${provider.id}')">Configure</button>
        <button class="btn btn-secondary btn-sm" onclick="checkWorkingModels('${provider.id}')" ${isChecking ? 'disabled' : ''}>
          ${isChecking ? '<span class="spinner"></span> Checking...' : 'Check Working Models'}
        </button>
        ${provider.model_count > 0 ? `<button class="btn btn-ghost btn-sm" onclick="viewModels('${provider.id}', '${escapeHtml(provider.name)}')">View Models</button>` : ''}
      </div>
    </div>
  `;
}

// ── Add Provider ──────────────────────────────────────────────────
async function handleAddProvider(e) {
  e.preventDefault();

  const name = document.getElementById('providerName').value.trim();
  const apiType = document.getElementById('apiType').value;
  const baseUrl = document.getElementById('baseUrl').value.trim();
  const apiKey = document.getElementById('apiKey').value.trim();

  let customHeaders = {};
  const headersRaw = document.getElementById('customHeaders').value.trim();
  if (headersRaw) {
    try {
      customHeaders = JSON.parse(headersRaw);
    } catch {
      showValidateResult('Invalid JSON in Custom Headers', false);
      return;
    }
  }

  const saveBtn = document.getElementById('btnSave');
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<span class="spinner"></span> Saving...';

  try {
    const result = await API.post('/api/providers', {
      name, api_type: apiType, base_url: baseUrl, api_key: apiKey, custom_headers: customHeaders,
    });

    closeModal('addProviderModal');
    resetAddForm();
    await loadProviders();

    if (result.validation?.success) {
      showToast(`${name} connected successfully`, 'success');
    } else {
      showToast(`${name} saved with connection issues: ${result.validation?.message || ''}`, 'error');
    }
  } catch (e) {
    showToast(`Failed to add provider: ${e.message}`, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';
  }
}

// ── Validate (without saving) ─────────────────────────────────────
async function validateProvider() {
  const apiType = document.getElementById('apiType').value;
  const baseUrl = document.getElementById('baseUrl').value.trim();
  const apiKey = document.getElementById('apiKey').value.trim();

  let customHeaders = {};
  const headersRaw = document.getElementById('customHeaders').value.trim();
  if (headersRaw) {
    try {
      customHeaders = JSON.parse(headersRaw);
    } catch {
      showValidateResult('Invalid JSON in Custom Headers', false);
      return;
    }
  }

  showValidateResult('<span class="spinner"></span> Validating...', null, 'validate-loading');
  const validateBtn = document.getElementById('btnValidate');
  validateBtn.disabled = true;

  try {
    const result = await API.post('/api/providers/validate', {
      api_type: apiType, base_url: baseUrl, api_key: apiKey, custom_headers: customHeaders,
    });

    showValidateResult(
      result.message + (result.details ? `<br><small>${escapeHtml(result.details)}</small>` : ''),
      result.success,
    );

    // Enable save button on success
    if (result.success) {
      document.getElementById('btnSave').disabled = false;
    }
  } catch (e) {
    showValidateResult(`Validation request failed: ${e.message}`, false);
  } finally {
    validateBtn.disabled = false;
  }
}

function showValidateResult(message, success, customClass = null) {
  const el = document.getElementById('validateResult');
  el.hidden = false;
  el.className = 'validate-result ' + (customClass || (success === true ? 'validate-success' : success === false ? 'validate-error' : ''));
  el.innerHTML = message;
}

// ── Configure Provider ────────────────────────────────────────────
function openConfigureModal(providerId) {
  const provider = providers.find(p => p.id === providerId);
  if (!provider) return;

  document.getElementById('configureId').value = providerId;
  document.getElementById('configureName').value = provider.name;
  document.getElementById('configureBaseUrl').value = provider.base_url;
  document.getElementById('configureApiKey').value = '';
  document.getElementById('configureTitle').textContent = `Configure ${provider.name}`;
  openModal('configureModal');
}

async function handleUpdateProvider(e) {
  e.preventDefault();

  const id = document.getElementById('configureId').value;
  const name = document.getElementById('configureName').value.trim();
  const baseUrl = document.getElementById('configureBaseUrl').value.trim();
  const apiKey = document.getElementById('configureApiKey').value.trim();

  const body = { name, base_url: baseUrl };
  if (apiKey) body.api_key = apiKey;

  const submitBtn = e.submitter || document.querySelector('#configureForm button[type="submit"]');
  const originalText = submitBtn ? submitBtn.textContent : 'Save';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Saving...';
  }

  try {
    await API.put(`/api/providers/${id}`, body);
    closeModal('configureModal');
    await loadProviders();
    showToast('Provider updated', 'success');
  } catch (err) {
    showToast(`Update failed: ${err.message}`, 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  }
}

async function deleteCurrentProvider() {
  const id = document.getElementById('configureId').value;
  const provider = providers.find(p => p.id === id);
  if (!provider) return;

  if (!confirm(`Delete "${provider.name}"? This cannot be undone.`)) return;

  const btn = document.querySelector('#configureModal .btn-danger');
  const originalText = btn ? btn.textContent : 'Delete';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Deleting...';
  }

  try {
    await API.del(`/api/providers/${id}`);
    closeModal('configureModal');
    await loadProviders();
    showToast(`${provider.name} removed`, 'info');
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

// ── Refresh Models ────────────────────────────────────────────────
async function refreshModels(providerId) {
  const provider = providers.find(p => p.id === providerId);
  if (!provider) return;

  const btn = document.querySelector(`button[onclick="refreshModels('${providerId}')"]`);
  if (btn) btn.disabled = true;

  showToast(`Refreshing models for ${provider.name}...`, 'info');
  try {
    const result = await API.post(`/api/providers/${providerId}/refresh-models`);
    await loadProviders();
    if (result.success) {
      showToast(`Found ${result.model_count} models for ${provider.name}`, 'success');
    } else {
      showToast(`Model discovery failed: ${result.message || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    showToast(`Refresh failed: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Check Working Models ──────────────────────────────────────────
async function checkWorkingModels(providerId) {
  const provider = providers.find(p => p.id === providerId);
  if (!provider) return;

  checkingProviders.add(providerId);
  renderProviders();
  showToast(`Checking models for ${provider.name}...`, 'info');

  try {
    await API.post(`/api/providers/${providerId}/check-working`);
    // Poll for progress
    pollCheckProgress(providerId, provider.name);
  } catch (e) {
    checkingProviders.delete(providerId);
    renderProviders();
    showToast(`Check failed: ${e.message}`, 'error');
  }
}

function pollCheckProgress(providerId, providerName) {
  const interval = setInterval(async () => {
    try {
      const result = await API.get(`/api/providers/${providerId}/models`);
      if (!result.checking) {
        clearInterval(interval);
        checkingProviders.delete(providerId);
        await loadProviders();
        showToast(`Model check complete for ${providerName}`, 'success');
      } else {
        // Update card while checking
        await loadProviders();
      }
    } catch {
      clearInterval(interval);
      checkingProviders.delete(providerId);
      renderProviders();
    }
  }, 3000);
}

// ── View Models ───────────────────────────────────────────────────
async function viewModels(providerId, providerName) {
  document.getElementById('modelsTitle').textContent = `${providerName} — Models`;
  const list = document.getElementById('modelsList');
  list.innerHTML = '<div style="text-align:center;padding:24px"><span class="spinner"></span> Loading...</div>';
  openModal('modelsModal');

  try {
    const result = await API.get(`/api/providers/${providerId}/models`);
    if (result.models.length === 0) {
      list.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No models discovered yet.</p>';
      return;
    }

    list.innerHTML = result.models.map(m => {
      const statusClass = {
        working: 'model-working',
        failed: 'model-failed',
        unchecked: 'model-unchecked',
        checking: 'model-checking',
      }[m.status] || 'model-unchecked';

      const statusLabel = {
        working: '✓ Working',
        failed: '✗ Failed',
        unchecked: '— Unchecked',
        checking: '⟳ Checking',
      }[m.status] || m.status;

      const errorTip = m.error_message ? ` title="${escapeHtml(m.error_message)}"` : '';

      return `
        <div class="model-item">
          <span class="model-name">${escapeHtml(m.model_id)}</span>
          <span class="model-badge ${statusClass}"${errorTip}>${statusLabel}</span>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--accent-danger);text-align:center;padding:24px">Failed to load models: ${escapeHtml(e.message)}</p>`;
  }
}

// ── Connect Account Modal ─────────────────────────────────────────
async function openConnectAccountModal() {
  const list = document.getElementById('accountProviderList');
  list.innerHTML = '<div style="text-align:center;padding:24px"><span class="spinner"></span> Loading...</div>';
  openModal('connectAccountModal');

  try {
    const accountProviders = await API.get('/api/account-providers');
    if (accountProviders.length === 0) {
      list.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No account providers available.</p>';
      return;
    }

    list.innerHTML = accountProviders.map(ap => `
      <div class="account-card">
        <div class="account-info">
          <h3>${escapeHtml(ap.name)}</h3>
          <p>${escapeHtml(ap.description)}</p>
        </div>
        ${ap.coming_soon
          ? '<span class="badge-coming-soon">Coming Soon</span>'
          : `<button class="btn btn-primary btn-sm">Connect</button>`
        }
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--accent-danger);text-align:center;padding:24px">Failed to load: ${escapeHtml(e.message)}</p>`;
  }
}

// ── API Type Hints ────────────────────────────────────────────────
function updateApiTypeHints() {
  const apiType = document.getElementById('apiType').value;
  const hint = document.getElementById('baseUrlHint');
  const baseUrl = document.getElementById('baseUrl');
  const apiKeyGroup = document.getElementById('apiKeyGroup');

  const hints = {
    openai_compatible: {
      placeholder: 'https://api.openrouter.ai/api/v1',
      hint: 'OpenAI-compatible /v1 endpoint (OpenRouter, DeepSeek, Groq, NVIDIA NIM, etc.)',
    },
    anthropic: {
      placeholder: 'https://api.anthropic.com',
      hint: 'Anthropic Messages API endpoint.',
    },
    gemini: {
      placeholder: 'https://generativelanguage.googleapis.com/v1beta/openai/',
      hint: 'Google AI Studio Gemini API (OpenAI compatibility layer).',
    },
    local: {
      placeholder: 'http://localhost:11434',
      hint: 'Local model server URL (Ollama, LM Studio, llama.cpp).',
    },
  };

  const h = hints[apiType] || hints.openai_compatible;
  baseUrl.placeholder = h.placeholder;
  hint.textContent = h.hint;

  // Local providers don't need an API key
  if (apiType === 'local') {
    apiKeyGroup.style.opacity = '0.5';
    document.getElementById('apiKey').required = false;
  } else {
    apiKeyGroup.style.opacity = '1';
    document.getElementById('apiKey').required = false; // Keep optional for flexibility
  }
}

async function handleResetData() {
  if (!confirm('⚠️ WARNING: This will delete ALL connected providers, routing choices, and runtime settings for fresh prototype testing!\n\nAre you sure you want to clear all user data?')) {
    return;
  }

  const btn = document.getElementById('btnResetData');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Resetting...';
  }

  try {
    const res = await API.post('/api/reset-data');
    showToast(res.message || 'All user data cleared', 'info');
    setTimeout(() => {
      window.location.reload();
    }, 400);
  } catch (err) {
    showToast('Failed to clear data: ' + err.message, 'error');
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Reset Data';
    }
  }
}

// ── Modal Helpers ─────────────────────────────────────────────────
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.hidden = false;
    modal.removeAttribute('hidden');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.hidden = true;
    modal.setAttribute('hidden', '');
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Close modals on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    closeModal(e.target.id);
  }
});

// Close modals on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay').forEach(m => {
      if (m.classList.contains('active')) closeModal(m.id);
    });
  }
});

function resetAddForm() {
  document.getElementById('addProviderForm').reset();
  document.getElementById('validateResult').hidden = true;
  document.getElementById('btnSave').disabled = false;
  updateApiTypeHints();
}

function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (input.type === 'password') {
    input.type = 'text';
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
  } else {
    input.type = 'password';
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  }
}

// ── Toast Notifications ───────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 300ms ease-out';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ── Utilities ─────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function timeAgo(isoString) {
  if (!isoString) return 'Never';
  const now = new Date();
  const then = new Date(isoString);
  const seconds = Math.floor((now - then) / 1000);

  if (seconds < 10) return 'Just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  return `${days} days ago`;
}

// ── Runtime Logic ─────────────────────────────────────────────────
async function loadRuntimeSettings() {
  try {
    const settings = await API.get('/api/runtime');
    document.getElementById('apiAuthToken').value = settings.api_auth_token;
    document.getElementById('serverPort').value = settings.server_port;
    document.getElementById('connectionTimeout').value = settings.connection_timeout;
    document.getElementById('rateLimitRequests').value = settings.rate_limit_requests;
    document.getElementById('rateLimitSeconds').value = settings.rate_limit_seconds;
    document.getElementById('skipTitleGeneration').checked = settings.skip_title_generation;
  } catch (e) {
    showToast('Failed to load runtime settings', 'error');
  }
}

async function handleSaveRuntime(e) {
  e.preventDefault();
  const btn = document.getElementById('btnSaveRuntime');
  const originalText = btn.textContent;
  btn.textContent = 'Saving...';
  btn.disabled = true;

  try {
    await API.put('/api/runtime', {
      server_port: parseInt(document.getElementById('serverPort').value, 10),
      connection_timeout: parseInt(document.getElementById('connectionTimeout').value, 10),
      rate_limit_requests: parseInt(document.getElementById('rateLimitRequests').value, 10),
      rate_limit_seconds: parseInt(document.getElementById('rateLimitSeconds').value, 10),
      skip_title_generation: document.getElementById('skipTitleGeneration').checked,
    });
    showToast('Runtime settings saved successfully', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

async function copyApiToken() {
  const token = document.getElementById('apiAuthToken').value;
  try {
    await navigator.clipboard.writeText(token);
    showToast('Token copied to clipboard', 'success');
  } catch (err) {
    showToast('Failed to copy token', 'error');
  }
}

async function regenerateApiToken() {
  if (!confirm('Are you sure you want to regenerate the API token? Any connected clients will need to be updated with the new token.')) {
    return;
  }
  
  const btn = document.getElementById('btnRegenerateToken');
  const originalText = btn ? btn.textContent : 'Regenerate';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Generating...';
  }
  
  try {
    const res = await API.post('/api/runtime/regenerate-token');
    document.getElementById('apiAuthToken').value = res.api_auth_token;
    showToast('New token generated and saved', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

// ── Model Routing Logic ───────────────────────────────────────────
let _availableModelsCache = {};

async function fetchAllModels() {
  const providersData = await API.get('/api/providers');
  const modelsMap = {};
  
  await Promise.all(providersData.map(async (p) => {
    try {
      const res = await API.get(`/api/providers/${p.id}/models`);
      const pModels = res.models || (Array.isArray(res) ? res : []);
      if (pModels.length > 0) {
        // Sort working models to the top of each provider
        pModels.sort((a, b) => {
          if (a.status === 'working' && b.status !== 'working') return -1;
          if (a.status !== 'working' && b.status === 'working') return 1;
          return (a.display_name || a.model_id).localeCompare(b.display_name || b.model_id);
        });

        modelsMap[p.id] = {
          providerName: p.name,
          models: pModels
        };
      }
    } catch (e) {
      console.error(`Failed to fetch models for ${p.id}`, e);
    }
  }));
  
  return modelsMap;
}

function renderCombobox(selectId, warningId, val, modelsMap, fallbackLabel) {
  const container = document.getElementById(selectId)?.closest('.routing-input-group');
  const warning = document.getElementById(warningId);
  if (!container) return;

  const allItems = [];
  let foundSelected = false;
  let selectedDisplayName = fallbackLabel ? `Fallback to ${fallbackLabel}` : 'Select a model...';

  for (const pid in modelsMap) {
    const group = modelsMap[pid];
    for (const m of group.models) {
      const optionVal = `${pid}:${m.model_id}`;
      const isSel = (val === optionVal);
      if (isSel) {
        foundSelected = true;
        selectedDisplayName = `${group.providerName} / ${m.display_name || m.model_id}`;
      }
      allItems.push({
        providerId: pid,
        providerName: group.providerName,
        modelId: m.model_id,
        value: optionVal,
        displayName: m.display_name || m.model_id,
        status: m.status || 'unchecked',
        selected: isSel
      });
    }
  }

  if (val && !foundSelected) {
    selectedDisplayName = `${val} (Unavailable)`;
    if (warning) warning.hidden = false;
  } else {
    if (warning) warning.hidden = true;
  }

  // Remove original native select element if present
  const origSelect = document.getElementById(selectId);
  if (origSelect && origSelect.tagName === 'SELECT') {
    origSelect.remove();
  }

  // Create or update combobox wrapper
  let wrapper = container.querySelector('.combobox-container');
  if (!wrapper) {
    wrapper = document.createElement('div');
    wrapper.className = 'combobox-container';
    container.prepend(wrapper);
  }

  const defaultPlaceholder = fallbackLabel ? `Fallback to ${fallbackLabel}` : 'Select a model...';
  const initialInputValue = val ? selectedDisplayName : '';

  wrapper.innerHTML = `
    <input type="hidden" id="${selectId}" name="${selectId}" value="${escapeHtml(val || '')}" data-display-name="${escapeHtml(selectedDisplayName)}" />
    <div class="combobox-input-wrapper">
      <input type="text" 
             class="combobox-input" 
             id="combobox-input-${selectId}" 
             value="${escapeHtml(initialInputValue)}" 
             placeholder="${escapeHtml(defaultPlaceholder)}"
             autocomplete="off"
             onfocus="openComboboxDropdown('${selectId}')"
             onclick="openComboboxDropdown('${selectId}')"
             oninput="filterComboboxOptions('${selectId}')"
             onblur="onComboboxBlur('${selectId}')" />
      <span class="combobox-input-badge" id="combobox-input-badge-${selectId}"></span>
      <span class="combobox-arrow">▼</span>
    </div>
    <div class="combobox-dropdown" id="combobox-dropdown-${selectId}" hidden>
      <div class="combobox-options-list" id="combobox-options-${selectId}">
        ${buildComboboxItemsHtml(selectId, allItems, fallbackLabel, val)}
      </div>
    </div>
  `;

  // Show the selected value's status inline without opening the dropdown
  let selectedStatus = '';
  if (val && foundSelected) {
    for (const pid in modelsMap) {
      const group = modelsMap[pid];
      for (const m of group.models) {
        if (val === `${pid}:${m.model_id}`) {
          selectedStatus = m.status || '';
          break;
        }
      }
      if (selectedStatus) break;
    }
  }
  updateComboboxInlineBadge(wrapper, selectedStatus);
}

function buildComboboxItemsHtml(selectId, allItems, fallbackLabel, selectedVal) {
  let html = '';
  
  const isDefaultSel = !selectedVal;
  const defaultLabel = fallbackLabel ? `Fallback to ${fallbackLabel}` : 'Select a model...';
  html += `
    <div class="combobox-option ${isDefaultSel ? 'selected' : ''}" 
         data-search-text="${escapeHtml(defaultLabel.toLowerCase())}"
         onmousedown="selectComboboxOption('${selectId}', '', '${escapeHtml(defaultLabel)}', '')">
      <span class="option-name" style="font-family: var(--font-body); color: var(--text-muted);">
        ${escapeHtml(defaultLabel)}
      </span>
    </div>
  `;

  const groups = {};
  const failedItems = [];
  for (const item of allItems) {
    if (item.status === 'failed') {
      failedItems.push(item);
      continue;
    }
    groups[item.providerName] = groups[item.providerName] || [];
    groups[item.providerName].push(item);
  }

  for (const provName in groups) {
    html += `<div class="combobox-group-label" data-group-name="${escapeHtml(provName)}">${escapeHtml(provName)}</div>`;
    for (const item of groups[provName]) {
      let badge = '';
      if (item.status === 'working') {
        badge = '<span class="badge-working-sm">✓ Working</span>';
      }

      const isSel = (item.value === selectedVal);
      const fullLabel = `${provName} / ${item.displayName}`;
      html += `
        <div class="combobox-option ${isSel ? 'selected' : ''}" 
             data-group-name="${escapeHtml(provName)}"
             data-search-text="${escapeHtml((provName + ' ' + item.displayName + ' ' + item.modelId).toLowerCase())}"
             onmousedown="selectComboboxOption('${selectId}', '${escapeHtml(item.value)}', '${escapeHtml(fullLabel)}', '${item.status}')">
          <span class="option-name">${escapeHtml(item.displayName)}</span>
          ${badge}
        </div>
      `;
    }
  }

  if (failedItems.length > 0) {
    html += `
      <details class="combobox-failed-group" data-group-name="__failed__">
        <summary class="combobox-failed-summary">Failed (${failedItems.length})</summary>
    `;
    for (const item of failedItems) {
      const isSel = (item.value === selectedVal);
      const fullLabel = `${item.providerName} / ${item.displayName}`;
      html += `
        <div class="combobox-option ${isSel ? 'selected' : ''}" 
             data-group-name="${escapeHtml(item.providerName)}"
             data-search-text="${escapeHtml((item.providerName + ' ' + item.displayName + ' ' + item.modelId).toLowerCase())}"
             onmousedown="selectComboboxOption('${selectId}', '${escapeHtml(item.value)}', '${escapeHtml(fullLabel)}', 'failed')">
          <span class="option-name">${escapeHtml(item.displayName)}</span>
          <span class="badge-failed-sm">❌ Failed</span>
        </div>
      `;
    }
    html += `</details>`;
  }
  return html;
}

function openComboboxDropdown(selectId) {
  const hiddenInput = document.getElementById(selectId);
  const container = hiddenInput ? hiddenInput.closest('.combobox-container') : null;
  if (!container) return;

  const input = document.getElementById(`combobox-input-${selectId}`);

  // Close all other open comboboxes
  document.querySelectorAll('.combobox-container').forEach(c => {
    if (c !== container) {
      c.classList.remove('open');
      const d = c.querySelector('.combobox-dropdown');
      if (d) d.hidden = true;
    }
  });

  container.classList.add('open');
  const dropdown = container.querySelector('.combobox-dropdown');
  if (dropdown) dropdown.hidden = false;

  // Show full list on open so user can scroll through all models
  showAllComboboxOptions(selectId);

  // Auto-select text so typing immediately filters
  if (input) {
    setTimeout(() => {
      try { input.select(); } catch {}
    }, 10);
  }
}

function showAllComboboxOptions(selectId) {
  const hiddenInput = document.getElementById(selectId);
  const container = hiddenInput ? hiddenInput.closest('.combobox-container') : null;
  if (!container) return;

  const options = container.querySelectorAll('.combobox-option');
  const groupLabels = container.querySelectorAll('.combobox-group-label');

  options.forEach(opt => opt.style.display = 'flex');
  groupLabels.forEach(lbl => lbl.style.display = 'block');

  // Failed group stays collapsed until the user presses to expand it
  const failedGroup = container.querySelector('.combobox-failed-group');
  if (failedGroup) {
    failedGroup.open = false;
    failedGroup.style.display = 'block';
  }
}

function filterComboboxOptions(selectId) {
  const hiddenInput = document.getElementById(selectId);
  const container = hiddenInput ? hiddenInput.closest('.combobox-container') : null;
  if (!container) return;

  const input = document.getElementById(`combobox-input-${selectId}`);
  const query = input ? input.value.toLowerCase().trim() : '';

  // If query is empty, show full list
  if (!query) {
    showAllComboboxOptions(selectId);
    return;
  }

  const options = container.querySelectorAll('.combobox-option');
  const groupLabels = container.querySelectorAll('.combobox-group-label');
  const visiblePerGroup = {};

  options.forEach(opt => {
    const searchText = opt.getAttribute('data-search-text') || '';
    const groupName = opt.getAttribute('data-group-name');
    
    if (searchText.includes(query)) {
      opt.style.display = 'flex';
      if (groupName) visiblePerGroup[groupName] = true;
    } else {
      opt.style.display = 'none';
    }
  });

  groupLabels.forEach(lbl => {
    const gName = lbl.getAttribute('data-group-name');
    if (visiblePerGroup[gName]) {
      lbl.style.display = 'block';
    } else {
      lbl.style.display = 'none';
    }
  });

  // Failed group: open only when a failed model matches the query
  const failedGroup = container.querySelector('.combobox-failed-group');
  if (failedGroup) {
    const failedOptions = failedGroup.querySelectorAll('.combobox-option');
    let visibleFailed = 0;
    failedOptions.forEach(o => { if (o.style.display !== 'none') visibleFailed++; });
    if (visibleFailed > 0) {
      failedGroup.style.display = 'block';
      failedGroup.open = true;
    } else {
      failedGroup.style.display = 'none';
    }
  }
}

function selectComboboxOption(selectId, value, displayLabel, status) {
  const hiddenInput = document.getElementById(selectId);
  const input = document.getElementById(`combobox-input-${selectId}`);
  const container = hiddenInput ? hiddenInput.closest('.combobox-container') : null;

  if (hiddenInput) {
    hiddenInput.value = value;
    hiddenInput.setAttribute('data-display-name', displayLabel);
    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
  }
  if (input) {
    input.value = value ? displayLabel : '';
  }

  if (container) {
    container.classList.remove('open');
    const dropdown = container.querySelector('.combobox-dropdown');
    if (dropdown) dropdown.hidden = true;
    updateComboboxInlineBadge(container, status || '');
  }
}

function updateComboboxInlineBadge(container, status) {
  const wrapper = container.querySelector('.combobox-input-wrapper');
  const badge = container.querySelector('.combobox-input-badge');
  if (!badge) return;
  if (status === 'working') {
    badge.textContent = '✓ Working';
    badge.className = 'combobox-input-badge badge-working';
    if (wrapper) wrapper.classList.add('has-status');
  } else if (status === 'failed') {
    badge.textContent = '✗ Not Working';
    badge.className = 'combobox-input-badge badge-failed';
    if (wrapper) wrapper.classList.add('has-status');
  } else {
    badge.textContent = '';
    badge.className = 'combobox-input-badge';
    if (wrapper) wrapper.classList.remove('has-status');
  }
}

function onComboboxBlur(selectId) {
  setTimeout(() => {
    const hiddenInput = document.getElementById(selectId);
    const input = document.getElementById(`combobox-input-${selectId}`);
    const container = hiddenInput ? hiddenInput.closest('.combobox-container') : null;

    if (container) {
      container.classList.remove('open');
      const dropdown = container.querySelector('.combobox-dropdown');
      if (dropdown) dropdown.hidden = true;
    }

    if (hiddenInput && input) {
      const storedVal = hiddenInput.value;
      const storedDisplay = hiddenInput.getAttribute('data-display-name');
      if (storedVal && storedDisplay) {
        input.value = storedDisplay;
      } else if (!storedVal) {
        input.value = '';
      }
    }
  }, 200);
}

// Close combobox dropdowns on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('.combobox-container')) {
    document.querySelectorAll('.combobox-container').forEach(c => {
      c.classList.remove('open');
      const d = c.querySelector('.combobox-dropdown');
      if (d) d.hidden = true;
    });
  }
});

function resolveModelName(modelsMap, providerModelStr) {
  if (!providerModelStr) return null;
  const [pid, mid] = providerModelStr.split(':');
  if (modelsMap[pid]) {
    const m = modelsMap[pid].models.find(x => x.model_id === mid);
    if (m) return m.display_name || m.model_id;
  }
  return providerModelStr;
}

function updateFallbackInfo(infoId, actualValue, effectiveValue, modelsMap) {
  const infoEl = document.getElementById(infoId);
  if (!infoEl) return;
  
  if (!actualValue && effectiveValue) {
    const name = resolveModelName(modelsMap, effectiveValue);
    infoEl.textContent = `Using: ${name}`;
    infoEl.hidden = false;
  } else {
    infoEl.hidden = true;
  }
}

async function loadRoutingSettings() {
  try {
    const btn = document.getElementById('btnSaveRouting');
    btn.textContent = 'Loading...';
    btn.disabled = true;
    
    const [modelsMap, routing] = await Promise.all([
      fetchAllModels(),
      API.get('/api/routing')
    ]);
    
    _availableModelsCache = modelsMap;

    // Resolve names for fallback labels
    const defaultName = resolveModelName(modelsMap, routing.effective_default_model);
    const primaryName = resolveModelName(modelsMap, routing.primary_coding_model);
    const heavyName = resolveModelName(modelsMap, routing.effective_heavy_analysis_model);

    renderCombobox('defaultModel', 'defaultWarning', routing.default_model, modelsMap, primaryName || 'Primary Coding Model');
    renderCombobox('primaryCodingModel', 'primaryCodingWarning', routing.primary_coding_model, modelsMap, null);
    renderCombobox('fastTasksModel', 'fastTasksWarning', routing.fast_tasks_model, modelsMap, defaultName || primaryName || 'Primary Coding Model');
    renderCombobox('heavyAnalysisModel', 'heavyAnalysisWarning', routing.heavy_analysis_model, modelsMap, defaultName || primaryName || 'Primary Coding Model');
    renderCombobox('researchModel', 'researchWarning', routing.research_model, modelsMap, heavyName || defaultName || primaryName || 'Heavy Analysis Model');

    renderCombobox('fallback1Model', null, routing.fallback_1, modelsMap, null);
    renderCombobox('fallback2Model', null, routing.fallback_2, modelsMap, null);
    renderCombobox('fallback3Model', null, routing.fallback_3, modelsMap, null);

    // Update fallback UI tags
    updateFallbackInfo('defaultFallbackInfo', routing.default_model, routing.effective_default_model, modelsMap);
    updateFallbackInfo('fastTasksFallbackInfo', routing.fast_tasks_model, routing.effective_fast_tasks_model, modelsMap);
    updateFallbackInfo('heavyAnalysisFallbackInfo', routing.heavy_analysis_model, routing.effective_heavy_analysis_model, modelsMap);
    updateFallbackInfo('researchFallbackInfo', routing.research_model, routing.effective_research_model, modelsMap);
    
    btn.textContent = 'Save Routing';
    btn.disabled = false;
  } catch (e) {
    showToast('Failed to load routing configuration', 'error');
    document.getElementById('btnSaveRouting').disabled = false;
  }
}

async function handleSaveRouting(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById('btnSaveRouting');
  const originalText = btn ? btn.textContent : 'Save Routing';
  if (btn) {
    btn.textContent = 'Saving...';
    btn.disabled = true;
  }

  try {
    const primaryVal = document.getElementById('primaryCodingModel')?.value || null;
    if (!primaryVal) {
      showToast('Please select a Primary Coding Model before saving.', 'warning');
      return;
    }

    const req = {
      default_model: document.getElementById('defaultModel')?.value || null,
      primary_coding_model: primaryVal,
      fast_tasks_model: document.getElementById('fastTasksModel')?.value || null,
      heavy_analysis_model: document.getElementById('heavyAnalysisModel')?.value || null,
      research_model: document.getElementById('researchModel')?.value || null,
      fallback_1: document.getElementById('fallback1Model')?.value || null,
      fallback_2: document.getElementById('fallback2Model')?.value || null,
      fallback_3: document.getElementById('fallback3Model')?.value || null,
    };
    
    const res = await API.put('/api/routing', req);
    
    // Re-render comboboxes based on new save result
    const defaultName = resolveModelName(_availableModelsCache, res.effective_default_model);
    const primaryName = resolveModelName(_availableModelsCache, res.primary_coding_model);
    const heavyName = resolveModelName(_availableModelsCache, res.effective_heavy_analysis_model);
    
    renderCombobox('defaultModel', 'defaultWarning', res.default_model, _availableModelsCache, primaryName || 'Primary Coding Model');
    renderCombobox('primaryCodingModel', 'primaryCodingWarning', res.primary_coding_model, _availableModelsCache, null);
    renderCombobox('fastTasksModel', 'fastTasksWarning', res.fast_tasks_model, _availableModelsCache, defaultName || primaryName || 'Primary Coding Model');
    renderCombobox('heavyAnalysisModel', 'heavyAnalysisWarning', res.heavy_analysis_model, _availableModelsCache, defaultName || primaryName || 'Primary Coding Model');
    renderCombobox('researchModel', 'researchWarning', res.research_model, _availableModelsCache, heavyName || defaultName || primaryName || 'Heavy Analysis Model');
    
    renderCombobox('fallback1Model', null, res.fallback_1, _availableModelsCache, null);
    renderCombobox('fallback2Model', null, res.fallback_2, _availableModelsCache, null);
    renderCombobox('fallback3Model', null, res.fallback_3, _availableModelsCache, null);
    
    updateFallbackInfo('defaultFallbackInfo', res.default_model, res.effective_default_model, _availableModelsCache);
    updateFallbackInfo('fastTasksFallbackInfo', res.fast_tasks_model, res.effective_fast_tasks_model, _availableModelsCache);
    updateFallbackInfo('heavyAnalysisFallbackInfo', res.heavy_analysis_model, res.effective_heavy_analysis_model, _availableModelsCache);
    updateFallbackInfo('researchFallbackInfo', res.research_model, res.effective_research_model, _availableModelsCache);

    showToast('Routing settings saved successfully', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.textContent = originalText;
      btn.disabled = false;
    }
  }
}

// ── Thinking Logic ────────────────────────────────────────────────

const THINKING_LEVEL_ORDER = ['auto', 'off', 'light', 'balanced', 'deep', 'xhigh', 'max'];

function displayThinkingLevel(level) {
  const lv = level || 'auto';
  return lv.charAt(0).toUpperCase() + lv.slice(1);
}

function resolveModelRef(providerModelStr) {
  if (!providerModelStr) return null;
  const [pid, mid] = providerModelStr.split(':');
  return pid && mid ? { providerId: pid, modelId: mid } : null;
}

function modelStatusBadgeHtml(modelInfo) {
  if (!modelInfo) return '';
  if (modelInfo.status === 'working') return '<span class="badge-working-sm">✓ Working</span>';
  if (modelInfo.status === 'failed') return '<span class="badge-failed-sm">✗ Failed</span>';
  return '';
}

async function loadThinkingSettings() {
  const btn = document.getElementById('btnSaveThinking');
  const container = document.getElementById('thinkingSectionsContainer');
  if (!container) return;
  if (btn) {
    btn.textContent = 'Loading...';
    btn.disabled = true;
  }

  try {
    // We need providers to resolve names, routing for effective models, and thinking for saved settings
    const [modelsMap, routing, thinking] = await Promise.all([
      fetchAllModels(),
      API.get('/api/routing'),
      API.get('/api/thinking')
    ]);

    container.innerHTML = ''; // clear

    const sectionsData = [
      { id: 'default_thinking', title: 'Default Model', effectiveModel: routing.effective_default_model, val: thinking.default_thinking },
      { id: 'primary_coding_thinking', title: 'Primary Coding', effectiveModel: routing.primary_coding_model, val: thinking.primary_coding_thinking },
      { id: 'fast_tasks_thinking', title: 'Fast Tasks', effectiveModel: routing.effective_fast_tasks_model, val: thinking.fast_tasks_thinking },
      { id: 'heavy_analysis_thinking', title: 'Heavy Analysis', effectiveModel: routing.effective_heavy_analysis_model, val: thinking.heavy_analysis_thinking },
      { id: 'research_thinking', title: 'Research', effectiveModel: routing.effective_research_model, val: thinking.research_thinking },
      { id: 'fallback_1_thinking', title: 'Fallback 1', effectiveModel: routing.fallback_1, val: thinking.fallback_1_thinking },
      { id: 'fallback_2_thinking', title: 'Fallback 2', effectiveModel: routing.fallback_2, val: thinking.fallback_2_thinking },
      { id: 'fallback_3_thinking', title: 'Fallback 3', effectiveModel: routing.fallback_3, val: thinking.fallback_3_thinking }
    ];

    let renderedCount = 0;
    for (const sec of sectionsData) {
      if (!sec.effectiveModel) continue;
      renderedCount++;

      const modelRef = resolveModelRef(sec.effectiveModel);
      const modelName = resolveModelName(modelsMap, sec.effectiveModel) || sec.effectiveModel;
      const modelInfo = modelRef
        ? (modelsMap[modelRef.providerId]?.models.find(m => m.model_id === modelRef.modelId) || null)
        : null;
      const modelStatus = modelInfo ? (modelInfo.status || 'unchecked') : 'unchecked';

      let caps = { supports_thinking: true, levels: [], supported_levels: [], max_level: null, saved: null };
      try {
        if (modelRef) {
          caps = await API.get(`/api/thinking/capabilities?provider_id=${encodeURIComponent(modelRef.providerId)}&model_id=${encodeURIComponent(modelRef.modelId)}`);
        }
      } catch (e) {
        console.error('Failed to get capabilities', e);
      }

      const capsSaved = caps && caps.saved ? caps.saved : null;
      const failed = modelStatus === 'failed';
      const verifiedWorking = modelStatus === 'working' || (capsSaved && capsSaved.verified === true);

      // Full 7-level vocabulary with per-level supported/is_cap flags
      const levels = caps && Array.isArray(caps.levels) && caps.levels.length > 0
        ? caps.levels
        : THINKING_LEVEL_ORDER.map(lv => ({ level: lv, supported: true, is_cap: false }));

      // Saved value wins only when it's still supported; otherwise fall back to the cap level
      const supportedSet = new Set(levels.filter(l => l.supported).map(l => l.level));
      const capLevel = (levels.find(l => l.is_cap) || {}).level || null;
      const value = sec.val && supportedSet.has(sec.val) ? sec.val : (capLevel || 'auto');
      const displayValue = failed ? 'Model failed check' : displayThinkingLevel(value);

      const statusBadge = modelStatusBadgeHtml(modelInfo);

      let hintHtml = '';
      if (failed) {
        hintHtml = '<div class="thinking-hint">Model failed the working check — run <strong>Check Working Models</strong> and refresh to re-verify.</div>';
      } else if (!verifiedWorking) {
        hintHtml = '<div class="thinking-hint">Not verified — run the model check to confirm thinking levels.</div>';
      } else if (caps && caps.max_level) {
        hintHtml = `<div class="thinking-hint thinking-hint-verified">Verified — model thinking cap: <strong>${escapeHtml(displayThinkingLevel(caps.max_level))}</strong></div>`;
      }

      const sectionEl = document.createElement('section');
      sectionEl.className = 'routing-section thinking-section';
      sectionEl.dataset.slot = sec.id;
      sectionEl.innerHTML = `
        <div class="thinking-header">
          <div>
            <h3>${escapeHtml(sec.title)}</h3>
            <p class="section-subtitle">${escapeHtml(modelName)}${statusBadge ? ' &nbsp;' + statusBadge : ''}</p>
          </div>
        </div>
        <div class="thinking-toggle-row">
          <span class="thinking-toggle-label">Thinking Level</span>
          <div class="combobox-container${failed ? ' is-locked' : ''}">
            <input type="hidden" id="${sec.id}" name="${sec.id}" value="${escapeHtml(failed ? '' : value)}" data-display-name="${escapeHtml(displayValue)}" ${failed ? 'disabled' : ''} />
            <div class="combobox-input-wrapper">
              <input type="text"
                     class="combobox-input"
                     id="combobox-input-${sec.id}"
                     value="${escapeHtml(displayValue)}"
                     placeholder="Select a level..."
                     autocomplete="off"
                     ${failed ? 'disabled' : `onfocus="openComboboxDropdown('${sec.id}')" onclick="openComboboxDropdown('${sec.id}')" oninput="filterComboboxOptions('${sec.id}')"`}
                     onblur="onComboboxBlur('${sec.id}')" />
              <span class="combobox-input-badge" id="combobox-input-badge-${sec.id}"></span>
              <span class="combobox-arrow">▼</span>
            </div>
            <div class="combobox-dropdown" id="combobox-dropdown-${sec.id}" hidden>
              <div class="combobox-options-list" id="combobox-options-${sec.id}">
                ${buildThinkingOptionsHtml(sec.id, levels, value, verifiedWorking, failed)}
              </div>
            </div>
          </div>
        </div>
        ${hintHtml}
        <hr class="section-divider" style="margin-top: var(--space-lg);" />
      `;
      container.appendChild(sectionEl);

      if (!failed) {
        updateComboboxInlineBadge(
          sectionEl.querySelector('.combobox-container'),
          verifiedWorking ? 'working' : ''
        );
      }
    }

    if (renderedCount === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding: var(--space-xl) 0; text-align: center;">
          <div class="empty-icon" style="font-size: 2.5rem; margin-bottom: var(--space-sm);">🧠</div>
          <h3 style="color: var(--text-primary); margin-bottom: var(--space-xs);">No Models Assigned</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem;">Please select a Primary Coding Model in the Model Routing tab first to configure thinking levels.</p>
        </div>
      `;
    } else if (container.lastElementChild) {
      const lastDivider = container.lastElementChild.querySelector('.section-divider');
      if (lastDivider) lastDivider.remove();
    }
  } catch (e) {
    console.error('Failed to load thinking settings', e);
    showToast('Failed to load thinking configuration', 'error');
  } finally {
    if (btn) {
      btn.textContent = 'Save Thinking Configuration';
      btn.disabled = false;
    }
  }
}

function buildThinkingOptionsHtml(selectId, levels, selectedVal, verifiedWorking, failed) {
  let html = '';
  for (const lv of levels) {
    const levelName = displayThinkingLevel(lv.level);
    const isSel = !failed && lv.level === selectedVal;
    const supported = failed ? false : (lv.supported !== false);

    let badge = '';
    if (failed) {
      badge = '<span class="badge-failed-sm">✗ Not Working</span>';
    } else if (verifiedWorking) {
      badge = supported
        ? '<span class="badge-working-sm">✓ Working</span>'
        : '<span class="badge-failed-sm">✗ Not Working</span>';
    }

    const disabledCls = supported ? '' : ' disabled-option';
    const handler = supported
      ? ` onmousedown="selectComboboxOption('${selectId}', '${lv.level}', '${escapeHtml(levelName)}', 'working')"`
      : '';
    html += `
      <div class="combobox-option${isSel ? ' selected' : ''}${disabledCls}"
           data-search-text="${lv.level.toLowerCase()}"
           ${handler}>
        <span class="option-name">${escapeHtml(levelName)}</span>
        ${badge}
      </div>
    `;
  }
  return html;
}

function collectThinkingPayload() {
  const ids = [
    'default_thinking', 'primary_coding_thinking', 'fast_tasks_thinking',
    'heavy_analysis_thinking', 'research_thinking',
    'fallback_1_thinking', 'fallback_2_thinking', 'fallback_3_thinking'
  ];
  const payload = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el && !el.disabled && el.value) payload[id] = el.value;
  }
  return payload;
}

let _thinkingSaveGuard = false;
async function handleSaveThinking(e) {
  if (e && e.preventDefault) e.preventDefault();
  if (_thinkingSaveGuard) return; // click + form submit double-fire guard
  _thinkingSaveGuard = true;
  const btn = document.getElementById('btnSaveThinking');
  const originalText = btn ? btn.textContent : 'Save Thinking Configuration';
  if (btn) {
    btn.textContent = 'Saving...';
    btn.disabled = true;
  }

  try {
    await API.put('/api/thinking', collectThinkingPayload());
    showToast('Thinking settings saved successfully', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.textContent = originalText;
      btn.disabled = false;
    }
    _thinkingSaveGuard = false;
  }
}

// ── Auto-save (Routing + Thinking) ────────────────────────────────

const ROUTING_FIELD_MAP = {
  defaultModel: 'default_model',
  primaryCodingModel: 'primary_coding_model',
  fastTasksModel: 'fast_tasks_model',
  heavyAnalysisModel: 'heavy_analysis_model',
  researchModel: 'research_model',
  fallback1Model: 'fallback_1',
  fallback2Model: 'fallback_2',
  fallback3Model: 'fallback_3',
};

let _autoSaveTimer = null;

function scheduleAutoSave(fn) {
  clearTimeout(_autoSaveTimer);
  _autoSaveTimer = setTimeout(fn, 700);
}

function initAutoSave() {
  document.addEventListener('change', (e) => {
    const target = e.target;
    if (!target || target.tagName !== 'INPUT' || !target.id) return;

    if (ROUTING_FIELD_MAP[target.id]) {
      scheduleAutoSave(() => autoSaveRoutingField(target.id));
      return;
    }
    if (target.id.endsWith('_thinking') && target.closest('#thinkingSectionsContainer')) {
      scheduleAutoSave(autoSaveThinking);
    }
  });
}

async function autoSaveRoutingField(inputId) {
  const field = ROUTING_FIELD_MAP[inputId];
  const value = document.getElementById(inputId) ? document.getElementById(inputId).value || null : null;
  if (field === 'primary_coding_model' && !value) {
    showToast('Primary Coding Model is required — change skipped', 'warning');
    return;
  }
  try {
    await API.put('/api/routing', { [field]: value });
    showToast('Routing setting saved', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function autoSaveThinking() {
  try {
    await API.put('/api/thinking', collectThinkingPayload());
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Web & Voice Logic ─────────────────────────────────────────────

let _currentNvidiaProviderId = null;

async function loadWebVoiceSettings() {
  try {
    const [settings, nvidiaStatus] = await Promise.all([
      API.get('/api/web-voice'),
      API.get('/api/web-voice/nvidia-status')
    ]);

    document.getElementById('enableWebSearch').checked = settings.enable_web_search;
    document.getElementById('allowPrivateNetwork').checked = settings.allow_private_network;
    document.getElementById('enableVoice').checked = settings.enable_voice;

    const missingState = document.getElementById('nvidiaMissingState');
    const connectedState = document.getElementById('nvidiaConnectedState');

    if (nvidiaStatus.configured) {
      missingState.hidden = true;
      connectedState.hidden = false;
      _currentNvidiaProviderId = nvidiaStatus.provider_id;
      
      const apiStatusEl = document.getElementById('nvidiaApiStatus');
      if (nvidiaStatus.status === 'connected') {
        apiStatusEl.textContent = '✓ Connected';
        apiStatusEl.style.color = '#10b981';
      } else if (nvidiaStatus.status === 'invalid_auth') {
        apiStatusEl.textContent = '❌ Invalid API Key';
        apiStatusEl.style.color = '#ef4444';
      } else {
        apiStatusEl.textContent = '⚠ ' + (nvidiaStatus.status || 'Not Configured');
        apiStatusEl.style.color = '#f59e0b';
      }

      document.getElementById('nvidiaApiKey').textContent = nvidiaStatus.api_key;

      // Fetch models for dropdown
      await populateVoiceModelsDropdown(nvidiaStatus.provider_id, settings.voice_model);
    } else {
      missingState.hidden = false;
      connectedState.hidden = true;
      _currentNvidiaProviderId = null;
    }
  } catch (err) {
    showToast('Failed to load Web & Voice settings', 'error');
  }
}

async function populateVoiceModelsDropdown(providerId, selectedModel) {
  try {
    const models = await API.get(`/api/providers/${providerId}/models`);
    const select = document.getElementById('voiceModelSelect');
    select.innerHTML = '<option value="">Select a model...</option>';
    
    for (const m of models) {
      const option = document.createElement('option');
      option.value = m.model_id;
      option.textContent = m.display_name;
      if (m.model_id === selectedModel) {
        option.selected = true;
      }
      select.appendChild(option);
    }
  } catch (err) {
    console.error('Failed to populate voice models', err);
  }
}

function handleConfigureNvidia() {
  openModal('addProviderModal');
  document.getElementById('providerName').value = 'NVIDIA NIM';
  document.getElementById('apiType').value = 'openai_compatible';
  document.getElementById('baseUrl').value = 'https://integrate.api.nvidia.com/v1';
  document.getElementById('apiKey').value = '';
  document.getElementById('customHeaders').value = '';
  updateApiTypeHints();
}

async function handleRefreshVoiceModels() {
  if (!_currentNvidiaProviderId) return;
  const btn = document.getElementById('btnRefreshVoiceModels');
  const originalText = btn.textContent;
  btn.textContent = 'Refreshing...';
  btn.disabled = true;

  try {
    await API.post(`/api/providers/${_currentNvidiaProviderId}/refresh-models`);
    
    // Maintain current selection if possible
    const currentSelected = document.getElementById('voiceModelSelect').value;
    await populateVoiceModelsDropdown(_currentNvidiaProviderId, currentSelected);
    
    showToast('Voice models refreshed successfully', 'success');
  } catch (err) {
    showToast('Failed to refresh voice models', 'error');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

async function handleSaveWebVoice(e) {
  e.preventDefault();
  const btn = document.getElementById('btnSaveWebVoice');
  const originalText = btn.textContent;
  btn.textContent = 'Saving...';
  btn.disabled = true;

  try {
    const req = {
      enable_web_search: document.getElementById('enableWebSearch').checked,
      allow_private_network: document.getElementById('allowPrivateNetwork').checked,
      enable_voice: document.getElementById('enableVoice').checked,
      voice_model: document.getElementById('voiceModelSelect').value || null,
    };
    
    await API.put('/api/web-voice', req);
    showToast('Web & Voice settings saved successfully', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

// ── Remote Access Logic ───────────────────────────────────────────

let _currentBrowsePath = '';

async function loadRemoteSettings() {
  try {
    const [settings, webVoice] = await Promise.all([
      API.get('/api/remote'),
      API.get('/api/web-voice')
    ]);

    document.getElementById('enableTelegram').checked = settings.enable_telegram;
    
    if (settings.has_token) {
      document.getElementById('telegramToken').value = settings.telegram_token_masked;
    } else {
      document.getElementById('telegramToken').value = '';
    }

    const pairStatus = document.getElementById('telegramPairedStatus');
    const btnPair = document.getElementById('btnPairTelegram');
    if (settings.telegram_paired_user_id) {
      pairStatus.textContent = `✓ Paired (@${settings.telegram_paired_username || settings.telegram_paired_user_id})`;
      pairStatus.style.color = '#10b981';
      btnPair.textContent = 'Unpair / Repair';
    } else {
      pairStatus.textContent = 'Not Paired';
      pairStatus.style.color = 'var(--text-muted)';
      btnPair.textContent = 'Pair Telegram';
    }

    document.getElementById('workspaceFolder').value = settings.workspace_folder || '';
    
    // Voice check
    const voiceCheckbox = document.getElementById('allowVoiceMessages');
    const voiceWarning = document.getElementById('remoteVoiceWarning');
    if (webVoice.enable_voice) {
      voiceCheckbox.disabled = false;
      voiceWarning.hidden = true;
      voiceCheckbox.checked = settings.allow_voice;
    } else {
      voiceCheckbox.disabled = true;
      voiceCheckbox.checked = false;
      voiceWarning.hidden = false;
    }

    document.getElementById('allowFileUploads').checked = settings.allow_file;
    document.getElementById('allowImageUploads').checked = settings.allow_image;
    document.getElementById('remoteConnectionStatus').textContent = '';

  } catch (err) {
    showToast('Failed to load Remote settings', 'error');
  }
}

async function handleSaveRemote(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById('btnSaveRemote');
  const originalText = btn.textContent;
  if (btn) {
    btn.textContent = 'Saving...';
    btn.disabled = true;
  }

  try {
    let tokenVal = document.getElementById('telegramToken').value.trim();
    if (tokenVal === '****************' || tokenVal.includes('**********')) {
      tokenVal = undefined; // don't update if masked
    }

    const req = {
      enable_telegram: document.getElementById('enableTelegram').checked,
      workspace_folder: document.getElementById('workspaceFolder').value,
      allow_voice: document.getElementById('allowVoiceMessages').checked,
      allow_file: document.getElementById('allowFileUploads').checked,
      allow_image: document.getElementById('allowImageUploads').checked,
    };
    if (tokenVal !== undefined) {
      req.telegram_token = tokenVal;
    }
    
    await API.put('/api/remote', req);
    if (e) showToast('Remote settings saved successfully', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.textContent = originalText;
      btn.disabled = false;
    }
  }
}

async function handlePairTelegram() {
  const tokenVal = document.getElementById('telegramToken').value.trim();
  if (!tokenVal || tokenVal.includes('*****')) {
    showToast('Please enter a valid (unmasked) Bot Token and save first, or enter it now.', 'warning');
    return;
  }

  const btn = document.getElementById('btnPairTelegram');
  const instructions = document.getElementById('telegramPairingInstructions');
  
  btn.disabled = true;
  instructions.hidden = false;
  
  try {
    const res = await API.post('/api/remote/telegram/pair', { telegram_token: tokenVal });
    if (res.success) {
      showToast('Successfully paired!', 'success');
      loadRemoteSettings();
    } else if (res.timeout) {
      showToast('Pairing timed out. Did you send /pair to the bot?', 'warning');
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    instructions.hidden = true;
  }
}

async function handleTestRemoteConnection() {
  const btn = document.getElementById('btnTestRemoteConnection');
  const statusEl = document.getElementById('remoteConnectionStatus');
  const checksContainer = document.getElementById('remoteConnectionChecks');
  
  btn.disabled = true;
  statusEl.textContent = 'Testing...';
  statusEl.style.color = 'var(--text-primary)';
  checksContainer.hidden = true;
  checksContainer.innerHTML = '';
  
  // Save first just in case
  await handleSaveRemote();

  try {
    const res = await API.post('/api/remote/telegram/test');
    statusEl.textContent = res.status;
    
    if (res.status === 'Ready') {
      statusEl.style.color = '#10b981'; // green
    } else if (res.status === 'Incomplete') {
      statusEl.style.color = '#f59e0b'; // yellow
    } else {
      statusEl.style.color = '#ef4444'; // red
    }
    
    // Render detailed checks
    if (res.checks && res.checks.length > 0) {
      checksContainer.hidden = false;
      res.checks.forEach(c => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.gap = '8px';
        row.style.fontSize = '0.9rem';
        row.style.color = c.passed ? '#10b981' : '#ef4444';
        
        row.innerHTML = `
          <span style="font-size: 1.1rem;">${c.passed ? '✓' : '✗'}</span>
          <span>${c.name}</span>
        `;
        checksContainer.appendChild(row);
      });
    }

  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
    statusEl.style.color = '#ef4444';
  } finally {
    btn.disabled = false;
  }
}

// ── Daemon Status Polling ──────────────────────────────────────────
let _daemonPollInterval = null;

async function fetchDaemonStatus() {
  const badge = document.getElementById('daemonStatusBadge');
  if (!badge) return;
  
  try {
    const res = await API.get('/api/remote/status');
    const s = res.status;
    badge.textContent = s;
    if (s === 'Running') {
      badge.style.color = '#10b981';
      badge.style.background = 'rgba(16, 185, 129, 0.1)';
    } else if (s === 'Error') {
      badge.style.color = '#ef4444';
      badge.style.background = 'rgba(239, 68, 68, 0.1)';
    } else if (s === 'Starting' || s === 'Stopping') {
      badge.style.color = '#f59e0b';
      badge.style.background = 'rgba(245, 158, 11, 0.1)';
    } else {
      badge.style.color = 'var(--text-primary)';
      badge.style.background = 'var(--bg-surface-hover)';
    }
  } catch (err) {
    badge.textContent = 'Disconnected';
  }
}

// Run poll every 3 seconds when remote view is active
function startDaemonPoll() {
  if (_daemonPollInterval) clearInterval(_daemonPollInterval);
  fetchDaemonStatus();
  _daemonPollInterval = setInterval(fetchDaemonStatus, 3000);
}
function stopDaemonPoll() {
  if (_daemonPollInterval) clearInterval(_daemonPollInterval);
  _daemonPollInterval = null;
}

// ── Folder Browser Logic
async function openFolderBrowser(path = '') {
  try {
    const res = await API.get(`/api/remote/fs/browse?path=${encodeURIComponent(path)}`);
    _currentBrowsePath = res.current;
    
    document.getElementById('browseCurrentPath').value = res.current || 'This PC / Root';
    
    const listEl = document.getElementById('browseDirList');
    listEl.innerHTML = '';
    
    // Add "Up" directory if applicable
    if (res.parent && res.parent !== res.current) {
      const upItem = document.createElement('div');
      upItem.className = 'dir-item';
      upItem.innerHTML = `<span class="dir-icon">📁</span> <span>.. (Up)</span>`;
      upItem.onclick = () => openFolderBrowser(res.parent);
      listEl.appendChild(upItem);
    }
    
    // Add directories
    for (const d of res.directories) {
      const item = document.createElement('div');
      item.className = 'dir-item';
      item.innerHTML = `<span class="dir-icon">📁</span> <span>${escapeHtml(d)}</span>`;
      // On Windows drive roots, d is "C:\", otherwise just folder name
      const nextPath = res.current ? (res.current.endsWith('\\') || res.current.endsWith('/') ? res.current + d : res.current + '/' + d) : d;
      item.onclick = () => openFolderBrowser(nextPath);
      listEl.appendChild(item);
    }
    
    openModal('browseFolderModal');
  } catch (err) {
    showToast('Failed to load directories: ' + err.message, 'error');
  }
}

function handleSelectFolder() {
  if (_currentBrowsePath) {
    document.getElementById('workspaceFolder').value = _currentBrowsePath;
  }
  closeModal('browseFolderModal');
}

// ── Developer Diagnostics ──────────────────────────────────────────
let _diagnosticsData = null;

async function loadDiagnostics() {
  try {
    _diagnosticsData = await API.get('/api/diagnostics');
    document.getElementById('diagnosticsOutput').textContent = JSON.stringify(_diagnosticsData, null, 2);
    openModal('diagnosticsModal');
  } catch (err) {
    showToast('Failed to load diagnostics', 'error');
  }
}

function exportDiagnostics() {
  if (!_diagnosticsData) return;
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(_diagnosticsData, null, 2));
  const dlAnchorElem = document.createElement('a');
  dlAnchorElem.setAttribute("href", dataStr);
  dlAnchorElem.setAttribute("download", "cosplay_diagnostics.json");
  dlAnchorElem.click();
}

// Shortcut listener for Diagnostics (Ctrl+Shift+D)
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
    e.preventDefault();
    loadDiagnostics();
  }
});
