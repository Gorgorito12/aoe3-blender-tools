// SPDX-License-Identifier: GPL-3.0-or-later
// Tasks running in their own process: a live log with progress and cancel, their outputs, and
// the screen that lists them all.
import { api, clear, dialog, fileText, fileUrl, fmt, h, storeSet, t, toast } from './core.js';

const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i;
const TEXT = /\.(txt|md|json|xml|csv|log)$/i;

// shows a job in `box` until it ends; calls onDone(job) then
export function watchJob(id, box, { onDone } = {}) {
  clear(box);
  const title = h('strong', {});
  const status = h('span', { class: 'pill' });
  const bar = h('i', { style: { width: '0%' } });
  const log = h('div', { class: 'log', role: 'log', 'aria-live': 'off' });
  const cancel = h('button', { type: 'button', class: 'danger', text: t('cancel'),
    onclick: async () => { await api('/api/cancel/' + id, {}); } });
  const outs = h('div', { class: 'stack' });
  box.append(h('div', { class: 'card stack' }, h('div', { class: 'row' }, title, status, h('span', { class: 'grow' }), cancel),
    h('div', { class: 'progress' }, bar), log, outs));
  let since = 0, stopped = false;
  const tick = async () => {
    if (stopped || !box.isConnected) return;
    let j;
    try { j = await api(`/api/jobs/${id}?since=${since}`); } catch (e) { log.append(e.message + '\n'); return; }
    title.textContent = j.title;
    status.textContent = t('status.' + j.status);
    status.className = 'pill ' + ({ done: 'ok', failed: 'bad', cancelled: 'bad', running: 'warn' }[j.status] || '');
    if (j.progress !== null) bar.style.width = (j.progress * 100).toFixed(1) + '%';
    const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
    for (const line of j.lines) {
      const bad = /error|traceback|refus|failed|exception/i.test(line);
      log.append(bad ? h('span', { class: 'err', text: line + '\n' }) : line + '\n');
    }
    if (atEnd) log.scrollTop = log.scrollHeight;
    since = j.next;
    if (j.status === 'running' || j.status === 'queued') { setTimeout(tick, 600); return; }
    stopped = true;
    cancel.hidden = true;
    bar.style.width = '100%';
    if (j.status === 'done') toast(t('job.done', { title: j.title }), 'ok');
    else toast(t('job.failed', { title: j.title, code: j.code }), 'bad');
    showOutputs(j.outputs, outs);
    onDone?.(j);
  };
  tick();
}

export async function showOutputs(paths, box) {
  clear(box);
  for (const p of paths || []) {
    const row = h('div', { class: 'row small' }, h('span', { class: 'mono grow', text: p }),
      h('button', { type: 'button', text: t('open.folder'), onclick: () => api('/api/open', { path: p }).catch(e => toast(e.message, 'bad')) }));
    box.append(row);
    let files;
    try {
      if (IMAGE.test(p) || TEXT.test(p)) files = [{ path: p, rel: p.split(/[\\/]/).pop() }];
      else files = (await api('/api/list?deep=1&path=' + encodeURIComponent(p))).files;
    } catch { continue; }
    const imgs = files.filter(f => IMAGE.test(f.path)).slice(0, 24);
    const texts = files.filter(f => TEXT.test(f.path)).slice(0, 12);
    // a survey's report or profile: its groups as a table
    for (const f of files.filter(f => /(^|[\\/])(textures|models)\.json$|profile[^\\/]*\.json$/i.test(f.path)).slice(0, 2)) {
      box.append(h('div', { class: 'row' }, h('button', { type: 'button', class: 'primary small', text: t('rs.see') + ' · ' + f.rel,
        onclick: () => { storeSet('results.open', { path: f.path }); location.hash = '#/results'; } })));
    }
    if (imgs.length) {
      const grid = h('div', { class: 'outputs' });
      box.append(grid);
      for (const f of imgs) {
        const img = h('img', { alt: f.rel, loading: 'lazy' });
        grid.append(h('figure', {}, img, h('figcaption', { text: f.rel })));
        fileUrl(f.path).then(u => { img.src = u; img.onclick = () => dialog(f.rel, h('img', { src: u, alt: f.rel })); }).catch(() => {});
      }
    }
    if (texts.length) {
      box.append(h('div', { class: 'row' }, texts.map(f => h('button', { type: 'button', class: 'small', text: f.rel,
        onclick: async () => { const text = await fileText(f.path); dialog(f.rel, h('pre', { class: 'log', text: String(text).slice(0, 200000) })); } }))));
    }
    if (files.length > imgs.length + texts.length) {
      box.append(h('p', { class: 'small muted', text: t('outputs.more', { n: fmt(files.length) }) }));
    }
  }
}

export async function jobsScreen(main) {
  clear(main);
  const table = h('table', { class: 'jobs-table' });
  const detail = h('div', {});
  main.append(h('div', { class: 'head' }, h('div', {}, h('h1', { text: t('nav.jobs') }), h('p', { class: 'muted', text: t('jobs.intro') }))),
    h('div', { class: 'stack' }, h('div', { class: 'card' }, table), detail));
  const draw = async () => {
    if (!table.isConnected) return;
    const jobs = await api('/api/jobs');
    clear(table);
    table.append(h('tr', {}, [t('jobs.task'), t('jobs.status'), t('jobs.started'), t('jobs.time'), ''].map(x => h('th', { text: x }))));
    if (!jobs.length) table.append(h('tr', {}, h('td', { colspan: 5, class: 'muted', text: t('jobs.none') })));
    for (const j of jobs) {
      const secs = ((j.ended || Date.now() / 1000) - (j.started || Date.now() / 1000));
      table.append(h('tr', {}, h('td', { text: j.title }), h('td', { class: 'status-' + j.status, text: t('status.' + j.status) }),
        h('td', { text: j.started ? new Date(j.started * 1000).toLocaleTimeString() : '' }), h('td', { text: fmt(secs, 0) + ' s' }),
        h('td', {}, h('button', { type: 'button', text: t('jobs.show'), onclick: () => watchJob(j.id, detail) }))));
    }
    setTimeout(draw, 2000);
  };
  draw();
}
