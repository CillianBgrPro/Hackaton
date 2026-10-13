(function () {
"use strict";
const DATA = JSON.parse(document.getElementById("sig-data").textContent);
const BASE = JSON.parse(document.getElementById("sig-base").textContent);
const FAM = DATA.families, MOT = DATA.motifs, MODES = DATA.modes, COMS = DATA.communes;
const NF = FAM.length;
const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("fr-FR");
const pct = (a, b) => b ? Math.round(100 * a / b) : 0;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "svg") e.innerHTML = v; // internal markup only, never data
    else if (k === "style") e.setAttribute("style", v);
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) { if (k == null || k === false) continue; e.append(k.nodeType ? k : document.createTextNode(String(k))); }
  return e;
}
const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }

/* ---------- records ---------- */
const MONTH_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const MONTH_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const BANDS = [
  { label: "Nuit", range: "0h–5h", a: 0, b: 5 }, { label: "Matin", range: "5h–9h", a: 5, b: 9 },
  { label: "Journée", range: "9h–16h", a: 9, b: 16 }, { label: "Fin de journée", range: "16h–20h", a: 16, b: 20 },
  { label: "Soirée", range: "20h–24h", a: 20, b: 24 }];
const R = DATA.recs.map((a) => {
  const [y, mo, d, hh, mi] = a[1].match(/\d+/g).map(Number);
  return { id: a[0], y, mo, d, h: hh, min: mi, dt: new Date(y, mo - 1, d, hh, mi), mode: a[2], lieu: a[3], lat: a[4], lng: a[5],
    motifs: a[6], fams: a[7], fam: a[7][0], com: a[8], stop: a[9], stopD: a[10], lines: a[11] ? a[11].split(" ") : [],
    key: a[10] <= 250 ? a[9] : a[3], band: BANDS.findIndex((b) => hh >= b.a && hh < b.b) };
});
const Y0 = R[0].y, M0 = R[0].mo;
R.forEach((r) => { r.m = (r.y - Y0) * 12 + (r.mo - M0); });
const NM = Math.max(...R.map((r) => r.m)) + 1;
const MONTHS = Array.from({ length: NM }, (_, i) => { const k = M0 - 1 + i; return { m: k % 12, y: Y0 + Math.floor(k / 12) }; });
const FIRST = R.reduce((a, r) => r.dt < a.dt ? r : a), LAST = R.reduce((a, r) => r.dt > a.dt ? r : a);
const dateLong = (dt) => dt.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
const dateFull = (dt) => { const t = dt.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); return t.charAt(0).toUpperCase() + t.slice(1); };
const hhmm = (r) => String(r.h).padStart(2, "0") + "h" + String(r.min).padStart(2, "0");
const dmy = (r) => String(r.d).padStart(2, "0") + "/" + String(r.mo).padStart(2, "0") + "/" + r.y;
const monthLabel = (i, long) => long ? MONTH_LONG[MONTHS[i].m] + " " + MONTHS[i].y : MONTH_SHORT[MONTHS[i].m] + " " + MONTHS[i].y;
const LINECOL = Object.fromEntries(BASE.lines.map((l) => [l.id, l.col]));

/* ---------- shapes (internal SVG strings) ---------- */
function shapeSVG(f, size = 18, ring = true) {
  const c = `var(--f${f})`, st = ring ? `stroke:var(--ring);stroke-width:2;stroke-linejoin:round;` : "";
  let inner;
  switch (FAM[f].shape) {
    case "triangle": inner = `<polygon points="9,1.2 17.2,15.8 0.8,15.8" style="fill:${c};${st}"/>`; break;
    case "diamond": inner = `<polygon points="9,0.8 17.2,9 9,17.2 0.8,9" style="fill:${c};${st}"/>`; break;
    case "square": inner = `<rect x="2" y="2" width="14" height="14" rx="2" style="fill:${c};${st}"/>`; break;
    case "circle": inner = `<circle cx="9" cy="9" r="7.4" style="fill:${c};${st}"/>`; break;
    default: inner = (ring ? `<circle cx="9" cy="9" r="7.6" style="fill:var(--ring)"/>` : "") + `<circle cx="9" cy="9" r="5.2" style="fill:var(--ring);stroke:${c};stroke-width:3.2"/>`;
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 18 18" aria-hidden="true" focusable="false">${inner}</svg>`;
}

/* ---------- state & filtering ---------- */
const ALL = (n) => new Set(Array.from({ length: n }, (_, i) => i));
const S = { m0: 0, m1: NM - 1, fams: ALL(NF), modes: ALL(MODES.length), bands: ALL(BANDS.length), com: -1, motif: -1, view: "points", sort: { k: "date", dir: -1 }, tables: {} };
function pass(r, skip) {
  if (skip !== "period" && (r.m < S.m0 || r.m > S.m1)) return false;
  if (skip !== "fam" && !r.fams.some((f) => S.fams.has(f))) return false;
  if (skip !== "mode" && !S.modes.has(r.mode)) return false;
  if (skip !== "band" && !S.bands.has(r.band)) return false;
  if (skip !== "com" && S.com >= 0 && r.com !== S.com) return false;
  if (skip !== "motif" && S.motif >= 0 && !r.motifs.includes(S.motif)) return false;
  return true;
}
function toggleSolo(set, i, n) {
  if (set.size === n) { set.clear(); set.add(i); }
  else if (set.has(i)) { set.delete(i); if (!set.size) for (let k = 0; k < n; k++) set.add(k); }
  else { set.add(i); }
}

/* ---------- filter UI ---------- */
const ld = $("ld"), in0 = $("m0"), in1 = $("m1");
in0.max = in1.max = NM - 1; in1.value = NM - 1;
const stationX = (i) => `calc(8px + (100% - 16px) * ${i / (NM - 1)})`;
MONTHS.forEach((mm, i) => {
  ld.append(h("div", { class: "ld-st", "data-i": i, style: `left:${stationX(i)}` }));
  const showYear = i === 0 || mm.m === 0;
  ld.append(h("div", { class: "ld-lab", style: `left:${stationX(i)}` }, MONTH_SHORT[mm.m].replace(".", ""), showYear ? h("b", null, String(mm.y)) : null));
});
function onRange(e) {
  let a = +in0.value, b = +in1.value;
  if (a > b) { if (e && e.target === in0) b = a; else a = b; }
  S.m0 = a; S.m1 = b; update();
}
in0.addEventListener("input", onRange); in1.addEventListener("input", onRange);
const PRESETS = [{ label: "12 mois", a: 0, b: NM - 1 }];
for (let q = 0; q < NM; q++) {
  const mm = MONTHS[q];
  if (mm.m % 3 === 0 && q + 2 < NM) PRESETS.push({ label: `T${mm.m / 3 + 1} ${mm.y}`, a: q, b: q + 2 });
  else if (q === 0 && mm.m % 3 !== 0) { const end = q + (2 - (mm.m % 3)); PRESETS.push({ label: `T${Math.floor(mm.m / 3) + 1} ${mm.y}`, a: q, b: end }); }
}
PRESETS.forEach((p) => $("presets").append(h("button", { class: "chip", type: "button", "data-a": p.a, "data-b": p.b, "aria-pressed": "false", onclick: () => { S.m0 = p.a; S.m1 = p.b; update(); } }, p.label)));

function chipGroup(id, items, setKey) {
  const g = $(id);
  items.forEach((it, i) => g.append(h("button", { class: "chip", type: "button", "data-i": i, "aria-pressed": "true",
    onclick: () => { toggleSolo(S[setKey], i, items.length); update(); } }, it.icon ? h("span", { svg: it.icon, style: "display:inline-flex" }) : null, it.label, h("span", { class: "n" }))));
}
chipGroup("g-fam", FAM.map((f, i) => ({ label: f.short, icon: shapeSVG(i, 14, false) })), "fams");
chipGroup("g-mode", MODES.map((m) => ({ label: m })), "modes");
chipGroup("g-band", BANDS.map((b) => ({ label: `${b.label} ${b.range}` })), "bands");

const selCom = $("sel-com"), selMot = $("sel-mot");
selCom.addEventListener("change", () => { S.com = +selCom.value; update(); fitFiltered(); });
selMot.append(h("option", { value: "-1" }, "Tous les motifs"));
FAM.forEach((f, fi) => {
  const og = h("optgroup", { label: f.label });
  MOT.forEach((m, mi) => { if (m[1] === fi) og.append(h("option", { value: mi }, m[0])); });
  selMot.append(og);
});
selMot.addEventListener("change", () => { S.motif = +selMot.value; update(); });
function resetAll() { S.m0 = 0; S.m1 = NM - 1; S.fams = ALL(NF); S.modes = ALL(MODES.length); S.bands = ALL(BANDS.length); S.com = -1; S.motif = -1; update(); fitFiltered(true); }
$("reset").addEventListener("click", resetAll);
document.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", resetAll));

/* ---------- tooltip ---------- */
const tt = $("tt");
function showTT(ev, nodes) {
  tt.replaceChildren(...nodes); tt.hidden = false;
  let x, y;
  if (ev.clientX != null && ev.type !== "focus") { x = ev.clientX; y = ev.clientY; }
  else { const b = ev.target.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
  const w = tt.offsetWidth, hgt = tt.offsetHeight;
  let left = x + 14, top = y - hgt - 10;
  if (left + w > innerWidth - 8) left = x - w - 14;
  if (top < 8) top = y + 16;
  tt.style.left = Math.max(8, left) + "px"; tt.style.top = top + "px";
}
const hideTT = () => { tt.hidden = true; };
function ttRows(rows) { return rows.map(([color, label, v]) => h("div", { class: "tt-r" }, h("i", { style: `background:${color}` }), h("span", null, label), h("b", null, fmt(v)))); }

/* ---------- map & basemap ---------- */
function dec(str) {
  let i = 0, lat = 0, lng = 0; const out = [];
  while (i < str.length) {
    let b, sh = 0, res = 0;
    do { b = str.charCodeAt(i++) - 63; res |= (b & 31) << sh; sh += 5; } while (b >= 32);
    lat += (res & 1) ? ~(res >> 1) : (res >> 1);
    sh = 0; res = 0;
    do { b = str.charCodeAt(i++) - 63; res |= (b & 31) << sh; sh += 5; } while (b >= 32);
    lng += (res & 1) ? ~(res >> 1) : (res >> 1);
    out.push([lat / 1e5, lng / 1e5]);
  }
  return out;
}
const map = L.map("map", { minZoom: 10, maxZoom: 19, zoomSnap: 0.5, maxBounds: [[47.62, 1.55], [48.12, 2.32]], maxBoundsViscosity: 0.7, worldCopyJump: false });
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution("Fond : IGN BD TOPO®, API Découpage administratif · Lignes et arrêts : GTFS TAO (transport.data.gouv.fr) · Rendu Leaflet");
[["p-base", 200], ["p-water", 210], ["p-roads", 220], ["p-rail", 230], ["p-bus", 240], ["p-tram", 250], ["p-labels", 450]].forEach(([n, z]) => {
  const p = map.createPane(n); p.style.zIndex = z; if (n !== "p-bus" && n !== "p-tram") p.style.pointerEvents = "none";
});
const poly = (rings, cls, pane) => L.polygon(rings, { pane, className: cls, interactive: false, smoothFactor: 0.6 });
const line = (lines, cls, pane, opts) => L.polyline(lines, Object.assign({ pane, className: cls, interactive: false, lineCap: "round", lineJoin: "round", smoothFactor: 0.6 }, opts || {}));
const outerRing = [[47.3, 1.2], [47.3, 2.7], [48.5, 2.7], [48.5, 1.2]];
poly([outerRing, ...BASE.metro.map((p) => dec(p[0]))], "b-outside", "p-base").addTo(map);
const lyrCommunes = L.layerGroup([line(BASE.communes.flatMap((c) => c.r.map((p) => dec(p[0]))), "b-commune", "p-base", { weight: 1 })]).addTo(map);
line(BASE.metro.map((p) => dec(p[0])), "b-metro", "p-base", { weight: 1.5 }).addTo(map);
poly(BASE.water.map((p) => p.map(dec)), "b-water", "p-water").addTo(map);
const RD = {};
RD.r5 = line(BASE.r5.map(dec), "b-local", "p-roads");
RD.r4 = line(BASE.r4.map(dec), "b-road", "p-roads").addTo(map);
RD.c3 = line(BASE.r3.map(dec), "b-cas", "p-roads").addTo(map);
RD.r3 = line(BASE.r3.map(dec), "b-road", "p-roads").addTo(map);
RD.c1 = line(BASE.r1.map(dec), "b-cas", "p-roads").addTo(map);
RD.r1 = line(BASE.r1.map(dec), "b-road", "p-roads").addTo(map);
RD.rail = line(BASE.rail.map(dec), "b-rail", "p-rail").addTo(map);
const lyrBus = L.layerGroup(), lyrTram = L.layerGroup().addTo(map), tramParts = [], busParts = [];
BASE.lines.forEach((l) => {
  const g = l.g.map(dec), tip = `${l.t === 0 ? "Tram" : "Ligne"} ${l.id} · ${l.name}`;
  if (l.t === 0) {
    const c = line(g, "b-tram-cas", "p-tram"); const t = line(g, "b-tram", "p-tram", { interactive: true });
    t.bindTooltip(tip, { sticky: true }); tramParts.push(c, t); lyrTram.addLayer(c).addLayer(t);
  } else {
    const b = line(g, "b-bus", "p-bus", { interactive: true }); b.bindTooltip(tip, { sticky: true }); busParts.push(b); lyrBus.addLayer(b);
  }
});
const lbl = (latlng, cls, text) => L.marker(latlng, { pane: "p-labels", interactive: false, keyboard: false,
  icon: L.divIcon({ className: "lbl " + cls, html: "", iconSize: [0, 0] }) }).on("add", function () { const el = this.getElement(); if (el) el.replaceChildren(h("span", null, text)); });
const lyrComLabels = L.layerGroup(BASE.communes.map((c) => lbl(c.c, "lbl-com", c.n)));
const tramStops = BASE.stops.filter((st) => st.tram), busStops = BASE.stops.filter((st) => !st.tram);
const lyrTramStops = L.layerGroup(tramStops.flatMap((st) => [L.circleMarker(st.c, { pane: "p-tram", radius: 3.5, weight: 2, className: "b-stop", interactive: false }), lbl(st.c, "lbl-stop tram", st.n)]));
const lyrBusDots = L.layerGroup(busStops.map((st) => L.circleMarker(st.c, { pane: "p-bus", radius: 2.2, weight: 1.2, className: "b-stop", interactive: false })));
const lyrBusLabels = L.layerGroup(busStops.map((st) => lbl(st.c, "lbl-stop", st.n)));
function zoomStyle() {
  const z = map.getZoom();
  const k = z < 11.5 ? 0 : z < 13 ? 1 : z < 14 ? 2 : z < 15 ? 3 : z < 16 ? 4 : 5;
  const W = { r1: [1.4, 2.2, 3.2, 4.6, 6.5, 9], r3: [0.9, 1.4, 2.2, 3.4, 5, 7.5], r4: [0.5, 0.9, 1.5, 2.4, 3.8, 6], r5: [0, 0, 0.8, 1.6, 2.8, 4.6], tram: [2, 2.5, 3, 3.6, 4.2, 5], bus: [1, 1.2, 1.6, 2, 2.6, 3], rail: [0.8, 1, 1.4, 1.8, 2.2, 2.6] };
  RD.r1.setStyle({ weight: W.r1[k] }); RD.c1.setStyle({ weight: W.r1[k] + (k > 1 ? 2.2 : 1.4) });
  RD.r3.setStyle({ weight: W.r3[k] }); RD.c3.setStyle({ weight: W.r3[k] + (k > 1 ? 1.8 : 1.1) });
  RD.r4.setStyle({ weight: W.r4[k] }); RD.r5.setStyle({ weight: W.r5[k] }); RD.rail.setStyle({ weight: W.rail[k] });
  tramParts.forEach((p, i) => p.setStyle({ weight: i % 2 === 0 ? W.tram[k] + 2.5 : W.tram[k] }));
  busParts.forEach((p) => p.setStyle({ weight: W.bus[k] }));
  const vis = (lyr, on) => { if (on && !map.hasLayer(lyr)) map.addLayer(lyr); else if (!on && map.hasLayer(lyr)) map.removeLayer(lyr); };
  vis(RD.r5, z >= 13);
  vis(lyrComLabels, z >= 11.5 && z <= 13.5 && $("t-com").checked);
  vis(lyrTramStops, z >= 14 && $("t-tram").checked);
  vis(lyrBusDots, z >= 15.5);
  vis(lyrBusLabels, z >= 16.5);
}
map.on("zoomend", zoomStyle);
$("t-tram").addEventListener("change", (e) => { e.target.checked ? lyrTram.addTo(map) : map.removeLayer(lyrTram); zoomStyle(); });
$("t-bus").addEventListener("change", (e) => { e.target.checked ? lyrBus.addTo(map) : map.removeLayer(lyrBus); });
$("t-com").addEventListener("change", (e) => { e.target.checked ? lyrCommunes.addTo(map) : map.removeLayer(lyrCommunes); zoomStyle(); });

/* ---------- signal markers ---------- */
const ICONS = FAM.map((_, f) => L.divIcon({ className: "sig-ic", html: shapeSVG(f, 18), iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -10], tooltipAnchor: [0, -10] }));
function badge(id) {
  const col = LINECOL[id] || "#888888";
  const n = parseInt(col.slice(1), 16), lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return h("span", { class: "badge", style: `background:${col};color:${lum > 0.6 ? "#111" : "#fff"}` }, id);
}
function popup(r) {
  return h("div", { class: "pop" },
    h("div", { class: "pop-head" }, h("span", { svg: shapeSVG(r.fam, 14, false), style: "display:inline-flex" }), FAM[r.fam].label),
    h("div", { class: "pop-date" }, `${dateFull(r.dt)} · ${hhmm(r)}`),
    h("ul", { class: "pop-motifs" }, r.motifs.map((m) => h("li", null, MOT[m][0]))),
    h("dl", null,
      h("dt", null, "Mode"), h("dd", null, MODES[r.mode]),
      h("dt", null, "Lieu"), h("dd", null, r.lieu),
      h("dt", null, "Commune"), h("dd", null, COMS[r.com]),
      h("dt", null, "Arrêt proche"), h("dd", null, `${r.stop} · ${fmt(r.stopD)} m`),
      r.lines.length ? [h("dt", null, "Lignes"), h("dd", null, h("span", { class: "badges" }, r.lines.map(badge)))] : null),
    h("div", { class: "pop-id" }, `Signalement n° ${r.id}`));
}
R.forEach((r) => {
  r.marker = L.marker([r.lat, r.lng], { icon: ICONS[r.fam], fam: r.fam, keyboard: true, riseOnHover: true, alt: `${FAM[r.fam].short}, ${dmy(r)}` });
  r.marker.bindPopup(() => popup(r), { maxWidth: 330, autoPanPadding: [30, 30] });
  r.marker.bindTooltip(`${dmy(r)} · ${MOT[r.motifs[0]][0]}`, { direction: "top" });
});
function clusterIcon(cl) {
  const ms = cl.getAllChildMarkers(), n = ms.length, cnt = new Array(NF).fill(0);
  ms.forEach((m) => cnt[m.options.fam]++);
  const sz = Math.round(30 + Math.min(22, Math.log2(n) * 4.6)), c = sz / 2, rr = c - 5, C = 2 * Math.PI * rr;
  const parts = cnt.filter(Boolean).length, gap = parts > 1 ? 2 : 0;
  let off = 0, segs = "";
  cnt.forEach((v, f) => {
    if (!v) return;
    const len = C * v / n, dash = Math.max(0.8, len - gap);
    segs += `<circle cx="${c}" cy="${c}" r="${rr}" fill="none" style="stroke:var(--f${f})" stroke-width="6" stroke-dasharray="${dash.toFixed(2)} ${(C - dash).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" transform="rotate(-90 ${c} ${c})"/>`;
    off += len;
  });
  return L.divIcon({ className: "sig-cl", iconSize: [sz, sz],
    html: `<svg width="${sz}" height="${sz}" viewBox="0 0 ${sz} ${sz}" aria-hidden="true"><circle cx="${c}" cy="${c}" r="${c - 0.5}" style="fill:var(--surface)"/>${segs}<text x="${c}" y="${c}" dy="0.36em" text-anchor="middle" style="fill:var(--ink);font:800 ${n >= 100 ? 11 : 12}px var(--font-ui)">${n}</text></svg>` });
}
const cluster = L.markerClusterGroup({ maxClusterRadius: 44, showCoverageOnHover: false, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 18, chunkedLoading: true, iconCreateFunction: clusterIcon, spiderLegPolylineOptions: { weight: 1.5, color: "#7d949b", opacity: 0.8 } });
const isDark = () => { const t = document.documentElement.getAttribute("data-theme"); return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; };
const HEAT = {
  light: { 0.2: "#fde6cf", 0.4: "#f9b071", 0.6: "#ec6a35", 0.8: "#bf2a1c", 1: "#6e0b14" },
  dark: { 0.2: "#4a1d15", 0.4: "#9c3320", 0.6: "#e0622e", 0.8: "#ffaf66", 1: "#fff2c6" } };
const heatGrad = () => HEAT[isDark() ? "dark" : "light"];
const heat = L.heatLayer([], { radius: 24, blur: 20, maxZoom: 15, minOpacity: 0.28, max: 1, gradient: heatGrad() });
function applyView() {
  const showPts = S.view !== "heat", showHeat = S.view !== "points";
  if (showPts && !map.hasLayer(cluster)) map.addLayer(cluster); if (!showPts && map.hasLayer(cluster)) map.removeLayer(cluster);
  if (showHeat && !map.hasLayer(heat)) map.addLayer(heat); if (!showHeat && map.hasLayer(heat)) map.removeLayer(heat);
  document.querySelectorAll(".seg [data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === S.view)));
  renderLegend();
}
document.querySelectorAll(".seg [data-view]").forEach((b) => b.addEventListener("click", () => { S.view = b.dataset.view; applyView(); }));
function onTheme() { heat.setOptions({ gradient: heatGrad() }); renderLegend(); }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", onTheme);
new MutationObserver(onTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

let F = R.slice();
function coreBounds(pts) {
  if (pts.length < 20) return L.latLngBounds(pts.map((r) => [r.lat, r.lng])).pad(0.12);
  const q = (arr, t) => arr[Math.min(arr.length - 1, Math.max(0, Math.round(t * (arr.length - 1))))];
  const la = pts.map((r) => r.lat).sort((a, b) => a - b), lo = pts.map((r) => r.lng).sort((a, b) => a - b);
  return L.latLngBounds([q(la, 0.03), q(lo, 0.03)], [q(la, 0.97), q(lo, 0.97)]).pad(0.06);
}
function fitFiltered(all) {
  const pts = all ? R : F;
  if (!pts.length) return;
  map.fitBounds(coreBounds(pts), { maxZoom: 15, animate: !reduceMotion });
}
$("recenter").addEventListener("click", () => fitFiltered(false));
function scrollToMap() { $("map").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" }); }
function focusRecord(r) {
  if (S.view === "heat") { S.view = "both"; applyView(); }
  scrollToMap();
  cluster.zoomToShowLayer(r.marker, () => r.marker.openPopup());
}

function renderLegend() {
  const lg = $("legend"); const kids = [];
  if (S.view !== "heat") {
    kids.push(h("div", { class: "lg-title" }, "Famille principale"));
    FAM.forEach((f, i) => kids.push(h("div", { class: "lg-row" }, h("span", { svg: shapeSVG(i, 14), style: "display:inline-flex" }), f.short, h("span", { class: "n", "data-lg": i }))));
  }
  if (S.view !== "points") {
    const g = heatGrad(), stops = Object.entries(g).map(([k, v]) => `${v} ${k * 100}%`).join(", ");
    if (kids.length) kids.push(h("hr"));
    kids.push(h("div", { class: "lg-title" }, "Densité de signalements"));
    kids.push(h("div", { class: "heat-bar", style: `background:linear-gradient(90deg, transparent 0%, ${stops})` }));
    kids.push(h("div", { class: "heat-scale" }, h("span", null, "faible"), h("span", null, "forte")));
  }
  lg.replaceChildren(...kids);
  updateLegendCounts();
}
function updateLegendCounts() {
  const c = new Array(NF).fill(0); F.forEach((r) => c[r.fam]++);
  document.querySelectorAll("[data-lg]").forEach((e) => { e.textContent = fmt(c[+e.dataset.lg]); });
}

/* ---------- KPIs ---------- */
function groupStops(list) {
  const g = new Map();
  list.forEach((r) => { let o = g.get(r.key); if (!o) g.set(r.key, o = { key: r.key, isStop: r.stopD <= 250, n: 0, fam: new Array(NF).fill(0), lat: 0, lng: 0, recs: [] }); o.n++; o.fam[r.fam]++; o.lat += r.lat; o.lng += r.lng; o.recs.push(r); });
  return [...g.values()].map((o) => Object.assign(o, { lat: o.lat / o.n, lng: o.lng / o.n })).sort((a, b) => b.n - a.n || a.key.localeCompare(b.key, "fr"));
}
function renderKPIs() {
  const n = F.length, tot = R.length;
  const sur = F.filter((r) => r.fams.includes(0)).length;
  const modeC = MODES.map((_, i) => F.filter((r) => r.mode === i).length);
  const bandC = BANDS.map((_, i) => F.filter((r) => r.band === i).length);
  const bi = bandC.indexOf(Math.max(...bandC));
  const top = groupStops(F)[0];
  const kpi = (cls, label, value, sub) => h("div", { class: "kpi " + (cls || "") }, h("span", { class: "kpi-label" }, label), h("span", { class: "kpi-value" }, value), h("span", { class: "kpi-sub" }, sub));
  const others = modeC.map((c, i) => [c, i]).slice(1).filter(([c]) => c).map(([c, i]) => `${pct(c, n)} % ${MODES[i].toLowerCase() === "tram" ? "en tram" : MODES[i]}`);
  $("kpis").replaceChildren(
    kpi("hero", "Signalements", fmt(n), n === tot ? `retenus après nettoyage, ${MONTHS.length} mois` : `sur ${fmt(tot)}, soit ${pct(n, tot)} % de l'ensemble`),
    kpi("", "Sûreté et atteintes aux personnes", n ? h("span", { class: "sw" }, h("span", { svg: shapeSVG(0, 18, false), style: "display:inline-flex" }), fmt(sur)) : "–", n ? `${pct(sur, n)} % des signalements` : "aucun signalement"),
    kpi("", "Part du bus", n ? `${pct(modeC[0], n)} %` : "–", n ? (others.join(", ") || "aucun autre mode") : ""),
    kpi("", "Créneau le plus chargé", n ? BANDS[bi].range : "–", n ? `${BANDS[bi].label.toLowerCase()}, ${pct(bandC[bi], n)} % des signalements` : ""),
    kpi("", top && top.isStop ? "Arrêt le plus concerné" : "Lieu le plus concerné", top ? top.key : "–", top ? `${fmt(top.n)} signalement${top.n > 1 ? "s" : ""}${top.isStop ? " à moins de 250 m" : ""}` : ""));
}

/* ---------- motif panel & bar lists ---------- */
function segTrack(counts, scale, total) {
  return h("div", { class: "track", "aria-hidden": "true" }, counts.map((v, f) => v ? h("span", { class: "seg-b", style: `width:calc(${(100 * v / scale).toFixed(3)}% - 2px);background:var(--f${f})` }) : null).filter(Boolean));
}
function renderMotifs() {
  const n = F.length, box = $("motifs");
  const famC = FAM.map((_, f) => F.filter((r) => r.fams.includes(f)).length);
  const motC = MOT.map((_, m) => F.filter((r) => r.motifs.includes(m)).length);
  const scale = Math.max(1, ...famC);
  const kids = [];
  FAM.forEach((f, fi) => {
    const fc = famC[fi]; if (!fc && !S.fams.has(fi)) return;
    kids.push(h("div", { class: "brow fam" },
      h("span", { class: "bl" }, h("span", { svg: shapeSVG(fi, 14, false), style: "display:inline-flex" }), f.label),
      h("span", { class: "bv" }, fmt(fc), h("small", null, `${pct(fc, n)} %`)),
      h("div", { class: "track" }, fc ? h("span", { class: "seg-b", style: `width:${(100 * fc / scale).toFixed(3)}%;background:var(--f${fi})` }) : null)));
    MOT.map((m, mi) => [m, mi]).filter(([m, mi]) => m[1] === fi && (motC[mi] || S.motif === mi)).sort((a, b) => motC[b[1]] - motC[a[1]]).forEach(([m, mi]) => {
      kids.push(h("button", { class: "brow mot", type: "button", "aria-pressed": String(S.motif === mi), title: S.motif === mi ? "Retirer ce filtre" : "Filtrer sur ce motif",
        onclick: () => { S.motif = S.motif === mi ? -1 : mi; update(); } },
        h("span", { class: "bl" }, m[0]), h("span", { class: "bv" }, fmt(motC[mi])),
        h("div", { class: "track" }, motC[mi] ? h("span", { class: "seg-b", style: `width:${(100 * motC[mi] / scale).toFixed(3)}%;background:var(--f${fi});opacity:.6` }) : null)));
    });
  });
  if (!kids.length) kids.push(h("p", { class: "panel-note" }, "Aucun signalement pour cette sélection."));
  box.replaceChildren(...kids);
}
function barList(el, rows, opts) {
  const scale = Math.max(1, ...rows.map((r) => r.n));
  el.replaceChildren(...(rows.length ? rows.map((r) => {
    const content = [h("span", { class: "bl", title: r.label }, r.label), h("span", { class: "bv" }, fmt(r.n), opts.total ? h("small", null, `${pct(r.n, opts.total)} %`) : null), segTrack(r.fam, scale)];
    return r.onclick ? h("button", { class: "brow", type: "button", "aria-pressed": r.pressed == null ? null : String(r.pressed), onclick: r.onclick, title: r.title }, ...content) : h("div", { class: "brow" }, ...content);
  }) : [h("p", { class: "panel-note" }, "Aucun signalement pour cette sélection.")]));
}
function renderLists() {
  const n = F.length;
  barList($("c-stops"), groupStops(F).slice(0, 10).map((g) => ({ label: g.isStop ? g.key : `${g.key} (hors arrêt)`, n: g.n, fam: g.fam, title: "Zoomer sur la carte",
    onclick: () => { scrollToMap(); map.flyTo([g.lat, g.lng], 17, { animate: !reduceMotion }); } })), {});
  const comRows = COMS.map((c, i) => { const rs = F.filter((r) => r.com === i); const fam = new Array(NF).fill(0); rs.forEach((r) => fam[r.fam]++); return { label: c, n: rs.length, fam, i }; })
    .filter((r) => r.n || r.i === S.com).sort((a, b) => b.n - a.n);
  barList($("c-com"), comRows.map((r) => ({ ...r, pressed: S.com === r.i, title: S.com === r.i ? "Retirer ce filtre" : "Filtrer sur cette commune",
    onclick: () => { S.com = S.com === r.i ? -1 : r.i; update(); fitFiltered(S.com < 0); } })), { total: n });
  const modeRows = MODES.map((m, i) => { const rs = F.filter((r) => r.mode === i); const fam = new Array(NF).fill(0); rs.forEach((r) => fam[r.fam]++); return { label: m, n: rs.length, fam, i }; }).filter((r) => r.n);
  barList($("c-mode"), modeRows, { total: n });
}

/* ---------- column charts (SVG) ---------- */
function niceScale(v, n = 4) { const raw = Math.max(v, 1) / n, p = Math.pow(10, Math.floor(Math.log10(raw))); const step = Math.max(1, [1, 2, 5, 10].map((m) => m * p).find((x) => x >= raw)); return { max: step * Math.ceil(Math.max(v, 1) / step), step }; }
function roundTop(x, y, w, hgt, r) { r = Math.min(r, hgt, w / 2); return `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`; }
function columnChart(el, cfg) {
  const W = Math.max(280, el.clientWidth), H = cfg.height, mt = cfg.caps ? 20 : 12, mb = cfg.mb || 34, ml = 30, mr = 6;
  const pw = W - ml - mr, ph = H - mt - mb, n = cfg.n;
  const totals = cfg.stacks.map((st) => st.reduce((a, b) => a + b, 0));
  const sc = niceScale(Math.max(1, ...totals)), ymax = sc.max, ky = ph / ymax;
  const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.aria });
  const step = sc.step, ticks = Math.round(ymax / step);
  for (let t = 0; t <= ticks; t++) {
    const v = t * step, y = mt + ph - v * ky;
    svg.append(s("line", { x1: ml, x2: W - mr, y1: y, y2: y, style: `stroke:${t === 0 ? "var(--line-strong)" : "var(--line)"}`, "stroke-width": 1, "shape-rendering": "crispEdges" }));
    const tx = s("text", { x: ml - 6, y: y, dy: "0.32em", "text-anchor": "end", style: "fill:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums" }); tx.textContent = fmt(Math.round(v * 10) / 10); svg.append(tx);
  }
  (cfg.bg || []).forEach((b) => svg.append(b(ml, mt, pw, ph, n)));
  const band = pw / n, bw = Math.min(cfg.maxBar || 24, band * 0.64);
  for (let i = 0; i < n; i++) {
    const x = ml + band * i + (band - bw) / 2; let y = mt + ph;
    const st = cfg.stacks[i], active = cfg.active ? cfg.active[i] : true;
    const nz = st.map((v, k) => [v, k]).filter(([v]) => v > 0);
    const g = s("g", { style: active ? "" : "opacity:.28" });
    nz.forEach(([v, k], j) => {
      const isTop = j === nz.length - 1, hh = v * ky, gapPx = isTop ? 0 : 2;
      const hgt = Math.max(0.5, hh - gapPx), yTop = y - hh;
      const fill = cfg.colors ? cfg.colors(k, i) : "var(--bar)";
      g.append(isTop ? s("path", { d: roundTop(x, yTop, bw, hgt, 4), style: `fill:${fill}` }) : s("rect", { x, y: yTop + gapPx, width: bw, height: hgt, style: `fill:${fill}` }));
      y -= hh;
    });
    svg.append(g);
    if (cfg.caps && totals[i]) { const t = s("text", { x: x + bw / 2, y: mt + ph - totals[i] * ky - 5, "text-anchor": "middle", style: `fill:var(--ink-2);font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;${active ? "" : "opacity:.4"}` }); t.textContent = totals[i]; svg.append(t); }
    const lab = cfg.xlabel(i);
    if (lab) lab.forEach((txt, li) => { if (!txt) return; const t = s("text", { x: x + bw / 2, y: mt + ph + 15 + li * 12, "text-anchor": "middle", style: `fill:var(--${li ? "muted" : "ink-2"});font-size:${li ? 10 : 11}px;${li ? "font-weight:700" : ""}` }); t.textContent = txt; svg.append(t); });
    const hit = s("rect", { class: "hit", x: ml + band * i, y: mt, width: band, height: ph + 4, tabindex: 0, role: "button", "aria-label": cfg.hitLabel(i) });
    const show = (ev) => showTT(ev, cfg.tip(i)); hit.addEventListener("pointermove", show); hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", hideTT); hit.addEventListener("blur", hideTT);
    if (cfg.onClick) { hit.addEventListener("click", () => cfg.onClick(i)); hit.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); cfg.onClick(i); } }); }
    svg.append(hit);
  }
  (cfg.fg || []).forEach((b) => svg.append(b(ml, mt, pw, ph, n)));
  el.replaceChildren(svg);
}
function miniTable(el, head, rows) {
  el.replaceChildren(h("div", { class: "scroll-x" }, h("table", { class: "mini-table" }, h("thead", null, h("tr", null, head.map((x) => h("th", { scope: "col" }, x)))),
    h("tbody", null, rows.map((r) => h("tr", null, r.map((c, i) => i ? h("td", null, c) : h("th", { scope: "row", style: "text-align:left;font-weight:600;color:var(--ink)" }, c))))))));
}
FAM.forEach((f, i) => $("month-legend").append(h("span", null, h("i", { style: `background:var(--f${i})` }), f.short)));
$("month-note").textContent = `Mois incomplets (*) : la collecte commence le ${dateLong(FIRST.dt)} et s'arrête le ${dateLong(LAST.dt)}.`;
function renderMonth() {
  const base = R.filter((r) => pass(r, "period"));
  const stacks = MONTHS.map(() => new Array(NF).fill(0));
  base.forEach((r) => stacks[r.m][r.fam]++);
  const el = $("c-month");
  const partial = (i) => (i === 0 && FIRST.d > 1) || (i === NM - 1 && LAST.d < 28);
  if (S.tables.month) {
    miniTable(el, ["Mois", ...FAM.map((f) => f.short), "Total"], MONTHS.map((_, i) => [monthLabel(i, true) + (partial(i) ? " *" : ""), ...stacks[i].map(fmt), fmt(stacks[i].reduce((a, b) => a + b, 0))]));
    return;
  }
  columnChart(el, { n: NM, height: 250, stacks, caps: true, mb: 36, aria: "Nombre de signalements par mois, par famille principale",
    colors: (k) => `var(--f${k})`, active: MONTHS.map((_, i) => i >= S.m0 && i <= S.m1),
    xlabel: (i) => [MONTH_SHORT[MONTHS[i].m].replace(".", "") + (partial(i) ? "*" : ""), (i === 0 || MONTHS[i].m === 0) ? String(MONTHS[i].y) : ""],
    hitLabel: (i) => `${monthLabel(i, true)} : ${stacks[i].reduce((a, b) => a + b, 0)} signalements`,
    tip: (i) => { const t = stacks[i].reduce((a, b) => a + b, 0); return [h("div", { class: "tt-h" }, monthLabel(i, true) + (partial(i) ? " (mois incomplet)" : "")), h("div", { class: "tt-v" }, `${fmt(t)} signalement${t > 1 ? "s" : ""}`), ...ttRows(FAM.map((f, k) => [`var(--f${k})`, f.short, stacks[i][k]]).filter((x) => x[2]).reverse())]; },
    onClick: (i) => { if (S.m0 === i && S.m1 === i) { S.m0 = 0; S.m1 = NM - 1; } else { S.m0 = i; S.m1 = i; } update(); } });
}
function renderHour() {
  const base = R.filter((r) => pass(r, "band"));
  const c = new Array(24).fill(0); base.forEach((r) => c[r.h]++);
  const el = $("c-hour");
  if (S.tables.hour) { miniTable(el, ["Heure", "Signalements", "Créneau"], c.map((v, i) => [`${i}h–${i + 1}h`, fmt(v), BANDS[BANDS.findIndex((b) => i >= b.a && i < b.b)].label])); return; }
  const bandOf = (i) => BANDS.findIndex((b) => i >= b.a && i < b.b);
  columnChart(el, { n: 24, height: 250, stacks: c.map((v) => [v]), caps: false, mb: 34, maxBar: 16, aria: "Nombre de signalements par heure de la journée",
    active: c.map((_, i) => S.bands.has(bandOf(i))),
    xlabel: (i) => BANDS.some((b) => b.a === i) ? [`${i}h`, ""] : null,
    hitLabel: (i) => `${i}h à ${i + 1}h : ${c[i]} signalements`,
    tip: (i) => [h("div", { class: "tt-h" }, `De ${i}h à ${i + 1}h · ${BANDS[bandOf(i)].label.toLowerCase()}`), h("div", { class: "tt-v" }, `${fmt(c[i])} signalement${c[i] > 1 ? "s" : ""}`)],
    fg: [(ml, mt, pw, ph) => { const g = s("g", {}); const band = pw / 24;
      BANDS.forEach((b, bi) => {
        if (b.a > 0) g.append(s("line", { x1: ml + band * b.a, x2: ml + band * b.a, y1: mt - 4, y2: mt + ph, style: "stroke:var(--line-strong)", "stroke-width": 1, "shape-rendering": "crispEdges" }));
        const wpx = band * (b.b - b.a), label = b.label;
        if (wpx > label.length * 6.2 + 6) { const t = s("text", { x: ml + band * (b.a + b.b) / 2, y: mt - 2, "text-anchor": "middle", style: "fill:var(--muted);font-size:10.5px;font-weight:600" }); t.textContent = label; g.append(t); }
      });
      const tEnd = s("text", { x: ml + pw - 2, y: mt + ph + 15, "text-anchor": "end", style: "fill:var(--ink-2);font-size:11px" }); tEnd.textContent = "24h"; g.append(tEnd);
      return g; }] });
}
document.querySelectorAll("[data-table]").forEach((b) => b.addEventListener("click", () => {
  const k = b.dataset.table; S.tables[k] = !S.tables[k];
  b.setAttribute("aria-pressed", String(S.tables[k])); b.textContent = S.tables[k] ? "Voir le graphique" : "Voir le tableau";
  k === "month" ? renderMonth() : renderHour();
}));

/* ---------- record table ---------- */
const COLS = [
  { k: "date", label: "Date", v: (r) => r.dt.getTime(), cell: (r) => h("td", { class: "num" }, dmy(r)) },
  { k: "heure", label: "Heure", v: (r) => r.h * 60 + r.min, cell: (r) => h("td", { class: "num" }, hhmm(r)) },
  { k: "mode", label: "Mode", v: (r) => MODES[r.mode], cell: (r) => h("td", null, MODES[r.mode]) },
  { k: "fam", label: "Famille", v: (r) => r.fam, cell: (r) => h("td", null, h("span", { class: "famc" }, h("span", { svg: shapeSVG(r.fam, 13, false), style: "display:inline-flex" }), FAM[r.fam].short)) },
  { k: "motif", label: "Motif", v: (r) => MOT[r.motifs[0]][0], cell: (r) => h("td", null, r.motifs.map((m) => MOT[m][0]).join(" ; ")) },
  { k: "lieu", label: "Lieu", v: (r) => r.lieu, cell: (r) => h("td", null, r.lieu, r.stopD <= 250 && r.stop !== r.lieu ? h("div", { class: "muted", style: "font-size:12px" }, `Arrêt ${r.stop}`) : null) },
  { k: "com", label: "Commune", v: (r) => COMS[r.com], cell: (r) => h("td", null, COMS[r.com]) }];
function renderHead() {
  $("thead").replaceChildren(...COLS.map((c) => h("th", { scope: "col", "aria-sort": S.sort.k === c.k ? (S.sort.dir > 0 ? "ascending" : "descending") : null },
    h("button", { type: "button", onclick: () => { S.sort = { k: c.k, dir: S.sort.k === c.k ? -S.sort.dir : (c.k === "date" ? -1 : 1) }; renderHead(); renderTable(); } }, c.label, S.sort.k === c.k ? (S.sort.dir > 0 ? " ↑" : " ↓") : ""))));
}
function renderTable() {
  const col = COLS.find((c) => c.k === S.sort.k);
  const rows = F.slice().sort((a, b) => { const x = col.v(a), y = col.v(b); const c = typeof x === "string" ? x.localeCompare(y, "fr") : x - y; return c * S.sort.dir || (b.dt - a.dt); });
  $("tbody").replaceChildren(...rows.map((r) => {
    const tr = h("tr", { tabindex: 0, title: "Voir sur la carte" }, COLS.map((c) => c.cell(r)));
    tr.addEventListener("click", () => focusRecord(r));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") focusRecord(r); });
    return tr;
  }));
  $("list-note").textContent = `${fmt(F.length)} signalement${F.length > 1 ? "s" : ""} selon les filtres. Cliquez sur une ligne pour la situer sur la carte, ou sur un en-tête pour trier.`;
}

/* ---------- method ---------- */
function renderMethod() {
  const ex = DATA.excluded;
  const byReason = {}; ex.forEach((e) => { const k = e.raison.startsWith("Doublon") ? "Doublons exacts" : e.raison; byReason[k] = (byReason[k] || 0) + 1; });
  const total = R.length + ex.length;
  $("method").replaceChildren(
    h("div", null,
      h("h3", null, "Données"),
      h("p", null, `L'export contient ${fmt(total)} signalements, du ${dateLong(FIRST.dt)} au ${dateLong(LAST.dt)}. Chaque signalement indique une date et une heure, un mode, un lieu, des coordonnées GPS et un ou plusieurs motifs.`),
      h("h3", null, "Nettoyage"),
      h("ul", null, Object.entries(byReason).map(([k, v]) => h("li", null, `${k} : ${v} retiré${v > 1 ? "s" : ""}`)), h("li", null, `${fmt(R.length)} signalements conservés.`)),
      h("p", null, "Lignes retirées : ", ex.map((e) => `ligne ${e.ligne} (${e.raison.toLowerCase()}, ${e.lieu})`).join(" ; "), "."),
      h("p", null, "Motifs harmonisés : fautes de frappe corrigées (« Dégration », « Situtation »), majuscules et accents unifiés. Un signalement à plusieurs motifs compte dans chacun d'eux. Sa famille principale, qui donne la couleur et le symbole sur la carte, suit l'ordre de priorité : sûreté, incivilités, conducteur, réclamations, autre.")),
    h("div", null,
      h("h3", null, "Familles de motifs"),
      h("ul", null, FAM.map((f, fi) => h("li", null, h("b", null, f.label), " : ", MOT.filter((m) => m[1] === fi).map((m) => m[0]).join(", ")))),
      h("h3", null, "Rattachements géographiques"),
      h("p", null, "La commune est déduite des coordonnées et des contours communaux officiels. Un signalement se situe à Gidy, commune desservie par la ligne 53 mais hors Métropole. L'arrêt le plus proche est calculé à vol d'oiseau à partir des arrêts du GTFS TAO, et les arrêts de même nom (quais) sont regroupés."),
      h("h3", null, "Sources du fond de carte"),
      h("p", null, "Routes, cours d'eau et voies ferrées : IGN BD TOPO®. Contours communaux : API Découpage administratif (geo.api.gouv.fr). Lignes, arrêts et couleurs de lignes : GTFS du réseau TAO publié sur transport.data.gouv.fr. Les mêmes données sont fournies en GeoJSON, KML et CSV pour un usage SIG.")));
}

/* ---------- header copy ---------- */
$("lede").textContent = `${fmt(R.length)} signalements géolocalisés entre le ${dateLong(FIRST.dt)} et le ${dateLong(LAST.dt)}, classés par famille de motifs, mode de transport et moment de la journée.`;
$("meta-clean").textContent = `${fmt(DATA.excluded.length)} lignes écartées (tests, doublons, coordonnées hors réseau)`;

/* ---------- update ---------- */
function syncControls() {
  in0.value = S.m0; in1.value = S.m1;
  const sel = $("ld-sel"); sel.style.left = stationX(S.m0); sel.style.width = `calc((100% - 16px) * ${(S.m1 - S.m0) / (NM - 1)})`;
  ld.querySelectorAll(".ld-st").forEach((e) => e.classList.toggle("on", +e.dataset.i >= S.m0 && +e.dataset.i <= S.m1));
  $("period-out").textContent = S.m0 === S.m1 ? monthLabel(S.m0, true) : `${monthLabel(S.m0)} → ${monthLabel(S.m1)}`;
  $("presets").querySelectorAll(".chip").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.a === S.m0 && +b.dataset.b === S.m1)));
  const cnt = (skip, fn, len) => { const c = new Array(len).fill(0); R.forEach((r) => { if (pass(r, skip)) fn(r, c); }); return c; };
  const cf = cnt("fam", (r, c) => r.fams.forEach((f) => c[f]++), NF), cm = cnt("mode", (r, c) => c[r.mode]++, MODES.length), cb = cnt("band", (r, c) => c[r.band]++, BANDS.length);
  [["g-fam", "fams", cf], ["g-mode", "modes", cm], ["g-band", "bands", cb]].forEach(([id, key, c]) => $(id).querySelectorAll(".chip").forEach((b) => { const i = +b.dataset.i; b.setAttribute("aria-pressed", String(S[key].has(i))); b.querySelector(".n").textContent = fmt(c[i]); }));
  const cc = cnt("com", (r, c) => c[r.com]++, COMS.length);
  selCom.replaceChildren(h("option", { value: "-1" }, "Toutes les communes"), ...COMS.map((c, i) => h("option", { value: i }, `${c} (${cc[i]})`)));
  selCom.value = S.com; selMot.value = S.motif;
  $("f-count").replaceChildren(h("b", null, fmt(F.length)), ` / ${fmt(R.length)} signalements affichés`);
}
function update() {
  F = R.filter((r) => pass(r));
  syncControls();
  cluster.clearLayers(); cluster.addLayers(F.map((r) => r.marker));
  heat.setLatLngs(F.map((r) => [r.lat, r.lng, 0.5]));
  $("map-empty").hidden = F.length > 0;
  updateLegendCounts(); renderKPIs(); renderMotifs(); renderLists(); renderMonth(); renderHour(); renderTable();
}

renderHead(); renderMethod();
map.fitBounds(coreBounds(R));
requestAnimationFrame(() => { map.invalidateSize(); map.fitBounds(coreBounds(R), { animate: false }); });
zoomStyle(); applyView(); update();
let rz = 0;
new ResizeObserver(() => { cancelAnimationFrame(rz); rz = requestAnimationFrame(() => { renderMonth(); renderHour(); map.invalidateSize(); }); }).observe(document.querySelector(".charts"));
})();
