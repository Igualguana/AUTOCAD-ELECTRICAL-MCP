/**
 * api.js — Thin HTTP wrapper around the FastAPI backend.
 * All functions return parsed JSON or throw an Error on failure.
 */

'use strict';

const API = {
  base: '',   // same origin

  async _fetch(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== null) opts.body = JSON.stringify(body);
    const res = await fetch(this.base + path, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  // ── Status ─────────────────────────────────────────────────────────────
  getStatus() { return this._fetch('GET', '/api/status'); },

  // ── Tools ──────────────────────────────────────────────────────────────
  getTools()  { return this._fetch('GET', '/api/tools'); },

  // ── Logs ───────────────────────────────────────────────────────────────
  getLogs(limit = 150, minLevel = 'DEBUG') {
    return this._fetch('GET', `/api/logs?limit=${limit}&min_level=${minLevel}`);
  },
  clearLogs() { return this._fetch('DELETE', '/api/logs'); },

  // ── History ────────────────────────────────────────────────────────────
  getHistory(limit = 50) { return this._fetch('GET', `/api/history?limit=${limit}`); },
  clearHistory()          { return this._fetch('DELETE', '/api/history'); },

  // ── Drawing info (legacy — active drawing + project) ───────────────────
  getDrawingInfo() { return this._fetch('GET', '/api/drawing/info'); },

  // ── Drawings management ────────────────────────────────────────────────
  /** List all drawings currently open in AutoCAD. */
  getDrawings() { return this._fetch('GET', '/api/drawings'); },

  /** Open / activate a drawing by sheet number, name, or partial path. */
  openDrawing(nameOrPath) {
    return this._fetch('POST', '/api/drawings/open', { name_or_path: nameOrPath });
  },

  // ── Providers ──────────────────────────────────────────────────────────
  getProviders() { return this._fetch('GET', '/api/providers'); },
  switchProvider(provider, model = null) {
    return this._fetch('POST', '/api/providers/switch', { provider, model });
  },

  // ── Chat ───────────────────────────────────────────────────────────────
  // mode: "auto" | "electrical" | "2d" | "3d"
  chat(message, provider = null, mode = null, lang = null) {
    return this._fetch('POST', '/api/chat', { message, provider, mode, lang });
  },

  // ── Direct tool execution ──────────────────────────────────────────────
  executeTool(tool, params = {}) {
    return this._fetch('POST', '/api/execute', { tool, params });
  },
};
