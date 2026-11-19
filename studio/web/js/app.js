// SPDX-License-Identifier: GPL-3.0-or-later
// The studio's page: navigation, language, theme, and the screens.
import { api, clear, h, loadLanguages, sayGoodbye, setLanguage, storeGet, storeSet, t } from './core.js';
import { buildingsScreen } from './buildings.js';
import { areaScreen, toolScreen } from './tools.js';
import { jobsScreen } from './jobs.js';
import { settingsScreen } from './settings.js';
import { inspectScreen } from './inspect.js';
import { retexScreen } from './retex.js';
import { flagsScreen } from './flags.js';
import { texmakerScreen } from './texmaker.js';
import { settlementScreen } from './settlement.js';
import { resultsScreen } from './results.js';
import { hudScreen } from './hud.js';
import { meshinScreen } from './meshin.js';
import { welcomeScreen } from './welcome.js';

const SCREENS = [
  { id: 'buildings', icon: '🏛' },
  { id: 'textures', icon: '🎨' },
  { id: 'survey', icon: '🔎' },
  { id: 'art', icon: '🚩' },
  { id: 'jobs', icon: '⏱' },
  { id: 'settings', icon: '⚙' },
  { id: 'dev', icon: '🛠' },
];

// the screens made for their task, shown first on their area: [route, title key, intro key]
const SCREENS_OF = {
  buildings: [['meshin', 'm.title', 'm.intro'], ['settlement', 'se.title', 'se.intro']],
  survey: [['inspect', 'i.title', 'i.intro'], ['results', 'rs.title', 'rs.intro']],
  textures: [['retex', 'r.title', 'r.intro'], ['texmaker', 'x.title', 'x.intro']],
  art: [['hud', 'h.title', 'h.intro'], ['flags', 'f.title', 'f.intro']],
};
// the area each of those screens belongs to, for the navigation
const AREA_OF = { welcome: 'settings', buildtools: 'buildings', meshin: 'buildings',
  ...Object.fromEntries(Object.entries(SCREENS_OF).flatMap(([a, list]) => list.map(([r]) => [r, a]))) };

const app = {
  state: null,
  leave: [],
  onLeave(fn) { this.leave.push(fn); },
  go(route) { location.hash = '#/' + route; },
  // what an area's screen shows above its tools
  extraFor(area) {
    const screens = SCREENS_OF[area];
    if (!screens) return null;
    return h('div', { class: 'tool-grid', style: { marginBottom: '14px' } }, screens.map(([route, title, intro]) =>
      h('button', { type: 'button', class: 'card tool-card featured', onclick: () => this.go(route) },
        h('strong', { text: t(title) }), h('span', { class: 'muted', text: t(intro) }))));
  },
};

async function show() {
  const route = (location.hash.replace(/^#\//, '') || 'buildings');
  for (const fn of app.leave.splice(0)) { try { fn(); } catch { /* already gone */ } }
  // each visit draws into a page of its own: a screen still loading when the user moves on then
  // draws into a page no longer shown, never over the next screen
  const main = h('div', { class: 'page' });
  clear(document.getElementById('main')).append(main);
  const [head, rest] = route.split('/');
  drawNav(head === 'tool' ? toolArea(rest) : AREA_OF[head] || head);
  try {
    if (head === 'buildings') await buildingsScreen(main, app);
    else if (head === 'jobs') await jobsScreen(main, app);
    else if (head === 'settings') await settingsScreen(main, app);
    else if (head === 'tool') await toolScreen(main, app, rest);
    else if (head === 'inspect') await inspectScreen(main, app);
    else if (head === 'retex') await retexScreen(main, app);
    else if (head === 'flags') await flagsScreen(main, app);
    else if (head === 'texmaker') await texmakerScreen(main, app);
    else if (head === 'welcome') await welcomeScreen(main, app);
    else if (head === 'settlement') await settlementScreen(main, app);
    else if (head === 'results') await resultsScreen(main, app);
    else if (head === 'hud') await hudScreen(main, app);
    else if (head === 'meshin') await meshinScreen(main, app);
    else if (head === 'buildtools') await areaScreen(main, app, 'buildings');   // the area's own forms
    else await areaScreen(main, app, head);
  } catch (e) {
    clear(main).append(h('div', { class: 'notice bad' }, e.message));
  }
  document.getElementById('main').focus({ preventScroll: true });
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
  setInterval(() => api('/api/ping', {}).catch(() => {}), 10000);   // a failed ping shows the offline bar
  window.addEventListener('pagehide', sayGoodbye);
  api('/api/ping', {}).catch(() => {});
  // the first start: the welcome, until the game's folder is set or the user says later
  if (!app.state.settings.paths.game && !storeGet('welcomed', false) && !location.hash) location.hash = '#/welcome';
  await show();
}

start().catch(e => {
  document.getElementById('main').append(h('div', { class: 'notice bad' }, 'The studio could not start: ' + e.message));
});
