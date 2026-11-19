// SPDX-License-Identifier: GPL-3.0-or-later
// The in-game HUD drawn as the game draws it, at the screen's own pixels: each gadget's size1024
// rectangle scaled from the 1024 x 768 layout space, its colour, its texture (cropped by
// texturecoords, tiled, or its first state), its text in the game's font, its foreground, then its
// children, siblings in z order. What the engine does that the files do not say is gathered in
// ASSUMED: each is to verify in game and the screen says so.

export const ASSUMED = {
  stretch: 'each axis scaled on its own: x * width / 1024, y * height / 768',
  zorder: 'children over their parent; siblings, and the top-level gadgets of all files, by z, then file order',
  textcolor: 'white when a gadget gives none',
  align: 'left and top unless textcenterhoriz / textjustifyright, textcentervert / texttruecentervert',
  wrap: 'one line unless textwrapon',
  tile: 'a tiled texture repeats at its own texel size times width / 1024',
  fontsize: 'measured: AscentHeight is the text cell (ascent + descent) in screen pixels, as Windows sizes a font ("Tactics", StatAreaText 12, at 1920 x 1080)',
  fontmissing: 'measured: a font fonts3.xml lacks (StatText 10, IngameDialogs 12) is drawn as "Arial nobold nodrop 12" whatever its size (regular Arial, a 14-pixel cell at 1920 x 1080: "Train Points", "LOS"); whether the game takes that entry or a default of the same values is to verify',
  fontwidth: 'which fonts3.xml override applies at a screen width: the base values at 1024, an override from its ResX upward',
  icons: 'an icon in a text, <icon="(16)(path)">, is drawn as tall as the text cell and 0.72 as wide (about 10 x 14 at 1920 x 1080, as measured for make_stat_icon)',
  progress: 'a progressBar is drawn as its progressbarbackground, then its progressbarmask over the share done',
  engine: 'what the game writes into the gadgets it fills, and its colours (labels yellow, attack rows cyan), is the unit simulation: aoe3game/unitpanel.py',
};

const ICON = /<icon="\((\d+)\)\(([^)]*)\)">/g;

// a line of text as runs: [{text}] and [{icon: path}], other markup taken out
export function runs(line) {
  const out = [];
  let last = 0;
  for (const m of line.matchAll(ICON)) {
    if (m.index > last) out.push({ text: line.slice(last, m.index).replace(/<[^>]*>/g, '') });
    out.push({ icon: m[2], size: Number(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ text: line.slice(last).replace(/<[^>]*>/g, '') });
  return out.filter(r => r.icon || r.text);
}

// sample values for the live texts the screen shows without a game running
export const SAMPLES = {
  resource: '1000', numgatherers: '5', numunits: '12', numidle: '0', currentunithp: '150', currentunitmaximumhp: '150',
  currentunitlos: '16', currentunittrainpoints: '30', currentunitmaxvelocityfloat: '4.00',
  currentunitmaxvelocity: '4', currentunitcapacity: '0 / 0', currentunitname: 'Musketeer', popcount: '40',
  popcap: '200', totalpop: '40', futurepop: '', playerage: 'Colonial Age', playername: 'Player 1',
  currentunitattack: '23', currentunitgatherrate: '', gametime: '12:34', gamespeed: 'Normal', gameversion: '1.14',
  aidifficulty: 'Hard', numdancers: '0', dancedescription: '', dancequickvalue: '',
};

// a gadget name against a moment's patterns (any case, * for any text)
function globber(patterns) {
  const esc = p => p.split('*').map(part => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*');
  return new RegExp('^(' + patterns.map(esc).join('|') + ')$', 'i');
}

export function parseColour(v, fallback = [255, 255, 255]) {
  const n = String(v || '').trim().split(/[\s,]+/).map(Number);
  return n.length >= 3 && n.slice(0, 3).every(x => Number.isFinite(x)) ? n.slice(0, 3) : fallback;
}

// fonts3.xml's values for a font at a screen width (the base values are the 1024 layout's own;
// an override applies from its ResX upward: to verify), or null when there is no such entry
export const FALLBACK_FONT = 'arial nobold nodrop 12';

export function fontAt(fonts, font, size, width, height = width * 0.75) {
  let entry = font ? fonts[`${font} ${size}`.toLowerCase()] : null;
  let fallback = null;
  if (!entry && font) {
    // not in fonts3.xml: drawn as "Arial nobold nodrop 12", whatever the size asked (measured)
    entry = fonts[FALLBACK_FONT];
    fallback = `${font} ${size}`;
    if (!entry) return { Name: fallback, TypeFace: 'Arial', AscentHeight: 12 * height / 768, Bold: false, Fallback: fallback };
  }
  if (!entry) return null;
  const p = { ...entry.params };
  const xs = [...new Set([...Object.keys(entry.overrides).map(Number), 1024])].sort((a, b) => a - b);
  let chosen = null;
  for (const x of xs) if (x <= width) chosen = x;
  if (chosen === null) chosen = xs[0];
  if (chosen !== 1024 && entry.overrides[chosen]) Object.assign(p, entry.overrides[chosen]);
  p.Name = entry.name; p.ResX = chosen;
  if (fallback) p.Fallback = fallback;
  return p;
}

// a gadget's text as the screen shows it: $$id$$fallback through the string table, {fn(args)}
// through the samples (or the simulation's values), \n as a line break
export function displayText(text, strings, live = {}) {
  if (!text) return '';
  let s = text.replace(/\$\$(\d+)\$\$([^\n<{$]*)/g, (m, id, fallback) => (strings[id] ? strings[id][0] : fallback));
  s = s.replace(/\{([A-Za-z_]\w*)(\([^)]*\))?\}/g, (m, fn) => {
    const key = fn.toLowerCase();
    if (key in live) return live[key];
    return key in SAMPLES ? SAMPLES[key] : m;
  });
  return s.replace(/\\n/g, '\n');
}

export class HudRenderer {
  constructor(scene, assets) {
    this.scene = scene;
    this.assets = assets;               // { image(path) -> ImageBitmap|null, face(typeface) -> css family|null, ratio(family) }
    this.byId = scene.gadgets;
    this.children = new Map();
    this.tops = [];
    for (const g of scene.gadgets) {
      if (g.parent === null || g.parent === undefined) this.tops.push(g);
      else {
        if (!this.children.has(g.parent)) this.children.set(g.parent, []);
        this.children.get(g.parent).push(g);
      }
    }
    const byZ = (a, b) => (num(a.attrs.z) - num(b.attrs.z)) || (a.file - b.file) || (a.id - b.id);
    this.tops.sort(byZ);
    for (const list of this.children.values()) list.sort(byZ);
    this.skin = new RegExp(scene.skin);
    const rules = scene.rules || { moments: [], oneOf: [] };
    this.moments = rules.moments.map(m => ({ ...m, re: globber(m.names) }));
    this.oneOf = rules.oneOf.map(o => ({ ...o, rx: new RegExp(o.re) }));
  }

  // whether a gadget shows: not hidden (unless shown on purpose), the chosen skin, its parent shown
  shown(g, opts) {
    for (let x = g; x; x = x.parent !== null && x.parent !== undefined ? this.byId[x.parent] : null) {
      if (opts.override && opts.override[x.id] !== undefined) {
        if (!opts.override[x.id]) return false;
        continue;
      }
      const engine = opts.live && opts.live[x.name.toLowerCase()];
      if (engine && engine.show === false) return false;
      if (engine && engine.show === true) continue;          // the game shows it, whatever the file says
      if ('hidden' in x.attrs && !opts.showHidden) return false;
      const m = this.skin.exec(x.name);
      if (m && !(m[1] === opts.culture && m[2] === (opts.variant === 'min' ? 'Min' : 'Max'))) return false;
      const moment = this.moments.find(mo => mo.re.test(x.name));
      if (moment && !(opts.moments ? opts.moments[moment.id] : moment.on)) return false;
      for (const o of this.oneOf) {
        const hit = o.rx.exec(x.name);
        if (hit && hit[1] !== ((opts.oneOf && opts.oneOf[o.re]) || o.show)) return false;
      }
    }
    return true;
  }

  // [gadget, x, y, w, h] in screen pixels, in the order they are drawn
  layout(width, height, opts) {
    const sx = width / 1024, sy = height / 768;
    const out = [];
    const visit = g => {
      if (!this.shown(g, opts)) return;
      if (g.rect.length === 4) {
        const [x1, y1, x2, y2] = g.rect;
        out.push([g, x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy]);
      }
      for (const c of this.children.get(g.id) || []) visit(c);
    };
    for (const g of this.tops) visit(g);
    return out;
  }

  draw(ctx, width, height, opts) {
    this.height = height;
    ctx.clearRect(0, 0, width, height);
    if (opts.backdrop) { ctx.fillStyle = opts.backdrop; ctx.fillRect(0, 0, width, height); }
    const list = this.layout(width, height, opts);
    const missing = { textures: new Set(), fonts: new Set() };
    for (const [g, x, y, w, h] of list) {
      const a = g.attrs;
      if (a.backgroundcolor !== undefined) {
        const [r, gg, b] = parseColour(a.backgroundcolor, [0, 0, 0]);
        const alpha = a.backgroundalpha !== undefined ? Math.max(0, Math.min(1, Number(a.backgroundalpha) || 0)) : 1;
        ctx.fillStyle = `rgba(${r},${gg},${b},${alpha})`;
        ctx.fillRect(x, y, w, h);
      }
      const engine = opts.live && opts.live[g.name.toLowerCase()];
      const bg = (engine && engine.background) || a.background || (g.states.length ? g.states[opts.state || 0] || g.states[0] : '');
      if (bg) this.texture(ctx, bg, engine && engine.background ? {} : a, x, y, w, h, width, missing);
      if (g.type === 'progressbar') {
        // a progress bar: its background, then its mask over the share done (the game's: to verify)
        const share = engine && engine.fraction !== undefined && engine.fraction !== null ? engine.fraction : 1;
        if (a.progressbarbackground) this.texture(ctx, a.progressbarbackground, {}, x, y, w, h, width, missing);
        if (a.progressbarmask && share > 0) {
          ctx.save(); ctx.beginPath(); ctx.rect(x, y, w * Math.min(1, share), h); ctx.clip();
          this.texture(ctx, a.progressbarmask, {}, x, y, w, h, width, missing);
          ctx.restore();
        }
      }
      if (g.text || (engine && engine.text)) this.text(ctx, g, x, y, w, h, width, opts, missing, engine);
      if (a.foreground) this.texture(ctx, a.foreground, a, x, y, w, h, width, missing);
    }
    return { list, missing };
  }

  texture(ctx, path, a, x, y, w, h, width, missing) {
    const img = this.assets.image(path);
    if (!img) { if (img === null) missing.textures.add(path); return; }
    let [u1, v1, u2, v2] = [0, 0, 1, 1];
    if (a.texturecoords) {
      const t = a.texturecoords.trim().split(/\s+/).map(Number);
      if (t.length >= 4 && t.every(Number.isFinite)) [u1, v1, u2, v2] = t;
    }
    const sxp = u1 * img.width, syp = v1 * img.height, swp = (u2 - u1) * img.width, shp = (v2 - v1) * img.height;
    const tiled = 'tilebackground' in a || 'tilebackgroundhoriz' in a || 'tilebackgroundvert' in a;
    if (tiled && !a.texturecoords) {
      const k = width / 1024;
      const tw = img.width * k, th = img.height * k;
      ctx.save();
      ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
      const horiz = 'tilebackground' in a || 'tilebackgroundhoriz' in a;
      const vert = 'tilebackground' in a || 'tilebackgroundvert' in a;
      for (let ty = y; ty < y + h; ty += vert ? th : h)
        for (let tx = x; tx < x + w; tx += horiz ? tw : w)
          ctx.drawImage(img, tx, ty, horiz ? tw : w, vert ? th : h);
      ctx.restore();
      return;
    }
    if (swp > 0 && shp > 0) ctx.drawImage(img, sxp, syp, swp, shp, x, y, w, h);
  }

  text(ctx, g, x, y, w, h, width, opts, missing, engine) {
    const a = g.attrs;
    const shown = engine && engine.text ? engine.text : displayText(g.text, this.scene.strings, opts.liveTexts || {});
    if (!shown) return;
    const size = a.textfontsize || '12';
    const f = fontAt(this.scene.fonts, a.textfont, size, width, this.height);
    if ((!f || f.Fallback) && a.textfont) missing.fonts.add(`${a.textfont} ${size}`);
    const face = f ? f.TypeFace : 'Arial';
    const family = this.assets.face(face);
    // the cell (ascent + descent) in pixels gives the em; the baseline sits an ascent below the top
    const cell = f ? Number(f.AscentHeight) : Number(size) * (this.height / 768);
    const [asc, desc] = this.assets.metrics(family);
    const px = Math.max(4, cell / (asc + desc));
    const ascent = px * asc;
    ctx.save();
    ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    ctx.font = `${f && f.Bold ? 'bold ' : ''}${f && f.Italic ? 'italic ' : ''}${px.toFixed(2)}px "${family}", Arial, sans-serif`;
    const [r, gg, b] = engine && engine.colour ? engine.colour : parseColour(a.textcolor);
    const colour = `rgb(${r},${gg},${b})`;
    const centre = 'textcenterhoriz' in a, right = 'textjustifyright' in a;
    ctx.textAlign = centre ? 'center' : right ? 'right' : 'left';
    ctx.textBaseline = 'alphabetic';
    const lines = [];
    for (const para of shown.split('\n')) {
      if ('textwrapon' in a && !para.includes('<icon')) lines.push(...wrap(ctx, para.replace(/<[^>]*>/g, ''), w));
      else lines.push(para);
    }
    const iconH = cell, iconW = cell * 0.72;
    const widthOf = parts => parts.reduce((s, r) => s + (r.icon ? iconW : ctx.measureText(r.text).width), 0);
    const lineH = cell;
    const total = lines.length * lineH;
    let top = y;
    if ('textcentervert' in a || 'texttruecentervert' in a) top = y + (h - total) / 2;
    else if ('textbottomfill' in a) top = y + h - total;
    ctx.textAlign = 'left';
    lines.forEach((line, i) => {
      const base = top + i * lineH + ascent;
      const parts = runs(line);
      const lw = widthOf(parts);
      let cx = centre ? x + (w - lw) / 2 : right ? x + w - lw : x;
      for (const part of parts) {
        if (part.icon) {
          const img = this.assets.image(part.icon);
          if (img) ctx.drawImage(img, cx, top + i * lineH + (lineH - iconH) / 2, iconW, iconH);
          else if (img === null) missing.textures.add(part.icon);
          cx += iconW;
          continue;
        }
        if (f && f.BackgroundShadow) {
          const off = Math.max(1, Number(f.BackgroundOffset) || 0);
          ctx.fillStyle = 'rgba(0,0,0,0.85)';
          ctx.fillText(part.text, cx + off, base + off);
        }
        if (f && f.BackgroundOutline) {
          ctx.strokeStyle = 'rgba(0,0,0,0.9)'; ctx.lineWidth = 2; ctx.lineJoin = 'round';
          ctx.strokeText(part.text, cx, base);
        }
        ctx.fillStyle = colour;
        ctx.fillText(part.text, cx, base);
        cx += ctx.measureText(part.text).width;
      }
    });
    ctx.restore();
  }

  // the gadget under a screen point: the last drawn one that holds it
  hit(list, px, py) {
    for (let i = list.length - 1; i >= 0; i--) {
      const [g, x, y, w, h] = list[i];
      if (px >= x && px <= x + w && py >= y && py <= y + h) return g;
    }
    return null;
  }
}

function num(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }

function wrap(ctx, text, width) {
  const out = []; let line = '';
  for (const word of text.split(/\s+/)) {
    const test = line ? line + ' ' + word : word;
    if (ctx.measureText(test).width > width && line) { out.push(line); line = word; } else line = test;
  }
  if (line) out.push(line);
  return out;
}
