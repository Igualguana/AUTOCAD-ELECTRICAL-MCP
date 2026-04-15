/**
 * main.js — AutoCAD Electrical MCP Dashboard
 * Depends on: api.js (loaded first), i18n.js (loaded second).
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
  recentDrawings: JSON.parse(localStorage.getItem('autocad-mcp-recents') || '[]'),
};

// ═══════════════════════════════════════════════════════════════════════════
// DOM HELPERS
// ═══════════════════════════════════════════════════════════════════════════
const $  = id  => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

const chatArea       = $('chat-area');
const chatInput      = $('chat-input');
const btnSend        = $('btn-send');
const sendIcon       = $('send-icon');
const providerSelect = $('provider-select');
const metaProvider   = $('meta-provider');
const toolsGrid      = $('tools-grid');
const logArea        = $('log-area');
const toast          = $('toast');

// ═══════════════════════════════════════════════════════════════════════════
// TOAST
// ═══════════════════════════════════════════════════════════════════════════
let _toastTimer = null;
function showToast(msg, type = 'info', duration = 3200) {
  toast.textContent = msg;
  toast.className = `toast show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { toast.className = 'toast'; }, duration);
}

// ═══════════════════════════════════════════════════════════════════════════
// LANGUAGE SWITCHER
// ═══════════════════════════════════════════════════════════════════════════
function initLangSwitcher() {
  const btns = $$('.lang-btn');
  btns.forEach(btn => {
    if (btn.dataset.lang === i18n.lang) btn.classList.add('active');
    btn.addEventListener('click', () => {
      const lang = btn.dataset.lang;
      if (lang === i18n.lang) return;
      i18n.setLang(lang);
      btns.forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
    });
  });
}

// Re-render every piece of dynamic text when language changes
window.addEventListener('langchange', () => {
  updateModeHint();
  updateWelcomeChips();
  updateWelcomeSubtitle();
  updateChatPlaceholder();
  updateMetaProvider();

  // Refresh panels that have been loaded so text stays consistent
  if (_toolsLoaded) { _toolsLoaded = false; loadTools(); }

  // Re-render drawings if panel was visited
  if (_drawingsLoaded) renderDrawingsData(_lastDrawingsData);

  // Re-render right panel (static text + dynamic list)
  initRightPanelStatic();
  if (_lastRpData) renderRightPanel(_lastRpData);

  // Logs
  if (state.activePanel === 'logs') loadLogs();

  // Log-level filter options
  ['DEBUG', 'INFO', 'WARN', 'ERROR'].forEach((lvl, i) => {
    const opt = $('log-level-filter')?.options[i];
    if (!opt) return;
    const keys = ['logs.all', 'logs.infoPlus', 'logs.warnPlus', 'logs.errorsOnly'];
    if (opt) opt.textContent = i18n.t(keys[i]);
  });

  // Update send button title
  if (state.isLoading) sendIcon.innerHTML = '…';
});

// ═══════════════════════════════════════════════════════════════════════════
// PANEL NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════
function showPanel(name) {
  state.activePanel = name;
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.panel === name));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id === `panel-${name}`));

  if (name === 'tools')    loadTools();
  if (name === 'drawings') loadDrawings();
  if (name === 'logs')     loadLogs();
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
    const dotAcad = $('dot-autocad');
    const valAcad = $('val-autocad');
    if (s.autocad?.connected) {
      dotAcad.className = 'status-dot dot-pulse';
      valAcad.textContent = s.autocad.drawing || i18n.t('status.noDrawing');
      valAcad.title = s.autocad.version || '';
    } else {
      dotAcad.className = 'status-dot dot-off';
      valAcad.textContent = i18n.t('status.disconnected');
    }

    // Ollama
    const dotOll = $('dot-ollama');
    const valOll = $('val-ollama');
    if (s.ollama?.available) {
      dotOll.className = 'status-dot dot-on';
      const n = (s.ollama.models || []).length;
      valOll.textContent = i18n.t(n === 1 ? 'status.models' : 'status.modelsPlural', { n });
    } else {
      dotOll.className = 'status-dot dot-off';
      valOll.textContent = i18n.t('status.disconnected');
    }

    // MCP tools count
    $('val-mcp').textContent = i18n.t('status.tools', { n: s.mcp?.tools ?? 0 });

    // Active drawing in topbar
    const drawingName = s.autocad?.drawing || i18n.t('status.noDrawing');
    $('val-drawing').textContent = drawingName;

    // Provider label
    if (s.provider?.active) updateMetaProvider(s.provider.active, s.provider.model);
  } catch (e) {
    console.warn('Status refresh failed:', e);
  }
}

function updateMetaProvider(provider, model) {
  if (!metaProvider) return;
  const p = provider || state.activeProvider;
  const m = model || '';
  metaProvider.textContent = p
    ? `${i18n.t('chat.engine')}: ${p}${m ? ' / ' + m : ''}`
    : '';
}

// ═══════════════════════════════════════════════════════════════════════════
// PROVIDERS
// ═══════════════════════════════════════════════════════════════════════════
async function loadProviders() {
  try {
    const data = await API.getProviders();
    state.providers      = data.providers;
    state.activeProvider = data.active;
    providerSelect.innerHTML = '';
    data.providers.forEach(p => {
      const opt = document.createElement('option');
      opt.value    = p.name;
      opt.textContent = `${p.name} · ${p.model || '—'}`;
      opt.selected = p.active;
      providerSelect.appendChild(opt);
    });
    updateMetaProvider(data.active, data.providers.find(p => p.active)?.model);
  } catch (e) {
    console.warn('Could not load providers:', e);
  }
}

providerSelect.addEventListener('change', async () => {
  const sel = providerSelect.value;
  try {
    await API.switchProvider(sel);
    state.activeProvider = sel;
    showToast(i18n.t('providers.switchSuccess', { name: sel }), 'success');
    await refreshStatus();
  } catch (e) {
    showToast(i18n.t('providers.switchError', { msg: e.message }), 'error');
  }
});

$('btn-refresh').addEventListener('click', async () => {
  await refreshStatus();
  showToast(i18n.t('toast.statusRefreshed'), 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// DRAWING MODE SELECTOR
// ═══════════════════════════════════════════════════════════════════════════
function updateModeHint() {
  const hint = $('mode-hint');
  if (hint) hint.textContent = i18n.t(`chat.modeHint.${state.drawingMode}`);
}

function updateChatPlaceholder() {
  if (chatInput) {
    chatInput.placeholder = i18n.t(`chat.placeholder.${state.drawingMode}`);
  }
}

function setDrawingMode(mode) {
  state.drawingMode = mode;
  $$('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  updateModeHint();
  updateChatPlaceholder();
}

$$('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => setDrawingMode(btn.dataset.mode));
});

// ═══════════════════════════════════════════════════════════════════════════
// CHAT
// ═══════════════════════════════════════════════════════════════════════════
function updateWelcomeSubtitle() {
  const el = $('welcome-subtitle');
  if (el) el.textContent = i18n.t('chat.welcome.subtitle');
}

function updateWelcomeChips() {
  // Chip labels + message text both come from i18n
  const chipMsgMap = {
    'chat.welcome.chips.activeDrawing': '¿What is the active drawing?',
    'chat.welcome.chips.line2d':        'Draw a line from 0,0 to 100,50',
    'chat.welcome.chips.rect2d':        'Draw a rectangle from 0,0 to 80,60',
    'chat.welcome.chips.box3d':         'Create a 3D box 80x80x80 at origin',
    'chat.welcome.chips.line3d':        'Draw a 3D line from 0,0,0 to 100,100,100',
    'chat.welcome.chips.isoView':       'Switch to SE isometric view',
    'chat.welcome.chips.bom':           'Generate the project BOM',
  };
  // msg in current language
  const msgMap = {
    en: {
      'chat.welcome.chips.activeDrawing': 'What is the active drawing?',
      'chat.welcome.chips.line2d':        'Draw a line from 0,0 to 100,50',
      'chat.welcome.chips.rect2d':        'Draw a rectangle from 0,0 to 80,60',
      'chat.welcome.chips.box3d':         'Create a 3D box 80x80x80 at origin',
      'chat.welcome.chips.line3d':        'Draw a 3D line from 0,0,0 to 100,100,100',
      'chat.welcome.chips.isoView':       'Switch to SE isometric view',
      'chat.welcome.chips.bom':           'Generate the project BOM',
    },
    es: {
      'chat.welcome.chips.activeDrawing': '¿Cuál es el dibujo activo?',
      'chat.welcome.chips.line2d':        'Dibuja una línea de 0,0 a 100,50',
      'chat.welcome.chips.rect2d':        'Dibuja un rectángulo de 0,0 a 80,60',
      'chat.welcome.chips.box3d':         'Crea una caja 3D de 80x80x80 en el origen',
      'chat.welcome.chips.line3d':        'Dibuja una línea 3D de 0,0,0 a 100,100,100',
      'chat.welcome.chips.isoView':       'Cambia a vista isométrica SE',
      'chat.welcome.chips.bom':           'Genera el BOM del proyecto',
    },
  };
  $$('.example-chip[data-msg-key]').forEach(chip => {
    const key = chip.dataset.msgKey;
    chip.textContent = i18n.t(key);
    const msgs = msgMap[i18n.lang] || msgMap.en;
    chip.dataset.msg = msgs[key] || key;
  });
}

function ensureChatReady() {
  const welcome = chatArea.querySelector('#chat-welcome');
  if (welcome) welcome.remove();
}

function nowStr() {
  return new Date().toLocaleTimeString(i18n.lang, { hour: '2-digit', minute: '2-digit' });
}

function simpleMarkdown(text) {
  return text
    .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function appendMessage(role, content, extra = {}) {
  ensureChatReady();

  const wrap  = document.createElement('div');
  wrap.className = `chat-msg ${role}${extra.failed ? ' failed' : ''}`;

  if (role === 'tool' && extra.tool) {
    const badge = document.createElement('div');
    badge.className = `tool-badge${extra.failed ? ' failed' : ''}`;
    badge.innerHTML = `${extra.failed ? '✕' : '✓'} <strong>${extra.tool}</strong>`;
    wrap.appendChild(badge);
  }

  const meta    = document.createElement('div');
  meta.className = 'msg-meta';
  meta.textContent = nowStr();
  wrap.appendChild(meta);

  const bubble  = document.createElement('div');
  bubble.className = 'msg-bubble msg-content';
  bubble.innerHTML  = simpleMarkdown(content);
  wrap.appendChild(bubble);

  chatArea.appendChild(wrap);
  chatArea.scrollTop = chatArea.scrollHeight;
  return wrap;
}

function showThinking() {
  ensureChatReady();
  const el    = document.createElement('div');
  el.id       = 'thinking-indicator';
  el.className = 'thinking';
  el.innerHTML = `<span>${i18n.t('chat.thinking')}</span><span class="thinking-dots"><span></span><span></span><span></span></span>`;
  chatArea.appendChild(el);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function hideThinking() {
  $('thinking-indicator')?.remove();
}

function setLoading(loading) {
  state.isLoading = loading;
  chatInput.disabled = loading;
  btnSend.classList.toggle('loading', loading);
  sendIcon.innerHTML = loading
    ? '<span style="font-size:16px">…</span>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/></svg>';
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
    const res = await API.chat(msg, state.activeProvider, state.drawingMode, i18n.lang);
    hideThinking();

    if (res.action === 'compound') {
      const label = res.intent ? `compound: ${res.intent}` : 'compound';
      appendMessage('tool', res.text, { tool: label, failed: !res.success });
    } else if (res.action === 'tool_call') {
      appendMessage('tool', res.text, { tool: res.tool, failed: !res.success });
    } else if (res.action === 'error' || !res.success) {
      appendMessage('error', res.text || res.error || 'Unknown error');
    } else {
      appendMessage('assistant', res.text || '…');
    }

    if (res.action === 'tool_call') {
      setTimeout(refreshStatus, 900);
      // Refresh drawings panel if it's open (a tool may have changed the active drawing)
      if (state.activePanel === 'drawings') setTimeout(loadDrawings, 1200);
    }
  } catch (e) {
    hideThinking();
    appendMessage('error', i18n.t('chat.connectionError', { msg: e.message }));
  } finally {
    setLoading(false);
    chatInput.focus();
  }
}

btnSend.addEventListener('click', sendMessage);

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

// Welcome chips
chatArea.addEventListener('click', e => {
  const chip = e.target.closest('.example-chip');
  if (!chip) return;
  if (chip.dataset.mode) setDrawingMode(chip.dataset.mode);
  chatInput.value = chip.dataset.msg || chip.textContent;
  chatInput.focus();
  chatInput.dispatchEvent(new Event('input'));
});

// Clear history
$('btn-clear-history').addEventListener('click', async () => {
  await API.clearHistory().catch(() => {});
  chatArea.innerHTML = '';
  // Rebuild welcome screen
  const w = document.createElement('div');
  w.id = 'chat-welcome';
  w.className = 'chat-welcome';
  w.innerHTML = `
    <div class="welcome-bolt">⚡</div>
    <h3 data-i18n="chat.welcome.title"></h3>
    <p id="welcome-subtitle"></p>
    <div class="welcome-examples" id="welcome-examples">
      <button class="example-chip" data-msg-key="chat.welcome.chips.activeDrawing" data-mode="auto">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.line2d"        data-mode="2d">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.rect2d"        data-mode="2d">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.box3d"         data-mode="3d">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.line3d"        data-mode="3d">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.isoView"       data-mode="3d">—</button>
      <button class="example-chip" data-msg-key="chat.welcome.chips.bom"           data-mode="electrical">—</button>
    </div>`;
  chatArea.appendChild(w);
  i18n._applyDOM();
  updateWelcomeChips();
  updateWelcomeSubtitle();
  showToast(i18n.t('chat.historyCleared'), 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// TOOLS PANEL
// ═══════════════════════════════════════════════════════════════════════════
let _toolsLoaded = false;

async function loadTools() {
  if (_toolsLoaded) return;
  toolsGrid.innerHTML = `<div class="loading-msg">${i18n.t('tools.loading')}</div>`;
  try {
    const data = await API.getTools();
    renderTools(data.tools);
    _toolsLoaded = true;
  } catch (e) {
    toolsGrid.innerHTML = `<div class="loading-msg" style="color:var(--error)">${i18n.t('tools.error', { msg: e.message })}</div>`;
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
      const name  = document.createElement('span');
      name.className = 'tool-name';
      name.textContent = tool.name;
      const badge = document.createElement('span');
      badge.className = 'tool-cat-badge';
      badge.textContent = cat;
      header.append(name, badge);

      const desc = document.createElement('div');
      desc.className = 'tool-desc';
      desc.textContent = tool.description;

      card.append(header, desc);
      card.addEventListener('click', () => {
        showPanel('chat');
        chatInput.value = `${i18n.lang === 'es' ? 'Ejecuta' : 'Execute'} ${tool.name}`;
        chatInput.focus();
      });

      cards.appendChild(card);
    });

    section.appendChild(cards);
    toolsGrid.appendChild(section);
  }
}

$('tools-search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase().trim();
  $$('.tool-card').forEach(card => {
    const match = !q || card.dataset.name.includes(q) || card.dataset.desc.includes(q);
    card.classList.toggle('tool-hidden', !match);
  });
  $$('.tool-category').forEach(cat => {
    const visible = cat.querySelectorAll('.tool-card:not(.tool-hidden)').length > 0;
    cat.style.display = visible ? '' : 'none';
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// DRAWINGS PANEL
// ═══════════════════════════════════════════════════════════════════════════
let _drawingsLoaded = false;
let _lastDrawingsData = null;

function saveRecentDrawing(name, fullPath) {
  if (!name) return;
  const rec = state.recentDrawings.filter(r => r.name !== name);
  rec.unshift({ name, path: fullPath || name, ts: Date.now() });
  state.recentDrawings = rec.slice(0, 10);
  localStorage.setItem('autocad-mcp-recents', JSON.stringify(state.recentDrawings));
}

async function loadDrawings() {
  $('active-drawing-card').innerHTML = `<div class="loading-msg">${'…'}</div>`;
  $('drawings-list').innerHTML = '';
  try {
    const data = await API.getDrawings();
    _lastDrawingsData = data;
    _drawingsLoaded = true;
    renderDrawingsData(data);
  } catch (e) {
    $('active-drawing-card').innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">🔌</span>
        <span>${i18n.t('drawings.notConnected')}</span>
      </div>`;
    $('drawings-list').innerHTML = '';
  }
  renderRecentDrawings();
}

function renderDrawingsData(data) {
  if (!data) return;
  const drawings = data.drawings || [];

  // Active card
  const activeEl = $('active-drawing-card');
  const active   = drawings.find(d => d.active);
  if (active) {
    activeEl.innerHTML = `
      <div class="drawing-active-card">
        <div class="drawing-active-info">
          <div class="drawing-active-icon">📐</div>
          <div>
            <div class="drawing-active-name">${escapeHtml(active.name)}</div>
            <div class="drawing-active-path">${escapeHtml(active.full_path || active.name)}</div>
          </div>
        </div>
        <span class="badge-active">${i18n.t('drawings.activeLabel')}</span>
      </div>`;
  } else {
    activeEl.innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">📐</span>
        <span>${i18n.t('drawings.noActiveDrawing')}</span>
      </div>`;
  }

  // Open drawings list
  const listEl  = $('drawings-list');
  const others  = drawings.filter(d => !d.active);
  if (drawings.length === 0) {
    listEl.innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">📂</span>
        <span>${i18n.t('drawings.noDrawings')}</span>
      </div>`;
    return;
  }

  listEl.innerHTML = '';
  drawings.forEach(dwg => {
    const card = document.createElement('div');
    card.className = `drawing-card${dwg.active ? ' is-active' : ''}`;

    const savedLabel = dwg.saved
      ? `<span style="color:var(--success)">${i18n.t('drawings.savedYes')}</span>`
      : `<span style="color:var(--warning)">${i18n.t('drawings.savedNo')}</span>`;

    card.innerHTML = `
      <div class="drawing-card-info">
        <div class="drawing-card-icon">${dwg.active ? '📐' : '📄'}</div>
        <div>
          <div class="drawing-card-name">${escapeHtml(dwg.name)}</div>
          <div class="drawing-card-sub">${savedLabel}</div>
        </div>
      </div>
      <div class="drawing-card-actions">
        ${dwg.active
          ? `<span class="badge-active">${i18n.t('drawings.activeLabel')}</span>`
          : `<button class="btn-sm-primary btn-activate" data-name="${escapeHtml(dwg.name)}">${i18n.t('drawings.setActive')}</button>`
        }
      </div>`;
    listEl.appendChild(card);
  });

  // Activate button handlers
  listEl.querySelectorAll('.btn-activate').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      activateDrawing(btn.dataset.name);
    });
  });

  // Card click = activate
  listEl.querySelectorAll('.drawing-card:not(.is-active)').forEach(card => {
    card.addEventListener('click', () => {
      const btn = card.querySelector('.btn-activate');
      if (btn) activateDrawing(btn.dataset.name);
    });
  });
}

function renderRecentDrawings() {
  const el       = $('recent-drawings-list');
  const clearBtn = $('btn-clear-recent');
  if (!state.recentDrawings.length) {
    el.innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">🕑</span>
        <span>${i18n.t('drawings.noRecentDrawings')}</span>
      </div>`;
    if (clearBtn) clearBtn.style.display = 'none';
    return;
  }
  if (clearBtn) clearBtn.style.display = '';

  el.innerHTML = '';
  state.recentDrawings.forEach(rec => {
    const card = document.createElement('div');
    card.className = 'drawing-card';
    card.style.cursor = 'pointer';
    card.innerHTML = `
      <div class="drawing-card-info">
        <div class="drawing-card-icon">🕑</div>
        <div>
          <div class="drawing-card-name">${escapeHtml(rec.name)}</div>
          <div class="drawing-card-sub" style="font-family:var(--font-mono);font-size:11px">${escapeHtml(rec.path || rec.name)}</div>
        </div>
      </div>
      <div class="drawing-card-actions">
        <button class="btn-sm-primary btn-activate-recent" data-name="${escapeHtml(rec.name)}">${i18n.t('drawings.setActive')}</button>
      </div>`;
    el.appendChild(card);
  });

  el.querySelectorAll('.btn-activate-recent').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      activateDrawing(btn.dataset.name);
    });
  });
}

async function activateDrawing(nameOrPath) {
  try {
    const res = await API.openDrawing(nameOrPath);
    if (res.success) {
      showToast(i18n.t('drawings.activateSuccess', { name: res.drawing || nameOrPath }), 'success');
      saveRecentDrawing(res.drawing || nameOrPath, nameOrPath);
      await Promise.all([loadDrawings(), loadRightPanel()]);
      setTimeout(refreshStatus, 600);
    } else {
      showToast(i18n.t('drawings.activateError', { msg: res.error || '?' }), 'error');
    }
  } catch (e) {
    showToast(i18n.t('drawings.activateError', { msg: e.message }), 'error');
  }
}

// Open Drawing form toggle
$('btn-open-drawing-toggle').addEventListener('click', () => {
  const form  = $('open-drawing-form');
  const open  = form.style.display === 'none' || !form.style.display;
  form.style.display = open ? '' : 'none';
  if (open) $('drawing-name-input').focus();
});

$('btn-cancel-open-drawing').addEventListener('click', () => {
  $('open-drawing-form').style.display = 'none';
  $('drawing-name-input').value = '';
});

$('btn-do-open-drawing').addEventListener('click', doOpenDrawing);

$('drawing-name-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doOpenDrawing();
  if (e.key === 'Escape') {
    $('open-drawing-form').style.display = 'none';
    $('drawing-name-input').value = '';
  }
});

async function doOpenDrawing() {
  const val = $('drawing-name-input').value.trim();
  if (!val) return;
  const btn = $('btn-do-open-drawing');
  btn.disabled = true;
  try {
    const res = await API.openDrawing(val);
    if (res.success) {
      showToast(i18n.t('drawings.openSuccess', { name: res.drawing || val }), 'success');
      saveRecentDrawing(res.drawing || val, val);
      $('open-drawing-form').style.display = 'none';
      $('drawing-name-input').value = '';
      await Promise.all([loadDrawings(), loadRightPanel()]);
      setTimeout(refreshStatus, 600);
    } else {
      showToast(i18n.t('drawings.openError', { msg: res.error || '?' }), 'error');
    }
  } catch (e) {
    showToast(i18n.t('drawings.openError', { msg: e.message }), 'error');
  } finally {
    btn.disabled = false;
  }
}

$('btn-refresh-drawings').addEventListener('click', loadDrawings);

// Clear recent drawings
$('btn-clear-recent')?.addEventListener('click', () => {
  state.recentDrawings = [];
  localStorage.removeItem('autocad-mcp-recents');
  renderRecentDrawings();
});

// ═══════════════════════════════════════════════════════════════════════════
// RIGHT PANEL — Drawing Files
// ═══════════════════════════════════════════════════════════════════════════

/** Write all static text into the right panel via i18n.t() — no dependency on
 *  data-i18n attributes or service-worker-cached HTML. Call on load + langchange.
 */
function initRightPanelStatic() {
  const set = (id, key) => { const el = $(id); if (el) el.textContent = i18n.t(key); };
  set('rp-title',         'rightPanel.title');
  set('rp-subtitle',      'rightPanel.subtitle');
  set('rp-btn-open-label','rightPanel.openButton');
  set('rp-tip-text',      'rightPanel.tip');
}

function formatFileSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatAge(unixTs) {
  if (!unixTs) return '';
  const diffMs  = Date.now() - unixTs * 1000;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1)   return i18n.t('rightPanel.ageMoments');
  if (diffMin < 60)  return i18n.t('rightPanel.ageMinutes', { n: diffMin });
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24)    return i18n.t('rightPanel.ageHours',   { n: diffH });
  return i18n.t('rightPanel.ageDays', { n: Math.round(diffH / 24) });
}

let _lastRpData = null;

async function loadRightPanel() {
  try {
    const data = await API.getDrawings();
    _lastRpData = data;
    renderRightPanel(data);
  } catch (e) {
    renderRightPanelError();
  }
}

function renderRightPanel(data) {
  const list = $('rp-list');
  if (!list) return;

  if (!data || !data.success) {
    renderRightPanelError();
    return;
  }

  const drawings = data.drawings || [];

  if (!drawings.length) {
    list.innerHTML = `
      <div class="rp-empty">
        <span class="rp-empty-icon">📂</span>
        <span>${i18n.t('rightPanel.noDrawings')}</span>
      </div>`;
    return;
  }

  list.innerHTML = '';
  drawings.forEach(dwg => {
    const item = document.createElement('div');
    item.className = `rp-item${dwg.active ? ' is-active' : ''}`;

    const sizePart = formatFileSize(dwg.file_size);
    const agePart  = formatAge(dwg.last_modified);
    const meta     = [sizePart, agePart].filter(Boolean).join(' · ');

    item.innerHTML = `
      <div class="rp-file-icon">${dwg.active ? '📐' : '📄'}</div>
      <div class="rp-file-info">
        <div class="rp-file-name">${escapeHtml(dwg.name)}</div>
        ${meta ? `<div class="rp-file-meta">${escapeHtml(meta)}</div>` : ''}
      </div>
      ${dwg.active
        ? `<span class="rp-badge">${i18n.t('rightPanel.activeLabel')}</span>`
        : ''
      }`;

    if (!dwg.active) {
      item.addEventListener('click', () => activateDrawing(dwg.name));
    }

    list.appendChild(item);
  });
}

function renderRightPanelError() {
  const list = $('rp-list');
  if (!list) return;
  list.innerHTML = `
    <div class="rp-empty">
      <span class="rp-empty-icon">🔌</span>
      <span>${i18n.t('rightPanel.notConnected')}</span>
    </div>`;
}

// Wire up right panel controls
$('rp-btn-refresh')?.addEventListener('click', loadRightPanel);
$('rp-btn-open')?.addEventListener('click', () => {
  // Switch to the Drawings panel and open the form
  showPanel('drawings');
  const form = $('open-drawing-form');
  if (form) {
    form.style.display = '';
    $('drawing-name-input')?.focus();
  }
});

// Right panel re-render is handled by the langchange listener near the top of the file.

// ═══════════════════════════════════════════════════════════════════════════
// LOGS PANEL
// ═══════════════════════════════════════════════════════════════════════════
async function loadLogs() {
  const level = $('log-level-filter').value;
  try {
    const data = await API.getLogs(150, level);
    renderLogs(data.logs);
  } catch (e) {
    logArea.innerHTML = `<div class="loading-msg" style="color:var(--error)">${i18n.t('logs.error', { msg: e.message })}</div>`;
  }
}

function renderLogs(logs) {
  if (!logs.length) {
    logArea.innerHTML = `<div class="loading-msg">${i18n.t('logs.empty')}</div>`;
    return;
  }
  logArea.innerHTML = '';
  logs.forEach(entry => {
    const row = document.createElement('div');
    row.className = 'log-entry';
    const ts  = (entry.timestamp || '').split('T')[1] || entry.timestamp || '';
    row.innerHTML = `
      <span class="log-ts">${ts.substring(0,12)}</span>
      <span class="log-level ${entry.level}">${entry.level}</span>
      <span class="log-src">${escapeHtml(entry.source || '')}</span>
      <span class="log-msg">${escapeHtml(entry.message || '')}</span>`;
    logArea.appendChild(row);
  });
  logArea.scrollTop = logArea.scrollHeight;
}

$('log-level-filter').addEventListener('change', loadLogs);

$('btn-clear-logs').addEventListener('click', async () => {
  await API.clearLogs().catch(() => {});
  logArea.innerHTML = `<div class="loading-msg">${i18n.t('logs.cleared')}</div>`;
  showToast(i18n.t('logs.cleared'), 'info', 2000);
});

// ═══════════════════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════════════════
function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ═══════════════════════════════════════════════════════════════════════════
// PWA — Install prompt
// ═══════════════════════════════════════════════════════════════════════════
let _installPrompt = null;
const btnInstall   = $('btn-install');

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _installPrompt = e;
  if (btnInstall) btnInstall.style.display = 'flex';
  showToast(i18n.lang === 'es'
    ? 'App disponible para instalar — clic en "Install App"'
    : 'App is ready to install — click "Install App"', 'info', 6000);
});

if (btnInstall) {
  btnInstall.addEventListener('click', async () => {
    if (!_installPrompt) return;
    _installPrompt.prompt();
    const { outcome } = await _installPrompt.userChoice;
    if (outcome === 'accepted') {
      showToast(i18n.lang === 'es' ? 'App instalada correctamente' : 'App installed', 'success', 4000);
      btnInstall.style.display = 'none';
    }
    _installPrompt = null;
  });
}

window.addEventListener('appinstalled', () => {
  if (btnInstall) btnInstall.style.display = 'none';
  _installPrompt = null;
});

// Register Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then(reg => console.info('[PWA] SW registered, scope:', reg.scope))
      .catch(err => console.warn('[PWA] SW registration failed:', err));
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════════════
(async function init() {
  // Apply initial i18n state
  initLangSwitcher();
  updateWelcomeSubtitle();
  updateWelcomeChips();
  setDrawingMode(state.drawingMode);   // sets hint + placeholder

  // Init right panel static text, then load data
  initRightPanelStatic();

  // Load providers, status, and right panel in parallel
  await Promise.all([loadProviders(), refreshStatus(), loadRightPanel()]);

  // Poll status every 10 s; refresh right panel every 15 s
  setInterval(refreshStatus, 10_000);
  setInterval(loadRightPanel, 15_000);

  // Auto-refresh logs when logs panel is active
  setInterval(() => {
    if (state.activePanel === 'logs') loadLogs();
  }, 5_000);

  chatInput.focus();
})();
