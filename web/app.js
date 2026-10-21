/* LUI forskningskart — static SPA over web/data/*.json */
const D = {};                 // loaded data
const idx = {};               // indexes
const MACRO_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939"];
const EDGE_LABEL = { coauthor: "Medforfatter", cites: "Siterer", shared_group: "Samme forskningsgruppe", shared_project: "Samme prosjekt", topic_similarity: "Tematisk likhet" };
const EDGE_COLOR = { coauthor: "#0d5c8a", cites: "#c75b12", shared_group: "#2ca02c", shared_project: "#9467bd", topic_similarity: "#999" };
const HELP = {
  core: "Antall registrerte arbeider i Cristin/NVA i de vitenskapelige kategoriene artikkel, kapittel, bok/antologi, doktoravhandling og forskningsrapport, alle år. Foredrag, lærebøker, formidling og media telles ikke her.",
  all: "Alle registrerte arbeider i Cristin/NVA der personen står som forfatter, alle kategorier (også foredrag, lærebøker, formidling og media).",
  joint: "Antall arbeider (alle kategorier, inntil 30 forfattere) der personen er medforfatter sammen med minst én LUI-ansatt.",
  topicN: "Antall av personens arbeider (vitenskapelige arbeider og foredrag med tittel) der dette temaet har vekt ≥ 0,2. Hvert arbeid får 1–4 tema med vekter som summerer til 1.",
  score: "Andel av personens temaprofil: for hvert arbeid summeres temavekt × kategorivekt (artikkel 1,0; kapittel 0,9; bok/avhandling 1,2; rapport 0,7; foredrag 0,3; lærebok 0,5; formidling 0,2) × nyhetsvekt (halveres per 8 år). Presentasjonstekst og egne nøkkelord teller som 1,5–2 arbeider. Summen normaliseres til 1 per person.",
  topicPubs: "Arbeider der dette temaet er blant de 1–4 tildelte temaene, og som passerer filtrene over (type, år, institutt).",
  topicPersons: "Personer med temaet i profilen med styrke ≥ 0,05 (se forklaring på styrke).",
  similarity: "Cosinus-likhet mellom de to personenes temaprofiler (vektorer over 78 tema): 0 = ingen felles tema, 1 = identisk profil.",
  theoryOverlap: "Andel av utgangspersonens teoretiske rammeverk (gjenkjent med kontrollerte vokabularer i sammendrag, innledning og konklusjon) som kandidaten også bruker.",
  totalScore: "Vektet sum: tematisk overlapp (cosinus + nøkkelordtreff) × w1 + felles teori × w2 + komplementær metode × w3 + bonus for ikke-medforfattere × w4 + bonus for annet institutt × w5 + nylig aktivitet × w6, med vektene fra glidebryterne.",
  relations: "Registrerte relasjoner mellom personer: medforfatterskap (vektet 1/(k−1) per arbeid med k kjente forfattere), siteringer (via OpenAlex), felles forskningsgruppe, felles prosjekt og tematisk likhet (cosinus ≥ 0,35).",
};
const GROUP_LABEL = { article: "Artikkel", chapter: "Kapittel", monograph: "Bok", phd: "Doktoravhandling", report: "Rapport", lecture: "Foredrag", textbook: "Lærebok", popular: "Populærvitenskap", media: "Media", thesis: "Oppgave", other: "Annet" };

const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => (n ?? 0).toLocaleString("nb-NO");
const uniq = a => [...new Set(a)];
const THIS_YEAR = new Date().getFullYear();

async function load() {
  const names = ["meta", "taxonomy", "persons", "edges", "groups", "projects", "orders"];
  const res = await Promise.all(names.map(n => fetch(`data/${n}.json${V}`).then(r => r.json())));
  names.forEach((n, i) => D[n] = res[i]);
  // edges are stored as compact arrays: [s, t, type, w, n, y0, y1, ev]
  D.edges = D.edges.map(e => Array.isArray(e) ? { s: e[0], t: e[1], type: e[2], w: e[3], n: e[4], y0: e[5], y1: e[6], ev: e[7] || [] } : e);
  D.pubs = [];
  idx.person = new Map(D.persons.map(p => [p.id, p]));
  idx.topic = new Map(D.taxonomy.topics.map(t => [t.topic_id, t]));
  idx.macro = new Map(D.taxonomy.macro.map((m, i) => [m.macro_id, { ...m, i }]));
  idx.theory = new Map(D.taxonomy.theories.map(t => [t.theory_id, t]));
  idx.method = new Map(D.taxonomy.methods.map(t => [t.method_id, t]));
  idx.group = new Map(D.groups.map(g => [g.id, g]));
  idx.project = new Map(D.projects.map(p => [p.id, p]));
  idx.unit = new Map(D.meta.units.map(u => [u.unit_id, u]));
  idx.edgesByPerson = new Map();
  for (const e of D.edges) for (const k of [e.s, e.t]) {
    if (!idx.edgesByPerson.has(k)) idx.edgesByPerson.set(k, []);
    idx.edgesByPerson.get(k).push(e);
  }
  idx.subfields = uniq(D.persons.flatMap(p => (p.subfields || []).map(x => x[0]))).sort();
  idx.community = new Map(Object.entries(D.orders.community || {}).map(([k, v]) => [k, +v]));
  idx.personOrder = new Map((D.orders.personOrder || []).map((id, i) => [id, i]));
  idx.personOrderTopic = new Map((D.orders.personOrderTopic || []).map((id, i) => [id, i]));
  idx.topicOrder = new Map((D.orders.topicOrder || []).map((id, i) => [id, i]));
  const allYears = D.persons.flatMap(p => p.yrsAll || []);
  idx.minYear = Math.max(1970, Math.min(...allYears)); idx.maxYear = Math.max(...allYears);
  idx.search = new MiniSearch({ fields: ["name", "title", "bio", "keywords", "topicLabels", "unitName", "aff"], storeFields: ["id"],
    searchOptions: { prefix: true, fuzzy: 0.2, boost: { name: 3, keywords: 2, topicLabels: 2 } } });
  idx.search.addAll(D.persons.map(p => ({ id: p.id, name: p.name, title: p.title, bio: p.bio, keywords: (p.keywords || []).join(" "),
    topicLabels: (p.topics || []).map(t => topicLabel(t.t) + " " + t.t).join(" "), unitName: unitName(p.unit), aff: p.aff || "" })));
  $("#meta").innerHTML = `Data generert ${esc(D.meta.generated)} · <span title="Ansatte i LUIs ansattoversikt, ikke-listede LUI-tilknyttede og medforfattere (tidligere LUI, andre OsloMet-enheter, eksterne).">${fmt(D.meta.nPersons)} personer</span> · <span title="Arbeider i Cristin/NVA med minst én kjent forfatter (alle kategorier).">${fmt(D.meta.nPubs)} publikasjoner</span> · <span title="${esc(HELP.relations)}">${fmt(D.meta.nEdges)} relasjoner</span>`;
}

/* ---- publications are fetched on demand (per person / per topic / search index) ---- */
const pubCache = new Map();
const V = window.__v && window.__v !== "dev" ? `?v=${window.__v}` : "";   // deploy-time version for cache busting
async function fetchJSON(url) { try { const r = await fetch(url.startsWith("http") ? url : url + V); if (!r.ok) return null; return await r.json(); } catch { return null; } }
async function pubsFor(personId) {
  if (!personId) return [];
  if (!pubCache.has(personId)) pubCache.set(personId, fetchJSON(`data/pubs/by_person/${encodeURIComponent(personId.replace(":", "_"))}.json`).then(x => x || []));
  return pubCache.get(personId);
}
async function pubsForTopic(topicId) {
  const key = "topic:" + topicId;
  if (!pubCache.has(key)) pubCache.set(key, fetchJSON(`data/pubs/by_topic/${encodeURIComponent(topicId)}.json`).then(x => (x || []).map(r => ({ core: 1, abs: 1, ...r }))));
  return pubCache.get(key);
}
async function pubsIndex() {
  if (!pubCache.has("index")) pubCache.set("index", fetchJSON("data/pubs_index.json").then(rows => (rows || []).map(r => ({
    id: r[0], title: r[1], year: r[2], group: r[3], core: r[4], venue: r[5], doi: r[6], nva: r[7], lang: r[8], cited: r[9],
    authors: r[10].map(id => ({ p: id, n: idx.person.get(id)?.name || id })), nAuthors: r[11], topics: r[12].map(t => ({ t })), theories: r[13], methods: r[14], sf: r[15], abs: r[16], kw: [] }))));
  return pubCache.get("index");
}
/** Live details from OpenAlex (optional). Never required: on failure the stored data stays as it is. */
async function oaDetails(pub, el) {
  el.textContent = "henter …";
  if (!pub.doi) { el.textContent = "ingen DOI – ingen ekstern oppslagskilde"; return; }
  let d = null, status = 0;
  try { const r = await fetch(`https://api.openalex.org/works/https://doi.org/${encodeURIComponent(pub.doi)}?select=id,cited_by_count,referenced_works_count,primary_topic,open_access&mailto=pcmoan@gmail.com`); status = r.status; if (r.ok) d = await r.json(); } catch { status = 0; }
  if (!d) { el.textContent = status === 404 ? "ikke registrert i OpenAlex (DOI-lenken over gjelder fortsatt)" : "eksternt oppslag ikke tilgjengelig akkurat nå – lagrede opplysninger vises"; return; }
  el.innerHTML = `OpenAlex: ${d.cited_by_count ?? 0} siteringer · ${d.referenced_works_count ?? 0} referanser${d.primary_topic ? ` · ${esc(d.primary_topic.display_name)}` : ""}${d.open_access?.oa_url ? ` · <a href="${esc(d.open_access.oa_url)}" target="_blank" rel="noopener">åpen fulltekst</a>` : ""} · <a href="${esc(d.id)}" target="_blank" rel="noopener">OpenAlex</a>`;
}
const topicLabel = id => { const t = idx.topic.get(id); return t ? (t.label_nb || t.label_en || id) : id; };
const macroOf = id => { const t = idx.topic.get(id); return t ? idx.macro.get(t.macro_id) : null; };
const macroColor = m => m ? MACRO_COLORS[m.i % MACRO_COLORS.length] : "#999";
const unitName = id => idx.unit.get(id)?.short_code || "";
/** Institute code for LUI staff; "(Ekstern)" / "(OsloMet)" for coauthor nodes outside LUI. */
const unitLabel = p => !p ? "" : (p.listed || !p.type || p.type === "former_lui") ? (unitName(p.unit) || "LUI") : p.type === "oslomet" ? "(OsloMet)" : "(Ekstern)";
const personLink = p => `<a href="#/person/${esc(p.id)}">${esc(p.name)}</a>`;
const topicChip = (t, extra = "") => { const m = macroOf(t.t ?? t); const id = t.t ?? t;
  return `<a class="chip m" style="background:${macroColor(m)}" href="#/topic/${esc(id)}" title="${esc(id)} · ${esc(m?.label_nb || "")}">${esc(topicLabel(id))}${extra}</a>`; };

/* ---------------- filter state in the URL (#/view?key=value) ---------------- */
let suppressRoute = false;
function getQS() { const i = location.hash.indexOf("?"); return i < 0 ? {} : Object.fromEntries(new URLSearchParams(location.hash.slice(i + 1))); }
function setQS(obj) {
  const base = location.hash.split("?")[0] || "#/";
  const qs = new URLSearchParams(Object.entries(obj).filter(([, v]) => v !== "" && v != null && v !== false).map(([k, v]) => [k, v === true ? "1" : v]));
  suppressRoute = true; history.replaceState(null, "", base + (qs.toString() ? "?" + qs : "")); suppressRoute = false;
}
const optionsHtml = (opts, sel) => opts.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(sel) ? "selected" : ""}>${esc(l)}</option>`).join("");
const unitOptions = () => D.meta.units.filter(u => u.short_code !== "LUI").map(u => [u.unit_id, `${u.short_code} – ${u.name_nb}`]);
const topicOptions = () => D.taxonomy.topics.slice().sort((a, b) => (idx.macro.get(a.macro_id)?.i ?? 99) - (idx.macro.get(b.macro_id)?.i ?? 99)).map(t => [t.topic_id, `${t.topic_id} · ${t.label_nb || t.label_en}`]);
const macroOptions = () => D.taxonomy.macro.map(m => [m.macro_id, `${m.macro_id} · ${m.label_nb || m.label_en}`]);
const theoryOptions = () => D.taxonomy.theories.map(t => [t.theory_id, t.label]);
const methodOptions = () => D.taxonomy.methods.map(t => [t.method_id, t.label]);
const groupOptions = () => D.groups.slice().sort((a, b) => (a.name || "").localeCompare(b.name || "", "nb")).map(g => [g.id, g.name || g.id]);
const subfieldOptions = () => idx.subfields.map(s => [s, s]);
const typeOptions = () => Object.entries(GROUP_LABEL);

/** Build a toolbar from a field spec; values live in the hash query string. */
function filterBar(container, fields, onChange) {
  const st = getQS();
  const html = fields.map(f => {
    const v = st[f.id] ?? f.value ?? "";
    if (f.type === "search") return `<input type="search" id="f_${f.id}" placeholder="${esc(f.label)}" value="${esc(v)}">`;
    if (f.type === "text") return `<input type="text" id="f_${f.id}" placeholder="${esc(f.label)}" value="${esc(v)}" ${f.list ? `list="${f.list}"` : ""} style="min-width:${f.width || 180}px">`;
    if (f.type === "select") return `<label>${esc(f.label)} <select id="f_${f.id}"><option value="">${esc(f.all || "alle")}</option>${optionsHtml(f.options, v)}</select></label>`;
    if (f.type === "check") return `<label><input type="checkbox" id="f_${f.id}" ${v && v !== "0" ? "checked" : ""}> ${esc(f.label)}</label>`;
    if (f.type === "range") return `<label>${esc(f.label)} <input type="range" id="f_${f.id}" min="${f.min}" max="${f.max}" step="${f.step}" value="${esc(v)}"><span id="f_${f.id}_v">${esc(v)}</span></label>`;
    if (f.type === "years") return `<label>år <input type="number" id="f_${f.id}0" min="${idx.minYear}" max="${idx.maxYear}" value="${esc(st[f.id + "0"] ?? "")}" placeholder="${idx.minYear}" style="width:5.5em"> – <input type="number" id="f_${f.id}1" min="${idx.minYear}" max="${idx.maxYear}" value="${esc(st[f.id + "1"] ?? "")}" placeholder="${idx.maxYear}" style="width:5.5em"></label>`;
    if (f.type === "number") return `<label>${esc(f.label)} <input type="number" id="f_${f.id}" min="0" value="${esc(v)}" style="width:4.5em"></label>`;
    if (f.type === "multi") { const sel = new Set(String(v).split(",").map(x => x.trim()).filter(Boolean));
      return `<details class="multi" id="f_${f.id}" data-label="${esc(f.label)}"><summary>${esc(f.label)}: <span class="sum">${esc(f.options.filter(([val]) => sel.has(val)).map(([, l]) => l).join(", ") || "ingen")}</span></summary>
        <div class="menu">${f.options.map(([val, l]) => `<label><input type="checkbox" value="${esc(val)}" ${sel.has(val) ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div></details>`; }
    return "";
  }).join("") + `<button type="button" id="f_reset" class="small">nullstill</button><span id="f_count" class="muted"></span>`;
  container.innerHTML = html;
  const read = () => {
    const out = {};
    for (const f of fields) {
      if (f.type === "years") { out[f.id + "0"] = $(`#f_${f.id}0`).value; out[f.id + "1"] = $(`#f_${f.id}1`).value; continue; }
      const el = $(`#f_${f.id}`);
      if (f.type === "multi") { const vals = [...el.querySelectorAll("input:checked")].map(x => x.value); out[f.id] = vals.join(","); el.querySelector(".sum").textContent = f.options.filter(([val]) => vals.includes(val)).map(([, l]) => l).join(", ") || "ingen"; continue; }
      out[f.id] = f.type === "check" ? el.checked : el.value;
      if (f.type === "range") $(`#f_${f.id}_v`).textContent = el.value;
    }
    return out;
  };
  const fire = () => { const v = read(); setQS(v); onChange(v); };
  container.querySelectorAll("input, select").forEach(el => el.addEventListener("input", fire));
  $("#f_reset").addEventListener("click", () => { setQS({}); container.querySelectorAll("input,select").forEach(el => {
      const multi = el.closest("details.multi");
      if (multi) { const f = fields.find(f => "f_" + f.id === multi.id); el.checked = String(f?.value || "").split(",").includes(el.value); }
      else if (el.type === "checkbox") el.checked = !!fields.find(f => "f_" + f.id === el.id)?.value; else if (el.type === "range") el.value = fields.find(f => "f_" + f.id === el.id)?.value ?? el.min; else el.value = ""; }); fire(); });
  const v = read(); onChange(v);
  return read;
}
const yearRange = (f, key = "y") => [+f[key + "0"] || idx.minYear, +f[key + "1"] || idx.maxYear];
const overlaps = (span, [y0, y1]) => !span || (span[1] >= y0 && span[0] <= y1);

const SCOPE_OPTS = [["lui", "LUI inkl. tidligere og ikke-listede"], ["oslomet", "+ andre OsloMet-ansatte"], ["all", "alle inkl. eksterne medforfattere"]];
const SCOPE_FIELD = () => ({ id: "scope", type: "select", label: "personer", all: "ansatte i oversikten", options: SCOPE_OPTS });
const isLui = p => p.listed || !p.type || p.type === "former_lui";
function scopeOk(p, scope) {
  if (!scope) return !!p.listed;
  if (scope === "lui") return isLui(p);
  if (scope === "oslomet") return isLui(p) || p.type === "oslomet";
  return true;
}
const EXT_LABEL = { former_lui: "tidligere/annen LUI-tilknytning", oslomet: "annen enhet ved OsloMet", external: "ekstern medforfatter" };
/** Shared predicate for persons given a filter state. */
function personMatches(p, f) {
  const [y0, y1] = yearRange(f);
  const yearsSet = f.y0 || f.y1;
  if (f.unit && p.unit !== f.unit) return false;
  if (f.type && p.type !== f.type) return false;
  if (!scopeOk(p, f.scope)) return false;
  if (f.macro && !p.topics.some(t => macroOf(t.t)?.macro_id === f.macro && t.s >= 0.05)) return false;
  if (f.topic && !p.topics.some(t => t.t === f.topic && t.s >= (+f.tmin || 0.05))) return false;
  if (f.theory && !p.theories.some(t => t.t === f.theory)) return false;
  if (f.method && !p.methods.some(t => t.t === f.method)) return false;
  if (f.group && !p.groups.some(g => g.g === f.group)) return false;
  if (f.subfield && !(p.subfields || []).some(([s]) => s === f.subfield)) return false;
  if (f.minCore && (p.nCore || 0) < +f.minCore) return false;
  if (yearsSet) {
    const ys = (f.coreOnly ? p.yrs : p.yrsAll) || [];
    if (!ys.some(y => y >= y0 && y <= y1)) return false;
  }
  return true;
}
const activeIn = (p, y0, y1) => (p.yrsAll || []).some(y => y >= y0 && y <= y1);
/** Shared predicate for publications. */
function pubMatches(pub, f) {
  const [y0, y1] = yearRange(f);
  if (pub.year && (pub.year < y0 || pub.year > y1)) return false;
  if (!pub.year && (f.y0 || f.y1)) return false;
  if (f.coreOnly && !pub.core) return false;
  if (f.ptype && pub.group !== f.ptype) return false;
  if (f.topic && !pub.topics.some(t => t.t === f.topic)) return false;
  if (f.macro && !pub.topics.some(t => macroOf(t.t)?.macro_id === f.macro)) return false;
  if (f.theory && !pub.theories.includes(f.theory)) return false;
  if (f.method && !pub.methods.includes(f.method)) return false;
  if (f.subfield && pub.sf !== f.subfield) return false;
  if (f.lang && pub.lang !== f.lang) return false;
  if (f.abs && !pub.abs) return false;
  return true;
}
function downloadCSV(name, rows) {
  const csv = rows.map(r => r.map(x => `"${String(x ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" })); a.download = name; a.click();
}

/* ---------------- router ---------------- */
const routes = {
  "": viewExplore, matrix: viewMatrix, graph: viewGraph, topics: viewTopics, topic: viewTopic, person: viewPerson,
  pair: viewPair, score: viewScore, about: viewAbout, group: viewGroup, project: viewProject, pubs: viewPubs, relmatrix: viewRelMatrix,
};
function route() {
  if (suppressRoute) return;
  const parts = location.hash.replace(/^#\/?/, "").split("?")[0].split("/").map(decodeURIComponent);
  const fn = routes[parts[0]] || viewExplore;
  document.querySelectorAll("header nav a").forEach(a => a.classList.toggle("active", a.getAttribute("href") === `#/${parts[0]}`));
  $("#app").innerHTML = "";
  fn(...parts.slice(1));
  window.scrollTo(0, 0);
}

/* ---------------- explore ---------------- */
const PERSON_FILTERS = () => [
  { id: "q", type: "search", label: "Søk … (navn, tema, nøkkelord, tittelord, f.eks. flerspråklighet, Bourdieu, T12)" },
  { id: "unit", type: "select", label: "institutt", options: unitOptions() },
  { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
  { id: "macro", type: "select", label: "makrotema", options: macroOptions() },
  { id: "topic", type: "select", label: "tema", options: topicOptions() },
  { id: "theory", type: "select", label: "teori", options: theoryOptions() },
  { id: "method", type: "select", label: "metode", options: methodOptions() },
  { id: "group", type: "select", label: "forskningsgruppe", options: groupOptions() },
  { id: "subfield", type: "select", label: "OpenAlex-felt", options: subfieldOptions() },
  { id: "y", type: "years" },
  { id: "minCore", type: "number", label: "min. vitensk. publ." },
  { id: "coreOnly", type: "check", label: "årsfilter bare på vitenskapelige", value: true },
  SCOPE_FIELD(),
];
function viewExplore() {
  const app = $("#app");
  app.innerHTML = `
    <h1>Hvem forsker på hva ved LUI?</h1>
    <p class="muted">Søk og filtrer på institutt, tema (kode eller navn), teori, metode, forskningsgruppe, fagfelt og årstall. Klikk på en person for profil, samarbeid og forslag til nye samarbeidspartnere.</p>
    <div class="toolbar" id="bar"></div>
    <div class="toolbar no-print"><button type="button" id="csv">Last ned liste (CSV)</button><a href="#/pubs" class="small">→ søk i publikasjoner</a></div>
    <div class="grid" id="list"></div>`;
  let current = [];
  filterBar($("#bar"), PERSON_FILTERS(), f => {
    let people = f.q ? idx.search.search(f.q).map(r => idx.person.get(r.id)) : [...D.persons].sort((a, b) => a.name.localeCompare(b.name, "nb"));
    people = people.filter(p => personMatches(p, f));
    current = people;
    $("#f_count").textContent = `${people.length} personer`;
    $("#list").innerHTML = people.slice(0, 400).map(p => personCard(p, f)).join("") + (people.length > 400 ? `<p class="muted">… ${people.length - 400} flere, avgrens søket.</p>` : "");
  });
  $("#csv").addEventListener("click", () => downloadCSV("lui-personer.csv", [["navn", "tittel", "institutt", "type", "vitensk_publ", "første_år", "siste_år", "primærtema", "profil"],
    ...current.map(p => [p.name, p.title, unitLabel(p), p.type, p.nCore, p.years?.[0], p.years?.[1], p.topics.filter(t => t.p).map(t => `${t.t} ${topicLabel(t.t)}`).join(" | "), p.url])]));
}
function personCard(p, f = {}) {
  let tops = (p.topics || []).filter(t => t.p || t.s >= 0.15).slice(0, 4);
  if (f.topic && !tops.some(t => t.t === f.topic)) { const t = p.topics.find(t => t.t === f.topic); if (t) tops = [t, ...tops].slice(0, 4); }
  return `<div class="card">
    <div class="name">${personLink(p)}</div>
    <div class="sub">${p.listed ? `${esc(p.title || "")} · ${esc(unitLabel(p))}` : `${esc(EXT_LABEL[p.type] || "ikke i ansattoversikten")}${p.aff ? ` · ${esc(p.aff)}${p.country && p.country !== "NO" ? ` (${esc(p.country)})` : ""}` : ""}`}</div>
    <div class="sub"><span title="${esc(p.listed || !p.nJoint ? HELP.core : HELP.joint)}">${p.listed || !p.nJoint ? `${p.nCore} vitensk. publ.` : `${p.nJoint} felles publ. med LUI`}</span>${p.years ? ` <span title="Første og siste registrerte publiseringsår">(${p.years[0]}–${p.years[1]})</span>` : ""}${p.thin && p.listed ? ' · <span title="lite tekstgrunnlag">tynn profil</span>' : ""}</div>
    <div class="chips">${tops.map(t => topicChip(t)).join("")}${tops.length ? "" : (p.keywords || []).slice(0, 4).map(k => `<span class="chip k">${esc(k)}</span>`).join("")}</div>
  </div>`;
}

/* ---------------- publications search ---------------- */
async function viewPubs() {
  const app = $("#app");
  app.innerHTML = `<h1>Publikasjoner</h1><p class="muted">Filtrer alle registrerte arbeider med minst én LUI-forfatter.</p><div class="toolbar" id="bar"></div>
    <div class="toolbar no-print"><button type="button" id="csv">Last ned (CSV)</button></div><div id="list"></div>`;
  $("#list").innerHTML = '<p class="muted">Laster publikasjonsindeks …</p>';
  const PUBS = await pubsIndex();
  const langs = uniq(PUBS.map(p => p.lang).filter(Boolean)).sort();
  let current = [];
  filterBar($("#bar"), [
    { id: "q", type: "search", label: "tittelord, forfatter, tidsskrift, emneord …" },
    { id: "unit", type: "select", label: "institutt (forfatter)", options: unitOptions() },
    { id: "ptype", type: "select", label: "type", options: typeOptions() },
    { id: "macro", type: "select", label: "makrotema", options: macroOptions() },
    { id: "topic", type: "select", label: "tema", options: topicOptions() },
    { id: "theory", type: "select", label: "teori", options: theoryOptions() },
    { id: "method", type: "select", label: "metode", options: methodOptions() },
    { id: "subfield", type: "select", label: "OpenAlex-felt", options: subfieldOptions() },
    { id: "lang", type: "select", label: "språk", options: langs.map(l => [l, l]) },
    { id: "y", type: "years" },
    { id: "coreOnly", type: "check", label: "bare vitenskapelige", value: true },
    { id: "abs", type: "check", label: "har sammendrag" },
  ], f => {
    const q = (f.q || "").toLowerCase().split(/\s+/).filter(Boolean);
    let pubs = PUBS.filter(p => pubMatches(p, f) && (!f.unit || p.authors.some(a => a.p && idx.person.get(a.p)?.unit === f.unit)));
    if (q.length) pubs = pubs.filter(p => { const hay = [p.title, p.venue, ...p.authors.map(a => a.n)].join(" ").toLowerCase(); return q.every(w => hay.includes(w)); });
    pubs.sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
    current = pubs;
    $("#f_count").textContent = `${pubs.length} publikasjoner`;
    $("#list").innerHTML = pubs.slice(0, 300).map(p => pubItem(p)).join("") + (pubs.length > 300 ? `<p class="muted">… ${pubs.length - 300} flere, avgrens.</p>` : "");
  });
  $("#csv").addEventListener("click", () => downloadCSV("lui-publikasjoner.csv", [["år", "tittel", "type", "forfattere", "kanal", "doi", "nva", "tema", "siteringer"],
    ...current.map(p => [p.year, p.title, p.group, p.authors.map(a => a.n).join("; "), p.venue, p.doi, p.nva, p.topics.map(t => t.t).join(" "), p.cited])]));
}

/* ---------------- person ---------------- */
function personVector(p) { const v = new Map(); for (const t of p.topics || []) v.set(t.t, t.s); return v; }
function cosine(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (const [k, x] of a) { na += x * x; if (b.has(k)) dot += x * b.get(k); }
  for (const x of b.values()) nb += x * x;
  return dot / (Math.sqrt(na) * Math.sqrt(nb) || 1);
}
function neighbours(p) {
  const out = new Map();
  for (const e of idx.edgesByPerson.get(p.id) || []) {
    const other = e.s === p.id ? e.t : e.s;
    if (!out.has(other)) out.set(other, {});
    out.get(other)[e.type] = e;
  }
  return out;
}
function pubItem(pub, hl) {
  const authors = pub.authors.map(a => a.p ? `<a href="#/person/${esc(a.p)}" ${a.p === hl ? 'style="font-weight:600"' : ""}>${esc(a.n)}</a>` : esc(a.n)).join("; ");
  const links = [pub.doi ? `<a href="https://doi.org/${esc(pub.doi)}" target="_blank" rel="noopener">DOI</a>` : "",
    pub.nva ? `<a href="https://nva.sikt.no/registration/${esc(pub.nva)}" target="_blank" rel="noopener">NVA</a>` : ""].filter(Boolean).join(" ");
  const more = pub.doi ? `<a href="#" class="small no-print" data-oa="${esc(pub.id)}">mer</a>` : "";
  return `<div class="pub" data-pub="${esc(pub.id)}"><span class="t">${esc(pub.title)}</span><span class="badge">${esc(GROUP_LABEL[pub.group] || pub.group)}</span>${pub.cited ? `<span class="badge">${pub.cited} sit.</span>` : ""}${pub.sf ? `<span class="badge" title="OpenAlex subfield">${esc(pub.sf)}</span>` : ""}
    <div class="meta">${authors}${pub.nAuthors > pub.authors.length ? ` (+${pub.nAuthors - pub.authors.length} andre)` : ""} (${pub.year ?? "?"}). ${esc(pub.venue || "")} ${links} ${more} ${(pub.topics || []).map(t => topicChip(t)).join(" ")}<span class="small muted" data-oa-out></span></div></div>`;
}
function bars(items, labelFn, max = 1) {
  return items.map(t => `<div class="bar"><span>${labelFn(t)}</span><div class="track" title="${esc(HELP.score)}"><div class="fill" style="width:${Math.round(100 * t.s / max)}%"></div></div><span class="num small" title="${esc(HELP.score)}">${t.s.toFixed(2)}</span></div>`).join("");
}
async function viewPerson(id) {
  const p = idx.person.get(id);
  const app = $("#app");
  if (!p) { app.innerHTML = "<p>Fant ikke personen.</p>"; return; }
  const pubs = (await pubsFor(id)).slice().sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  window.__lastPubs = pubs;
  if (location.hash.split("?")[0] !== `#/person/${id}`) return;   // user navigated on while loading
  const nb = neighbours(p);
  const coll = [...nb.entries()].map(([oid, es]) => ({ p: idx.person.get(oid), es })).filter(x => x.p)
    .sort((a, b) => (b.es.coauthor?.w ?? 0) + (b.es.cites?.w ?? 0) - (a.es.coauthor?.w ?? 0) - (a.es.cites?.w ?? 0));
  const myVec = personVector(p);
  const suggestions = D.persons.filter(o => o.id !== id && o.listed && !nb.get(o.id)?.coauthor && o.topics.length)
    .map(o => ({ p: o, s: cosine(myVec, personVector(o)) })).filter(x => x.s > 0.3).sort((a, b) => b.s - a.s).slice(0, 12);
  const maxS = Math.max(0.01, ...p.topics.map(t => t.s));
  const unit = idx.unit.get(p.unit);
  app.innerHTML = `
    <h1>${esc(p.name)}</h1>
    <div class="muted">${p.listed ? `${esc(p.title || "")} · ${esc(unit?.name_nb || "")}` : `${esc(EXT_LABEL[p.type] || "ikke i ansattoversikten")}${p.aff ? ` · ${esc(p.aff)}${p.country ? ` (${esc(p.country)})` : ""}` : ""}${p.nJoint ? ` · ${p.nJoint} felles publikasjoner med LUI` : ""}`} ${p.url ? `· <a href="${esc(p.url)}" target="_blank" rel="noopener">profil på oslomet.no</a>` : ""}
      ${p.orcid ? `· <a href="https://orcid.org/${esc(p.orcid)}" target="_blank" rel="noopener">ORCID</a>` : ""} ${p.cristin ? `· <a href="https://app.cristin.no/persons/show.jsf?id=${esc(p.cristin)}" target="_blank" rel="noopener">Cristin</a>` : ""}</div>
    <div class="toolbar no-print" style="margin:.5rem 0 .2rem">
      <a class="btn" href="#/graph?focus=${encodeURIComponent(p.name)}&et=coauthor,cites&ext=1">Graf: ${esc(p.name)} og medforfattere →</a>
      <a class="btn" href="#/score?who=${encodeURIComponent(p.name)}">Finn samarbeid for ${esc(p.name)} →</a>
      <a class="btn" href="#/matrix?pp=${encodeURIComponent([p.id, ...D.persons.filter(o => o.id !== id && o.listed && o.topics.length).map(o => ({ o, s: cosine(myVec, personVector(o)) })).sort((a, b) => b.s - a.s).slice(0, 12).map(x => x.o.id)].join(","))}" title="personen og de 12 med høyest tematisk likhet (cosinus)">Interessematrise: ${esc(p.name)} + 12 nærmeste →</a>
    </div>
    ${p.bio ? `<p>${esc(p.bio)}</p>` : '<p class="muted">Ingen presentasjonstekst funnet.</p>'}
    <div class="cols">
      <div>
        <h2>Forskningstema</h2>
        <p class="muted small" title="${esc(HELP.score)}">Søylen viser temaets andel av profilen; hold musepekeren over tallene for forklaring.</p>
        ${p.topics.length ? bars(p.topics.slice(0, 12), t => topicChip(t) + `<span class="muted small" title="${esc(HELP.topicN)}"> ${t.n} publ.</span>`, maxS) : '<p class="muted">Ingen tematiserte publikasjoner ennå.</p>'}
        ${p.theories.length ? `<h3>Teoretiske rammeverk</h3><div class="chips">${p.theories.slice(0, 10).map(t => `<a class="chip" href="#/pubs?theory=${esc(t.t)}" title="${t.s.toFixed(2)}">${esc(idx.theory.get(t.t)?.label || t.t)}</a>`).join("")}</div>` : ""}
        ${p.methods.length ? `<h3>Metoder</h3><div class="chips">${p.methods.slice(0, 10).map(t => `<a class="chip" href="#/pubs?method=${esc(t.t)}" title="${t.s.toFixed(2)}">${esc(idx.method.get(t.t)?.label || t.t)}</a>`).join("")}</div>` : ""}
        ${(p.subfields || []).length ? `<h3>OpenAlex-fagfelt</h3><div class="chips">${p.subfields.map(([s, n]) => `<span class="chip k">${esc(s)} (${n})</span>`).join("")}</div>` : ""}
        ${p.keywords.length ? `<h3>Egne nøkkelord (Cristin)</h3><div class="chips">${p.keywords.map(k => `<span class="chip k">${esc(k)}</span>`).join("")}</div>` : ""}
        <h2 title="${esc(HELP.all)}">Publikasjoner (${pubs.length})</h2>
        <div class="toolbar no-print" id="pbar"></div>
        <div id="pubs"></div>
      </div>
      <div>
        <h2>Samarbeid</h2>
        ${coll.length ? `<table class="tbl"><tr><th>Person</th><th>Relasjon</th></tr>${coll.slice(0, 40).map(c => `<tr><td>${personLink(c.p)} <a class="small" href="#/pair/${esc(id)}/${esc(c.p.id)}">par</a></td><td class="small">${Object.values(c.es).map(e => `<span style="color:${EDGE_COLOR[e.type]}" title="${e.type === "coauthor" ? "Antall felles arbeider (inntil 30 forfattere) og årsspenn" : e.type === "cites" ? "Antall siteringer mellom de to personenes arbeider (OpenAlex)" : e.type === "topic_similarity" ? HELP.similarity : ""}">${EDGE_LABEL[e.type]}${e.type === "coauthor" || e.type === "cites" ? ` (${e.n}${e.y0 ? `, ${e.y0}–${e.y1}` : ""})` : ""}</span>`).join(", ")}</td></tr>`).join("")}</table>` : '<p class="muted">Ingen registrerte relasjoner.</p>'}
        <h2>Mulige nye samarbeidspartnere</h2>
        <p class="muted small">Tematisk nærhet uten eksisterende medforfatterskap. <a href="#/score?who=${encodeURIComponent(p.name)}">Juster kriterier →</a></p>
        ${suggestions.length ? `<table class="tbl">${suggestions.map(s => `<tr><td>${personLink(s.p)}<div class="small muted">${esc(unitLabel(s.p))} · ${esc(s.p.title || "")}</div></td><td class="num">${s.s.toFixed(2)}</td><td><a class="small" href="#/pair/${esc(id)}/${esc(s.p.id)}">par</a></td></tr>`).join("")}</table>` : '<p class="muted">Trenger temaprofil.</p>'}
        ${p.groups.length ? `<h2>Forskningsgrupper</h2><ul>${p.groups.map(g => `<li><a href="#/group/${esc(g.g)}">${esc(idx.group.get(g.g)?.name || g.g)}</a> <span class="muted small">${esc(g.r)}</span></li>`).join("")}</ul>` : ""}
        ${p.projects.length ? `<h2>Prosjekter</h2><ul>${p.projects.slice(0, 25).map(pr => `<li><a href="#/project/${esc(pr.p)}">${esc(idx.project.get(pr.p)?.title_nb || idx.project.get(pr.p)?.title_en || pr.p)}</a></li>`).join("")}</ul>` : ""}
      </div>
    </div>`;
  const myTopics = uniq(pubs.flatMap(x => x.topics.map(t => t.t))).map(t => [t, `${t} · ${topicLabel(t)}`]);
  filterBar($("#pbar"), [
    { id: "ptype", type: "select", label: "type", options: typeOptions() },
    { id: "topic", type: "select", label: "tema", options: myTopics },
    { id: "y", type: "years" },
    { id: "coreOnly", type: "check", label: "bare vitenskapelige", value: true },
  ], f => { const list = pubs.filter(x => pubMatches(x, f)); $("#f_count").textContent = `${list.length} vist`; $("#pubs").innerHTML = list.map(x => pubItem(x, id)).join("") || '<p class="muted">Ingen.</p>'; });
}

/* ---------------- pair ---------------- */
async function viewPair(a, b) {
  const pa = idx.person.get(a), pb = idx.person.get(b), app = $("#app");
  if (!pa || !pb) { app.innerHTML = "<p>Fant ikke personene.</p>"; return; }
  const pubsA = await pubsFor(a);
  window.__lastPubs = pubsA;
  const va = personVector(pa), vb = personVector(pb);
  const shared = [...va.keys()].filter(k => vb.has(k)).map(k => ({ t: k, s: Math.min(va.get(k), vb.get(k)) })).sort((x, y) => y.s - x.s);
  const onlyA = pa.topics.filter(t => !vb.has(t.t) && t.s >= 0.1).slice(0, 6), onlyB = pb.topics.filter(t => !va.has(t.t) && t.s >= 0.1).slice(0, 6);
  const joint = pubsA.filter(p => p.authors.some(x => x.p === b)).sort((x, y) => (y.year ?? 0) - (x.year ?? 0));
  const es = neighbours(pa).get(b) || {};
  const gA = new Set(pa.groups.map(g => g.g)), gB = new Set(pb.groups.map(g => g.g)), prA = new Set(pa.projects.map(x => x.p)), prB = new Set(pb.projects.map(x => x.p));
  const thA = new Set(pa.theories.map(t => t.t)), thB = new Set(pb.theories.map(t => t.t)), meA = new Set(pa.methods.map(t => t.t)), meB = new Set(pb.methods.map(t => t.t));
  app.innerHTML = `
    <h1>${personLink(pa)} &amp; ${personLink(pb)}</h1>
    <div class="muted">${esc(unitLabel(pa))} · ${esc(pa.title || "")} &nbsp;|&nbsp; ${esc(unitLabel(pb))} · ${esc(pb.title || "")} &nbsp;|&nbsp; <span title="${esc(HELP.similarity)}">tematisk likhet ${cosine(va, vb).toFixed(2)}</span></div>
    <div class="cols"><div>
      <h2>Felles tema</h2>${shared.length ? `<div class="chips">${shared.map(t => topicChip(t, ` ${t.s.toFixed(2)}`)).join("")}</div>` : '<p class="muted">Ingen felles tema.</p>'}
      <h3>Komplementære tema</h3>
      <div class="small muted">${esc(pa.name)}:</div><div class="chips">${onlyA.map(t => topicChip(t)).join("") || "–"}</div>
      <div class="small muted">${esc(pb.name)}:</div><div class="chips">${onlyB.map(t => topicChip(t)).join("") || "–"}</div>
      ${[...thA].filter(x => thB.has(x)).length ? `<h3>Felles teori</h3><div class="chips">${[...thA].filter(x => thB.has(x)).map(x => `<span class="chip">${esc(idx.theory.get(x)?.label || x)}</span>`).join("")}</div>` : ""}
      ${[...meA].filter(x => meB.has(x)).length ? `<h3>Felles metode</h3><div class="chips">${[...meA].filter(x => meB.has(x)).map(x => `<span class="chip">${esc(idx.method.get(x)?.label || x)}</span>`).join("")}</div>` : ""}
      <h2 title="Arbeider i Cristin/NVA der begge står som forfattere (alle kategorier).">Felles publikasjoner (${joint.length})</h2>${joint.map(p => pubItem(p)).join("") || '<p class="muted">Ingen.</p>'}
    </div><div>
      <h2>Relasjoner</h2>
      <ul>${Object.values(es).map(e => `<li><span style="color:${EDGE_COLOR[e.type]}">${EDGE_LABEL[e.type]}</span>: vekt ${e.w}, ${e.n} belegg${e.y0 ? ` (${e.y0}–${e.y1})` : ""}</li>`).join("") || "<li class='muted'>Ingen direkte relasjon</li>"}</ul>
      ${[...gA].filter(g => gB.has(g)).length ? `<h3>Felles forskningsgrupper</h3><ul>${[...gA].filter(g => gB.has(g)).map(g => `<li><a href="#/group/${esc(g)}">${esc(idx.group.get(g)?.name || g)}</a></li>`).join("")}</ul>` : ""}
      ${[...prA].filter(x => prB.has(x)).length ? `<h3>Felles prosjekter</h3><ul>${[...prA].filter(x => prB.has(x)).map(x => `<li><a href="#/project/${esc(x)}">${esc(idx.project.get(x)?.title_nb || x)}</a></li>`).join("")}</ul>` : ""}
      <h3>Felles kontakter</h3>
      ${(() => { const na = neighbours(pa), nbb = neighbours(pb); const common = [...na.keys()].filter(k => nbb.has(k) && k !== a && k !== b).map(k => idx.person.get(k)).filter(Boolean); return common.length ? `<ul>${common.slice(0, 20).map(c => `<li>${personLink(c)}</li>`).join("")}</ul>` : '<p class="muted">Ingen.</p>'; })()}
    </div></div>`;
}

/* ---------------- topics ---------------- */
function viewTopics() {
  const app = $("#app");
  if (!D.taxonomy.topics.length) { app.innerHTML = '<h1>Tema</h1><p class="notice">Temataksonomien er ikke bygget ennå (fase 5–6 i planen).</p>'; return; }
  app.innerHTML = `<h1>Forskningstema</h1><p class="muted">${D.taxonomy.topics.length} tema i ${D.taxonomy.macro.length} makrogrupper. Tall: personer / publikasjoner. Temakoden (f.eks. T12) kan brukes i søk og filtre.</p><div class="toolbar" id="bar"></div><div id="list"></div>`;
  filterBar($("#bar"), [{ id: "q", type: "search", label: "filtrer tema …" }, { id: "macro", type: "select", label: "makrotema", options: macroOptions() }, { id: "unit", type: "select", label: "institutt (personer)", options: unitOptions() }], f => {
    const q = (f.q || "").toLowerCase();
    const peopleIn = u => D.persons.filter(p => p.listed && (!u || p.unit === u));
    const ppl = peopleIn(f.unit);
    $("#list").innerHTML = D.taxonomy.macro.filter(m => !f.macro || m.macro_id === f.macro).map(m => {
      const ts = D.taxonomy.topics.filter(t => t.macro_id === m.macro_id && (!q || [t.topic_id, t.label_nb, t.label_en, t.definition_nb, t.definition_en, ...(t.keywords || [])].join(" ").toLowerCase().includes(q)));
      if (!ts.length) return "";
      return `<h2 style="border-color:${macroColor(idx.macro.get(m.macro_id))}">${esc(m.macro_id)} · ${esc(m.label_nb || m.label_en)} <span class="muted small">${esc(m.definition || "")}</span></h2>
      <div class="grid">${ts.map(t => { const n = f.unit ? ppl.filter(p => p.topics.some(x => x.t === t.topic_id && x.s >= 0.05)).length : t.n_persons;
        return `<div class="card"><div class="name"><span class="muted small">${esc(t.topic_id)}</span> <a href="#/topic/${esc(t.topic_id)}">${esc(t.label_nb || t.label_en)}</a></div>
        <div class="sub">${esc(t.label_en || "")}</div><div class="small">${esc(t.definition_nb || t.definition_en || "")}</div><div class="sub"><span title="${esc(HELP.topicPersons)}">${n} personer</span> · <span title="Arbeider der temaet er blant de 1–4 tildelte temaene (vitenskapelige arbeider og foredrag med tittel).">${t.n_pubs} publ.</span></div></div>`; }).join("")}</div>`; }).join("");
    $("#f_count").textContent = "";
  });
}
async function viewTopic(id) {
  const t = idx.topic.get(id), app = $("#app");
  if (!t) { app.innerHTML = "<p>Fant ikke temaet.</p>"; return; }
  const m = idx.macro.get(t.macro_id);
  const allPubs = await pubsForTopic(id);
  window.__lastPubs = allPubs;
  const adj = new Map();
  for (const p of D.persons) if (p.topics.some(x => x.t === id)) for (const x of p.topics) if (x.t !== id) adj.set(x.t, (adj.get(x.t) || 0) + x.s);
  const adjacent = [...adj.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  app.innerHTML = `
    <h1 style="border-left:6px solid ${macroColor(m)};padding-left:.5rem"><span class="muted">${esc(t.topic_id)}</span> ${esc(t.label_nb || t.label_en)}</h1>
    <div class="muted">${esc(t.label_en || "")} · makrogruppe: ${esc(m?.macro_id || "")} ${esc(m?.label_nb || "")}</div>
    <p>${esc(t.definition_nb || t.definition_en || "")}</p>
    ${t.keywords?.length ? `<div class="chips">${t.keywords.map(k => `<span class="chip k">${esc(k)}</span>`).join("")}</div>` : ""}
    <div class="toolbar" id="bar"></div>
    <div class="cols"><div><h2 id="ph">Personer</h2><div id="people"></div><h2 id="pubh">Publikasjoner</h2><div id="pubs"></div></div>
    <div><h2>Utvikling</h2><div class="small" id="trend"></div><h2>Nærliggende tema</h2><div class="chips">${adjacent.map(([k]) => topicChip(k)).join("")}</div>
    </div></div>`;
  $("#bar").insertAdjacentHTML("beforebegin", `<div class="toolbar no-print" style="margin:.4rem 0 .2rem">
      <a class="btn" href="#/graph?topic=${esc(id)}&et=coauthor,cites,shared_project&minw=0.25&color=unit&hideIso=0" title="Personer med dette temaet i profilen (styrke ≥ 0,05) og relasjonene mellom dem: medforfatterskap, siteringer og felles prosjekter">Graf: hvem har samarbeidet med hvem om ${esc(t.label_nb || t.label_en)} →</a>
      <a class="btn" href="#/relmatrix?topic=${esc(id)}&et=coauthor,cites,shared_project&hideIso=0">Relasjonsmatrise for temaet →</a>
      <a class="btn" href="#/matrix?pp=${encodeURIComponent(D.persons.filter(p => p.listed && p.topics.some(x => x.t === id && x.s >= 0.1)).sort((a, b) => (b.topics.find(x => x.t === id)?.s ?? 0) - (a.topics.find(x => x.t === id)?.s ?? 0)).slice(0, 80).map(p => p.id).join(","))}" title="Personer med dette temaet i profilen (styrke ≥ 0,10, inntil 80) og alle temaene de er interessert i">Interessematrise: personene med temaet og deres øvrige tema →</a>
    </div>`);
  filterBar($("#bar"), [
    { id: "unit", type: "select", label: "institutt", options: unitOptions() },
    { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
    { id: "ptype", type: "select", label: "publikasjonstype", options: typeOptions() },
    { id: "y", type: "years" },
    { id: "tmin", type: "range", label: "min. styrke", min: 0, max: 0.6, step: 0.05, value: 0.05 },
    SCOPE_FIELD(),
    { id: "coreOnly", type: "check", label: "bare vitenskapelige", value: true },
  ], f => {
    const pubs = allPubs.filter(p => pubMatches(p, f) && (!f.unit || p.authors.some(a => a.p && idx.person.get(a.p)?.unit === f.unit))).sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
    const yearsSet = f.y0 || f.y1;
    const [ya, yb] = yearRange(f);
    const people = D.persons.map(p => ({ p, s: (p.topics || []).find(x => x.t === id)?.s ?? 0, n: (p.topics || []).find(x => x.t === id)?.n ?? 0 }))
      .filter(x => x.s >= (+f.tmin || 0.05) && scopeOk(x.p, f.scope) && (!f.unit || x.p.unit === f.unit) && (!f.type || x.p.type === f.type) && (!yearsSet || activeIn(x.p, ya, yb))).sort((a, b) => b.s - a.s);
    $("#ph").textContent = `Personer (${people.length})`; $("#ph").title = HELP.topicPersons; $("#pubh").textContent = `Publikasjoner (${pubs.length})`; $("#pubh").title = HELP.topicPubs;
    $("#people").innerHTML = `<table class="tbl"><tr><th>Person</th><th>Institutt</th><th class="num" title="${esc(HELP.score)}">Styrke ⓘ</th><th class="num" title="${esc(HELP.topicN)}">Publ. ⓘ</th></tr>${people.slice(0, 100).map(x => `<tr><td>${personLink(x.p)}</td><td>${esc(unitLabel(x.p))}</td><td class="num">${x.s.toFixed(2)}</td><td class="num">${x.n}</td></tr>`).join("")}</table>`;
    $("#pubs").innerHTML = pubs.slice(0, 150).map(p => pubItem(p)).join("");
    const years = [...d3.rollup(pubs.filter(p => p.year), v => v.length, p => p.year).entries()].sort((a, b) => a[0] - b[0]);
    const drawTrend = () => {
      const el = $("#trend"); if (!el || !years.length) { if (el) el.innerHTML = '<span class="muted">Ingen årstall.</span>'; return; }
      const maxN = Math.max(...years.map(([, n]) => n));
      const blockPx = 9, reserved = 90;                              // year label + count
      const maxBlocks = Math.max(5, Math.floor((el.clientWidth - reserved) / blockPx));
      const unit = Math.max(1, Math.ceil(maxN / maxBlocks));          // publications per block
      el.innerHTML = years.map(([y, n]) => `<div class="trend-row"><span class="trend-y">${y}</span><span class="trend-bar" title="${n} publikasjoner">${"▮".repeat(Math.ceil(n / unit))}</span><span class="trend-n">${n}</span></div>`).join("") +
        `<div class="muted small">▮ = ${unit} publikasjon${unit > 1 ? "er" : ""}</div>`;
    };
    drawTrend();
    if (!window.__trendResize) { window.__trendResize = true; addEventListener("resize", () => { if (document.getElementById("trend")) drawTrend(); }); }
    $("#f_count").textContent = "";
  });
}

/* ---------------- group / project ---------------- */
function viewGroup(id) {
  const g = idx.group.get(id), app = $("#app");
  if (!g) { app.innerHTML = "<p>Fant ikke gruppen.</p>"; return; }
  const members = D.persons.filter(p => p.groups.some(x => x.g === id));
  app.innerHTML = `<h1>${esc(g.name)}</h1><div class="muted"><a href="${esc(g.url)}" target="_blank" rel="noopener">oslomet.no</a> · <a href="#/?group=${esc(id)}">filtrer utforsk-listen</a> · <a href="#/graph?group=${esc(id)}&et=coauthor,cites,shared_project">graf</a></div><p>${esc((g.description || "").slice(0, 1500))}</p>
    <h2>Medlemmer (${members.length})</h2><div class="grid">${members.map(p => personCard(p)).join("")}</div>
    <h2>Gruppens tema</h2><div class="chips">${aggregateTopics(members).slice(0, 15).map(([t, s]) => topicChip(t, ` ${s.toFixed(1)}`)).join("")}</div>`;
}
function viewProject(id) {
  const pr = idx.project.get(id), app = $("#app");
  if (!pr) { app.innerHTML = "<p>Fant ikke prosjektet.</p>"; return; }
  const members = D.persons.filter(p => p.projects.some(x => x.p === id));
  app.innerHTML = `<h1>${esc(pr.title_nb || pr.title_en)}</h1><div class="muted">${esc(pr.start_date || "")}–${esc(pr.end_date || "")} ${pr.status ? "· " + esc(pr.status) : ""} · <a href="${esc(pr.url)}" target="_blank" rel="noopener">kilde</a></div>
    <p>${esc((pr.summary || "").slice(0, 2000))}</p><h2>Deltakere ved LUI (${members.length})</h2><div class="grid">${members.map(p => personCard(p)).join("")}</div>`;
}
function aggregateTopics(people) {
  const agg = new Map();
  for (const p of people) for (const t of p.topics) agg.set(t.t, (agg.get(t.t) || 0) + t.s);
  return [...agg.entries()].sort((a, b) => b[1] - a[1]);
}

/* ---------------- matrix ---------------- */
function viewMatrix() {
  const app = $("#app");
  if (!D.taxonomy.topics.length) { app.innerHTML = '<h1>Interessematrise</h1><p class="notice">Temataksonomien er ikke bygget ennå.</p>'; return; }
  app.innerHTML = `<h1>Interessematrise: personer × tema</h1><div class="toolbar" id="bar"></div>
    <div class="card no-print" style="margin-bottom:.6rem">
      <div class="toolbar" style="margin:0">
        <input type="text" id="addP" placeholder="legg til person …" list="mxPersons" style="min-width:220px">
        <input type="text" id="addT" placeholder="legg til tema (kode eller navn) …" list="mxTopics" style="min-width:260px">
        <button type="button" id="addFiltered">legg til alle filtrerte personer (maks 150)</button>
        <button type="button" id="clearSel">tøm utvalg</button>
        <span class="muted small">Et utvalg av personer og/eller tema gir en liten matrise i stedet for hele tabellen; utvalget ligger i lenken.</span>
      </div>
      <div class="chips" id="selChips"></div>
      <datalist id="mxPersons">${D.persons.filter(p => p.topics.length).map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>
      <datalist id="mxTopics">${D.taxonomy.topics.map(t => `<option value="${esc(t.topic_id)} · ${esc(t.label_nb || t.label_en)}">`).join("")}</datalist>
    </div>
    <div class="toolbar no-print"><button type="button" id="csv">Last ned matrise (CSV)</button></div>
    <div class="matrix-wrap" id="mx"></div><div class="tooltip" id="tip" hidden></div>`;
  let lastPeople = [], lastTopics = [], lastF = {}, redraw = () => {};
  const sel = { p: (getQS().pp || "").split(",").filter(Boolean), t: (getQS().tt || "").split(",").filter(Boolean) };
  const saveSel = () => { setQS({ ...lastF, pp: sel.p.join(","), tt: sel.t.join(",") }); renderChips(); redraw(); };
  const renderChips = () => { $("#selChips").innerHTML = sel.p.map(id => `<span class="chip">${esc(idx.person.get(id)?.name || id)} <a href="#" data-p="${esc(id)}" title="fjern">×</a></span>`).join("") +
      sel.t.map(id => topicChip(id).replace("</a>", ` <b data-t="${esc(id)}" style="cursor:pointer" title="fjern">×</b></a>`)).join("") || '<span class="muted small">Ingen utvalg – hele matrisen vises.</span>';
    $("#selChips").querySelectorAll("[data-p]").forEach(el => el.addEventListener("click", ev => { ev.preventDefault(); sel.p = sel.p.filter(x => x !== el.dataset.p); saveSel(); }));
    $("#selChips").querySelectorAll("[data-t]").forEach(el => el.addEventListener("click", ev => { ev.preventDefault(); ev.stopPropagation(); sel.t = sel.t.filter(x => x !== el.dataset.t); saveSel(); })); };
  $("#addP").addEventListener("change", ev => { const p = D.persons.find(x => x.name.toLowerCase() === ev.target.value.trim().toLowerCase()); if (p && !sel.p.includes(p.id)) { sel.p.push(p.id); ev.target.value = ""; saveSel(); } });
  $("#addT").addEventListener("change", ev => { const v = ev.target.value.trim().toLowerCase(); const t = D.taxonomy.topics.find(x => v.startsWith(x.topic_id.toLowerCase()) || (x.label_nb || "").toLowerCase() === v || (x.label_en || "").toLowerCase() === v); if (t && !sel.t.includes(t.topic_id)) { sel.t.push(t.topic_id); ev.target.value = ""; saveSel(); } });
  $("#addFiltered").addEventListener("click", () => { for (const p of lastPeople.slice(0, 150)) if (!sel.p.includes(p.id)) sel.p.push(p.id); saveSel(); });
  $("#clearSel").addEventListener("click", () => { sel.p = []; sel.t = []; saveSel(); });
  filterBar($("#bar"), [
    { id: "unit", type: "select", label: "institutt", options: unitOptions() },
    { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
    { id: "macro", type: "select", label: "makrotema (kolonner)", options: macroOptions() },
    { id: "topic", type: "select", label: "må ha tema", options: topicOptions() },
    { id: "theory", type: "select", label: "teori", options: theoryOptions() },
    { id: "method", type: "select", label: "metode", options: methodOptions() },
    { id: "group", type: "select", label: "forskningsgruppe", options: groupOptions() },
    { id: "y", type: "years" },
    { id: "minCore", type: "number", label: "min. vitensk. publ." },
    { id: "tmin", type: "range", label: "min. styrke", min: 0, max: 0.5, step: 0.05, value: 0.1 },
    { id: "sort", type: "select", label: "sorter", all: "blokkstruktur (co-clustering)", options: [["macro", "etter makrogruppe"], ["unit", "etter institutt"], ["name", "etter navn"], ["n", "etter antall publ."]] },
    { id: "coreOnly", type: "check", label: "årsfilter bare på vitenskapelige", value: true },
    SCOPE_FIELD(),
  ], f => { lastF = f; redraw = () => drawMatrix(f); drawMatrix(f); });
  renderChips();
  function drawMatrix(f) {
    const min = +f.tmin || 0;
    const block = !f.sort && idx.topicOrder.size > 0;
    const topicSort = (a, b) => block ? (idx.topicOrder.get(a.topic_id) ?? 1e9) - (idx.topicOrder.get(b.topic_id) ?? 1e9) : (idx.macro.get(a.macro_id)?.i ?? 99) - (idx.macro.get(b.macro_id)?.i ?? 99);
    let topics = D.taxonomy.topics.filter(t => !f.macro || t.macro_id === f.macro).sort(topicSort);
    let people = D.persons.filter(p => p.topics.length && personMatches(p, f));
    const hasSel = sel.p.length || sel.t.length;
    if (hasSel) {
      if (sel.p.length) people = sel.p.map(id => idx.person.get(id)).filter(Boolean);
      if (sel.t.length) topics = sel.t.map(id => idx.topic.get(id)).filter(Boolean);
      if (!sel.t.length) { const used = new Set(people.flatMap(p => p.topics.filter(t => t.s >= min).map(t => t.t))); topics = topics.filter(t => used.has(t.topic_id)); }
      if (!sel.p.length) { const ts = new Set(topics.map(t => t.topic_id)); people = people.filter(p => p.topics.some(t => ts.has(t.t) && t.s >= min)); }
    }
    if (block) people.sort((a, b) => (idx.personOrderTopic.get(a.id) ?? 1e9) - (idx.personOrderTopic.get(b.id) ?? 1e9));
    else if (f.sort === "name") people.sort((a, b) => a.name.localeCompare(b.name, "nb"));
    else if (f.sort === "unit") people.sort((a, b) => (a.unit || "").localeCompare(b.unit || "") || a.name.localeCompare(b.name, "nb"));
    else if (f.sort === "n") people.sort((a, b) => (b.nCore || 0) - (a.nCore || 0));
    else people.sort((a, b) => { const ma = macroOf(a.topics[0]?.t)?.i ?? 99, mb = macroOf(b.topics[0]?.t)?.i ?? 99; return ma - mb || (b.topics[0]?.s ?? 0) - (a.topics[0]?.s ?? 0); });
    lastPeople = people; lastTopics = topics;
    $("#f_count").textContent = `${people.length} personer × ${topics.length} tema${hasSel ? " (utvalg)" : ""}`;
    const topicText = t => `${t.topic_id} ${t.label_nb || t.label_en}`;
    const left = Math.min(420, 16 + 6.3 * Math.max(8, ...people.map(p => p.name.length)));
    const top = Math.min(460, 24 + 6.0 * Math.max(10, ...topics.map(t => topicText(t).length)));   // labels are vertical
    // fit the full width of the container: no horizontal scrolling
    const avail = Math.max(300, ($("#mx").clientWidth || 1000) - left - 16);
    const cw = Math.max(5, Math.min(topics.length <= 12 ? 30 : 22, Math.floor(avail / Math.max(1, topics.length))));
    const rh = people.length <= 15 ? 26 : people.length <= 40 ? 18 : 14;
    const w = left + topics.length * cw + 10, h = top + people.length * rh + 10;
    const svg = d3.create("svg").attr("width", w).attr("height", h);
    const g = svg.append("g");
    const tipT = $("#tip");
    g.selectAll("text.col").data(topics).join("text").attr("class", "col").attr("transform", (t, i) => `translate(${left + i * cw + cw / 2 + 3},${top - 6}) rotate(-90)`)
      .attr("fill", t => macroColor(idx.macro.get(t.macro_id))).attr("font-size", Math.min(11, Math.max(7, cw - 2))).text(t => topicText(t)).style("cursor", "pointer")
      .on("click", (e, t) => location.hash = `#/topic/${t.topic_id}`)
      .on("mousemove", (e, t) => { tipT.hidden = false; tipT.style.left = e.clientX + 14 + "px"; tipT.style.top = e.clientY + 14 + "px"; tipT.style.fontSize = "1.05rem"; tipT.innerHTML = `<b>${esc(t.topic_id)}</b> ${esc(t.label_nb || t.label_en)}<br><span style="opacity:.8">${esc(t.label_en || "")} · ${esc(idx.macro.get(t.macro_id)?.label_nb || "")}</span>`; })
      .on("mouseleave", () => { tipT.hidden = true; tipT.style.fontSize = ""; });
    g.selectAll("text.row").data(people).join("text").attr("class", "row").attr("x", left - 4).attr("y", (p, i) => top + i * rh + rh - 3).attr("text-anchor", "end")
      .attr("font-size", Math.min(11, Math.max(7, rh - 3))).text(p => p.name).style("cursor", "pointer").on("click", (e, p) => location.hash = `#/person/${p.id}`);
    const cells = [];
    const tpos = new Map(topics.map((t, j) => [t.topic_id, j]));
    people.forEach((p, i) => p.topics.forEach(t => { const j = tpos.get(t.t); if (j != null && t.s >= min) cells.push({ p, t, i, j }); }));
    if (block && D.orders.cocluster) {   // block separators from the co-clustering
      const pc = D.orders.cocluster.persons || {}, tc = D.orders.cocluster.topics || {};
      const rb = people.map((p, i) => i).filter(i => i > 0 && pc[people[i].id] !== pc[people[i - 1].id]);
      const cb = topics.map((t, j) => j).filter(j => j > 0 && tc[topics[j].topic_id] !== tc[topics[j - 1].topic_id]);
      g.selectAll("line.rb").data(rb).join("line").attr("x1", left).attr("x2", left + topics.length * cw).attr("y1", i => top + i * rh).attr("y2", i => top + i * rh).attr("stroke", "currentColor").attr("stroke-opacity", 0.35);
      g.selectAll("line.cb").data(cb).join("line").attr("y1", top).attr("y2", top + people.length * rh).attr("x1", j => left + j * cw).attr("x2", j => left + j * cw).attr("stroke", "currentColor").attr("stroke-opacity", 0.35);
    }
    const tip = $("#tip");
    g.selectAll("rect.cell").data(cells).join("rect").attr("class", "cell").attr("x", c => left + c.j * cw + 1).attr("y", c => top + c.i * rh + 1).attr("width", cw - 2).attr("height", rh - 2)
      .attr("fill", c => macroColor(macroOf(c.t.t))).attr("fill-opacity", c => 0.25 + 0.75 * Math.min(1, c.t.s / 0.6)).style("cursor", "pointer")
      .on("mousemove", (e, c) => { tip.hidden = false; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px"; tip.textContent = `${c.p.name} — ${c.t.t} ${topicLabel(c.t.t)}: ${c.t.s.toFixed(2)} (${c.t.n} publ.)`; })
      .on("mouseleave", () => tip.hidden = true).on("click", (e, c) => location.hash = `#/person/${c.p.id}`);
    $("#mx").replaceChildren(svg.node());
  }
  $("#csv").addEventListener("click", () => downloadCSV("lui-matrise.csv", [["person", "institutt", ...lastTopics.map(t => t.topic_id)],
    ...lastPeople.map(p => { const v = personVector(p); return [p.name, unitLabel(p), ...lastTopics.map(t => (v.get(t.topic_id) ?? 0).toFixed(3))]; })]));
}

/* ---------------- graph (D3 force layout on canvas) ---------------- */
function viewGraph() {
  const app = $("#app");
  app.innerHTML = `<h1>Samarbeidsgraf</h1><div class="toolbar" id="bar"></div>
    <div class="legend" id="legend"></div>
    <div class="graph-wrap"><div id="cy" style="position:relative"><canvas id="gc" style="width:100%;height:100%;display:block;cursor:grab"></canvas>
      <div class="small muted no-print" style="position:absolute;left:8px;bottom:6px">scroll = zoom · dra bakgrunn = panorer · dra node = flytt · klikk node = sentrer med kontakter i ringer · dobbeltklikk bakgrunn = tilbake</div></div>
      <div class="panel" id="side"><p class="muted">Klikk på en node eller kant for detaljer.</p></div></div>
    <datalist id="pnames">${D.persons.map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`;
  const st = getQS();
  let sim = null, nodes = [], links = [], transform = d3.zoomIdentity, hover = null, selected = null, f = {}, commFilter = null, fitFn = () => {};
  const canvas = $("#gc"), ctx = canvas.getContext("2d");
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const unitColor = d3.scaleOrdinal(d3.schemeTableau10).domain(D.meta.units.map(u => u.unit_id));
  const commColor = d3.scaleOrdinal(d3.schemeTableau10);
  const nodeColor = p => f.color === "macro" ? macroColor(macroOf(p.topics[0]?.t)) : f.color === "community" ? commColor(idx.community.get(p.id) ?? -1) : unitColor(p.unit);

  let view = { width: 900, height: 600 };
  function size() { const b = canvas.getBoundingClientRect(); let w = Math.floor(b.width), h = Math.floor(b.height);
    if (w < 50 || h < 50) { w = Math.max(w, 900); h = Math.max(h, 600); }   // hidden/collapsed pane
    const dpr = devicePixelRatio || 1; canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); view = { width: w, height: h }; return view; }
  function draw() {
    const r = view; ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.restore();
    ctx.save();
    ctx.translate(transform.x, transform.y); ctx.scale(transform.k, transform.k);
    const fg = css("--fg") || "#222";
    const nbSel = new Set(); if (selected) { nbSel.add(selected.id); for (const l of links) { if (l.source.id === selected.id) nbSel.add(l.target.id); if (l.target.id === selected.id) nbSel.add(l.source.id); } }
    ctx.lineCap = "round";
    for (const l of links) {
      const dim = selected && !(l.source.id === selected.id || l.target.id === selected.id);
      ctx.globalAlpha = dim ? 0.06 : 0.45; ctx.strokeStyle = EDGE_COLOR[l.type]; ctx.lineWidth = (0.6 + Math.min(4, Math.log2(1 + l.w))) / Math.sqrt(transform.k);
      ctx.beginPath(); ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y); ctx.stroke();
      if (l.type === "cites") { const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len, tx = l.target.x - ux * l.target.r, ty = l.target.y - uy * l.target.r, a = 4 / Math.sqrt(transform.k);
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - ux * a * 2 - uy * a, ty - uy * a * 2 + ux * a); ctx.lineTo(tx - ux * a * 2 + uy * a, ty - uy * a * 2 - ux * a); ctx.closePath(); ctx.fillStyle = EDGE_COLOR[l.type]; ctx.fill(); }
    }
    ctx.globalAlpha = 1;
    for (const n of nodes) {
      const dim = selected && !nbSel.has(n.id);
      ctx.globalAlpha = dim ? 0.25 : 1; ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI); ctx.fillStyle = n.color; ctx.fill();
      if (n === hover || n === selected) { ctx.lineWidth = 2 / transform.k; ctx.strokeStyle = fg; ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
    const showAll = transform.k >= 1.6 || nodes.length <= 120;
    ctx.fillStyle = fg; ctx.font = `${10 / Math.max(0.6, transform.k)}px system-ui, sans-serif`; ctx.textAlign = "center";
    for (const n of nodes) if (showAll || n.r >= 12 || n === hover || n === selected || (selected && nbSel.has(n.id))) ctx.fillText(n.label, n.x, n.y + n.r + 10 / Math.max(0.6, transform.k));
    ctx.restore();
  }
  function nodeAt(px, py) { const [x, y] = transform.invert([px, py]); let best = null, bd = 1e9; for (const n of nodes) { const d = Math.hypot(n.x - x, n.y - y); if (d < Math.max(n.r + 3, 6) / transform.k && d < bd) { best = n; bd = d; } } return best; }
  function linkAt(px, py) { const [x, y] = transform.invert([px, py]); let best = null, bd = 4 / transform.k; for (const l of links) { const ax = l.source.x, ay = l.source.y, bx = l.target.x, by = l.target.y, L2 = (bx - ax) ** 2 + (by - ay) ** 2 || 1; const t = Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / L2)); const d = Math.hypot(x - (ax + t * (bx - ax)), y - (ay + t * (by - ay))); if (d < bd) { best = l; bd = d; } } return best; }
  const showNode = n => { const p = idx.person.get(n.id); $("#side").innerHTML = personCard(p) + `<p class="small">${EDGE_LABEL.coauthor}: ${links.filter(l => l.type === "coauthor" && (l.source.id === n.id || l.target.id === n.id)).length} · ${EDGE_LABEL.cites}: ${links.filter(l => l.type === "cites" && (l.source.id === n.id || l.target.id === n.id)).length}</p><p><a href="#/person/${esc(p.id)}">Åpne profil →</a> · <a href="#/graph?focus=${encodeURIComponent(p.name)}&et=${esc(f.et || "")}">fokuser →</a></p>`; };
  const showLink = async l => { const e = l.e, a = idx.person.get(e.s), b = idx.person.get(e.t);
    $("#side").innerHTML = `<b>${personLink(a)} – ${personLink(b)}</b><div style="color:${EDGE_COLOR[e.type]}">${EDGE_LABEL[e.type]}, vekt ${e.w}, ${e.n} belegg${e.y0 ? ` (${e.y0}–${e.y1})` : ""}</div><div id="edgeEv" class="muted small">henter …</div><p><a href="#/pair/${esc(e.s)}/${esc(e.t)}">Åpne par →</a></p>`;
    let ev = "";
    if (e.type === "coauthor") { const pubs = (await pubsFor(e.s)).filter(p => p.authors.some(x => x.p === e.t)).sort((x, y) => (y.year ?? 0) - (x.year ?? 0)); ev = pubs.map(p => `<div class="pub"><span class="t">${esc(p.title)}</span> <span class="muted">(${p.year ?? "?"})</span></div>`).join("") || "Felles publikasjoner vises på parsiden."; }
    else if (e.type === "cites") ev = `${e.n} sitering(er) mellom publikasjonene deres (se parsiden).`;
    else if (e.type === "shared_group") ev = e.ev.map(g => esc(idx.group.get(g)?.name || g)).join("<br>");
    else if (e.type === "shared_project") ev = e.ev.map(x => esc(idx.project.get(x)?.title_nb || x)).join("<br>");
    else ev = e.ev.map(t => topicChip(t)).join(" ");
    const out = $("#edgeEv"); if (out) out.innerHTML = ev; };

  // interaction: zoom/pan on background, drag nodes, click for details
  const zoom = d3.zoom().scaleExtent([0.15, 8]).filter(ev => ev.type === "wheel" || (!ev.button && !nodeAt(ev.offsetX, ev.offsetY))).on("zoom", ev => { transform = ev.transform; draw(); });
  d3.select(canvas).call(zoom).on("dblclick.zoom", () => { if (egoFit) resetLayout(); else sim?.on("end")?.(); });
  d3.select(canvas).call(d3.drag().container(canvas).subject(ev => nodeAt(ev.x, ev.y))
    .on("start", ev => { if (!ev.active) sim?.alphaTarget(0.25).restart(); ev.subject.fx = ev.subject.x; ev.subject.fy = ev.subject.y; canvas.style.cursor = "grabbing"; })
    .on("drag", ev => { const [x, y] = transform.invert([ev.x, ev.y]); ev.subject.fx = x; ev.subject.fy = y; })
    .on("end", ev => { if (!ev.active) sim?.alphaTarget(0); ev.subject.fx = null; ev.subject.fy = null; canvas.style.cursor = "grab"; }));
  canvas.addEventListener("mousemove", ev => { const h = nodeAt(ev.offsetX, ev.offsetY); if (h !== hover) { hover = h; canvas.title = h ? h.label : ""; draw(); } });
  canvas.addEventListener("click", ev => { const n = nodeAt(ev.offsetX, ev.offsetY); if (n) { selected = n; showNode(n); egoLayout(n); } else { const l = linkAt(ev.offsetX, ev.offsetY); if (l) { selected = null; showLink(l); } else selected = null; } draw(); });
  /** Centre a node and arrange its 1st/2nd/3rd-degree contacts on rings around it; farther nodes may leave the view. */
  let egoFit = null;
  function egoLayout(center) {
    if (!sim) return;
    const depth = new Map([[center.id, 0]]);
    const adj = new Map();
    for (const l of links) { (adj.get(l.source.id) || adj.set(l.source.id, []).get(l.source.id)).push(l.target.id); (adj.get(l.target.id) || adj.set(l.target.id, []).get(l.target.id)).push(l.source.id); }
    const q = [center.id];
    while (q.length) { const id = q.shift(), d = depth.get(id); if (d >= 3) continue; for (const nb of adj.get(id) || []) if (!depth.has(nb)) { depth.set(nb, d + 1); q.push(nb); } }
    for (const n of nodes) { n.fx = null; n.fy = null; }
    const cx = center.x, cy = center.y;
    center.fx = cx; center.fy = cy;
    const gap = 110 * (+f.spread || 1.5) / 1.5;
    const radiusOf = n => { const d = depth.get(n.id); return d == null ? gap * 5 : d * gap; };
    // let the rings dominate: weak links and repulsion while arranging, collide keeps nodes apart along each ring
    sim.force("radial", d3.forceRadial(radiusOf, cx, cy).strength(n => depth.has(n.id) ? 1 : 0.2))
       .force("x", null).force("y", null)
       .force("link", d3.forceLink(links).id(n => n.id).distance(gap).strength(0.03))
       .force("charge", d3.forceManyBody().strength(-25).distanceMax(gap * 1.2))
       .force("collide", d3.forceCollide().radius(n => n.r + 6).iterations(3));
    sim.alpha(1); sim.stop();
    for (let i = 0; i < 220; i++) sim.tick();
    egoFit = nodes.filter(n => depth.has(n.id));
    fitFn(false, egoFit);
    sim.alpha(0.15).restart();
  }
  function resetLayout() {
    if (!sim) return;
    for (const n of nodes) { n.fx = null; n.fy = null; }
    egoFit = null; selected = null;
    sim.force("radial", null);
    apply();
  }
  addEventListener("resize", () => { if (document.body.contains(canvas)) { size(); draw(); } });

  filterBar($("#bar"), [
    { id: "et", type: "multi", label: "kanttyper", options: Object.entries(EDGE_LABEL), value: "coauthor,cites" },
    { id: "unit", type: "select", label: "institutt", options: unitOptions() },
    { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
    { id: "macro", type: "select", label: "makrotema", options: macroOptions() },
    { id: "topic", type: "select", label: "tema", options: topicOptions() },
    { id: "theory", type: "select", label: "teori", options: theoryOptions() },
    { id: "group", type: "select", label: "forskningsgruppe", options: groupOptions() },
    { id: "y", type: "years" },
    { id: "minw", type: "range", label: "min. vekt", min: 0, max: 5, step: 0.25, value: 0.5 },
    { id: "minCore", type: "number", label: "min. vitensk. publ." },
    { id: "color", type: "select", label: "farge", all: "institutt", options: [["macro", "makrotema"], ["community", "fellesskap (Louvain)"]] },
    { id: "spread", type: "range", label: "spredning", min: 0.5, max: 3, step: 0.25, value: 1.5 },
    { id: "focus", type: "text", label: "fokuser på person …", list: "pnames" },
    { id: "hideIso", type: "check", label: "skjul isolerte", value: true },
    { id: "ext", type: "check", label: "ta med eksterne medforfattere (grå)" },
    SCOPE_FIELD(),
  ], state => { f = state; apply(); });
  $("#legend").addEventListener("click", ev => {
    const el = ev.target.closest("[data-legend]"); if (!el) return;
    const [kind, val] = el.dataset.legend.split(":");
    const set = (id, v) => { const c = $(id); if (!c) return; c.value = c.value === v ? "" : v; c.dispatchEvent(new Event("input", { bubbles: true })); };
    if (kind === "unit") set("#f_unit", val);
    else if (kind === "macro") set("#f_macro", val);
    else if (kind === "et") { const cb = $(`#f_et input[value="${val}"]`); if (cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event("input", { bubbles: true })); } }
    else if (kind === "comm") { commFilter = commFilter === +val ? null : +val; apply(); }
  });
  function apply() {
    const types = new Set((f.et || "coauthor,cites").split(",").map(s => s.trim()).filter(Boolean));
    const [y0, y1] = yearRange(f); const yearsSet = f.y0 || f.y1;
    const minw = +f.minw || 0, spread = +f.spread || 1.5;
    const focus = f.focus ? D.persons.find(p => p.name.toLowerCase() === f.focus.toLowerCase()) : null;
    let edges = D.edges.filter(e => types.has(e.type) && e.w >= minw && (!yearsSet || !e.y0 || overlaps([e.y0, e.y1], [y0, y1])));
    let people = D.persons.filter(p => personMatches(p, { ...f, y0: "", y1: "" }) || (focus && p.id === focus.id));
    if (yearsSet) people = people.filter(p => focus?.id === p.id || activeIn(p, y0, y1));
    if (commFilter != null) people = people.filter(p => (idx.community.get(p.id) ?? -1) === commFilter || focus?.id === p.id);
    let ids = new Set(people.map(p => p.id));
    if (f.ext) {   // external coauthors linked (by the chosen edge types) to the people shown
      const extra = new Set();
      for (const e of edges) { if (ids.has(e.s) && !ids.has(e.t)) extra.add(e.t); if (ids.has(e.t) && !ids.has(e.s)) extra.add(e.s); }
      for (const id of extra) { const p = idx.person.get(id); if (p && !isLui(p)) { ids.add(id); people.push(p); } }
    }
    if (focus) { const nb = new Set([focus.id]); for (const e of edges) { if (e.s === focus.id) nb.add(e.t); if (e.t === focus.id) nb.add(e.s); } ids = new Set([...ids].filter(i => nb.has(i))); people = D.persons.filter(p => ids.has(p.id)); }
    edges = edges.filter(e => ids.has(e.s) && ids.has(e.t));
    if (f.hideIso) { const deg = new Set(); edges.forEach(e => { deg.add(e.s); deg.add(e.t); }); people = people.filter(p => deg.has(p.id)); }
    // legend: every swatch is a toggle filter
    const item = (key, color, label, on) => `<span data-legend="${esc(key)}" class="${on ? "on" : ""}" title="klikk for å filtrere"><i style="background:${color}"></i>${esc(label)}</span>`;
    const commCounts = new Map(); for (const p of people) { const c = idx.community.get(p.id) ?? -1; commCounts.set(c, (commCounts.get(c) || 0) + 1); }
    $("#legend").innerHTML = (f.color === "macro" ? D.taxonomy.macro.map(m => item(`macro:${m.macro_id}`, macroColor(idx.macro.get(m.macro_id)), m.label_nb || m.label_en, f.macro === m.macro_id))
      : f.color === "community" ? [...commCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14).map(([c, n]) => item(`comm:${c}`, commColor(c), `fellesskap ${c} (${n})`, commFilter === c))
      : D.meta.units.filter(u => u.short_code !== "LUI").map(u => item(`unit:${u.unit_id}`, unitColor(u.unit_id), u.short_code, f.unit === u.unit_id))).join("") +
      Object.keys(EDGE_LABEL).map(t => item(`et:${t}`, types.has(t) ? EDGE_COLOR[t] : "transparent", EDGE_LABEL[t], types.has(t))).join("") +
      (f.scope || f.ext ? `<span><i style="background:#9a9a9a"></i>utenfor LUI</span>` : "") +
      (commFilter != null && f.color !== "community" ? `<span data-legend="comm:${commFilter}" class="on"><i style="background:${commColor(commFilter)}"></i>fellesskap ${commFilter} ×</span>` : "");
    // keep positions of nodes that survive a filter change so the layout stays calm
    const old = new Map(nodes.map(n => [n.id, n]));
    const r = size();
    nodes = people.map(p => { const o = old.get(p.id); return { id: p.id, label: p.name, color: isLui(p) ? nodeColor(p) : "#9a9a9a", r: isLui(p) ? 4 + 1.6 * Math.sqrt(p.nCore || 0) : 3 + Math.sqrt(p.nJoint || 1), x: o?.x ?? r.width / 2 + (Math.random() - 0.5) * r.width * 0.6, y: o?.y ?? r.height / 2 + (Math.random() - 0.5) * r.height * 0.6 }; });
    const byId = new Map(nodes.map(n => [n.id, n]));
    links = edges.map(e => ({ source: byId.get(e.s), target: byId.get(e.t), type: e.type, w: e.w, e }));
    selected = focus ? byId.get(focus.id) || null : null; hover = null;
    sim?.stop();
    const deg = new Map(); for (const l of links) { deg.set(l.source.id, (deg.get(l.source.id) || 0) + 1); deg.set(l.target.id, (deg.get(l.target.id) || 0) + 1); }
    const fit = (animate = true, subset = null) => { const fin = (subset || nodes).filter(n => isFinite(n.x) && isFinite(n.y)); if (!fin.length) return; const xs = fin.map(n => n.x), ys = fin.map(n => n.y); const x0 = Math.min(...xs) - 50, x1 = Math.max(...xs) + 50, y0 = Math.min(...ys) - 50, y1 = Math.max(...ys) + 50;
      const k = Math.min(4, 0.95 / Math.max((x1 - x0) / r.width, (y1 - y0) / r.height)); const t = d3.zoomIdentity.translate(r.width / 2 - k * (x0 + x1) / 2, r.height / 2 - k * (y0 + y1) / 2).scale(k);
      if (animate) d3.select(canvas).transition().duration(600).call(zoom.transform, t); else d3.select(canvas).call(zoom.transform, t); };
    fitFn = fit;
    sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(n => n.id).distance(l => (40 + 80 / (1 + Math.log2(1 + l.w))) * spread)
        .strength(l => Math.min(0.8, (0.3 + 0.1 * Math.log2(1 + l.w)) / Math.sqrt(Math.min(deg.get(l.source.id) || 1, deg.get(l.target.id) || 1)))))
      .force("charge", d3.forceManyBody().strength(n => -(60 + 4 * n.r) * spread).distanceMax(700 * spread).theta(0.9))
      .force("collide", d3.forceCollide().radius(n => n.r + 4).iterations(2))
      .force("x", d3.forceX(r.width / 2).strength(0.03 / spread))
      .force("y", d3.forceY(r.height / 2).strength(0.035 / spread))
      .alpha(1).alphaDecay(0.018).velocityDecay(0.3)
      .on("tick", draw).on("end", () => fit(true, egoFit));
    // warm up synchronously so the layout is settled at once (and works when requestAnimationFrame is paused)
    sim.stop();
    const warm = Math.max(60, Math.min(250, Math.floor(400000 / Math.max(1, links.length + 10 * nodes.length))));
    for (let i = 0; i < warm; i++) sim.tick();
    // connected components: keep small ones on a ring around the giant component instead of letting them drift to the edge
    const compOf = new Map(nodes.map(n => [n.id, n.id]));
    const find = x => { while (compOf.get(x) !== x) { compOf.set(x, compOf.get(compOf.get(x))); x = compOf.get(x); } return x; };
    for (const l of links) { const a = find(l.source.id), b = find(l.target.id); if (a !== b) compOf.set(a, b); }
    const comps = new Map(); for (const n of nodes) { const c = find(n.id); if (!comps.has(c)) comps.set(c, []); comps.get(c).push(n); }
    const ordered = [...comps.values()].sort((a, b) => b.length - a.length);
    if (ordered.length > 1 && ordered[0].length >= 3) {
      const giant = ordered[0], small = ordered.slice(1);
      const radii = small.map(c => 10 + 9 * Math.sqrt(c.length));
      for (const c of small) for (const n of c) n.small = true;
      // place the small components on a ring around the giant component's current extent
      const placeRing = () => {
        const cx = d3.mean(giant, n => n.x), cy = d3.mean(giant, n => n.y);
        const R = Math.max(80, d3.quantile(giant.map(n => Math.hypot(n.x - cx, n.y - cy)).filter(isFinite).sort(d3.ascending), 0.9) || 80);
        let ring = R + 35, ang = -Math.PI / 2, start = 0;
        const steps = radii.map(r => (2 * r + 14) / ring);
        const total = d3.sum(steps), scale = total < 2 * Math.PI ? 2 * Math.PI / total : 1;
        for (let i = 0; i < small.length; i++) {
          const step = steps[i] * scale;
          if (scale === 1 && i > start && ang + Math.PI / 2 + step > 2 * Math.PI) { ring += 2 * Math.max(...radii.slice(start, i)) + 30; ang = -Math.PI / 2; start = i; }
          if (!isFinite(ring)) ring = R + 35;
          ang += step / 2;
          const tx = cx + ring * Math.cos(ang), ty = cy + ring * Math.sin(ang);
          for (const n of small[i]) { n.tx = tx; n.ty = ty; }
          ang += step / 2;
        }
      };
      // targets must exist before the forces read them; distanceMax takes a number
      placeRing(); for (const c of small) for (const n of c) { n.x = n.tx + (Math.random() - 0.5) * 20; n.y = n.ty + (Math.random() - 0.5) * 20; }
      const setForces = () => sim
        .force("x", d3.forceX(n => n.small ? n.tx : r.width / 2).strength(n => n.small ? 0.35 : 0.03 / spread))
        .force("y", d3.forceY(n => n.small ? n.ty : r.height / 2).strength(n => n.small ? 0.35 : 0.035 / spread))
        .force("charge", d3.forceManyBody().strength(n => n.small ? -15 : -(60 + 4 * n.r) * spread).distanceMax(700 * spread).theta(0.9));
      setForces();
      sim.alpha(0.5); for (let i = 0; i < 60; i++) sim.tick();
      // the giant settles during these ticks, so re-place the ring on its final extent before the last ticks
      placeRing(); setForces();
      sim.alpha(0.3); for (let i = 0; i < 50; i++) sim.tick();
    }
    fit(false);
    sim.alpha(0.2).restart();
    if (selected) showNode(selected);
    $("#f_count").textContent = `${people.length} personer, ${edges.length} relasjoner`;
    draw();
  }
}

/* ---------------- scoring ---------------- */
function viewScore() {
  const app = $("#app");
  app.innerHTML = `<h1>Finn samarbeidspartnere</h1>
    <p class="muted">Velg utgangspunkt (en person eller en idé i fritekst), avgrens kandidatene og vekt kriteriene. Resultatet er en rangert liste du kan skrive ut som PDF.</p>
    <div class="toolbar" id="bar"></div>
    <div class="card" id="weights">
      ${[["wTopic", "Tematisk overlapp", 1], ["wTheory", "Felles teori", 0.5], ["wMethod", "Komplementær metode", 0.3], ["wNew", "Bonus: ikke medforfattere før", 0.5], ["wUnit", "Bonus: annet institutt", 0.2], ["wActive", "Nylig aktivitet (siste 5 år)", 0.3]]
        .map(([id, lab, v]) => `<div class="slider"><span>${lab}</span><input type="range" id="${id}" min="0" max="1" step="0.1" value="${getQS()[id] ?? v}"><span id="${id}v">${getQS()[id] ?? v}</span></div>`).join("")}
    </div>
    <div class="toolbar no-print"><button type="button" id="csv">Last ned (CSV)</button></div>
    <div id="res"></div><datalist id="pnames2">${D.persons.filter(p => p.listed).map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`;
  const ideaVector = text => {
    const words = text.toLowerCase().split(/[^a-zæøåäöü0-9-]+/).filter(w => w.length > 2);
    const v = new Map();
    for (const t of D.taxonomy.topics) { const hay = [t.topic_id, t.label_nb, t.label_en, t.definition_nb, t.definition_en, ...(t.keywords || [])].join(" ").toLowerCase(); let s = 0; for (const w of words) if (hay.includes(w)) s += 1; if (s) v.set(t.topic_id, s); }
    const kwHits = new Map();
    for (const p of D.persons) { let s = 0; const hay = ((p.keywords || []).join(" ") + " " + (p.bio || "") + " " + (p.topics || []).map(t => topicLabel(t.t)).join(" ")).toLowerCase(); for (const w of words) if (hay.includes(w)) s += 1; if (s) kwHits.set(p.id, s / words.length); }
    return { v, kwHits };
  };
  let current = [], state = {};
  const off = new Set((getQS().off || "").split(",").filter(Boolean));          // topics switched off by the user
  const tChip = (id, extra = "") => { const m = macroOf(id); return `<a class="chip m toggle ${off.has(id) ? "off" : ""}" data-toggle="${esc(id)}" href="#/topic/${esc(id)}" style="background:${macroColor(m)}" title="${esc(id)} · klikk for å slå av/på i sammenligningen · ctrl/cmd-klikk åpner temaet">${esc(topicLabel(id))}${extra}</a>`; };
  $("#app").addEventListener("click", ev => { const a = ev.target.closest("a.toggle[data-toggle]"); if (!a || ev.ctrlKey || ev.metaKey) return; ev.preventDefault(); const id = a.dataset.toggle; off.has(id) ? off.delete(id) : off.add(id); run(); });
  const run = () => {
    const f = state;
    const W = {}; ["wTopic", "wTheory", "wMethod", "wNew", "wUnit", "wActive"].forEach(id => { W[id] = +$("#" + id).value; $("#" + id + "v").textContent = W[id]; });
    const who = f.who ? D.persons.find(p => p.name.toLowerCase() === f.who.toLowerCase()) : null;
    const idea = (f.idea || "").trim();
    if (!who && !idea) { $("#res").innerHTML = '<p class="muted">Velg en person eller skriv en idé.</p>'; return; }
    let base, baseTh = new Set(), baseMe = new Set(), nb = new Map(), kwHits = new Map();
    if (who) { base = personVector(who); baseTh = new Set(who.theories.map(t => t.t)); baseMe = new Set(who.methods.map(t => t.t)); nb = neighbours(who); }
    else { const iv = ideaVector(idea); base = iv.v; kwHits = iv.kwHits; }
    const baseAll = new Map(base);
    for (const id of off) base.delete(id);
    setQS({ ...f, ...W, off: [...off].join(",") });
    const rows = D.persons.filter(p => p.id !== who?.id && personMatches(p, f)).map(p => {
      const topic = base.size ? cosine(base, personVector(p)) : 0;
      const theory = baseTh.size ? p.theories.filter(t => baseTh.has(t.t)).length / Math.max(1, baseTh.size) : 0;
      const method = baseMe.size ? p.methods.filter(t => !baseMe.has(t.t)).length / Math.max(1, p.methods.length) : 0;
      const joint = who ? (nb.get(p.id)?.coauthor?.n || 0) : null;
      const isNew = who ? (joint ? 0 : 1) : 0;
      const otherUnit = who ? (p.unit !== who.unit ? 1 : 0) : 0;
      const active = p.years && p.years[1] >= THIS_YEAR - 5 ? 1 : 0;
      const kw = kwHits.get(p.id) || 0;
      const rel = topic > 0.2 || kw > 0 ? 1 : 0;
      const score = W.wTopic * (topic + kw) + W.wTheory * theory + W.wMethod * method * rel + W.wNew * isNew * rel + W.wUnit * otherUnit * rel + W.wActive * active * rel;
      return { p, score, topic, theory, method, isNew, kw, joint };
    }).filter(r => r.score > 0.15).sort((a, b) => b.score - a.score).slice(0, 50);
    current = rows;
    const baseTopics = [...baseAll.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15);
    $("#res").innerHTML = `<h2>Forslag${who ? ` for ${esc(who.name)}` : ` for «${esc(idea)}»`} (${rows.length})</h2>
      <p class="small muted">Tema som brukes i sammenligningen – klikk på en flis for å slå den av (strek gjennom) eller på igjen:</p>
      <div class="chips" style="margin-bottom:.6rem">${baseTopics.map(([t, v]) => tChip(t, ` ${v.toFixed(2)}`)).join("") || '<span class="muted">ingen temaprofil</span>'}</div>
      <table class="tbl"><tr><th>#</th><th>Person</th><th>Institutt</th><th>Felles / relevante tema</th><th class="num" title="Antall arbeider (inntil 30 forfattere) der utgangspersonen og kandidaten er medforfattere">Felles publ. ⓘ</th><th class="num" title="${esc(HELP.similarity)}">Tema ⓘ</th><th class="num" title="${esc(HELP.theoryOverlap)}">Teori ⓘ</th><th class="num" title="${esc(HELP.totalScore)}">Score ⓘ</th><th></th></tr>
      ${rows.map((r, i) => { const pv = personVector(r.p); const shared = [...base.keys()].filter(k => pv.has(k)).sort((a, b) => pv.get(b) - pv.get(a)).slice(0, 3);
        return `<tr><td>${i + 1}</td><td>${personLink(r.p)}<div class="small muted">${esc(r.p.title || "")}${who && !r.isNew ? " · medforfattere" : ""}</div></td><td>${esc(unitLabel(r.p))}</td><td><div class="chips">${shared.map(t => tChip(t)).join("")}</div></td><td class="num">${r.joint == null ? "–" : r.joint}</td><td class="num">${r.topic.toFixed(2)}</td><td class="num">${r.theory.toFixed(2)}</td><td class="num"><b>${r.score.toFixed(2)}</b></td><td>${who ? `<a class="small" href="#/pair/${esc(who.id)}/${esc(r.p.id)}">par</a>` : ""}</td></tr>`; }).join("")}</table>`;
  };
  filterBar($("#bar"), [
    { id: "who", type: "text", label: "person (navn) …", list: "pnames2", width: 220 },
    { id: "idea", type: "text", label: "… eller beskriv en idé med nøkkelord (f.eks. KI vurdering skriving barnetrinn)", width: 420 },
    { id: "unit", type: "select", label: "institutt", options: unitOptions() },
    { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
    { id: "macro", type: "select", label: "makrotema", options: macroOptions() },
    { id: "theory", type: "select", label: "teori", options: theoryOptions() },
    { id: "method", type: "select", label: "metode", options: methodOptions() },
    { id: "y", type: "years" },
    { id: "minCore", type: "number", label: "min. vitensk. publ." },
    SCOPE_FIELD(),
  ], f => { state = f; run(); });
  document.querySelectorAll("#weights input").forEach(x => x.addEventListener("input", run));
  $("#csv").addEventListener("click", () => downloadCSV("lui-forslag.csv", [["rang", "navn", "institutt", "tittel", "felles_publ", "tema", "teori", "score"], ...current.map((r, i) => [i + 1, r.p.name, unitLabel(r.p), r.p.title, r.joint ?? "", r.topic.toFixed(2), r.theory.toFixed(2), r.score.toFixed(2)])]));
}

/* ---------------- seriation: Louvain on the filtered graph, spectral block ordering, best-of candidates ---------------- */
function rcmOrder(nodes, adj) {
  const visited = new Set(), order = [];
  const deg = id => [...(adj.get(id) || new Map()).keys()].filter(x => nodes.has(x)).length;
  for (const start of [...nodes].sort((a, b) => deg(a) - deg(b))) {
    if (visited.has(start)) continue;
    visited.add(start);
    const q = [start];
    while (q.length) {
      const n = q.shift(); order.push(n);
      for (const x of [...(adj.get(n) || new Map()).keys()].filter(x => nodes.has(x) && !visited.has(x)).sort((a, b) => deg(a) - deg(b))) { visited.add(x); q.push(x); }
    }
  }
  return order.reverse();
}
/** Weighted adjacency Map(id -> Map(id -> w)) restricted to ids. */
function buildAdj(ids, edges) {
  const idset = new Set(ids), adj = new Map(ids.map(i => [i, new Map()]));
  for (const e of edges) { if (!idset.has(e.s) || !idset.has(e.t) || e.s === e.t) continue; adj.get(e.s).set(e.t, (adj.get(e.s).get(e.t) || 0) + e.w); adj.get(e.t).set(e.s, (adj.get(e.t).get(e.s) || 0) + e.w); }
  return adj;
}
/** Multi-level Louvain modularity optimisation. Returns Map(id -> community index). */
function louvain(ids, adj, seed = 1) {
  let rnd = seed; const rand = () => (rnd = (rnd * 1664525 + 1013904223) % 4294967296) / 4294967296;
  // current graph: node -> Map(neighbour -> w); membership of original ids
  let graph = new Map(ids.map(i => [i, new Map(adj.get(i) || [])]));
  let members = new Map(ids.map(i => [i, [i]]));
  for (let level = 0; level < 10; level++) {
    const nodesL = [...graph.keys()];
    const k = new Map(nodesL.map(n => [n, [...graph.get(n).values()].reduce((a, b) => a + b, 0)]));
    const m2 = [...k.values()].reduce((a, b) => a + b, 0) || 1;     // 2m
    const comm = new Map(nodesL.map(n => [n, n]));
    const tot = new Map(nodesL.map(n => [n, k.get(n)]));
    let moved = true, rounds = 0;
    while (moved && rounds++ < 50) {
      moved = false;
      const order = nodesL.slice().sort(() => rand() - 0.5);
      for (const n of order) {
        const cn = comm.get(n), kn = k.get(n);
        const wTo = new Map();
        for (const [nb, w] of graph.get(n)) { const c = comm.get(nb); wTo.set(c, (wTo.get(c) || 0) + w); }
        tot.set(cn, tot.get(cn) - kn); comm.set(n, null);
        let best = cn, bestGain = (wTo.get(cn) || 0) - tot.get(cn) * kn / m2;
        for (const [c, w] of wTo) { const gain = w - tot.get(c) * kn / m2; if (gain > bestGain + 1e-12) { bestGain = gain; best = c; } }
        comm.set(n, best); tot.set(best, tot.get(best) + kn);
        if (best !== cn) moved = true;
      }
    }
    const groups = new Map();
    for (const n of nodesL) { const c = comm.get(n); if (!groups.has(c)) groups.set(c, []); groups.get(c).push(n); }
    if (groups.size === nodesL.length) break;                      // no aggregation happened
    const newGraph = new Map(), newMembers = new Map();
    for (const [c, ns] of groups) {
      newMembers.set(c, ns.flatMap(n => members.get(n)));
      const row = new Map();
      for (const n of ns) for (const [nb, w] of graph.get(n)) { const cb = comm.get(nb); if (cb !== c) row.set(cb, (row.get(cb) || 0) + w); }
      newGraph.set(c, row);
    }
    graph = newGraph; members = newMembers;
  }
  const out = new Map(); let ci = 0;
  for (const ns of members.values()) { for (const n of ns) out.set(n, ci); ci++; }
  return out;
}
/** Fiedler-vector ordering of a small weighted graph (power iteration on the normalised Laplacian). */
function spectralOrder(list, adj) {
  const n = list.length;
  if (n <= 3) return list.slice();
  const pos = new Map(list.map((id, i) => [id, i]));
  const W = Array.from({ length: n }, () => new Float64Array(n));
  for (let i = 0; i < n; i++) for (const [nb, w] of adj.get(list[i]) || []) { const j = pos.get(nb); if (j != null) W[i][j] += w; }
  const d = W.map(r => r.reduce((a, b) => a + b, 0) + 1e-9), sd = d.map(Math.sqrt);
  const v1 = sd.map(x => x / Math.hypot(...sd));                     // trivial eigenvector of the normalised Laplacian
  let v = new Float64Array(n).map(() => Math.random() - 0.5);
  const proj = x => { let dot = 0; for (let i = 0; i < n; i++) dot += x[i] * v1[i]; for (let i = 0; i < n; i++) x[i] -= dot * v1[i]; };
  // iterate M = 2I - L_norm (largest eigenvector orthogonal to v1 = Fiedler vector)
  for (let it = 0; it < 300; it++) {
    proj(v);
    const nv = new Float64Array(n);
    for (let i = 0; i < n; i++) { let s = 0; const Wi = W[i]; for (let j = 0; j < n; j++) if (Wi[j]) s += Wi[j] / (sd[i] * sd[j]) * v[j]; nv[i] = v[i] + s; }
    const norm = Math.hypot(...nv) || 1; for (let i = 0; i < n; i++) v[i] = nv[i] / norm;
  }
  return list.map((id, i) => [id, v[i] / sd[i]]).sort((a, b) => a[1] - b[1]).map(x => x[0]);
}
/** Linear arrangement cost: sum w·|pos(i)-pos(j)| / sum w (lower = more block-diagonal). */
function arrangementCost(order, adj) {
  const pos = new Map(order.map((id, i) => [id, i])); let num = 0, den = 0;
  for (const [a, row] of adj) for (const [b, w] of row) if (a < b && pos.has(a) && pos.has(b)) { num += w * Math.abs(pos.get(a) - pos.get(b)); den += w; }
  return den ? num / den : 0;
}
function components(ids, adj) {
  const seen = new Set(), comps = [];
  for (const id of ids) { if (seen.has(id)) continue; const comp = [], q = [id]; seen.add(id); while (q.length) { const n = q.shift(); comp.push(n); for (const x of adj.get(n)?.keys() || []) if (!seen.has(x)) { seen.add(x); q.push(x); } } comps.push(comp); }
  return comps.sort((a, b) => b.length - a.length);
}
/** Order blocks so that strongly connected blocks are adjacent, then order inside each block. */
function orderByBlocks(comp, comm, adj) {
  const blocks = new Map();
  for (const id of comp) { const c = comm.get(id) ?? -1; if (!blocks.has(c)) blocks.set(c, []); blocks.get(c).push(id); }
  const keys = [...blocks.keys()];
  // community-level graph
  const cadj = new Map(keys.map(k => [k, new Map()]));
  for (const id of comp) for (const [nb, w] of adj.get(id) || []) { const a = comm.get(id) ?? -1, b = comm.get(nb) ?? -1; if (a !== b && cadj.has(b)) cadj.get(a).set(b, (cadj.get(a).get(b) || 0) + w); }
  const keyOrder = keys.length > 3 ? spectralOrder(keys, cadj) : keys.sort((a, b) => blocks.get(b).length - blocks.get(a).length);
  const out = [];
  for (const k of keyOrder) { const b = blocks.get(k); out.push(...(b.length <= 400 ? spectralOrder(b, adj) : rcmOrder(new Set(b), adj))); }
  return out;
}
/** Group key for the top level of the hierarchy: department for LUI staff, category for others. */
const unitKeyOf = p => p.listed || !p.type || p.type === "former_lui" ? (p.unit || "LUI") : p.type;
const unitKeyLabel = k => idx.unit.get(k)?.short_code || EXT_LABEL[k] || k;
/** Hierarchical: institutes (ordered by mutual connectivity) -> Louvain communities within each institute -> spectral order. */
function seriateHierarchical(ids, adj) {
  const groups = new Map();
  for (const id of ids) { const k = unitKeyOf(idx.person.get(id) || {}); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(id); }
  const keys = [...groups.keys()];
  const gadj = new Map(keys.map(k => [k, new Map()]));
  const keyOf = new Map(); for (const [k, members] of groups) for (const id of members) keyOf.set(id, k);
  for (const id of ids) for (const [nb, w] of adj.get(id) || []) { const a = keyOf.get(id), b = keyOf.get(nb); if (a !== b && b != null) gadj.get(a).set(b, (gadj.get(a).get(b) || 0) + w); }
  const keyOrder = keys.length > 3 ? spectralOrder(keys, gadj) : keys.sort((a, b) => groups.get(b).length - groups.get(a).length);
  const comm = new Map(); const order = [];
  for (const k of keyOrder) {
    const members = groups.get(k);
    const sub = new Map(members.map(id => [id, new Map([...(adj.get(id) || [])].filter(([nb]) => keyOf.get(nb) === k))]));
    const comps = components(members, sub);
    const lv = louvain(members, sub, 1);
    for (const comp of comps) {
      const ordered = comp.length <= 2 ? comp : orderByBlocks(comp, lv, sub);
      for (const id of ordered) { comm.set(id, `${k}|${lv.get(id)}`); order.push(id); }
    }
  }
  return { order, comm };
}
/** Order person ids so that the filtered relation matrix is as block-diagonal as possible. */
let lastSeriation = { cost: null, communities: null, method: "", units: null };
function seriate(ids, edges, mode = "block") {
  const people = ids.map(id => idx.person.get(id)).filter(Boolean);
  if (mode === "name") return people.sort((a, b) => a.name.localeCompare(b.name, "nb")).map(p => p.id);
  if (mode === "unit") return people.sort((a, b) => (a.unit || "").localeCompare(b.unit || "") || a.name.localeCompare(b.name, "nb")).map(p => p.id);
  const adj = buildAdj(ids, edges);
  if (mode === "block") {   // default: hierarchical institute -> community -> spectral
    const h = seriateHierarchical(ids, adj);
    lastSeriation = { cost: arrangementCost(h.order, adj), communities: h.comm, method: "hierarkisk: institutt → fellesskap → spektral", units: new Map(h.order.map(id => [id, unitKeyOf(idx.person.get(id) || {})])) };
    return h.order;
  }
  if (mode === "global") { const o = people.sort((a, b) => (idx.personOrder.get(a.id) ?? 1e9) - (idx.personOrder.get(b.id) ?? 1e9)).map(p => p.id); lastSeriation = { cost: arrangementCost(o, adj), communities: idx.community, method: "global", units: null }; return o; }
  const comps = components(ids, adj);
  const candidates = [];
  // (a) Louvain on the filtered graph (two seeds) + spectral ordering of and within blocks
  for (const seed of [1, 7]) {
    const comm = louvain(ids, adj, seed);
    const order = comps.flatMap(c => c.length <= 2 ? c : orderByBlocks(c, comm, adj));
    candidates.push({ order, comm, method: `louvain(seed ${seed})+spectral` });
  }
  // (b) faculty-wide communities + spectral inside
  candidates.push({ order: comps.flatMap(c => c.length <= 2 ? c : orderByBlocks(c, idx.community, adj)), comm: idx.community, method: "globale fellesskap+spectral" });
  // (c) plain spectral per component
  candidates.push({ order: comps.flatMap(c => c.length <= 400 ? spectralOrder(c, adj) : rcmOrder(new Set(c), adj)), comm: candidates[0].comm, method: "spectral" });
  for (const c of candidates) c.cost = arrangementCost(c.order, adj);
  candidates.sort((a, b) => a.cost - b.cost);
  lastSeriation = { cost: candidates[0].cost, communities: candidates[0].comm, method: candidates[0].method, units: null };
  return candidates[0].order;
}
function unitBoundaries(order) {
  const u = lastSeriation.units, b = [];
  if (!u) return b;
  for (let i = 1; i < order.length; i++) if (u.get(order[i]) !== u.get(order[i - 1])) b.push(i);
  return b;
}
function blockBoundaries(order) {
  const comm = lastSeriation.communities || idx.community, b = [];
  for (let i = 1; i < order.length; i++) if ((comm.get(order[i]) ?? -1) !== (comm.get(order[i - 1]) ?? -1)) b.push(i);
  return b;
}

/* ---------------- relational matrix (person x person) ---------------- */
function viewRelMatrix() {
  const app = $("#app");
  app.innerHTML = `<h1>Relasjonsmatrise: personer × personer</h1>
    <p class="muted">Hver celle er en relasjon (medforfatterskap, sitering, felles gruppe/prosjekt eller tematisk likhet). Standardrekkefølgen er hierarkisk: institutter (ordnet etter hvor sterkt de henger sammen) → Louvain-fellesskap innenfor hvert institutt → spektral ordning innen hvert fellesskap, slik at hvert institutt og hvert fellesskap er en sammenhengende blokk langs diagonalen. Tykke linjer og fargebånd markerer institutter, tynne linjer fellesskap. «Flat blokkstruktur» optimaliserer i stedet hele utvalget under ett (laveste arrangementskostnad av flere kandidater).</p>
    <div class="toolbar" id="bar"></div>
    <div class="legend">${Object.entries(EDGE_LABEL).map(([k, v]) => `<span><i style="background:${EDGE_COLOR[k]}"></i>${v}</span>`).join("")}</div>
    <div class="toolbar no-print"><button type="button" id="csv">Last ned matrise (CSV)</button></div>
    <div class="matrix-wrap" id="mx"></div><div class="tooltip" id="tip" hidden></div>`;
  let lastOrder = [], lastCells = [];
  const st = getQS();
  filterBar($("#bar"), [
    { id: "et", type: "multi", label: "kanttyper (brukes i klyngingen)", options: Object.entries(EDGE_LABEL), value: "coauthor,cites,shared_project" },
    { id: "unit", type: "select", label: "institutt", options: unitOptions() },
    { id: "type", type: "select", label: "stilling", options: [["academic", "vitenskapelig"], ["admin", "administrativ"], ["former_lui", "tidligere/annen LUI"], ["oslomet", "annen OsloMet"], ["external", "ekstern"]] },
    { id: "macro", type: "select", label: "makrotema", options: macroOptions() },
    { id: "topic", type: "select", label: "tema", options: topicOptions() },
    { id: "theory", type: "select", label: "teori", options: theoryOptions() },
    { id: "group", type: "select", label: "forskningsgruppe", options: groupOptions() },
    { id: "y", type: "years" },
    { id: "minw", type: "range", label: "min. vekt", min: 0, max: 5, step: 0.25, value: 0 },
    { id: "minCore", type: "number", label: "min. vitensk. publ." },
    { id: "order", type: "select", label: "rekkefølge", all: "hierarkisk: institutt → fellesskap → spektral", options: [["flat", "flat blokkstruktur (Louvain på utvalget)"], ["global", "blokkstruktur (hele fakultetet)"], ["unit", "institutt, alfabetisk"], ["name", "navn"]] },
    { id: "hideIso", type: "check", label: "skjul personer uten relasjoner", value: true },
    SCOPE_FIELD(),
  ], f => {
    const types = new Set((f.et || "").split(",").map(x => x.trim()).filter(Boolean));
    const [y0, y1] = yearRange(f); const yearsSet = f.y0 || f.y1;
    let people = D.persons.filter(p => personMatches(p, { ...f, y0: "", y1: "" }));
    if (yearsSet) people = people.filter(p => activeIn(p, y0, y1));
    let ids = new Set(people.map(p => p.id));
    let edges = D.edges.filter(e => types.has(e.type) && e.w >= (+f.minw || 0) && ids.has(e.s) && ids.has(e.t) && (!yearsSet || !e.y0 || overlaps([e.y0, e.y1], [y0, y1])));
    if (f.hideIso) { const deg = new Set(); edges.forEach(e => { deg.add(e.s); deg.add(e.t); }); ids = new Set([...ids].filter(i => deg.has(i))); }
    const order = seriate([...ids], edges, f.order === "flat" ? "flatblock" : (f.order || "block"));
    const pos = new Map(order.map((id, i) => [id, i]));
    const cells = [];
    for (const e of edges) {
      const i = pos.get(e.s), j = pos.get(e.t);
      cells.push({ i, j, e }); if (e.type !== "cites") cells.push({ i: j, j: i, e });
    }
    lastOrder = order; lastCells = cells;
    const nBlocks = new Set(order.map(id => (lastSeriation.communities || idx.community).get(id) ?? -1)).size;
    $("#f_count").textContent = `${order.length} personer, ${edges.length} relasjoner · ${nBlocks} blokker · arrangementskostnad ${lastSeriation.cost != null ? lastSeriation.cost.toFixed(1) : "–"} (${lastSeriation.method || f.order || "blokk"})`;
    const cw = Math.max(6, Math.min(14, Math.floor(900 / Math.max(1, order.length))));
    const longest = Math.max(8, ...order.map(id => (idx.person.get(id)?.name || id).length));
    const left = Math.min(420, 16 + 6.3 * longest), top = Math.min(460, 24 + 6.0 * longest);
    const w = left + order.length * cw + 10, h = top + order.length * cw + 10;
    const svg = d3.create("svg").attr("width", w).attr("height", h);
    const g = svg.append("g");
    const showLabels = cw >= 8;
    const commMap = lastSeriation.communities || idx.community;
    const comm = id => commMap.get(id) ?? -1;
    const commColor = d3.scaleOrdinal(d3.schemeTableau10);
    const unitColorM = d3.scaleOrdinal(d3.schemeTableau10).domain(D.meta.units.map(u => u.unit_id));
    const labelColor = id => lastSeriation.units ? unitColorM(lastSeriation.units.get(id)) : commColor(comm(id));
    g.selectAll("text.col").data(order).join("text").attr("class", "col").attr("transform", (id, i) => `translate(${left + i * cw + cw / 2 + 3},${top - 8}) rotate(-90)`)
      .attr("fill", id => labelColor(id)).text(id => showLabels ? (idx.person.get(id)?.name || id) : "").style("cursor", "pointer").on("click", (e, id) => location.hash = `#/person/${id}`);
    g.selectAll("text.row").data(order).join("text").attr("class", "row").attr("x", left - 4).attr("y", (id, i) => top + i * cw + cw - 2).attr("text-anchor", "end")
      .attr("fill", id => labelColor(id)).text(id => showLabels ? (idx.person.get(id)?.name || id) : "").style("cursor", "pointer").on("click", (e, id) => location.hash = `#/person/${id}`);
    const bounds = blockBoundaries(order);
    const ub = unitBoundaries(order);
    // institute bands along both axes (hierarchical mode)
    if (lastSeriation.units) {
      const runs = []; let startI = 0;
      for (let i = 1; i <= order.length; i++) if (i === order.length || lastSeriation.units.get(order[i]) !== lastSeriation.units.get(order[startI])) { runs.push([startI, i, lastSeriation.units.get(order[startI])]); startI = i; }
      g.selectAll("rect.ub").data(runs).join("rect").attr("x", left - (left - 6)).attr("y", d => top + d[0] * cw).attr("width", 4).attr("height", d => (d[1] - d[0]) * cw).attr("fill", d => unitColorM(d[2]));
      g.selectAll("rect.ubt").data(runs).join("rect").attr("y", top - (top - 6)).attr("x", d => left + d[0] * cw).attr("height", 4).attr("width", d => (d[1] - d[0]) * cw).attr("fill", d => unitColorM(d[2]));
      g.selectAll("text.ul").data(runs.filter(d => (d[1] - d[0]) * cw > 24)).join("text").attr("class", "ul").attr("x", 10).attr("y", d => top + d[0] * cw + 10).attr("font-weight", "600").attr("fill", d => unitColorM(d[2])).text(d => unitKeyLabel(d[2]));
      g.selectAll("line.ub").data(ub).join("line").attr("x1", 6).attr("x2", left + order.length * cw).attr("y1", i => top + i * cw).attr("y2", i => top + i * cw).attr("stroke", "currentColor").attr("stroke-opacity", 0.8).attr("stroke-width", 1.5);
      g.selectAll("line.uc").data(ub).join("line").attr("y1", 6).attr("y2", top + order.length * cw).attr("x1", i => left + i * cw).attr("x2", i => left + i * cw).attr("stroke", "currentColor").attr("stroke-opacity", 0.8).attr("stroke-width", 1.5);
    }
    g.selectAll("line.b").data(bounds).join("line").attr("class", "b").attr("x1", left).attr("x2", left + order.length * cw).attr("y1", i => top + i * cw).attr("y2", i => top + i * cw).attr("stroke", "currentColor").attr("stroke-opacity", 0.35);
    g.selectAll("line.c").data(bounds).join("line").attr("class", "c").attr("y1", top).attr("y2", top + order.length * cw).attr("x1", i => left + i * cw).attr("x2", i => left + i * cw).attr("stroke", "currentColor").attr("stroke-opacity", 0.35);
    g.append("rect").attr("x", left).attr("y", top).attr("width", order.length * cw).attr("height", order.length * cw).attr("fill", "none").attr("stroke", "currentColor").attr("stroke-opacity", 0.2);
    const tip = $("#tip");
    g.selectAll("rect.cell").data(cells).join("rect").attr("class", "cell").attr("x", c => left + c.j * cw + 0.5).attr("y", c => top + c.i * cw + 0.5).attr("width", cw - 1).attr("height", cw - 1)
      .attr("fill", c => EDGE_COLOR[c.e.type]).attr("fill-opacity", c => 0.35 + 0.65 * Math.min(1, c.e.w / 3)).style("cursor", "pointer")
      .on("mousemove", (ev, c) => { tip.hidden = false; tip.style.left = ev.clientX + 12 + "px"; tip.style.top = ev.clientY + 12 + "px"; tip.textContent = `${idx.person.get(order[c.i])?.name} – ${idx.person.get(order[c.j])?.name}: ${EDGE_LABEL[c.e.type]} (vekt ${c.e.w}, ${c.e.n})${c.e.y0 ? ` ${c.e.y0}–${c.e.y1}` : ""}`; })
      .on("mouseleave", () => tip.hidden = true).on("click", (ev, c) => location.hash = `#/pair/${order[c.i]}/${order[c.j]}`);
    $("#mx").replaceChildren(svg.node());
  });
  $("#csv").addEventListener("click", () => {
    const n = lastOrder.length, M = Array.from({ length: n }, () => Array(n).fill(0));
    for (const c of lastCells) M[c.i][c.j] += c.e.w;
    downloadCSV("lui-relasjonsmatrise.csv", [["", ...lastOrder.map(id => idx.person.get(id)?.name)], ...lastOrder.map((id, i) => [idx.person.get(id)?.name, ...M[i].map(v => v ? v.toFixed(2) : "")])]);
  });
}

/* ---------------- about ---------------- */
function viewAbout() {
  const n = D.persons.filter(p => p.listed).length;
  $("#app").innerHTML = `<h1>Om LUI forskningskart</h1>
    <p>Kartet viser forskningsinteresser, samarbeid og siteringer for ansatte ved ${esc(D.meta.faculty)}. Formålet er å gjøre det lettere å finne kolleger å samarbeide med, spørre om råd eller utvikle nye forskningsideer sammen med.</p>
    <h2>Datagrunnlag</h2>
    <ul><li><b>Ansatte og presentasjoner:</b> ansattoversikten på oslomet.no (${n} personer, både vitenskapelige og administrative), inkludert forskningsgrupper og prosjekter.</li>
    <li><b>Publikasjoner, medforfattere og prosjekter:</b> Cristin og Nasjonalt vitenarkiv (NVA), inkludert sammendrag, emneord og åpne fulltekster (innledning og konklusjon brukes i tematiseringen).</li>
    <li><b>Siteringer, fagfelt og nøkkelord:</b> OpenAlex (via DOI). Dekningen for norskspråklige arbeider er ufullstendig; siteringstall må leses med det i mente.</li></ul>
    <h2>Personkrets</h2>
    <p>Standardvisningen omfatter ansatte i LUIs ansattoversikt. Via «personer»-filteret kan du utvide til tidligere eller ikke-listede LUI-tilknyttede, andre OsloMet-ansatte og eksterne medforfattere. Eksterne noder bærer færre attributter: navn, institusjon, land, eventuelt ORCID og antall felles publikasjoner (artikler med mer enn 30 forfattere er holdt utenfor).</p>
    <h2>Filtre</h2>
    <p>Alle visninger kan avgrenses på institutt, stillingstype, makrotema og tema (kode T1–T99 eller navn), teori, metode, forskningsgruppe, OpenAlex-fagfelt, årstall og minste antall vitenskapelige publikasjoner. Filtrene ligger i adresselinjen, så en filtrert visning kan deles som lenke eller skrives ut.</p>
    <h2>Metode</h2>
    <p>Tekstene (tittel, sammendrag, emneord, innledning, konklusjon) representeres med en flerspråklig språkmodell, grupperes, og gruppene er redigert til en taksonomi på ${D.taxonomy.topics.length} tema i ${D.taxonomy.macro.length} makrogrupper. Hver publikasjon får 1–3 tema; personprofilen er en vektet sum over publikasjonene (nyere og vitenskapelige arbeider teller mest). Teori og metode gjenkjennes med kontrollerte vokabularer. Alle tall er indikasjoner, ikke fasit.</p>
    <h2>Personvern</h2>
    <p>Bare offentlig tilgjengelige, profesjonelle opplysninger er brukt. E-post, telefon og bilder er ikke lagret i kartet. Ansatte som ønsker retting eller reservasjon kan kontakte prosjekteier.</p>
    <h2>PDF</h2><p>Alle sider har utskriftsvisning: bruk «PDF»-knappen (eller Ctrl/Cmd+P) og velg «Lagre som PDF».</p>`;
}

/* ---------------- sortable tables: click a header to sort, click again to reverse ---------------- */
document.addEventListener("click", ev => {
  const th = ev.target.closest("table.tbl th"); if (!th) return;
  const table = th.closest("table"), headRow = th.parentElement, col = [...headRow.children].indexOf(th);
  const rows = [...table.querySelectorAll("tr")].filter(r => r !== headRow && r.children.length > col);
  const text = r => (r.children[col]?.textContent || "").trim();
  const num = v => { const m = v.replace(/\s/g, "").replace(",", ".").match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : NaN; };
  const vals = rows.map(text).filter(Boolean);
  const numeric = vals.length && vals.filter(v => !isNaN(num(v))).length >= 0.8 * vals.length;
  const dir = th.classList.contains("sort-asc") ? -1 : 1;
  headRow.querySelectorAll("th").forEach(h => h.classList.remove("sort-asc", "sort-desc"));
  th.classList.add(dir === 1 ? "sort-asc" : "sort-desc");
  rows.sort((a, b) => { const x = text(a), y = text(b);
    if (numeric) { const nx = num(x), ny = num(y); return (isNaN(nx) ? 1 : isNaN(ny) ? -1 : nx - ny) * dir; }
    return x.localeCompare(y, "nb", { numeric: true, sensitivity: "base" }) * dir; });
  for (const r of rows) r.parentElement.appendChild(r);
});
document.addEventListener("click", ev => {
  const a = ev.target.closest("a[data-oa]"); if (!a) return;
  ev.preventDefault();
  const row = a.closest(".pub"), id = a.dataset.oa;
  const pub = [...pubCache.values()].flatMap(v => (v && typeof v.then !== "function") ? v : []).find(x => x.id === id) || window.__lastPubs?.find(x => x.id === id);
  if (pub) oaDetails(pub, row.querySelector("[data-oa-out]"));
});
load().then(() => { route(); addEventListener("hashchange", route); }).catch(e => { $("#app").innerHTML = `<p class="notice">Kunne ikke laste data: ${esc(e.message)}</p>`; });
