# LUI Research-Interest Map — Project Plan

Faculty: **Fakultet for lærerutdanning og internasjonale studier (LUI), OsloMet**
Goal: a local database + web page that shows who researches what at LUI, how people are
connected (coauthorship, citations, shared groups/projects, shared topics), lets users
query and score relationships, and produces PDF reports — to help colleagues start
collaborations, find advisors, and seed new research ideas.

Status of this document: plan only. Every data-source claim below was verified by
live probes on 2026-10-21 (see §2). Nothing has been scraped at scale yet.

---

## 1. Scope and target numbers

| Item | Verified count | Source |
|---|---|---|
| Staff listed under LUI | 628 (21 pages × 30) | oslomet.no/om/ansatteoversikt?unitcode=lui |
| …of which "Vitenskapelig" (academic) | 464 | same, `&type=vitenskapelig` |
| …"Administrativ" | 164 | same, `&type=administrativ` |
| Persons in LUI in Cristin | 785 (incl. inactive, hourly, admin) | api.cristin.no/v2/persons?institution=215&parent_unit_id=215.4.0.0 |
| Registered results for LUI (all time) | 28 264 | Cristin / NVA search, unit=215.4.0.0 |
| …since 2015 | 17 238 | Cristin `published_since=2015` |
| …Academic articles | 2 278 | NVA facet `type` |
| …Academic chapters | 2 143 | NVA |
| …Academic monographs | 96 | NVA |
| …PhD theses | 135 | NVA |
| …Research reports | 761 | NVA |
| …Conference lectures (often have abstracts) | 6 762 | NVA |
| Active Cristin projects at OsloMet | 322 | api.cristin.no/v2/projects?institution=215&status=ACTIVE |

**Decisions**
- Persons: store and profile **all 628 listed staff** (decision 2026-10-21: academic and
  administrative alike). Staff without publications get a profile from bio, Cristin
  keywords, group and project membership, and are marked "thin".
- Publications: store *all* results of profiled persons, but weight by type. Core corpus
  for topic modelling = academic articles, chapters, monographs, PhD theses, research
  reports, plus conference lectures/posters that carry an abstract. Time window for
  topic modelling: 2010 → present (older work kept but down-weighted; adjustable).
- Language: corpus is mixed Norwegian (bokmål/nynorsk) and English. All models and
  prompts must be multilingual; output taxonomy labels in **both** Norwegian and English.

---

## 2. Verified data sources (what each gives, how it joins)

### 2.1 OsloMet web (HTML, server-rendered, no login)
- **Listing** `https://www.oslomet.no/om/ansatteoversikt?unitcode=lui&p=N` (N = 1…21).
  Cards contain: username (URL slug `/om/ansatt/<username>/`), full name, position
  title, e-mail, phone. Filters `type=vitenskapelig|administrativ` work.
- **Profile** `https://www.oslomet.no/om/ansatt/<username>/` (English twin at
  `/en/about/employee/<username>/`). Sections observed: *Kort om* (free-text bio),
  *Fakultet / Institutt* (department), *Forskningsgrupper* (links to
  `/forskning/forskningsgrupper/<slug>`), *Forskningsprosjekter* (links + one-paragraph
  descriptions), *Publikasjoner og forskningsresultater* with tabs (Vitenskapelige
  publikasjoner, Fagbøker/lærebøker, Forskningsrapporter, Formidling…). Publication
  entries list every author; **internal coauthors are hyperlinked by username**, which
  gives a free, exact coauthor edge. DOI and handle links are included. Coverage of
  the bio section varies (some profiles are empty shells). No ORCID on profile pages.
- **Research group pages** `/forskning/forskningsgrupper/<slug>`: leaders, five
  focus areas, methods, projects. The member list is loaded by AJAX:
  `data-action="/ajax/module/member/block/<id>/simple?...&token=…"`. The token is
  page-bound: fetch the group page and the AJAX URL in the **same cookie session**
  (verified: returns Primærmedlemmar / Sekundærmedlemmar / Eksterne medlemmar with
  `/om/ansatt/<username>/` links, 32 members for "Digitale læringsarenaer").
- **Project pages** `/forskning/forskningsprosjekter/<slug>`: description, participants
  (to be confirmed per page; fall back to Cristin project participants).

### 2.2 Cristin API v2 (JSON, no key, generous rate)
- LUI unit id is **215.4.0.0** (not 215.6). Sub-units (from NVA org tree):
  215.4.1.0 Fakultetsadministrasjonen · 215.4.2.0 Inst. for barnehagelærerutdanning (BLU) ·
  215.4.3.0 Inst. for grunnskole- og faglærerutdanning (GFU, 195 persons) ·
  215.4.4.0 Inst. for internasjonale studier og tolkeutdanning (IST) ·
  215.4.5.0 Inst. for yrkesfaglærerutdanning (YLU) · 215.4.6.0 Timelønnede LUI ·
  215.4.7.0 NAFO.
- `persons?institution=215&parent_unit_id=215.4.0.0&per_page=…` → id, name.
- `persons/<id>` → ORCID (in ~15 % of a sample), **curated subject keywords** (~25 %),
  `background` (free-text research interests, rare), e-mail (rare), affiliations with
  unit id + position + active flag.
- `persons/<id>/results?fields=all` → full result list; `results/<id>/contributors` →
  every author with `cristin_person_id` and affiliation unit (this is the authoritative
  coauthor table, including external coauthors).
- Results carry `summary` on ~63 % (recent sample), `links` (DOI, ARKIV handle),
  `nva_result_id`, category code, journal with NVI level, projects, funding.
- `projects/<id>` → title, participants with `cristin_person_id` and roles, keywords,
  project categories, coordinating unit, related results. Note: the combination
  `participant_institution`+`unit` is rejected (400); use `institution=215` and filter
  locally by participant unit.

### 2.3 NVA — Nasjonalt vitenarkiv (JSON, no key; ODA has migrated into NVA)
- `GET https://api.nva.unit.no/search/resources?unit=215.4.0.0&size=200` with
  `nextResults` cursor paging; facets via `aggregation=all` (type, contributor,
  journal, files, fundingSource…). `contributor=<cristinPersonId>` filter works.
  `category=AcademicArticle` etc. filter works.
- `GET https://api.nva.unit.no/publication/<id>` **with `Accept: application/json`**
  (without it you get a 303 to the web app) → `entityDescription.abstract`,
  `alternativeAbstracts`, `tags` (author keywords), `language`, `reference`
  (journal/channel, NVI level), `contributors[]` with `identity.id =
  …/cristin/person/<id>`, `verificationStatus`, affiliations → organization ids;
  `projects[]`, `fundings[]`, `associatedArtifacts[]`.
- Full text: `associatedArtifacts[type=OpenFile]` has `identifier`, `license`,
  `publisherVersion`, `mimeType`. Download URL is obtained from
  `GET /publication/<pubId>/filelink/<fileId>` → `PresignedUriResponse.id` (short-lived
  S3 URL). Verified working without auth. hdl.handle.net/11250/… now redirects to NVA.
- `GET /cristin/person/<id>` → ORCID, names, e-mail (contactDetails), affiliations.
  `GET /cristin/organization/<id>` → labels and `hasPart`. `GET /cristin/project/<id>`.

### 2.4 OpenAlex (JSON, free; use `mailto=` polite pool: 10 req/s, 100k/day)
- Institution: OsloMet = `I184531372`, ROR `04q12yn84` (17 498 works, 4 756 authors).
- Works by DOI, batched 50 per call: `works?filter=doi:A|B|C…&select=…`. Each work:
  `abstract_inverted_index` (reconstructable), `topics[]` (4-level hierarchy
  domain→field→subfield→topic with scores), `keywords[]`, `concepts[]`,
  `referenced_works[]`, `cited_by_count`, `counts_by_year`, `fwci`, `authorships[]`
  (author id, ORCID when known, institutions), `best_oa_location.pdf_url`.
- Citation edges: for each of our works W, `referenced_works` ∩ {our works} gives
  internal citations directly; `works?filter=cites:W…` gives citing works (external
  citation counts). Coverage caveat: Norwegian-language and non-DOI outputs are poorly
  covered (OsloMet 2015+: 13 328 English vs 846 Norwegian works); OpenAlex also
  mislabels language sometimes. Treat OpenAlex as enrichment, Cristin/NVA as truth.
- Author matching: OpenAlex author ids are resolved per work via DOI; ORCID lookup
  works only when ORCID is already linked in OpenAlex (Laake: not linked, but her
  author record exists and lists 17 works and topic counts).

### 2.5 Join keys (identity resolution)
1. **OsloMet username ↔ Cristin person id**: (a) e-mail match (NVA `cristin/person`
   has e-mail for many), (b) exact normalised name match restricted to Cristin persons
   in 215.4.*, (c) DOI/handle overlap between the profile's publication list and the
   Cristin result list, (d) manual review file for the remainder (expect 5–10 %).
2. **Cristin result ↔ NVA publication**: `nva_result_id` is given in Cristin results.
3. **Cristin result ↔ OpenAlex work**: DOI; fallback title+year fuzzy match (≥ 0.95
   token-set ratio) only for items without DOI.
4. **Internal coauthor edges**: from NVA/Cristin contributors (cristin ids) — the
   OsloMet profile hyperlinks serve as a cross-check.

### 2.6 Tooling available locally
Python 3.14 with `pymupdf`, `pypdf`, `numpy`, `sqlite3`; Node 22. Missing (to install in
a venv): `httpx`, `beautifulsoup4`, `lxml`, `pandas`, `networkx`, `scikit-learn`,
`rapidfuzz`, `sentence-transformers` (or an embeddings API), `anthropic` SDK for
LLM tagging. Browser automation is **not** needed — all sources are reachable with
plain HTTP (the group-member AJAX only needs a cookie jar).

---

## 3. Legal, ethical and politeness constraints
- All sources are public, but the result is a profile of named employees → personal
  data (GDPR art. 6(1)(f) legitimate interest for internal collaboration). Keep the
  web page internal (OsloMet network / login) until the faculty has approved it;
  include an opt-out contact; show only professional data. **Do not store** phone
  numbers or photos; do not scrape private e-mail; keep e-mail only as a join key.
- Full-text PDFs: download only files marked OpenFile with a licence, store locally,
  never redistribute; the web page shows our derived summaries and links to NVA/DOI,
  not the PDFs.
- Rate limits: OsloMet web ≤ 1 request/s with a descriptive User-Agent; Cristin ≤ 5/s;
  NVA ≤ 5/s; OpenAlex ≤ 8/s with `mailto`. Check `oslomet.no/robots.txt` before run.
- Everything is cached raw so re-runs do not re-hit the servers.

---

## 4. Architecture overview

```
 OsloMet web ──┐
 Cristin v2  ──┤  (1) scrape → data/raw/<source>/*.json|html   (immutable, dated)
 NVA         ──┤  (2) parse  → SQLite  data/db/lui.sqlite      (system of record)
 OpenAlex    ──┘  (3) enrich → text corpus (abstract/intro/conclusion) in SQLite
                   (4) classify → topics (50–100) + macro (10) + theory/method tags
                   (5) build  → matrices (.npz/.parquet) + graph JSON + search index
                   (6) web    → static site (HTML/JS, Cytoscape.js, heat-map, print-to-PDF)
```

Everything is a plain Python package with one CLI (`python -m lui <stage>`), each
stage idempotent and re-runnable. SQLite is the only database; derived artefacts are
regenerated from it. No server is required to view the result (static site), which
keeps hosting trivial; an optional small API can be added later for live scoring if
the dataset outgrows the browser (it will not at ~500 people / ~15k publications).

### 4.1 Repository layout
```
ILU_interesser/
  PLAN.md                     this file
  tasks/todo.md               checkable work plan (kept in sync)
  pyproject.toml              deps; `lui` CLI
  config/
    units.yaml                unit ids, names (nb/en), short codes (BLU, GFU, IST, YLU, NAFO)
    publication_weights.yaml  weight per NVA/Cristin category
    taxonomy/                 seeds + final: micro_topics.yaml, macro_topics.yaml,
                              theories.yaml, methods.yaml (controlled vocabularies)
    identity_overrides.csv    manual username↔cristin_id fixes
  src/lui/
    http.py                   cached, rate-limited client (ETag/date, retries)
    scrape/ oslomet.py cristin.py nva.py openalex.py pdf.py
    parse/  oslomet.py cristin.py nva.py openalex.py sections.py
    identity.py               person resolution (§2.5)
    classify/ embed.py cluster.py llm_tag.py aggregate.py
    build/ matrices.py graph.py search_index.py export_web.py
    db/ schema.sql migrate.py
  data/
    raw/{oslomet,cristin,nva,openalex}/…   JSON/HTML as fetched + fetched_at
    pdf/<nva_pub_id>/<file_id>.pdf          open files only
    db/lui.sqlite
    derived/ person_topic.npz person_person_*.npz graph.json taxonomy.json …
  web/                        static site (index.html, app.js, styles.css, data/*.json)
  tests/                      parser fixtures from the probes in §2
```

---

## 5. Stage 1 — Scraping and raw storage

### 5.1 Common HTTP layer
- `httpx` client; per-host token-bucket rate limiter; retries with back-off on 429/5xx;
  descriptive User-Agent with contact e-mail.
- Cache: raw bytes written to `data/raw/<source>/<key>.<ext>` plus a sidecar
  `*.meta.json` (url, status, fetched_at, etag). Default: reuse cache if younger than
  N days (`--max-age`); `--refresh` forces re-fetch.

### 5.2 OsloMet
1. Listing: pages 1…until "no next" for `unitcode=lui` and for the two `type=` filters
   (so each person gets an academic/admin flag). Extract username, name, title, e-mail.
2. Profile per username (Norwegian; English only when Norwegian bio is empty). Extract
   department, bio text, group slugs, project slugs + blurbs, publication tabs
   (per entry: authors with internal usernames, year, title, venue, DOI/handle, tab).
3. Research groups: all slugs seen in profiles → group page (HTML) + member AJAX in the
   same session. Store leaders, primary/secondary/external members, focus-area text.
4. Projects: all slugs seen in profiles → project page; store description and any
   participant links.

Expected volume: ~21 + 2·21 listing pages, 628 profiles, ~40–60 group pages (+ AJAX),
~200 project pages. ≈ 1 000 requests, ~20 min at 1 req/s.

### 5.3 Cristin
1. Persons under 215.4.0.0 (paged, 785). Person detail for each.
2. For each person: `persons/<id>/results?fields=all&per_page=1000` (paged).
3. For every distinct result: `results/<id>/contributors`.
4. Projects: `projects?institution=215&per_page=1000` (all statuses), detail for each
   project that has ≥ 1 participant in 215.4.* or coordinating unit 215.4.*.
Expected: ~800 + ~800 + ~15 000 + ~400 requests ≈ 1 hour at 5 req/s.

### 5.4 NVA
1. Search `unit=215.4.0.0` cursor-paged, size 200 → ~142 pages; gives every
   publication id and its summary record.
2. Publication detail (`Accept: application/json`) for every record in the core corpus
   (scientific types + any record with `pendingOpenFileCount`/files); ~8 000 requests.
3. For each OpenFile with a PDF mime type and a licence: `filelink` → download to
   `data/pdf/`. Expect ~2 000–3 000 PDFs (7/20 articles in sample had open files).
4. `cristin/person/<id>` for every LUI person (e-mail, ORCID) — 785 requests.

### 5.5 OpenAlex
1. Collect all DOIs from Cristin/NVA results of profiled persons (~4 000–5 000).
2. Batch `works?filter=doi:…` (50 per call) with `select` of the needed fields.
3. For works found: no extra calls needed for internal citations (use
   `referenced_works`). For external citation counts use `cited_by_count` as is.
4. Author records for OpenAlex author ids that recur ≥ 3 times (topics, h-index,
   affiliation history) — ~500 requests.
5. Where NVA has no open file but OpenAlex `best_oa_location.pdf_url` exists, download
   that PDF (publisher OA) — respect robots and skip non-200.

### 5.6 Verification for Stage 1
- Row counts match the numbers in §1 (±2 %).
- Random sample of 20 profiles compared manually against the live page.
- Every raw file has a meta sidecar; re-running with cache produces zero network calls.

---

## 6. Stage 2 — Data model (SQLite)

Core entities (all ids are source ids; surrogate `person_id` is the OsloMet username
when present, else `cristin:<id>`):

```
person(person_id, username, cristin_person_id, orcid, openalex_author_id, name_full,
       name_first, name_last, title_nb, title_en, staff_type{academic,admin},
       unit_id, bio_nb, bio_en, cristin_background, email_hash, profile_url,
       resolved_by{email,name,doi,manual}, resolution_confidence)
unit(unit_id, parent_unit_id, name_nb, name_en, short_code)
research_group(group_id, slug, name, url, description, methods_text)
group_member(group_id, person_id, role{leader,primary,secondary,external}, name_raw)
project(project_id, cristin_project_id, slug, title_nb, title_en, summary, start, end,
        status, coordinating_unit_id, url)
project_participant(project_id, person_id, cristin_person_id, role)
project_keyword(project_id, keyword)
publication(pub_id, cristin_result_id, nva_id, doi, handle, title, year, language,
            category_code, category_group{article,chapter,monograph,phd,report,
            lecture,textbook,popular,media,other}, venue_name, venue_id, nvi_level,
            openalex_work_id, cited_by_count, fwci, is_core_corpus, weight)
publication_author(pub_id, author_order, cristin_person_id, person_id, name_raw,
                   affiliation_unit_id, is_internal, openalex_author_id)
publication_text(pub_id, kind{abstract,alt_abstract,tags,intro,conclusion,fulltext},
                 lang, source{nva,cristin,openalex,pdf}, text, char_count, licence)
publication_file(pub_id, file_id, licence, version, local_path, sha256, pages,
                 extracted_ok)
publication_keyword(pub_id, keyword, source{nva_tag,openalex_keyword,cristin})
openalex_topic(pub_id, topic_id, topic_name, subfield, field, domain, score)
citation(citing_pub_id, cited_pub_id, source{openalex}, is_internal)
person_keyword(person_id, keyword, source{cristin,bio_llm})
-- classification layer
topic(topic_id, slug, label_nb, label_en, definition_nb, definition_en, macro_id,
      n_pubs, n_persons, keywords_json, exemplar_pub_ids_json)
macro_topic(macro_id, slug, label_nb, label_en, definition, colour)
theory(theory_id, label, aliases_json)            -- controlled vocabulary
method(method_id, label, aliases_json)            -- controlled vocabulary
pub_topic(pub_id, topic_id, weight, evidence{llm,embedding,keyword}, rationale)
pub_theory(pub_id, theory_id, confidence, quote)
pub_method(pub_id, method_id, confidence)
person_topic(person_id, topic_id, score, n_pubs, recency_score, is_primary)
person_theory(person_id, theory_id, score) ; person_method(person_id, method_id, score)
-- relationship layer (materialised for speed; recomputable)
person_edge(src_person_id, dst_person_id, edge_type{coauthor,cites,cited_by,
            shared_group,shared_project,topic_similarity,theory_similarity},
            weight, n_evidence, evidence_json, first_year, last_year)
run_log(stage, started_at, finished_at, rows, notes)
```

Indexes on all foreign keys; a `fts5` virtual table over `publication.title`,
`publication_text.text`, `person.bio_*` for free-text search; views for the matrices.

---

## 7. Stage 3 — Text corpus (abstracts, introductions, conclusions)

1. **Abstract per publication**, preference order: NVA `abstract` → Cristin `summary`
   → OpenAlex reconstructed abstract → (none). Record source and language
   (detect with `lingua`/`langdetect`; NVA/Cristin give `language` too).
2. **Section extraction from PDFs** (`pymupdf`): text per page → rebuild paragraphs →
   find headings by font-size/bold + regex over multilingual headers:
   - intro: `^(1\.?\s*)?(Introduction|Innledning|Innleiing|Bakgrunn|Background|Introduksjon)`
   - conclusion: `(Conclusion[s]?|Concluding remarks|Konklusjon|Avslutning|Avsluttende
     (refleksjoner|kommentarer)|Oppsummering|Diskusjon og konklusjon|Implications)`
   - stop at next heading or references (`References|Referanser|Litteratur`).
   Store up to ~1 500 words per section. Flag failures; expect ~70 % success on
   journal articles, lower on chapters/reports. Keep `fulltext` only for local
   indexing, never exported to the web bundle.
3. **Person-level text**: bio (nb/en), Cristin `background`, Cristin keywords, group
   descriptions and project blurbs the person is attached to.
4. Quality gates: dedupe near-identical abstracts (same work in two records), drop
   boilerplate ("This article…" licences), normalise whitespace/hyphenation.

---

## 8. Stage 4 — Classification into 50–100 topics and 10 macro groups

Hybrid pipeline: unsupervised structure first, LLM for naming and consistent tagging,
human sign-off on the taxonomy.

1. **Document unit** = one core-corpus publication, text = title + abstract (+ tags +
   OpenAlex keywords/topic names + intro/conclusion snippets when available, capped at
   ~1 200 tokens).
2. **Embeddings**: multilingual sentence embeddings (local `bge-m3` or
   `multilingual-e5-large`, or an embeddings API). Store vectors in `data/derived/`.
3. **Clustering to propose candidate topics**: UMAP → HDBSCAN (BERTopic-style) with
   min cluster size tuned to yield ~120–180 raw clusters; c-TF-IDF keywords + 5
   exemplar abstracts per cluster. Also pull in signals from OpenAlex `topics`
   (subfield level) and Cristin/NVA keywords as cluster descriptors.
4. **Taxonomy design (LLM + human)**: an LLM is given all cluster descriptors and asked
   to merge/split into **50–100 descriptive micro-topics** (as few as possible while
   each remains "a thing people would say they work on"), each with: slug, label
   nb/en, 2-sentence definition, inclusion/exclusion notes, example keywords. Then
   group into **10 macro groups** (expected shape for LUI, to be confirmed by data):
   e.g. *Literacy, language & multilingualism · Mathematics & science education ·
   Arts, aesthetics & body (music, drama, PE, arts & crafts) · Early childhood
   education & care · Teacher education, professional development & practice ·
   Inclusion, special needs & diversity · Digital technologies & AI in education ·
   Citizenship, religion, society & international/development studies · Vocational
   education & work-based learning · Assessment, policy, governance & curriculum
   history*. A human (you) reviews and edits `config/taxonomy/*.yaml` before tagging.
5. **Controlled vocabularies for theory and method** (separate axes, ~40 each), seeded
   from the corpus by an LLM pass over a sample, then frozen: e.g. sociocultural /
   Vygotsky, Bourdieu, critical pedagogy, Bildung/Didaktik, variation theory,
   phenomenology, posthumanism/new materialism, sociomaterial/ANT, Foucault/
   governmentality, translanguaging, self-determination theory, TPACK… and methods:
   ethnography, interviews, design-based research, RCT/quasi-experimental,
   survey/psychometrics, discourse analysis, document/curriculum analysis,
   systematic review, action research, mixed methods, corpus linguistics…
6. **Per-publication tagging (LLM, bulk tier)**: structured JSON output per
   publication: 1–3 micro-topics with weights (sum 1), 0–3 theories with a supporting
   quote, 0–3 methods, educational level/context, confidence. Prompt contains the
   frozen taxonomy; temperature 0; validate against the vocab; retry on schema error.
   Volume ≈ 6 000–8 000 publications. Cache every response keyed by (pub_id,
   taxonomy_version, prompt_version). Spot-check 100 random tags manually; target
   ≥ 85 % agreement on primary topic.
7. **Person profiles**: `person_topic.score = Σ_pubs weight(topic) × w(category) ×
   recency(year)` with recency = 0.5^((now−year)/8); normalise per person; mark
   topics ≥ 0.15 as primary. Add bio-derived topics (LLM tag on bio text, weight 0.5)
   so people with few publications still get a profile. Same for theory/method.
8. **Macro profile** = sum over the member topics.

Outputs: `topic`, `macro_topic`, `pub_topic`, `person_topic` tables + a taxonomy
report (counts per topic, per department, orphan topics < 3 persons → merge).

---

## 9. Stage 5 — Matrices and graphs

Materialise as `.npz` (numpy) + JSON for the web, all from SQLite:

| Matrix / graph | Shape | Definition |
|---|---|---|
| Person × Topic (interest matrix) | ~470 × 50–100 | `person_topic.score` |
| Person × Macro | ~470 × 10 | aggregated |
| Person × Theory, Person × Method | ~470 × ~40 | scores |
| Topic × Topic co-occurrence | T × T | # pubs/persons sharing both topics (normalised: cosine / Jaccard) |
| Macro × Macro | 10 × 10 | same, aggregated |
| Person × Person — coauthorship | N × N | # joint pubs (weighted by category, 1/(k−1) per k-author paper), with years |
| Person × Person — citation | N × N | directed count of internal citations (OpenAlex refs) |
| Person × Person — shared group / project | N × N | counts |
| Person × Person — topic similarity | N × N | cosine of person×topic vectors (also theory/method variants) |
| Unit × Topic | 6 × T | department profiles |

Graph export (`graph.json`): nodes = persons (attrs: unit, title, primary topics,
macro colour, degree), topics, macro topics, groups, projects; typed edges with
weights and evidence ids (pub ids / group ids) so the UI can always "show why".
Also export GraphML/GEXF for Gephi and CSV edge lists for R/Python users.

Metrics computed once (networkx): degree/weighted degree, betweenness, community
detection (Louvain) on the combined weighted graph, "bridge" people between macro
groups, isolated academics (no internal coauthors) — these feed the recommendation
scorer.

---

## 10. Stage 6 — Web page

Static single-page app (no backend) served from `web/`; data loaded lazily from
`web/data/*.json` (persons ~0.3 MB, topics ~0.1 MB, edges ~1–2 MB, publications
metadata ~3 MB; full text never shipped).

Views
1. **Explore**: filters (department, topic, macro, theory, method, position, year
   range); search (MiniSearch / Lunr over names, bios, titles, keywords).
2. **Interest matrix**: person × topic heat map (sortable, clusterable, zoomable);
   click a cell → the publications behind it.
3. **Graph**: Cytoscape.js; toggle edge types (coauthor, citation, group, project,
   topic similarity) and thresholds; colour by macro group; node size by output or
   degree; click → side panel with evidence.
4. **Person page**: profile, primary topics, theories, methods, timeline of outputs,
   collaborators, "people like me" (nearest neighbours), "people I have not worked
   with who share my topics" (collaboration candidates), "who cites me / whom I cite".
5. **Pair page**: two people → shared topics, shared theories, joint pubs, shortest
   path between them, suggested themes for a joint project (from topic intersection ∪
   complementary neighbours).
6. **Topic / macro page**: definition, people ranked, trend by year, adjacent topics.
7. **Scoring**: user-adjustable weights (topic overlap, theory overlap, method
   complementarity, no existing coauthorship bonus, same/different department,
   recency) → ranked list of suggested collaborators for a person or for a free-text
   research idea (the idea is embedded client-side with a small ONNX model, or matched
   by keyword overlap as a fallback).
8. **PDF**: every page has print CSS; a "Generate PDF" button composes a report
   (person / pair / topic / custom selection with matrix and graph snapshots rendered
   via canvas → PNG) and uses the browser print dialog (reliable, zero dependencies).
   For batch reports a `lui export-pdf` CLI uses Playwright to print the same pages
   headlessly.

Tech: plain ES modules + a small build (Vite), D3 for the heat map, Cytoscape.js for the
graph, MiniSearch for search. Accessible, Norwegian/English toggle. Hosting: any static
host behind OsloMet login (or a local `python -m http.server` for the pilot).

---

## 11. Phasing, deliverables and verification

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Setup (½ day) | venv, package skeleton, schema, config, robots check, this plan reviewed | `lui --help` runs; schema applies to empty DB |
| 1. Scrape OsloMet (1 day) | raw HTML + parsed persons/groups/projects/profile-pubs | 628 persons, dept set for all, ≥ 95 % of academic staff have ≥ 1 group/project/pub |
| 2. Scrape Cristin + NVA (1–2 days incl. run time) | raw JSON, publications, authors, projects, files | counts within 2 % of §1; every core pub has contributors |
| 3. Identity resolution (½ day) | person table with cristin ids | ≥ 95 % of academic staff resolved automatically; rest in overrides file |
| 4. OpenAlex + PDFs + text (1–2 days) | abstracts for ≥ 80 % of core corpus; intro/conclusion for ≥ 50 % of articles | sample of 30 extractions checked by eye |
| 5. Taxonomy (2 days incl. your review) | `config/taxonomy/*.yaml`, taxonomy report | 50–100 topics, 10 macro, each topic ≥ 3 persons |
| 6. Tagging + profiles (1 day + API run) | pub_topic, person_topic, theory/method | 100-item spot check ≥ 85 % |
| 7. Matrices + graph (1 day) | derived files, metrics | matrices reproduce from DB; symmetric where expected |
| 8. Web app (3–4 days) | static site, PDF export | all 8 views work with real data; Lighthouse a11y ≥ 90 |
| 9. Pilot & feedback (ongoing) | 5–10 colleagues test, opt-out process | feedback logged; re-run pipeline end-to-end from cache |

Cross-cutting: every stage writes `run_log`; `lui verify` checks the invariants above
and prints a diff against the previous run; unit tests use the probe fixtures.

---

## 12. Risks and mitigations
- **Identity mismatches** (name variants, people with two affiliations): e-mail + DOI
  overlap + manual overrides; show `resolution_confidence` in the UI.
- **Sparse text for some staff** (lecturers with few publications): include bio,
  Cristin keywords, group/project membership; mark profile as "thin" rather than
  guessing.
- **Norwegian/nynorsk text and LLM topic drift**: frozen bilingual taxonomy, zero
  temperature, cached outputs, versioned prompts; re-tag only on taxonomy change.
- **OpenAlex coverage gaps** for Norwegian outputs: citations shown as "OpenAlex-based,
  partial"; coauthorship always from Cristin/NVA.
- **Site markup changes**: parsers are fixture-tested; raw HTML is archived so parsers
  can be re-run offline.
- **Token/cost**: tagging ~7 000 abstracts ≈ 10–15 M input tokens on a bulk-tier
  model; embeddings local. Estimate cost with current pricing before the run; the
  cluster step can be done fully locally if needed.
- **Privacy pushback**: internal-only hosting, opt-out, no sensitive fields, and a
  short data statement on the site.

---

## 13. Open questions for you (do not block Phases 0–4)
1. Should the time window for topic profiles be 2010→ or all years? (Plan: 2010→, with
   older work at low weight.)
2. Include hourly staff (215.4.6.0) and NAFO in the profiled set? (Plan: NAFO yes,
   hourly no.)
3. Which LLM/embedding provider may be used for the text (institutional constraints
   on sending abstracts to a cloud API)? Local-only is possible with smaller quality.
4. Hosting target for the pilot (local machine, OsloMet web server, GitHub Pages behind
   login)?
