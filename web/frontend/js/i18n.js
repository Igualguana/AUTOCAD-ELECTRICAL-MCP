/**
 * i18n.js — Bilingual internationalisation engine for AutoCAD MCP.
 *
 * Supported languages: English (en), Español (es)
 * Usage:
 *   i18n.t('nav.chat')                     → 'Chat'
 *   i18n.t('providers.switchSuccess', {name: 'ollama'}) → 'Engine changed to ollama'
 *   i18n.setLang('es')                     → switches language, updates DOM
 *
 * Adding a new language:
 *   1. Add a new key to TRANSLATIONS (e.g. TRANSLATIONS.fr = { ... })
 *   2. Add a button in the lang-switcher HTML in index.html
 */

'use strict';

// ═══════════════════════════════════════════════════════════════════════════
// TRANSLATION STRINGS
// Terms never translated: AutoCAD, DWG, MCP, Ollama, model names.
// ═══════════════════════════════════════════════════════════════════════════

const TRANSLATIONS = {

  // ── ENGLISH ──────────────────────────────────────────────────────────────
  en: {
    nav: {
      chat:     'Chat',
      tools:    'Tools',
      drawings: 'Drawings',
      logs:     'Logs',
    },
    topbar: {
      refresh:  'Refresh status',
      install:  'Install App',
    },
    status: {
      autocad:      'AutoCAD',
      ollama:       'Ollama',
      mcp:          'MCP',
      drawing:      'Drawing',
      disconnected: 'Disconnected',
      noDrawing:    'No drawing',
      tools:        '{n} tools',
      models:       '{n} model',
      modelsPlural: '{n} models',
    },
    chat: {
      title:         'Natural language → AutoCAD',
      clearHistory:  'Clear history',
      historyCleared:'History cleared',
      modeLabelHint: 'Mode',
      modeHint: {
        auto:       '46 tools · All categories',
        electrical: '46 tools · Electrical + 3D + 2D + Project',
        '2d':       '14 tools · Drawing + Project',
        '3d':       '23 tools · Drawing + Drawing3D + Project',
      },
      placeholder: {
        auto:       'AutoCAD instruction (Auto mode)…',
        electrical: 'Electrical instruction (symbols, ladder, cables, PLC)…',
        '2d':       '2D instruction (line, circle, rectangle, text, layer)…',
        '3d':       '3D instruction (box, sphere, cylinder, 3D line, view)…',
      },
      metaHint:      'Enter to send · Shift+Enter for new line',
      engine:        'Engine',
      thinking:      'AI processing',
      welcome: {
        title:    'AutoCAD Electrical MCP',
        subtitle: 'Type a natural language instruction to control AutoCAD.\nThe AI engine will interpret it and run the right tool.',
        chips: {
          activeDrawing: 'Active drawing',
          line2d:        '2D Line',
          rect2d:        '2D Rectangle',
          box3d:         '3D Box',
          line3d:        '3D Line',
          isoView:       'Isometric view',
          bom:           'Electrical BOM',
        },
      },
      connectionError: 'Connection error: {msg}',
    },
    tools: {
      title:           'Available MCP Tools',
      searchPlaceholder: 'Search tool…',
      loading:         'Loading tools…',
      error:           'Error loading tools: {msg}',
    },
    drawings: {
      title:              'Drawings',
      openButton:         'Open Drawing',
      pathPlaceholder:    'Sheet number or drawing name (e.g. Sheet_01.dwg)…',
      openAction:         'Open',
      cancel:             'Cancel',
      activeSection:      'Active Drawing',
      openSection:        'Open Drawings',
      recentSection:      'Recent Drawings',
      noActiveDrawing:    'No active drawing',
      noDrawings:         'No drawings available',
      noRecentDrawings:   'No recent drawings',
      setActive:          'Activate',
      activeLabel:        'Active',
      refresh:            'Refresh',
      openSuccess:        'Drawing opened: {name}',
      openError:          'Error opening drawing: {msg}',
      activateSuccess:    'Active drawing: {name}',
      activateError:      'Error activating drawing: {msg}',
      notConnected:       'AutoCAD is not connected',
      hint:               'Type a sheet number or drawing name. AutoCAD will open it from the project folder.',
      savedYes:           'Saved',
      savedNo:            'Unsaved *',
    },
    logs: {
      title:       'System Logs',
      clear:       'Clear',
      cleared:     'Logs cleared',
      all:         'All',
      infoPlus:    'INFO+',
      warnPlus:    'WARN+',
      errorsOnly:  'Errors only',
      loading:     'Loading logs…',
      empty:       'No log entries.',
      error:       'Error loading logs: {msg}',
    },
    providers: {
      switchSuccess: 'Engine changed to {name}',
      switchError:   'Error changing engine: {msg}',
    },
    toast: {
      statusRefreshed: 'Status refreshed',
    },
    rightPanel: {
      title:       'Drawing Files',
      subtitle:    'Open drawings in AutoCAD',
      openButton:  'Open Drawing',
      noDrawings:  'No drawings open',
      notConnected:'AutoCAD disconnected',
      activeLabel: 'Active',
      tip:         'Tip: You can also use the OPEN command in AutoCAD to open files.',
      recentTitle: 'Recent drawings',
      ageMoments:  'Just now',
      ageMinutes:  '{n} min ago',
      ageHours:    '{n} h ago',
      ageDays:     '{n} d ago',
    },
  },

  // ── ESPAÑOL ───────────────────────────────────────────────────────────────
  es: {
    nav: {
      chat:     'Chat',
      tools:    'Herramientas',
      drawings: 'Dibujos',
      logs:     'Registros',
    },
    topbar: {
      refresh:  'Actualizar estado',
      install:  'Instalar App',
    },
    status: {
      autocad:      'AutoCAD',
      ollama:       'Ollama',
      mcp:          'MCP',
      drawing:      'Dibujo',
      disconnected: 'Desconectado',
      noDrawing:    'Sin dibujo',
      tools:        '{n} herramientas',
      models:       '{n} modelo',
      modelsPlural: '{n} modelos',
    },
    chat: {
      title:         'Lenguaje natural → AutoCAD',
      clearHistory:  'Limpiar historial',
      historyCleared:'Historial borrado',
      modeLabelHint: 'Modo',
      modeHint: {
        auto:       '46 herramientas · Todas las categorías',
        electrical: '46 herramientas · Electrical + 3D + 2D + Project',
        '2d':       '14 herramientas · Drawing + Project',
        '3d':       '23 herramientas · Drawing + Drawing3D + Project',
      },
      placeholder: {
        auto:       'Instrucción para AutoCAD (modo Auto)…',
        electrical: 'Instrucción eléctrica (símbolos, escalera, cables, PLC)…',
        '2d':       'Instrucción 2D (línea, círculo, rectángulo, texto, capa)…',
        '3d':       'Instrucción 3D (caja, esfera, cilindro, línea 3D, vista)…',
      },
      metaHint:      'Enter para enviar · Shift+Enter para nueva línea',
      engine:        'Motor',
      thinking:      'IA procesando',
      welcome: {
        title:    'AutoCAD Electrical MCP',
        subtitle: 'Escribe una instrucción en lenguaje natural para controlar AutoCAD.\nEl motor IA la interpretará y ejecutará la herramienta correcta.',
        chips: {
          activeDrawing: 'Dibujo activo',
          line2d:        'Línea 2D',
          rect2d:        'Rectángulo 2D',
          box3d:         'Caja 3D',
          line3d:        'Línea 3D',
          isoView:       'Vista isométrica',
          bom:           'BOM eléctrico',
        },
      },
      connectionError: 'Error de conexión: {msg}',
    },
    tools: {
      title:           'Herramientas MCP disponibles',
      searchPlaceholder: 'Buscar herramienta…',
      loading:         'Cargando herramientas…',
      error:           'Error cargando herramientas: {msg}',
    },
    drawings: {
      title:              'Dibujos',
      openButton:         'Abrir Drawing',
      pathPlaceholder:    'Número de hoja o nombre del drawing (ej. Sheet_01.dwg)…',
      openAction:         'Abrir',
      cancel:             'Cancelar',
      activeSection:      'Drawing activo',
      openSection:        'Drawings abiertos',
      recentSection:      'Drawings recientes',
      noActiveDrawing:    'Sin drawing activo',
      noDrawings:         'No hay drawings disponibles',
      noRecentDrawings:   'Sin drawings recientes',
      setActive:          'Activar',
      activeLabel:        'Activo',
      refresh:            'Actualizar',
      openSuccess:        'Drawing abierto: {name}',
      openError:          'Error al abrir drawing: {msg}',
      activateSuccess:    'Drawing activo: {name}',
      activateError:      'Error al activar drawing: {msg}',
      notConnected:       'AutoCAD no está conectado',
      hint:               'Escribe un número de hoja o nombre. AutoCAD lo buscará en la carpeta del proyecto.',
      savedYes:           'Guardado',
      savedNo:            'Sin guardar *',
    },
    logs: {
      title:       'Registros del sistema',
      clear:       'Limpiar',
      cleared:     'Registros borrados',
      all:         'Todos',
      infoPlus:    'INFO+',
      warnPlus:    'WARN+',
      errorsOnly:  'Solo errores',
      loading:     'Cargando registros…',
      empty:       'Sin entradas de registro.',
      error:       'Error cargando registros: {msg}',
    },
    providers: {
      switchSuccess: 'Motor cambiado a {name}',
      switchError:   'Error al cambiar motor: {msg}',
    },
    toast: {
      statusRefreshed: 'Estado actualizado',
    },
    rightPanel: {
      title:       'Archivos de dibujo',
      subtitle:    'Drawings abiertos en AutoCAD',
      openButton:  'Abrir Drawing',
      noDrawings:  'No hay drawings abiertos',
      notConnected:'AutoCAD desconectado',
      activeLabel: 'Activo',
      tip:         'Consejo: También puedes usar el comando OPEN en AutoCAD para abrir archivos.',
      recentTitle: 'Drawings recientes',
      ageMoments:  'Ahora mismo',
      ageMinutes:  'Hace {n} min',
      ageHours:    'Hace {n} h',
      ageDays:     'Hace {n} d',
    },
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// I18N ENGINE
// ═══════════════════════════════════════════════════════════════════════════

class I18nEngine {
  constructor() {
    const stored  = localStorage.getItem('autocad-mcp-lang');
    const browser = (navigator.language || 'en').toLowerCase();
    this._lang = stored || (browser.startsWith('es') ? 'es' : 'en');
    document.documentElement.lang = this._lang;
  }

  /**
   * Get a translation by dot-path key with optional {var} interpolation.
   * Falls back to English, then returns the key itself.
   */
  t(key, vars = {}) {
    let val = this._resolve(TRANSLATIONS[this._lang], key)
           ?? this._resolve(TRANSLATIONS['en'], key)
           ?? key;

    if (typeof val !== 'string') return key;

    for (const [k, v] of Object.entries(vars)) {
      val = val.replaceAll(`{${k}}`, v);
    }
    return val;
  }

  _resolve(obj, key) {
    return key.split('.').reduce((o, k) => o?.[k], obj);
  }

  /** Switch language, persist to localStorage, update DOM, fire event. */
  setLang(lang) {
    if (!TRANSLATIONS[lang]) return;
    this._lang = lang;
    localStorage.setItem('autocad-mcp-lang', lang);
    document.documentElement.lang = lang;
    this._applyDOM();
    window.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
  }

  /** Apply translations to all data-i18n-* elements in the document. */
  _applyDOM() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = this.t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      el.placeholder = this.t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      el.title = this.t(el.dataset.i18nTitle);
    });
  }

  /** Apply translations immediately after DOM is ready. */
  init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this._applyDOM());
    } else {
      this._applyDOM();
    }
    return this;
  }

  get lang()      { return this._lang; }
  get available() { return Object.keys(TRANSLATIONS); }
}

// ── Singleton ───────────────────────────────────────────────────────────────
const i18n = new I18nEngine().init();
