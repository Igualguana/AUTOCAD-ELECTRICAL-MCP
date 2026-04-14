/**
 * main.js — UI state management and event handlers.
 * Depends on api.js (loaded first).
 */

'use strict';

// ═══════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════
const state = {
  activePanel:    'chat',
  isLoading:      false,
  providers:      [],
  activeProvider: null,
  drawingMode:    '2d',   // "auto" | "electrical" | "2d" | "3d"
};

// ═══════════════════════════════════════════════════════════════════════════
// DOM REFS
// ═══════════════════════════════════════════════════════════════════════════
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

const chatArea      = $('chat-area');
const chatInput     = $('chat-input');
const btnSend       = $('btn-send');
const sendIcon      = $('send-icon');
const providerSelect = $('provider-select');
const metaProvider  = $('meta-provider');
const toolsGrid     = $('tools-grid');
const logArea       = $('log-area');
const drawingInfo   = $('drawing-info');
const toast         = $('toast');

// ═══════════════════════════════════════════════════════════════════════════
// TOAST
// ═══════════════════════════════════════════════════════════════════════════
let _toastTimer = null;
function showToast(msg, type = 'info', duration = 3000) {
  toast.textContent = msg;
  toast.className = `toast show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { toast.className = 'toast'; }, duration);
}

// ═══════════════════════════════════════════════════════════════════════════
// PANEL NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════
function showPanel(name) {
  state.activePanel = name;
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.panel === name));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id === `panel-${name}`));

  // Lazy-load panel content
  if (name === 'tools')   loadTools();
  if (name === 'logs')    loadLogs();
  if (name === 'drawing') loadDrawingInfo();
}

$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => showPanel(btn.dataset.panel));
});

// ═══════════════════════════════════════════════════════════════════════════
// STATUS POLLING
// ═══════════════════════════════════════════════════════════════════════════
async function refreshStatus() {
  try {
    const s = await API.getStatus();

    // AutoCAD
    const dotAcad  = $('dot-autocad');
    const valAcad  = $('val-autocad');
    if (s.autocad.connected) {
      dotAcad.className = 'status-dot dot-pulse';
      valAcad.textContent = s.autocad.drawing || 'Sin dibujo';
      valAcad.title = s.autocad.version || '';
    } else {
      dotAcad.className = 'status-dot dot-off';
      valAcad.textContent = 'Desconectado';
    }

    // Ollama
    const dotOll = $('dot-ollama');
    const valOll = $('val-ollama');
    if (s.ollama.available) {
      dotOll.className = 'status-dot dot-on';
      const count = (s.ollama.models || []).length;
      valOll.textContent = `${count} modelo${count !== 1 ? 's' : ''}`;
    } else {
      dotOll.className = 'status-dot dot-off';
      valOll.textContent = 'No disponible';
    }

    // MCP
    $('val-mcp').textContent = `${s.mcp.tools} tools`;

    // Drawing (topbar)
    $('val-drawing').textContent = s.autocad.drawing || '—';

    // Provider label
    if (s.provider.active) {
      metaProvider.textContent = `Motor: ${s.provider.active} / ${s.provider.model || '—'}`;
    }
  } catch (e) {
    console.warn('Status refresh failed:', e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PROVIDERS
// ═══════════════════════════════════════════════════════════════════════════
async function loadProviders() {
  try {
    const data = await API.getProviders();
    state.providers = data.providers;
    state.activeProvider = data.active;

    providerSelect.innerHTML = '';
    data.providers.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = `${p.name} · ${p.model || '—'}`;
      opt.selected = p.active;
      providerSelect.appendChild(opt);
    });
  } catch (e) {
    console.warn('Could not load providers:', e);
  }
}

providerSelect.addEventListener('change', async () => {
  const selected = providerSelect.value;
  try {
    await API.switchProvider(selected);
    state.activeProvider = selected;
    showToast(`Motor cambiado a ${selected}`, 'success');
    await refreshStatus();
  } catch (e) {
    showToast(`Error al cambiar motor: ${e.message}`, 'error');
  }
});

$('btn-refresh').addEventListener('click', async () => {
  await refreshStatus();
  showToast('Estado actualizado', 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// DRAWING MODE SELECTOR
// ═══════════════════════════════════════════════════════════════════════════
const _MODE_HINTS = {
  auto:       '46 herramientas · Todas las categorías',
  electrical: '46 herramientas · Electrical + 3D + 2D + Project',
  '2d':       '14 herramientas · Drawing + Project',
  '3d':       '23 herramientas · Drawing + Drawing3D + Project',
};
const _MODE_PLACEHOLDERS = {
  auto:       'Instrucción para AutoCAD (modo Auto)…',
  electrical: 'Instrucción eléctrica (símbolos, escalera, cables, PLC)…',
  '2d':       'Instrucción 2D (línea, círculo, rectángulo, texto, capa)…',
  '3d':       'Instrucción 3D (caja, esfera, cilindro, línea 3D, vista)…',
};

function setDrawingMode(mode) {
  state.drawingMode = mode;
  $$('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  const hint = $('mode-hint');
  if (hint) hint.textContent = _MODE_HINTS[mode] || '';
  chatInput.placeholder = _MODE_PLACEHOLDERS[mode] || 'Instrucción para AutoCAD…';
}

$$('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => setDrawingMode(btn.dataset.mode));
});

// ═══════════════════════════════════════════════════════════════════════════
// CHAT
// ═══════════════════════════════════════════════════════════════════════════

/** Remove the welcome screen on first message */
function ensureChatReady() {
  const welcome = chatArea.querySelector('.chat-welcome');
  if (welcome) welcome.remove();
}

/** Render a simple timestamp string */
function nowStr() {
  return new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
}

/** Convert **bold**, `code`, and ```block``` to HTML */
function simpleMarkdown(text) {
  return text
    .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function appendMessage(role, content, extra = {}) {
  ensureChatReady();

  const wrap = document.createElement('div');
  wrap.className = `chat-msg ${role}${extra.failed ? ' failed' : ''}`;

  // Tool badge
  if (role === 'tool' && extra.tool) {
    const badge = document.createElement('div');
    badge.className = `tool-badge${extra.failed ? ' failed' : ''}`;
    badge.innerHTML = `${extra.failed ? '✗' : '✓'} <strong>${extra.tool}</strong>`;
    wrap.appendChild(badge);
  }

  // Meta (time)
  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  meta.textContent = nowStr();
  wrap.appendChild(meta);

  // Bubble
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble msg-content';
  bubble.innerHTML = simpleMarkdown(content);
  wrap.appendChild(bubble);

  chatArea.appendChild(wrap);
  chatArea.scrollTop = chatArea.scrollHeight;
  return wrap;
}

function showThinking() {
  ensureChatReady();
  const el = document.createElement('div');
  el.id = 'thinking-indicator';
  el.className = 'thinking';
  el.innerHTML = `<span>IA procesando</span><span class="thinking-dots"><span></span><span></span><span></span></span>`;
  chatArea.appendChild(el);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function hideThinking() {
  const el = $('thinking-indicator');
  if (el) el.remove();
}

function setLoading(loading) {
  state.isLoading = loading;
  chatInput.disabled = loading;
  btnSend.classList.toggle('loading', loading);
  sendIcon.textContent = loading ? '…' : '▶';
}

async function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg || state.isLoading) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';
  setLoading(true);

  appendMessage('user', msg);
  showThinking();

  try {
    const res = await API.chat(msg, state.activeProvider, state.drawingMode);
    hideThinking();

    if (res.action === 'compound') {
      // Multi-step drawing result
      const label = res.intent ? `compound: ${res.intent}` : 'compound';
      appendMessage('tool', res.text, { tool: label, failed: !res.success });
    } else if (res.action === 'tool_call') {
      appendMessage('tool', res.text, { tool: res.tool, failed: !res.success });
    } else if (res.action === 'error' || !res.success) {
      appendMessage('error', res.text || res.error || 'Error desconocido');
    } else {
      appendMessage('assistant', res.text || '(sin respuesta)');
    }

    // Refresh status after a tool call (AutoCAD may have changed)
    if (res.action === 'tool_call') {
      setTimeout(refreshStatus, 800);
    }
  } catch (e) {
    hideThinking();
    appendMessage('error', `Error de conexión: ${e.message}`);
  } finally {
    setLoading(false);
    chatInput.focus();
  }
}

btnSend.addEventListener('click', sendMessage);

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

// Example chips — also switch drawing mode if chip has data-mode attribute
chatArea.addEventListener('click', e => {
  const chip = e.target.closest('.example-chip');
  if (chip) {
    if (chip.dataset.mode) setDrawingMode(chip.dataset.mode);
    chatInput.value = chip.dataset.msg;
    chatInput.focus();
    chatInput.dispatchEvent(new Event('input'));
  }
});

// Clear history
$('btn-clear-history').addEventListener('click', async () => {
  await API.clearHistory().catch(() => {});
  chatArea.innerHTML = '';
  chatArea.innerHTML = `
    <div class="chat-welcome">
      <div class="welcome-icon">⚡</div>
      <h3>AutoCAD Electrical AI Control Center</h3>
      <p>Historial borrado. Escribe una instrucción para comenzar.</p>
    </div>`;
  showToast('Historial borrado', 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// TOOLS PANEL
// ═══════════════════════════════════════════════════════════════════════════
let _toolsLoaded = false;

async function loadTools() {
  if (_toolsLoaded) return;
  try {
    const data = await API.getTools();
    renderTools(data.tools);
    _toolsLoaded = true;
  } catch (e) {
    toolsGrid.innerHTML = `<div class="loading-msg" style="color:var(--error)">Error cargando herramientas: ${e.message}</div>`;
  }
}

function renderTools(byCategory) {
  toolsGrid.innerHTML = '';
  for (const [cat, tools] of Object.entries(byCategory)) {
    const section = document.createElement('div');
    section.className = `tool-category cat-${cat}`;
    section.dataset.cat = cat;

    const title = document.createElement('div');
    title.className = 'tool-category-title';
    title.textContent = `${cat} (${tools.length})`;
    section.appendChild(title);

    const cards = document.createElement('div');
    cards.className = 'tool-cards';

    tools.forEach(tool => {
      const card = document.createElement('div');
      card.className = 'tool-card';
      card.dataset.name = tool.name;
      card.dataset.desc = tool.description.toLowerCase();

      const header = document.createElement('div');
      header.className = 'tool-card-header';

      const name = document.createElement('span');
      name.className = 'tool-name';
      name.textContent = tool.name;

      const badge = document.createElement('span');
      badge.className = 'tool-cat-badge';
      badge.textContent = cat;

      header.appendChild(name);
      header.appendChild(badge);

      const desc = document.createElement('div');
      desc.className = 'tool-desc';
      desc.textContent = tool.description;

      card.appendChild(header);
      card.appendChild(desc);

      // Click to pre-fill chat with tool
      card.addEventListener('click', () => {
        showPanel('chat');
        chatInput.value = `Ejecuta ${tool.name}`;
        chatInput.focus();
      });

      cards.appendChild(card);
    });

    section.appendChild(cards);
    toolsGrid.appendChild(section);
  }
}

// Tool search
$('tools-search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase().trim();
  $$('.tool-card').forEach(card => {
    const match = !q || card.dataset.name.includes(q) || card.dataset.desc.includes(q);
    card.classList.toggle('tool-hidden', !match);
  });
  // Hide empty categories
  $$('.tool-category').forEach(cat => {
    const visible = cat.querySelectorAll('.tool-card:not(.tool-hidden)').length > 0;
    cat.style.display = visible ? '' : 'none';
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// LOGS PANEL
// ═══════════════════════════════════════════════════════════════════════════
async function loadLogs() {
  const level = $('log-level-filter').value;
  try {
    const data = await API.getLogs(150, level);
    renderLogs(data.logs);
  } catch (e) {
    logArea.innerHTML = `<div class="loading-msg" style="color:var(--error)">Error cargando logs: ${e.message}</div>`;
  }
}

function renderLogs(logs) {
  if (!logs.length) {
    logArea.innerHTML = '<div class="loading-msg">Sin entradas de log.</div>';
    return;
  }
  logArea.innerHTML = '';
  logs.forEach(entry => {
    const row = document.createElement('div');
    row.className = 'log-entry';

    const ts  = entry.timestamp.split('T')[1] || entry.timestamp;
    row.innerHTML = `
      <span class="log-ts">${ts}</span>
      <span class="log-level ${entry.level}">${entry.level}</span>
      <span class="log-src">${entry.source}</span>
      <span class="log-msg">${escapeHtml(entry.message)}</span>`;
    logArea.appendChild(row);
  });
  logArea.scrollTop = logArea.scrollHeight;
}

$('log-level-filter').addEventListener('change', loadLogs);

$('btn-clear-logs').addEventListener('click', async () => {
  await API.clearLogs().catch(() => {});
  logArea.innerHTML = '<div class="loading-msg">Logs borrados.</div>';
  showToast('Logs borrados', 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// DRAWING PANEL
// ═══════════════════════════════════════════════════════════════════════════
async function loadDrawingInfo() {
  try {
    const data = await API.getDrawingInfo();
    renderDrawingInfo(data);
  } catch (e) {
    drawingInfo.innerHTML = `<div class="no-data"><span class="no-data-icon">⚠️</span>Error: ${e.message}</div>`;
  }
}

function renderDrawingInfo(data) {
  const d = data.drawing;
  const p = data.project;

  if (!d || !d.success) {
    drawingInfo.innerHTML = `
      <div class="no-data">
        <span class="no-data-icon">📐</span>
        <p>No hay dibujo activo o AutoCAD no está conectado.</p>
        <p style="font-size:12px;color:var(--text-muted);margin-top:8px">${d?.error || ''}</p>
      </div>`;
    return;
  }

  let html = '';

  // Drawing card
  html += `<div class="info-card"><h3>Dibujo activo</h3>`;
  const drawingFields = [
    ['Nombre',   d.name || d.drawing || '—'],
    ['Ruta',     d.path || d.full_path || '—'],
    ['Guardado', d.saved !== undefined ? (d.saved ? 'Sí' : 'No *') : '—'],
  ];
  drawingFields.forEach(([k, v]) => {
    html += `<div class="info-row"><span class="info-key">${k}</span><span class="info-value">${escapeHtml(String(v))}</span></div>`;
  });
  html += '</div>';

  // Project card
  if (p && p.success) {
    html += `<div class="info-card"><h3>Proyecto</h3>`;
    const projFields = [
      ['Nombre',    p.project_name || '—'],
      ['Ruta',      p.project_path || '—'],
      ['Dibujos',   p.drawing_count ?? '—'],
    ];
    projFields.forEach(([k, v]) => {
      html += `<div class="info-row"><span class="info-key">${k}</span><span class="info-value">${escapeHtml(String(v))}</span></div>`;
    });
    html += '</div>';
  }

  drawingInfo.innerHTML = html;
}

$('btn-refresh-drawing').addEventListener('click', () => {
  drawingInfo.innerHTML = '<div class="loading-msg">Actualizando…</div>';
  loadDrawingInfo();
});

// ═══════════════════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════════════════
function escapeHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ═══════════════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════════════
(async function init() {
  await Promise.all([loadProviders(), refreshStatus()]);

  // Poll status every 10 seconds
  setInterval(refreshStatus, 10_000);

  // Auto-refresh logs if logs panel is active
  setInterval(() => {
    if (state.activePanel === 'logs') loadLogs();
  }, 5_000);

  chatInput.focus();
})();
