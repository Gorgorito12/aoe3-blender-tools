// SPDX-License-Identifier: GPL-3.0-or-later
// What every screen shares: the API, the language, small DOM helpers, toasts and dialogs.

const TOKEN = document.querySelector('meta[name="studio-token"]').content;

export async function api(path, body) {
  const opts = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Studio-Token': TOKEN } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const type = res.headers.get('Content-Type') || '';
  const data = type.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || String(data) || res.statusText);
  return data;
}

// the page is closing: the studio stops unless a page calls in again (a reload)
export function sayGoodbye() {
  navigator.sendBeacon('/api/bye', new Blob([JSON.stringify({ token: TOKEN })], { type: 'text/plain' }));
}

export async function fileUrl(path) {
  // an output's file, through the API (it needs the token): a blob URL the page can show
  const res = await fetch('/api/file?path=' + encodeURIComponent(path), { headers: { 'X-Studio-Token': TOKEN } });
  if (!res.ok) throw new Error(res.statusText);
  return URL.createObjectURL(await res.blob());
}

export async function fileText(path) {
  return api('/api/file?path=' + encodeURIComponent(path));
}

// -- language ------------------------------------------------------------------------------------
const dict = { en: {}, es: {} };
let lang = 'en';

export async function loadLanguages() {
  for (const l of ['en', 'es']) {
    const res = await fetch(`i18n/${l}.json`);
    dict[l] = await res.json();
  }
}

export function setLanguage(choice) {
  lang = choice === 'auto' || !choice ? ((navigator.language || 'en').toLowerCase().startsWith('es') ? 'es' : 'en') : choice;
  document.documentElement.lang = lang;
}

export function language() { return lang; }

// t(key, vars) -> the text in the current language, with {name} replaced from vars; a missing key
// falls back to English, then to `fallback`, then to the key itself
export function t(key, vars, fallback) {
  let s = dict[lang][key] ?? dict.en[key] ?? fallback ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

// a {en, es} pair from the catalog
export function tr(pair) {
  if (!pair) return '';
  if (typeof pair === 'string') return pair;
  return pair[lang] || pair.en || '';
}

// -- DOM -----------------------------------------------------------------------------------------
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.firstChild.remove(); return el; }

export function toast(message, kind = '') {
  const el = h('div', { class: `toast ${kind}`, role: kind === 'bad' ? 'alert' : 'status' }, message);
  document.getElementById('toasts').append(el);
  setTimeout(() => el.remove(), kind === 'bad' ? 9000 : 4500);
}

// a modal dialog; resolves with the value of the button pressed (or '' when closed)
export function dialog(title, body, buttons) {
  const d = document.getElementById('dialog');
  const form = clear(document.getElementById('dialog-form'));
  form.append(h('h2', { text: title }), body instanceof Node ? body : h('p', { text: body }),
    h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '14px' } },
      (buttons || [{ value: 'ok', label: t('ok'), primary: true }]).map(b =>
        h('button', { value: b.value, class: b.primary ? 'primary' : b.danger ? 'danger' : '', text: b.label }))));
  d.showModal();
  return new Promise(resolve => d.addEventListener('close', () => resolve(d.returnValue), { once: true }));
}

export async function confirmDialog(title, text, okLabel) {
  return (await dialog(title, text, [{ value: 'no', label: t('cancel') },
    { value: 'yes', label: okLabel || t('continue'), primary: true }])) === 'yes';
}

export async function pick(mode, opts = {}) {
  const r = await api('/api/pick', { mode, title: opts.title || '', initial: opts.initial || '', filters: opts.filters || [] });
  return mode === 'files' ? r.paths : r.path;
}

export function debounce(fn, ms) {
  let id;
  return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); };
}

export function fmt(n, digits = 0) {
  return Number(n).toLocaleString(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function storeGet(key, fallback) {
  try { const v = localStorage.getItem('studio.' + key); return v === null ? fallback : JSON.parse(v); }
  catch { return fallback; }
}

export function storeSet(key, value) {
  try { localStorage.setItem('studio.' + key, JSON.stringify(value)); } catch { /* private mode */ }
}
