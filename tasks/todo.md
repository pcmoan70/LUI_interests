# LUI Research-Interest Map — Task List

Plan: see ../PLAN.md. Tick items as they are completed; add a Review section per phase.

## Phase 0 — Setup
- [x] Probe all data sources and verify endpoints, counts, join keys (2026-10-21)
- [x] Write PLAN.md
- [x] Plan accepted 2026-10-21 (user: "do all staff, start"); open questions in §13 still open, defaults used
- [x] Check https://www.oslomet.no/robots.txt and api terms (Cristin, NVA, OpenAlex)
- [x] Create venv + pyproject (httpx, bs4, lxml, pandas, networkx, scikit-learn, rapidfuzz, pymupdf)
- [x] Package skeleton `src/lui` with CLI and cached rate-limited HTTP client
- [x] SQLite schema (`db/schema.sql`) + `lui db init`
- [x] `config/units.yaml` (weights are in code: scrape/cristin.py WEIGHTS)

## Phase 1 — Scrape OsloMet
- [x] Listing pages (all, academic, admin) → persons with staff_type
- [x] Profile pages (nb; en fallback) → dept, bio, groups, projects, publication tabs with internal coauthor usernames
- [x] Research-group pages + member AJAX (same cookie session) → leaders/members
- [x] Project pages → description/participants
- [ ] Parser fixtures/tests from probe HTML
- [x] Verify: 628 persons, dept for all (3 faculty leaders defaulted to 215.4.0.0), 45 groups, 141 web projects, 233 bios

## Phase 2 — Scrape Cristin + NVA
- [x] Cristin persons under 215.4.0.0 + person detail (ORCID, keywords, background, email)
- [x] Cristin results per person + contributors per result
- [x] Cristin projects (institution=215) filtered to LUI participants
- [x] NVA search unit=215.4.0.0 (cursor paging) → all publication ids
- [x] NVA publication detail (Accept: application/json) for core corpus
- [x] NVA cristin/person for e-mails
- [x] Load into SQLite; verified: 785 Cristin persons, 36 222 publications (10 637 core), 28 265 NVA records

## Phase 3 — Identity resolution
- [x] username ↔ cristin id via e-mail, name, DOI overlap (607 name, 18 e-mail)
- [x] `config/identity_overrides.csv` for the remainder (3 persons registered under other units)
- [x] Verify ≥ 95 % academic staff resolved → 628/628 resolved

## Phase 4 — OpenAlex, PDFs, text corpus
- [x] Batch DOI lookup (50/call) → topics, keywords, refs, citations, OA pdf url
- [x] Internal citation edges from referenced_works
- [x] NVA filelink → download OpenFile PDFs; OpenAlex OA PDFs as fallback
- [x] Abstract selection (NVA → Cristin → OpenAlex)
- [x] Intro/conclusion extraction (pymupdf + multilingual heading regex)
- [x] Abstract coverage: 5 470 of 10 637 core (51 %; lectures without abstracts pull it down; articles/chapters much higher); 1 252 PDFs with intro/conclusion. Manual check of extractions still open

## Phase 5 — Taxonomy
- [x] Embeddings for core corpus (9 492 pubs + 302 bios, multilingual-e5-base)
- [x] KMeans k=150 candidate clusters with c-TF-IDF descriptors (data/derived/clusters_k150.md)
- [x] 78 micro topics + 10 macro groups designed from the cluster report (config/taxonomy/micro_topics.yaml, macro_topics.yaml)
- [x] Theory (60) and method (31) controlled vocabularies (regex alias lists)
- [ ] User review of `config/taxonomy/*.yaml` (labels, merges); re-run `lui tag && lui build-edges && lui build-matrices && lui export-web` after edits

## Phase 6 — Tagging and profiles
- [x] Tagging: topic centroids (trimmed cluster mean + definition-nearest docs + definition embedding), softmax weights, cluster boost, PLUS lexical evidence (topic keywords in title/author keywords/abstract) and stated interests (bio + Cristin keywords, weight of two publications); conference talks with informative titles are in the corpus; audit of stated-but-missing interests in data/derived/attribution_audit.csv (user request 2026-10-21)
- [x] Bio-based tagging for thin profiles (bio embedding counts as 1.5 publications)
- [x] person_topic / person_theory / person_method aggregation with category weights and 8-year half-life recency
- [ ] 100-item spot check ≥ 85 %

## Phase 7 — Matrices and graph
- [x] `lui externals`: external coauthor nodes (≥1 joint core pub or ≥2 joint pubs, mass-author papers excluded) with name, affiliation, country, ORCID (frequent coauthors), joint count; categories former_lui / oslomet / external; person-scope filter in the app (user request 2026-10-21)
- [x] `lui build-matrices`: person×topic + person×person .npz, Louvain communities, spectral/co-cluster block orderings (orders.json)
- [ ] Person×Topic, Person×Macro, Topic×Topic, Unit×Topic aggregates for export
- [x] Person×Person: coauthor 1 715, citation 800, group 11 630, project 1 860, topic similarity edges
- [x] Louvain communities + orders.json; CSV downloads in the app (GraphML export still open)
- [ ] `lui verify` invariants

## Phase 8 — Web app
- [x] Static SPA (no build step; web/index.html, app.js, styles.css), data bundles via `lui export-web`, MiniSearch index
- [x] Interest matrix heat map (D3), block-ordered by co-clustering with separators
- [x] Relational matrix view seriated and optimised: components → Louvain on the filtered graph → spectral block/within-block order; best of 4 candidates by linear arrangement cost (shown on screen); CSV export
- [x] Interest matrix: build a selection of persons and topics (search + chips, URL-persisted) instead of the full table (user request 2026-10-21)
- [x] URL-persisted filters on all views: unit, staff type, macro/topic code, theory, method, group, OpenAlex subfield, year range, min. output, edge types/weights (user request 2026-10-21)
- [x] Graph view: D3 force layout on canvas (zoom, pan, drag, fit), edge-type/weight/year filters, colour by unit/macro/community, evidence panel (user request 2026-10-21)
- [x] Person, pair, topic/macro pages (written; needs taxonomy data to fully exercise)
- [x] Scoring panel with adjustable weights (written; needs taxonomy data to fully exercise)
- [x] Print CSS (browser print-to-PDF)
- [x] Low-memory web app: initial load ~7.5 MB (persons, compact edges, taxonomy, groups, projects, orders); publications fetched on demand per person/topic and as an index only on the publications page; optional live OpenAlex lookup per publication with graceful fallback (user request 2026-10-21)
- [x] Graph: clickable legend (department / macro / community / edge type toggles), canvas clearing fix, small disconnected components packed on a ring around the giant component (user requests 2026-10-21)
- [x] Relational matrix: hierarchical default order (institute → Louvain within institute → spectral) with institute bands and thick separators; flat optimised order still selectable; edge types for clustering chosen from a multi-select dropdown (user requests 2026-10-21)
- [x] All tables sortable by column (alphabetical / numeric, toggle direction); topic page gets the person-scope selector (user request 2026-10-21)
- [x] Non-LUI persons shown as (Ekstern) / (OsloMet) instead of an institute code (user request 2026-10-21)
- [x] Topic trend: one line per year, block value scales to fit; graph checkbox to include external coauthors as grey nodes (user requests 2026-10-21)
- [x] Person page: direct links to Graf (focused, with externals), Finn samarbeid (person prefilled) and the interest matrix (user request 2026-10-21)
- [x] Person → matrix link includes the 12 nearest persons by topic cosine; matrix labels untruncated with adaptive margins; Pages deploys with versioned asset/data URLs (cache busting) (user requests 2026-10-21)
- [x] Hover explanations (title tooltips) on all publication counts, strengths, similarity and score columns; topic page actions: graph of who collaborated with whom on the topic, relational matrix and interest matrix for the topic (user requests 2026-10-21)
- [x] Interest matrix: vertical topic labels, hover enlarges label + large tooltip, width fitted to the container (no horizontal scrolling) (user request 2026-10-21)
- [x] Finn samarbeid: column with number of joint publications (also in CSV) (user request 2026-10-21)
- [x] Graph: clicking a node centres it and arranges 1st/2nd/3rd-degree contacts on rings (ego layout); farther nodes may fall outside the fitted view; double-click background restores the normal layout (user request 2026-10-21)
- [x] Finn samarbeid: topic chips toggle on/off in the comparison (strike-through = off), persisted in the URL (user request 2026-10-21)
- [x] Topic page → interest matrix shows the persons with the topic (≥0.10, max 80) and all their other topics (user request 2026-10-21)
- [x] Second-degree relation 'Via felles kontakt' (two LUI persons sharing a coauthor/citation contact without being coauthors; weight = number of shared contacts, intermediaries as evidence; dashed in graph) (user request 2026-10-21)
- [x] Collaboration profiles (`lui build-collab`): coauthor scope LUI / other OsloMet / other Norwegian / international from Cristin affiliations (909 institutions resolved), partner institutions and countries, internal vs external citations; person-page section and `#/collab` overview per department with CSV (user request 2026-10-22)
- [x] Citation levels (`lui scrape-openalex-cites` + collab): citing works classified as own research group / LUI / other OsloMet / Norwegian / international / unknown; sums per person, department and topic; sortable external-citation share; partner institution tables (Norwegian + international, country markers, Cristin links, click-to-filter, unique external authors) (user requests 2026-10-22)
- [x] Scheduled daily task (Windows Task Scheduler, 07:15) `scripts/update_cites.cmd`: citing-works fetch within quota (budget 900/run, stops when <20 credits remain or on 429), build-collab, export-web, commit+push; log in data/scheduled.log. 1 000 of 2 799 cited works done; finishes over ~2 more days
- [ ] Playwright batch PDF export
- [ ] nb/en toggle, accessibility pass

## Phase 8b — Weekly incremental update (user request 2026-10-24: "schedule updates every week (Sunday), get only what's new")
Findings on change feeds: Cristin `/results?unit=215.4.0.0&modified_since=YYYY-MM-DD` and `/projects?institution=215&modified_since=`
work (117 LUI results changed since 2026-10-01); NVA `search/resources?...&modifiedSince=YYYY-MM-DD` works (same 117);
OpenAlex `from_updated_date`/`from_created_date` are paid-plan only, `from_publication_date` is free; oslomet.no has no feed.
- [x] `Fetcher(fresh=prefixes)` always refetches listing keys; `get(..., force=True)` per call
- [x] `--since auto|YYYY-MM-DD` for scrape-cristin (modified results: contributors replaced; modified projects) and scrape-nva (modifiedSince hits + details)
- [x] `--fresh` for scrape stages; scrape-openalex re-reads all DOI batches and queues works whose cited_by_count changed (`cite_refresh_queue`)
- [x] scrape-openalex-cites: queued works first and refetched (citing_work rows replaced), the rest from cache (no expiry); queue survives quota stops
- [x] `scripts/update_weekly.cmd`: incremental scrapes → identity, embed (incremental), tag, externals, edges, matrices, collab, export, verify → commit + push
- [x] Live test 2026-10-24: NVA 36 modified hits, Cristin 36 modified results (875 requests), OpenAlex 151 works queued, 80 refetched before quota stop (71 carry over); daily task replaced by weekly task "LUI forskningskart - ukentlig oppdatering" (Sun 07:15, plain local StartBoundary because of DST)
- [x] README: change-feed findings and weekly schedule

## Phase 9 — Pilot
- [ ] Data statement + opt-out contact on site
- [ ] Pilot with 5–10 colleagues; log feedback
- [ ] Manual review: data/derived/spotcheck_topics.csv (100 tags) and spotcheck_pdf.csv (30 extractions) — fill in the ok-columns
- [ ] End-to-end re-run from cache

## Review
- 2026-10-21: Source probing completed; findings recorded in PLAN.md §2. Key facts:
  LUI = Cristin unit 215.4.0.0; NVA JSON needs `Accept: application/json`; NVA file
  download via `/publication/{id}/filelink/{fileId}`; group members via page-bound
  AJAX token in the same cookie session; OpenAlex gives topics/refs/citations by DOI.
- 2026-10-21: Implemented stages scrape-oslomet, scrape-cristin, scrape-nva, scrape-openalex, scrape-pdf,
  identity, verify. Lesson: with several concurrent SQLite writers, every network call must happen
  outside the write transaction and commits must be per item, otherwise writers starve each other.
- 2026-10-21 (evening): Full pipeline run end to end. Taxonomy v1 (78 topics / 10 macro) built and applied;
  web app complete with filters, seriated matrices and force graph. Open: user review of taxonomy labels,
  manual spot-check of 30 PDF extractions and 100 topic tags, GraphML export, pilot/hosting.
