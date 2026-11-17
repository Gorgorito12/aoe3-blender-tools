// SPDX-License-Identifier: GPL-3.0-or-later
// Visits every screen of a running studio in a headless Edge or Chrome, in each language, and
// prints what is wrong as JSON: page errors, keys shown untranslated, a page wider than the
// window. Driven through the DevTools protocol with Node's own WebSocket (Node 22 or newer).
//
//   node tests/studio_ui.mjs <studio url> <browser exe> <profile folder> <routes,...> <languages,...>
//
// tests/test_studio_ui.py runs it on a studio it starts with a throwaway configuration.
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const [url, browser, profile, routeList, langList] = process.argv.slice(2);
const routes = routeList.split(',');
const languages = langList.split(',');
const here = dirname(fileURLToPath(import.meta.url));
const en = JSON.parse(readFileSync(join(here, '..', 'studio', 'web', 'i18n', 'en.json'), 'utf8'));
// keys that look like keys (a dot in them): seen on a page, they were never translated
const keys = Object.keys(en).filter(k => /^[a-z]+(\.[A-Za-z0-9_]+)+$/.test(k));

const port = 9300 + Math.floor(Math.random() * 400);
const proc = spawn(browser, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--window-size=1440,900', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--no-first-run',
  '--disable-extensions', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const done = (out, code = 0) => { proc.kill(); console.log(JSON.stringify(out)); process.exit(code); };

let ws;
for (let i = 0; i < 100 && !ws; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = list.find(x => x.type === 'page');
    if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
  } catch { /* not up yet */ }
  if (!ws) await sleep(150);
}
if (!ws) done({ error: 'the browser did not start' }, 2);
await new Promise(r => ws.addEventListener('open', r, { once: true }));

let id = 0;
const pending = new Map();
let problems = [];
ws.addEventListener('message', e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  const extension = s => /chrome-extension:|runtime\.lastError/.test(s || '');
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails;
    const text = d.exception?.description || d.text;
    if (!extension(text) && !extension(d.url)) problems.push('exception: ' + text);
  }
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    const text = m.params.args.map(a => a.value ?? a.description).join(' ');
    if (!extension(text)) problems.push('console: ' + text);
  }
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
    const { text, url: where } = m.params.entry;
    if (!extension(text) && !extension(where)) problems.push('log: ' + text + ' ' + (where || ''));
  }
});
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

const report = [];
await send('Page.navigate', { url });
await sleep(2500);
for (const lang of languages) {
  await evaluate(`fetch('/api/settings', {method: 'POST', headers: {'X-Studio-Token': document.querySelector('meta[name=studio-token]').content,
    'Content-Type': 'application/json'}, body: JSON.stringify({language: '${lang}'})}).then(r => r.status)`);
  await send('Page.reload');                // the page reads its language when it starts
  await sleep(2500);
  for (const route of routes) {
    problems = [];
    await send('Page.navigate', { url: `${url}#/${route}` });
    await sleep(route === 'buildings' ? 4500 : 2500);
    const seen = await evaluate(`(() => {
      const text = document.body.innerText;
      const keys = ${JSON.stringify(keys)};
      const shown = keys.filter(k => new RegExp('(^|[^\\\\w.])' + k.replace(/\\./g, '\\\\.') + '($|[^\\\\w.])').test(text));
      const main = document.getElementById('main');
      return { untranslated: shown, wide: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
        || main.scrollWidth > main.clientWidth + 1, title: document.querySelector('h1')?.textContent || '',
        lang: document.documentElement.lang };
    })()`);
    report.push({ route, lang_asked: lang, problems, ...seen });
  }
}
ws.close();
done({ report });
