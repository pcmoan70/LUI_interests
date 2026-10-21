# LUI forskningskart — research-interest map for OsloMet LUI

A local data pipeline and a static web app that map **who researches what** at the
Faculty of Education and International Studies (LUI), OsloMet: research topics, theories
and methods per person, coauthorship, citations, shared research groups and projects,
and external coauthors. The aim is practical: find colleagues to collaborate with, ask
for advice, or develop new research ideas together.

Everything runs locally. Sources are public (oslomet.no, Cristin, Nasjonalt vitenarkiv/NVA,
OpenAlex). No LLM API is required.

---

## Quick start

```bash
# 1. environment (Python 3.12+, Node is only needed for the optional syntax check)
python -m venv .venv
.venv/Scripts/python -m pip install -e .
.venv/Scripts/python -m pip install sentence-transformers      # embeddings (CPU is fine)

# 2. run the pipeline (Windows: set PYTHONUTF8=1 first)
set PYTHONUTF8=1
.venv/Scripts/python -m lui db-init
.venv/Scripts/python -m lui scrape-oslomet
.venv/Scripts/python -m lui scrape-cristin
.venv/Scripts/python -m lui scrape-nva
.venv/Scripts/python -m lui identity
.venv/Scripts/python -m lui scrape-openalex
.venv/Scripts/python -m lui scrape-pdf
.venv/Scripts/python -m lui embed
.venv/Scripts/python -m lui cluster -k 150        # only needed when (re)designing the taxonomy
.venv/Scripts/python -m lui tag -k 150
.venv/Scripts/python -m lui externals
.venv/Scripts/python -m lui tag -k 150            # gives the external nodes a light profile
.venv/Scripts/python -m lui build-edges
.venv/Scripts/python -m lui build-matrices
.venv/Scripts/python -m lui export-web
.venv/Scripts/python -m lui export-graph
.venv/Scripts/python -m lui verify

# 3. serve the web app
.venv/Scripts/python -m http.server 8765 --directory web
# open http://localhost:8765/
```

The first full run takes several hours (mostly polite rate limits against Cristin and NVA
and CPU embedding). Every HTTP response is cached under `data/raw/`, so re-runs are fast;
`--refresh` forces new downloads and `--max-age DAYS` controls cache age. `--limit N`
processes only N items for debugging.

---

## What the pipeline does

| Stage | What it does | Main output |
|---|---|---|
| `scrape-oslomet` | Staff listing (all units, academic/admin flag), profile pages (bio, department, groups, projects, publication tabs with internal coauthor links), research-group pages incl. the AJAX member lists, project pages | `person`, `research_group`, `group_member`, `project`, `profile_publication` |
| `scrape-cristin` | All persons under Cristin unit 215.4.0.0 (+ overrides), every result per person, every contributor list, OsloMet projects with LUI participants | `cristin_person`, `publication`, `publication_author`, `project_participant` |
| `scrape-nva` | Every NVA record for the faculty (cursor paging), full JSON for scientific items: abstracts, author keywords, verified contributor ids, open files; e-mails/ORCID per person | `publication_text`, `publication_keyword`, `publication_file` |
| `identity` | Links OsloMet usernames to Cristin ids by e-mail, name and DOI overlap, with `config/identity_overrides.csv` for the rest; propagates `person_id` to author rows | `person.cristin_person_id`, `person_keyword` |
| `scrape-openalex` | Batched DOI lookup: topic hierarchy, keywords, abstracts, reference lists, citation counts, OA links; internal citation edges | `openalex_topic`, `citation`, `publication_file` |
| `scrape-pdf` | Downloads open PDFs (NVA file links, OpenAlex OA) and extracts abstract, introduction and conclusion with multilingual heading rules | `publication_text` (kind intro/conclusion) |
| `embed` | One text per scientific publication (title, abstract, keywords, intro/conclusion) and per bio; multilingual sentence embeddings (`intfloat/multilingual-e5-base`), incremental | `data/derived/embeddings.npz`, `doc` |
| `cluster` | KMeans candidate clusters with c-TF-IDF descriptors and exemplars; the report used to design the taxonomy | `data/derived/clusters_k150.md` |
| `tag` | Assigns 1–4 topics per publication (embedding similarity to topic centroids + cluster membership + keyword evidence), theories and methods (regex vocabularies), aggregates person profiles (category weights, 8-year half-life, bio and Cristin keywords), writes an attribution audit | `pub_topic`, `pub_theory`, `pub_method`, `person_topic`, … |
| `externals` | Promotes external coauthors to light nodes (institution, country, ORCID for frequent coauthors, joint count); categories `former_lui`, `oslomet`, `external` | `person` (is_listed = 0) |
| `build-edges` | Person–person edges: coauthor, cites, shared_group, shared_project, topic_similarity | `person_edge` |
| `build-matrices` | Matrices as `.npz`, Louvain communities, spectral and co-cluster block orderings | `data/derived/matrices.npz`, `orders.json` |
| `export-web` | JSON bundles for the web app (never e-mail or full text) | `web/data/` |
| `export-graph` | GraphML, GEXF and CSV node/edge lists for Gephi, R, Python | `data/derived/person_graph.*` |
| `verify` | Coverage and invariant report | console |

All tables live in one SQLite file, `data/db/lui.sqlite` (schema in
`src/lui/db/schema.sql`). Open it with any SQLite browser.

---

## The web app (`web/`)

Static HTML/JS, no build step, Norwegian UI. Libraries from CDN: D3 (force layout,
heat maps), MiniSearch (search). Serve the folder with any static server.

| View | Purpose |
|---|---|
| **Utforsk** | Search and filter people; cards with primary topics; CSV download |
| **Publikasjoner** | Search all works with at least one known author (index loaded on demand) |
| **Interessematrise** | Persons × topics heat map, block-ordered by spectral co-clustering; build your own selection of persons and topics with the search fields (kept in the URL) |
| **Relasjonsmatrise** | Persons × persons, seriated to be as block-diagonal as possible (components → Louvain on the shown subset → spectral order; best of several candidates by arrangement cost, shown on screen) |
| **Graf** | D3 force layout on canvas: zoom, pan, drag, fit; edge types, weights and years; colour by department, macro group or community; external coauthors in grey |
| **Tema** | Taxonomy browser; each topic page lists persons, publications, trend and adjacent topics |
| **Person / par** | Profile, topics, theories, methods, publications, collaborators, suggested new partners; pair page with shared and complementary topics and joint work |
| **Finn samarbeid** | Ranked partner suggestions for a person or a free-text idea with adjustable weights |
| **PDF** | Every page has print CSS: use the PDF button or Ctrl/Cmd+P → save as PDF |

Filters are shared across views and persisted in the URL: department, staff type, macro
group, topic code (T01–T78), theory, method, research group, OpenAlex subfield, year
range, minimum scientific output, person scope (listed staff → LUI incl. former →
OsloMet → everyone incl. externals), edge types and weights.

Memory: the initial load is about 7.5 MB of JSON; publication lists are fetched per
person or topic when a page needs them. The optional "mer" link on a publication asks
OpenAlex for live citation and reference counts; if that fails, the stored data and the
DOI/NVA links stay as they are.

---

## Taxonomy and vocabularies (`config/taxonomy/`)

- `macro_topics.yaml` — 10 macro groups (M1–M10).
- `micro_topics.yaml` — 78 topics with bilingual labels, definitions, keywords and the
  candidate clusters that seed each topic centroid. Keywords also drive the lexical
  evidence channel, so keep them specific (word-boundary matching, ≥ 4 characters).
- `theories.yaml` (60) and `methods.yaml` (31) — regex alias lists, case-insensitive,
  matched against title + abstract + introduction + conclusion and against bios.

After editing any of these files run:

```bash
.venv/Scripts/python -m lui tag -k 150 && .venv/Scripts/python -m lui build-edges && .venv/Scripts/python -m lui build-matrices && .venv/Scripts/python -m lui export-web
```

`data/derived/attribution_audit.csv` lists interests stated in a bio or Cristin keyword
that did not make it into the person's profile (should be empty). Samples for manual
review: `data/derived/spotcheck_topics.csv` (100 tags) and `spotcheck_pdf.csv`
(30 extractions).

---

## Repository layout

```
PLAN.md                 full plan with verified source facts (section 2) and open questions (section 13)
README.md               this file
tasks/todo.md           checkable work plan and review log; tasks/lessons.md pitfalls
config/                 units.yaml, identity_overrides.csv, taxonomy/*.yaml
src/lui/                http.py (cached, rate-limited client), scrape/, identity.py, classify/, build/, db/, verify.py
data/raw/<source>/      every HTTP response as fetched (+ .meta.json)
data/pdf/               downloaded open-access PDFs (local only)
data/db/lui.sqlite      system of record
data/derived/           embeddings, clusters, matrices, orderings, graph exports, audit and spot-check files
web/                    the static app; web/data/ is regenerated by export-web
```

---

## Data sources and known quirks

- **oslomet.no**: server-rendered; research-group member lists come from an AJAX URL
  whose token is bound to the page view (fetch page and list in one cookie session).
- **Cristin API v2**: LUI is unit `215.4.0.0`. Some person records are access-restricted
  (401) and are treated as missing.
- **NVA**: request `Accept: application/json`; page with `nextSearchAfterResults`
  (offset paging stops at 10 000); PDFs via `/publication/{id}/filelink/{fileId}`
  (short-lived S3 link). The old ODA archive redirects here.
- **OpenAlex**: coverage of Norwegian-language works is partial; citations are therefore
  indicative. Papers with more than 30 authors (e.g. the ATLAS collaboration) are kept
  but excluded from coauthor edges and from external-node creation.
- Several concurrent scrapers share the SQLite file: fetch first, write afterwards,
  commit per item (see `tasks/lessons.md`).

---

## Privacy

Only public, professional information is used. E-mail addresses are stored solely as a
join key and never exported; phone numbers and photos are not stored. Full texts stay in
`data/` and are never shipped to the web bundle. Keep the site internal until the faculty
has approved it and include an opt-out contact (see the "Om" page).

---

## Status (2026-10-21)

Full pipeline run on all 628 listed staff (464 academic, 164 administrative), 26 unlisted
LUI-affiliated and 4 396 coauthor nodes; 36 222 publications (20 086 profiled);
78 topics / 10 macro groups; 9 101 coauthor, 4 468 citation, 11 630 group, 1 860 project
and about 9 000 topic-similarity edges. Open: review of the taxonomy labels, manual spot
checks, hosting and pilot. Details in `tasks/todo.md`.
