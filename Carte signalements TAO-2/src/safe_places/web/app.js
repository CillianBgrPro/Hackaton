(function () {
"use strict";
const D = JSON.parse(document.getElementById("d").textContent);
const BASE = JSON.parse(document.getElementById("b").textContent);
const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("fr-FR");
const pct = (a, b) => b ? Math.round(100 * a / b) : 0;
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) { const v = attrs[k]; if (v == null || v === false) continue;
    if (k === "class") e.className = v; else if (k === "style") e.setAttribute("style", v); else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v); }
  for (const k of kids.flat()) { if (k == null || k === false) continue; e.append(k.nodeType ? k : document.createTextNode(String(k))); }
  return e;
}
const CLS = [
  { k: "nuit", label: "Après 23 h 30 ou la nuit", short: "Nuit", v: "--c-nuit" },
  { k: "tard", label: "Jusqu'à 21 h – 23 h 30", short: "Tard", v: "--c-tard" },
  { k: "jour", label: "Journée (ferme avant 21 h)", short: "Journée", v: "--c-jour" },
  { k: "ferme", label: "Certains jours seulement", short: "Certains jours", v: "--c-partiel" },
  { k: "nr", label: "Horaires non renseignés", short: "Non renseignés", v: "--c-nr" }];
const CATS = [["boulangerie", "Boulangerie"], ["pharmacie", "Pharmacie"], ["tabac", "Tabac, presse"], ["superette", "Supérette, supermarché"], ["bar", "Bar, café"], ["restaurant", "Restaurant, restauration rapide"], ["hotel", "Hôtel"], ["station", "Station-service"], ["cinema", "Cinéma"], ["public", "Lieu public"]];
const CATN = Object.fromEntries(CATS);
const cssv = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const P = D.pois, STOPS = D.stops;
const S = { cls: new Set(CLS.map(c => c.k)), cat: new Set(CATS.map(c => c[0])), dist: 200, tram: false, sort: "stop" };
function toggleSolo(set, k, all) { if (set.size === all.length) { set.clear(); set.add(k); } else if (set.has(k)) { set.delete(k); if (!set.size) all.forEach(x => set.add(x)); } else set.add(k); }
function pass(p, skip) {
  if (p.d > S.dist) return false;
  if (S.tram && p.td > S.dist) return false;
  if (skip !== "cls" && !S.cls.has(p.cls)) return false;
  if (skip !== "cat" && !S.cat.has(p.k)) return false;
  return true;
}
/* filtres */
CLS.forEach(c => $("g-cls").append(h("button", { class: "chip", type: "button", "data-k": c.k, "aria-pressed": "true", onclick: () => { toggleSolo(S.cls, c.k, CLS.map(x => x.k)); update(); } },
  h("span", { class: "sw", style: c.k === "nr" ? "background:var(--surface);box-shadow:inset 0 0 0 2px var(--c-nr)" : `background:var(${c.v})` }), c.label, h("span", { class: "n" }))));
CATS.forEach(([k, l]) => $("g-cat").append(h("button", { class: "chip", type: "button", "data-k": k, "aria-pressed": "true", onclick: () => { toggleSolo(S.cat, k, CATS.map(x => x[0])); update(); } }, l, h("span", { class: "n" }))));
document.querySelectorAll("#g-dist button").forEach(b => b.addEventListener("click", () => { S.dist = +b.dataset.d; document.querySelectorAll("#g-dist button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); update(); }));
$("t-tram").addEventListener("change", e => { S.tram = e.target.checked; update(); });
$("reset").addEventListener("click", () => { S.cls = new Set(CLS.map(c => c.k)); S.cat = new Set(CATS.map(c => c[0])); S.dist = 200; S.tram = false; $("t-tram").checked = false; document.querySelectorAll("#g-dist button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.d === "200"))); update(); map.fitBounds(coreB); });
const sel = $("sel-stop");
sel.append(h("option", { value: "" }, "Choisir un arrêt…"));
STOPS.slice().filter(s => s.all > 0 || s.tram).sort((a, b) => a.n.localeCompare(b.n, "fr")).forEach((s, i) => sel.append(h("option", { value: s.n }, s.n + (s.tram ? " (tram)" : ""))));
sel.addEventListener("change", () => { const s = STOPS.find(x => x.n === sel.value); if (s) focusStop(s); });

/* carte */
function dec(str) { let i = 0, lat = 0, lng = 0; const out = []; while (i < str.length) { let b, sh = 0, r = 0; do { b = str.charCodeAt(i++) - 63; r |= (b & 31) << sh; sh += 5; } while (b >= 32); lat += (r & 1) ? ~(r >> 1) : (r >> 1); sh = 0; r = 0; do { b = str.charCodeAt(i++) - 63; r |= (b & 31) << sh; sh += 5; } while (b >= 32); lng += (r & 1) ? ~(r >> 1) : (r >> 1); out.push([lat / 1e5, lng / 1e5]); } return out; }
const map = L.map("map", { minZoom: 10, maxZoom: 19, zoomSnap: 0.5, maxBounds: [[47.62, 1.55], [48.12, 2.32]], maxBoundsViscosity: 0.7 });
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution("Lieux : © contributeurs OpenStreetMap (ODbL) · Fond : IGN BD TOPO® · Arrêts : GTFS TAO");
[["p-base", 200], ["p-water", 210], ["p-roads", 220], ["p-bus", 240], ["p-tram", 250], ["p-radius", 300], ["p-labels", 450]].forEach(([n, z]) => { const p = map.createPane(n); p.style.zIndex = z; if (n !== "p-bus") p.style.pointerEvents = "none"; });
const poly = (r, cls, pane) => L.polygon(r, { pane, className: cls, interactive: false, smoothFactor: .6 });
const line = (l, cls, pane, o) => L.polyline(l, Object.assign({ pane, className: cls, interactive: false, lineCap: "round", lineJoin: "round", smoothFactor: .6 }, o || {}));
poly([[[47.3, 1.2], [47.3, 2.7], [48.5, 2.7], [48.5, 1.2]], ...BASE.metro.map(p => dec(p[0]))], "b-outside", "p-base").addTo(map);
line(BASE.communes.flatMap(c => c.r.map(p => dec(p[0]))), "b-commune", "p-base", { weight: 1 }).addTo(map);
line(BASE.metro.map(p => dec(p[0])), "b-metro", "p-base", { weight: 1.5 }).addTo(map);
poly(BASE.water.map(p => p.map(dec)), "b-water", "p-water").addTo(map);
const RD = { r5: line(BASE.r5.map(dec), "b-local", "p-roads"), r4: line(BASE.r4.map(dec), "b-road", "p-roads").addTo(map), c3: line(BASE.r3.map(dec), "b-cas", "p-roads").addTo(map), r3: line(BASE.r3.map(dec), "b-road", "p-roads").addTo(map), c1: line(BASE.r1.map(dec), "b-cas", "p-roads").addTo(map), r1: line(BASE.r1.map(dec), "b-road", "p-roads").addTo(map) };
const tramParts = [], lyrBus = L.layerGroup();
BASE.lines.forEach(l => { const g = l.g.map(dec); if (l.t === 0) { const c = line(g, "b-tram-cas", "p-tram"), t = line(g, l.id === "A" ? "b-tram-a" : "b-tram-b", "p-tram"); tramParts.push(c, t); c.addTo(map); t.addTo(map); } else { const b = line(g, "b-bus", "p-bus", { interactive: true, weight: 1.6 }); b.bindTooltip(`Ligne ${l.id} · ${l.name}`, { sticky: true }); lyrBus.addLayer(b); } });
$("t-bus").addEventListener("change", e => e.target.checked ? lyrBus.addTo(map) : map.removeLayer(lyrBus));
const lbl = (ll, text) => L.marker(ll, { pane: "p-labels", interactive: false, keyboard: false, icon: L.divIcon({ className: "lbl", html: "", iconSize: [0, 0] }) }).on("add", function () { const el = this.getElement(); if (el) el.replaceChildren(h("span", null, text)); });
const tramStops = STOPS.filter(s => s.tram), busStops = STOPS.filter(s => !s.tram);
const lyrTram = L.layerGroup(tramStops.map(s => L.circleMarker(s.c, { pane: "p-tram", radius: 4, weight: 2, className: "b-stop", interactive: false }))).addTo(map);
const lyrTramLbl = L.layerGroup(tramStops.map(s => lbl(s.c, s.n)));
const lyrBusDots = L.layerGroup(busStops.map(s => L.circleMarker(s.c, { pane: "p-tram", radius: 2.5, weight: 1.3, className: "b-bstop", interactive: false })));
const lyrBusLbl = L.layerGroup(busStops.map(s => lbl(s.c, s.n)));
const pol = L.layerGroup(D.police.map(p => L.marker(p.c, { icon: L.divIcon({ className: "", html: '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect x="1" y="1" width="16" height="16" rx="4" fill="#1d4ed8" stroke="#fff" stroke-width="1.5"/><path d="M9 4.2 13 5.6v3c0 2.6-1.7 4.3-4 5.2-2.3-.9-4-2.6-4-5.2v-3z" fill="#fff"/></svg>', iconSize: [18, 18] }), title: p.n }).bindTooltip(p.n)));
$("t-pol").addEventListener("change", e => e.target.checked ? pol.addTo(map) : map.removeLayer(pol));
function zoomStyle() {
  const z = map.getZoom(), k = z < 11.5 ? 0 : z < 13 ? 1 : z < 14 ? 2 : z < 15 ? 3 : z < 16 ? 4 : 5;
  const W = { r1: [1.4, 2.2, 3.2, 4.6, 6.5, 9], r3: [.9, 1.4, 2.2, 3.4, 5, 7.5], r4: [.5, .9, 1.5, 2.4, 3.8, 6], r5: [0, 0, .8, 1.6, 2.8, 4.6], tram: [2, 2.5, 3, 3.6, 4.2, 5] };
  RD.r1.setStyle({ weight: W.r1[k] }); RD.c1.setStyle({ weight: W.r1[k] + 1.6 }); RD.r3.setStyle({ weight: W.r3[k] }); RD.c3.setStyle({ weight: W.r3[k] + 1.3 }); RD.r4.setStyle({ weight: W.r4[k] }); RD.r5.setStyle({ weight: W.r5[k] });
  tramParts.forEach((p, i) => p.setStyle({ weight: i % 2 === 0 ? W.tram[k] + 2.5 : W.tram[k] }));
  const vis = (l, on) => { if (on && !map.hasLayer(l)) map.addLayer(l); else if (!on && map.hasLayer(l)) map.removeLayer(l); };
  vis(RD.r5, z >= 13); vis(lyrTramLbl, z >= 14); vis(lyrBusDots, z >= 14.5); vis(lyrBusLbl, z >= 16.5);
}
map.on("zoomend", zoomStyle);
/* anneaux de priorité */
const prioStops = STOPS.filter(s => s.sig >= 2 || s.cite >= 2 || s.pole);
const ringLyr = L.layerGroup().addTo(map);
const radiusLyr = L.layerGroup().addTo(map);
/* lieux candidats */
const canvas = L.canvas({ padding: .5 });
const markers = new Map();
function color(p) { return cssv(CLS.find(c => c.k === p.cls).v); }
function popup(p) {
  const c = CLS.find(x => x.k === p.cls);
  return h("div", { class: "pop" },
    h("h3", null, p.n), h("div", { class: "tp" }, CATN[p.k]),
    h("div", { class: "cls" }, h("span", { class: "dot" + (p.cls === "nr" ? " hollow" : ""), style: p.cls === "nr" ? "" : `background:var(${c.v})` }), p.close ? `Ferme vers ${p.close} en semaine` : c.label),
    p.wk ? h("div", { style: "font-size:12px;color:var(--ink-2)" }, `Le week-end : jusqu'à ${p.wk}`) : null,
    h("dl", null,
      p.oh ? [h("dt", null, "Horaires OSM"), h("dd", null, p.oh)] : null,
      p.addr ? [h("dt", null, "Adresse"), h("dd", null, p.addr)] : null,
      h("dt", null, "Arrêt"), h("dd", null, `${p.stop} · ${p.d} m`, p.tram ? "" : (p.td <= 200 ? ` · tram ${p.tstop} ${p.td} m` : "")),
      h("dt", null, "Lignes"), h("dd", null, p.lines.slice(0, 8).join(" "))),
    p.k === "station" ? h("div", { class: "warn" }, p.auto ? "Station automatique : pas d'accueil la nuit." : "Vérifier la présence de personnel le soir.") : null,
    p.k === "bar" ? h("div", { class: "warn" }, "Bar : vérifier l'adhésion à un dispositif d'accueil type « Demandez Angela ».") : null,
    !p.named ? h("div", { class: "warn" }, "Lieu sans nom dans OpenStreetMap : à identifier sur place.") : null,
    h("div", { style: "margin-top:6px" }, h("a", { href: "https://www.openstreetmap.org/" + p.id, target: "_blank", rel: "noopener" }, "Voir la fiche OpenStreetMap ↗")));
}
P.forEach(p => {
  const m = L.circleMarker([p.lat, p.lon], { renderer: canvas, radius: p.cls === "nr" ? 4.5 : 6, weight: p.cls === "nr" ? 2 : 1.5, color: p.cls === "nr" ? color(p) : cssv("--ring"), fillColor: p.cls === "nr" ? cssv("--surface") : color(p), fillOpacity: 1 });
  m.bindPopup(() => popup(p), { maxWidth: 320 }); m.bindTooltip(p.n, { direction: "top", offset: [0, -6] });
  markers.set(p.id, m);
});
const poiLyr = L.layerGroup().addTo(map);
const coreB = L.latLngBounds(tramStops.map(s => s.c)).pad(0.05);
map.fitBounds(coreB);
requestAnimationFrame(() => { map.invalidateSize(); map.fitBounds(coreB, { animate: false }); });
function focusStop(s) {
  radiusLyr.clearLayers();
  L.circle(s.c, { radius: S.dist, pane: "p-radius", className: "b-radius", weight: 1.5, interactive: false }).addTo(radiusLyr);
  $("map").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  map.flyTo(s.c, 16.5, { animate: !matchMedia("(prefers-reduced-motion: reduce)").matches });
}
function restyle() {
  P.forEach(p => { const m = markers.get(p.id); m.setStyle({ color: p.cls === "nr" ? color(p) : cssv("--ring"), fillColor: p.cls === "nr" ? cssv("--surface") : color(p) }); });
  drawRings();
}
function stopCounts(s) {
  const near = P.filter(p => pass(p, "cls") && dist(p, s) <= S.dist);
  return { eve: near.filter(p => p.cls === "tard" || p.cls === "nuit").length, day: near.filter(p => p.day).length };
}
function dist(p, s) { const k = Math.cos((p.lat + s.c[0]) / 2 * Math.PI / 180); return Math.hypot((p.lat - s.c[0]) * 111320, (p.lon - s.c[1]) * 111320 * k); }
function drawRings() {
  ringLyr.clearLayers();
  prioStops.forEach(s => { const c = stopCounts(s); const col = c.eve === 0 ? cssv("--gap") : c.eve < 3 ? cssv("--warn") : cssv("--ok");
    L.circleMarker(s.c, { pane: "p-radius", radius: 11, weight: 3.5, color: col, fill: false, interactive: false }).addTo(ringLyr); });
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", restyle);
new MutationObserver(restyle).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
function legend() {
  $("legend").replaceChildren(h("div", { class: "lg-title" }, "Fermeture en semaine"),
    ...CLS.map(c => h("div", { class: "lg-row" }, h("span", { class: "dot" + (c.k === "nr" ? " hollow" : ""), style: c.k === "nr" ? "" : `background:var(${c.v})` }), c.label)),
    h("hr"), h("div", { class: "lg-title" }, "Arrêt prioritaire"),
    h("div", { class: "lg-row" }, h("span", { class: "ringk", style: "box-shadow:inset 0 0 0 3px var(--gap)" }), "Aucun lieu ouvert le soir"),
    h("div", { class: "lg-row" }, h("span", { class: "ringk", style: "box-shadow:inset 0 0 0 3px var(--warn)" }), "1 ou 2 lieux le soir"),
    h("div", { class: "lg-row" }, h("span", { class: "ringk", style: "box-shadow:inset 0 0 0 3px var(--ok)" }), "3 lieux ou plus le soir"));
}
/* panneaux */
function badge(id) { const col = id === "A" ? "#e2121a" : id === "B" ? "#762a80" : "#5f7078"; return h("span", { class: "badge", style: `background:${col}` }, id); }
function renderPrio() {
  const rows = prioStops.map(s => Object.assign({ s }, stopCounts(s))).sort((a, b) => (a.eve === 0 ? 0 : 1) - (b.eve === 0 ? 0 : 1) || (b.s.sig + 2 * b.s.sev + b.s.cite) - (a.s.sig + 2 * a.s.sev + a.s.cite));
  $("prio").replaceChildren(...rows.map(r => {
    const st = r.eve === 0 ? h("span", { class: "st gap" }, h("i"), "Aucun lieu") : r.eve < 3 ? h("span", { class: "st warn" }, h("i"), "À renforcer") : h("span", { class: "st ok" }, h("i"), "Couvert");
    const tr = h("tr", { tabindex: 0, title: "Zoomer sur l'arrêt" },
      h("td", { class: "nm" }, h("b", null, r.s.n), h("small", null, h("span", { class: "badges" }, r.s.l.slice(0, 5).map(badge)), r.s.pole ? ` · pôle ${r.s.pole === "centre" ? "centre-ville" : "campus"}` : "")),
      h("td", { class: "n" }, r.s.sig ? `${r.s.sig}${r.s.sev ? ` (${r.s.sev})` : ""}` : "–"), h("td", { class: "n" }, r.s.cite || "–"),
      h("td", { class: "n" }, String(r.eve)), h("td", { class: "n" }, String(r.day)), h("td", null, st));
    tr.addEventListener("click", () => focusStop(r.s)); tr.addEventListener("keydown", e => { if (e.key === "Enter") focusStop(r.s); });
    return tr;
  }));
}
function renderCats(F) {
  const order = ["nuit", "tard", "jour", "ferme", "nr"];
  const rows = CATS.map(([k, l]) => { const c = order.map(o => F.filter(p => p.k === k && p.cls === o).length); return { l, c, n: c.reduce((a, b) => a + b, 0) }; }).filter(r => r.n).sort((a, b) => b.n - a.n);
  const max = Math.max(1, ...rows.map(r => r.n));
  $("c-cat").replaceChildren(...rows.map(r => h("div", { class: "brow" }, h("span", { class: "bl" }, r.l), h("span", { class: "bv" }, fmt(r.n), h("small", null, `${r.c[0] + r.c[1]} le soir`)),
    h("div", { class: "track" }, r.c.map((v, i) => v ? h("i", { style: `width:calc(${100 * v / max}% - 2px);background:var(${CLS[i].v})${i === 4 ? ";opacity:.45" : ""}` }) : null)))));
}
$("cat-legend").replaceChildren(...CLS.map(c => h("span", null, h("i", { style: `background:var(${c.v})${c.k === "nr" ? ";opacity:.45" : ""}` }), c.short)));
function renderList(F) {
  const rows = F.slice().sort((a, b) => a.stop.localeCompare(b.stop, "fr") || a.d - b.d).slice(0, 600);
  $("tbody").replaceChildren(...rows.map(p => {
    const c = CLS.find(x => x.k === p.cls);
    const tr = h("tr", { title: "Voir sur la carte" },
      h("td", null, h("b", null, p.n)), h("td", { class: "muted" }, CATN[p.k]),
      h("td", null, h("span", { style: "display:inline-flex;align-items:center;gap:6px" }, h("span", { class: "dot" + (p.cls === "nr" ? " hollow" : ""), style: p.cls === "nr" ? "" : `background:var(${c.v})` }), p.close ? `ferme vers ${p.close}` : c.short)),
      h("td", { class: "num" }, `${p.stop} · ${p.d} m`), h("td", { class: "muted" }, p.addr || "–"),
      h("td", null, h("a", { href: "https://www.openstreetmap.org/" + p.id, target: "_blank", rel: "noopener" }, "OSM ↗")));
    tr.addEventListener("click", (e) => { if (e.target.tagName === "A") return; $("map").scrollIntoView({ block: "center" }); map.flyTo([p.lat, p.lon], 18); setTimeout(() => markers.get(p.id).openPopup(), 600); });
    return tr;
  }));
  $("list-note").textContent = `${fmt(F.length)} lieux selon les filtres${F.length > 600 ? " (600 premiers affichés)" : ""}, classés par arrêt. Les données OSM sont à vérifier sur place avant tout contact.`;
}
function renderKPIs(F) {
  const eve = F.filter(p => p.cls === "tard" || p.cls === "nuit").length, night = F.filter(p => p.cls === "nuit").length, nr = F.filter(p => p.cls === "nr").length;
  const tc = tramStops.map(s => stopCounts(s)); const cov = tc.filter(c => c.eve > 0).length;
  const gaps = prioStops.filter(s => stopCounts(s).eve === 0).length;
  const kpi = (l, v, s) => h("div", { class: "kpi" }, h("span", { class: "kpi-label" }, l), h("span", { class: "kpi-value" }, v), h("span", { class: "kpi-sub" }, s));
  $("kpis").replaceChildren(
    kpi("Lieux candidats", fmt(F.length), `à moins de ${S.dist} m d'un arrêt`),
    kpi("Ouverts après 21 h", fmt(eve), `dont ${fmt(night)} après 23 h 30 ou la nuit`),
    kpi("Arrêts de tram couverts le soir", `${cov} / ${tramStops.length}`, "au moins un lieu ouvert après 21 h"),
    kpi("Arrêts prioritaires sans lieu le soir", String(gaps), `sur ${prioStops.length} arrêts prioritaires · ${pct(nr, F.length)} % de lieux sans horaires`));
}
function update() {
  const F = P.filter(p => pass(p));
  poiLyr.clearLayers(); F.forEach(p => poiLyr.addLayer(markers.get(p.id)));
  const cnt = (skip, key, keys) => { const c = Object.fromEntries(keys.map(k => [k, 0])); P.forEach(p => { if (pass(p, skip)) c[p[key]]++; }); return c; };
  const cc = cnt("cls", "cls", CLS.map(c => c.k)), ck = cnt("cat", "k", CATS.map(c => c[0]));
  document.querySelectorAll("#g-cls .chip").forEach(b => { b.setAttribute("aria-pressed", String(S.cls.has(b.dataset.k))); b.querySelector(".n").textContent = fmt(cc[b.dataset.k]); });
  document.querySelectorAll("#g-cat .chip").forEach(b => { b.setAttribute("aria-pressed", String(S.cat.has(b.dataset.k))); b.querySelector(".n").textContent = fmt(ck[b.dataset.k]); });
  $("f-count").replaceChildren(h("b", null, fmt(F.length)), ` / ${fmt(P.length)} lieux`);
  drawRings(); renderKPIs(F); renderPrio(); renderCats(F); renderList(F);
}
/* textes */
const tot = P.length, eveAll = P.filter(p => p.cls === "tard" || p.cls === "nuit").length;
$("lede").textContent = `${fmt(tot)} commerces et lieux publics à moins de 200 m d'un arrêt de tram ou de bus pourraient accueillir le label. ${fmt(eveAll)} sont ouverts après 21 h, l'heure où commence le service de nuit. Les arrêts les plus signalés ou cités par les usagères sans aucun lieu ouvert le soir sont les premiers à démarcher.`;
$("method").replaceChildren(
  h("div", null,
    h("h3", null, "Sources"),
    h("p", null, `Commerces et lieux publics : OpenStreetMap (extrait Geofabrik du 11 octobre 2026), ${fmt(D.meta.total_metro)} lieux pertinents dans la Métropole, dont ${fmt(D.meta.with_hours_metro)} avec des horaires. Arrêts et lignes : GTFS TAO. Priorités : signalements nettoyés (sûreté et incivilités) et questionnaire usagères (51 réponses).`),
    h("h3", null, "Règles"),
    h("ul", null, h("li", null, "Distance à vol d'oiseau entre le lieu et l'arrêt le plus proche (200 m, environ 2 à 3 min à pied)."), h("li", null, "Horaire retenu : l'heure de fermeture tenue au moins trois soirs de semaine. « Tard » à partir de 21 h, « nuit » à partir de 23 h 30 ou 24 h/24."), h("li", null, "Arrêt prioritaire : au moins 2 signalements sûreté ou incivilités, ou 2 citations dans le questionnaire, ou situé dans un pôle pilote (centre-ville, campus de La Source)."))),
  h("div", null,
    h("h3", null, "Limites"),
    h("ul", null, h("li", null, `${pct(P.filter(p => p.cls === "nr").length, tot)} % des lieux n'ont pas d'horaires dans OpenStreetMap : ils peuvent être ouverts tard. Une vérification sur place ou par téléphone est nécessaire.`), h("li", null, "Les pharmacies de garde changent chaque nuit : elles ne figurent pas dans les données, à compléter avec le service de garde."), h("li", null, "Stations-service : beaucoup sont automatiques la nuit, sans accueil. Bars : vérifier l'adhésion à un dispositif comme « Demandez Angela »."), h("li", null, "Aucun de ces lieux n'est partenaire : la carte sert à préparer la prospection."))));
legend(); zoomStyle(); update();
new ResizeObserver(() => map.invalidateSize()).observe($("map"));
})();
