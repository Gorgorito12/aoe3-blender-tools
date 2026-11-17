// SPDX-License-Identifier: GPL-3.0-or-later
// The studio's page: navigation, language, theme, and the screens.
import { api, clear, h, loadLanguages, sayGoodbye, setLanguage, storeGet, storeSet, t, toast } from './core.js';
import { buildingsScreen } from './buildings.js';
import { areaScreen, toolScreen } from './tools.js';
import { jobsScreen } from './jobs.js';
import { settingsScreen } from './settings.js';
import { inspectScreen } from './inspect.js';

const SCREENS = [
  { id: 'buildings', icon: '🏛' },
  { id: 'textures', icon: '🎨' },
  { id: 'survey', icon: '🔎' },
  { id: 'art', icon: '🚩' },
  { id: 'jobs', icon: '⏱' },
  { id: 'settings', icon: '⚙' },
  { id: 'dev', icon: '🛠' },
];

const app = {
  state: null,
  leave: [],
  onLeave(fn) { this.leave.push(fn); },
  go(route) { location.hash = '#/' + route; },
  // what an area's screen shows above its tools
  extraFor(area) {
    if (area !== 'survey') return null;
    return h('button', { type: 'button', class: 'card tool-card', style: { marginBottom: '12px', width: '100%' },
      onclick: () => this.go('inspect') }, h('strong', { text: t('i.title') }), h('span', { class: 'muted', text: t('i.intro') }));
  },
};

async function show() {
  const route = (location.hash.replace(/^#\//, '') || 'buildings');
  for (const fn of app.leave.splice(0)) { try { fn(); } catch { /* already gone */ } }
  const main = document.getElementById('main');
  const [head, rest] = route.split('/');
  drawNav(head === 'tool' ? toolArea(rest) : head === 'inspect' ? 'survey' : head);
  try {
    if (head === 'buildings') await buildingsScreen(main, app);
    else if (head === 'jobs') await jobsScreen(main, app);
    else if (head === 'settings') await settingsScreen(main, app);
    else if (head === 'tool') await toolScreen(main, app, rest);
    else if (head === 'inspect') await inspectScreen(main, app);
    else await areaScreen(main, app, head);
  } catch (e) {
    clear(main).append(h('div', { class: 'notice bad' }, e.message));
  }
  main.focus({ preventScroll: true });
}

let toolAreas = {};
function toolArea(id) { return toolAreas[id] || 'buildings'; }

function drawNav(current) {
  const list = clear(document.getElementById('nav-list'));
  for (const s of SCREENS) {
    list.append(h('li', {}, h('button', { type: 'button', 'aria-current': s.id === current ? 'page' : null,
      onclick: () => app.go(s.id) }, h('span', { 'aria-hidden': 'true', text: s.icon }), t('nav.' + s.id))));
  }
}

function applyTheme(theme) {
  if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme');
  btn.textContent = { auto: '◐', light: '☀', dark: '☾' }[theme];
  btn.title = t('theme.' + theme);
}

async function start() {
  await loadLanguages();
  app.state = await api('/api/state');
  setLanguage(app.state.settings.language);
  document.getElementById('version').textContent = 'v' + app.state.version;
  const lang = document.getElementById('lang');
  for (const [v, label] of [['auto', t('lang.auto')], ['en', 'English'], ['es', 'Español']]) {
    lang.append(h('option', { value: v, selected: v === app.state.settings.language, text: label }));
  }
  lang.addEventListener('change', async () => {
    app.state = await api('/api/settings', { language: lang.value });
    setLanguage(lang.value);
    lang.options[0].text = t('lang.auto');
    show();
  });
  let theme = storeGet('theme', 'auto');
  applyTheme(theme);
  document.getElementById('theme').addEventListener('click', () => {
    theme = { auto: 'light', light: 'dark', dark: 'auto' }[theme];
    storeSet('theme', theme);
    applyTheme(theme);
  });
  try {
    const cat = await api('/api/catalog');
    toolAreas = Object.fromEntries(cat.tools.map(x => [x.id, x.area]));
  } catch { /* the tools screens say why */ }
  window.addEventListener('hashchange', show);
  setInterval(() => api('/api/ping', {}).catch(() => {}), 10000);
  window.addEventListener('pagehide', sayGoodbye);
  api('/api/ping', {}).catch(() => {});
  await show();
  if (!app.state.settings.paths.game && !storeGet('welcomed', false)) {
    storeSet('welcomed', true);
    toast(t('welcome'), 'ok');
  }
}

start().catch(e => {
  document.getElementById('main').append(h('div', { class: 'notice bad' }, 'The studio could not start: ' + e.message));
});
