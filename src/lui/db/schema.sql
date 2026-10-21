PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS unit (
  unit_id TEXT PRIMARY KEY,          -- cristin unit id e.g. 215.4.3.0
  parent_unit_id TEXT,
  name_nb TEXT, name_en TEXT, short_code TEXT
);

CREATE TABLE IF NOT EXISTS person (
  person_id TEXT PRIMARY KEY,        -- oslomet username, else 'cristin:<id>'
  username TEXT UNIQUE,
  cristin_person_id TEXT UNIQUE,
  orcid TEXT,
  openalex_author_id TEXT,
  name_full TEXT NOT NULL,
  name_first TEXT, name_last TEXT,
  title_nb TEXT, title_en TEXT,
  staff_type TEXT,                   -- academic | admin | NULL(unknown)
  unit_id TEXT REFERENCES unit(unit_id),
  unit_name_raw TEXT,
  bio_nb TEXT, bio_en TEXT,
  cristin_background TEXT,
  email TEXT,                        -- join key only; never exported
  profile_url TEXT,
  resolved_by TEXT, resolution_confidence REAL,
  is_listed INTEGER DEFAULT 1,       -- 1 = on oslomet LUI listing
  affiliation TEXT, country TEXT, n_joint INTEGER   -- external coauthors
);

-- staging table for Cristin persons under LUI (merged into person by identity stage)
CREATE TABLE IF NOT EXISTS cristin_person (
  cristin_person_id TEXT PRIMARY KEY,
  first_name TEXT, surname TEXT, orcid TEXT, email TEXT,
  background TEXT, keywords_json TEXT, affiliations_json TEXT,
  unit_id TEXT, position TEXT, active INTEGER, n_results INTEGER
);

CREATE TABLE IF NOT EXISTS research_group (
  group_id TEXT PRIMARY KEY,         -- slug
  name TEXT, url TEXT, description TEXT, methods_text TEXT, member_block_id TEXT
);
CREATE TABLE IF NOT EXISTS group_member (
  group_id TEXT REFERENCES research_group(group_id),
  person_id TEXT,                    -- NULL for externals without profile
  username TEXT, name_raw TEXT,
  role TEXT,                         -- leader | primary | secondary | external
  PRIMARY KEY (group_id, name_raw, role)
);

CREATE TABLE IF NOT EXISTS project (
  project_id TEXT PRIMARY KEY,       -- 'cristin:<id>' or 'web:<slug>'
  cristin_project_id TEXT, slug TEXT,
  title_nb TEXT, title_en TEXT, summary TEXT,
  start_date TEXT, end_date TEXT, status TEXT,
  coordinating_unit_id TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS project_participant (
  project_id TEXT REFERENCES project(project_id),
  person_id TEXT, cristin_person_id TEXT, username TEXT, name_raw TEXT, role TEXT,
  PRIMARY KEY (project_id, name_raw, role)
);
CREATE TABLE IF NOT EXISTS project_keyword (
  project_id TEXT REFERENCES project(project_id), keyword TEXT,
  PRIMARY KEY (project_id, keyword)
);

CREATE TABLE IF NOT EXISTS publication (
  pub_id TEXT PRIMARY KEY,           -- cristin result id when known, else nva id
  cristin_result_id TEXT UNIQUE, nva_id TEXT UNIQUE,
  doi TEXT, handle TEXT,
  title TEXT, year INTEGER, language TEXT,
  category_code TEXT, category_group TEXT,
  venue_name TEXT, venue_id TEXT, nvi_level TEXT,
  openalex_work_id TEXT, cited_by_count INTEGER, fwci REAL,
  is_core INTEGER DEFAULT 0, weight REAL DEFAULT 1.0,
  n_authors INTEGER
);
CREATE INDEX IF NOT EXISTS ix_pub_doi ON publication(doi);
CREATE INDEX IF NOT EXISTS ix_pub_year ON publication(year);

CREATE TABLE IF NOT EXISTS publication_author (
  pub_id TEXT REFERENCES publication(pub_id),
  author_order INTEGER,
  cristin_person_id TEXT, person_id TEXT, name_raw TEXT,
  affiliation_unit_id TEXT, is_internal INTEGER DEFAULT 0, openalex_author_id TEXT,
  PRIMARY KEY (pub_id, author_order)
);
CREATE INDEX IF NOT EXISTS ix_pa_person ON publication_author(person_id);
CREATE INDEX IF NOT EXISTS ix_pa_cristin ON publication_author(cristin_person_id);

CREATE TABLE IF NOT EXISTS publication_text (
  pub_id TEXT REFERENCES publication(pub_id),
  kind TEXT,                         -- abstract | alt_abstract | intro | conclusion | fulltext
  source TEXT,                       -- nva | cristin | openalex | pdf
  lang TEXT, text TEXT, char_count INTEGER, licence TEXT,
  PRIMARY KEY (pub_id, kind, source)
);
CREATE TABLE IF NOT EXISTS publication_file (
  pub_id TEXT REFERENCES publication(pub_id), file_id TEXT,
  licence TEXT, version TEXT, mime TEXT, size INTEGER, source TEXT,
  local_path TEXT, pages INTEGER, extracted_ok INTEGER, url TEXT,
  PRIMARY KEY (pub_id, file_id)
);
CREATE TABLE IF NOT EXISTS openalex_ref (work_id TEXT, ref_work_id TEXT, PRIMARY KEY (work_id, ref_work_id));
CREATE INDEX IF NOT EXISTS ix_oaref_ref ON openalex_ref(ref_work_id);
CREATE TABLE IF NOT EXISTS publication_keyword (
  pub_id TEXT REFERENCES publication(pub_id), keyword TEXT, source TEXT, score REAL,
  PRIMARY KEY (pub_id, keyword, source)
);
CREATE TABLE IF NOT EXISTS openalex_topic (
  pub_id TEXT REFERENCES publication(pub_id), topic_id TEXT, topic_name TEXT,
  subfield TEXT, field TEXT, domain TEXT, score REAL,
  PRIMARY KEY (pub_id, topic_id)
);
CREATE TABLE IF NOT EXISTS citation (
  citing_pub_id TEXT, cited_pub_id TEXT, source TEXT DEFAULT 'openalex',
  PRIMARY KEY (citing_pub_id, cited_pub_id)
);
CREATE TABLE IF NOT EXISTS person_keyword (
  person_id TEXT, keyword TEXT, source TEXT,  -- cristin | bio_llm
  PRIMARY KEY (person_id, keyword, source)
);
-- web profile publication list (for cross-checking coauthor links)
CREATE TABLE IF NOT EXISTS profile_publication (
  username TEXT, tab TEXT, year INTEGER, title TEXT, doi TEXT, handle TEXT,
  internal_usernames TEXT,           -- JSON list
  raw TEXT,
  PRIMARY KEY (username, tab, raw)
);

-- text documents used for embedding / clustering
CREATE TABLE IF NOT EXISTS doc (doc_id TEXT PRIMARY KEY, kind TEXT, text TEXT, n_chars INTEGER);

-- classification layer
CREATE TABLE IF NOT EXISTS macro_topic (macro_id TEXT PRIMARY KEY, slug TEXT, label_nb TEXT, label_en TEXT, definition TEXT, colour TEXT);
CREATE TABLE IF NOT EXISTS topic (
  topic_id TEXT PRIMARY KEY, slug TEXT, label_nb TEXT, label_en TEXT,
  definition_nb TEXT, definition_en TEXT, macro_id TEXT REFERENCES macro_topic(macro_id),
  keywords_json TEXT, exemplar_pub_ids_json TEXT
);
CREATE TABLE IF NOT EXISTS theory (theory_id TEXT PRIMARY KEY, label TEXT, aliases_json TEXT);
CREATE TABLE IF NOT EXISTS method (method_id TEXT PRIMARY KEY, label TEXT, aliases_json TEXT);
CREATE TABLE IF NOT EXISTS pub_topic (pub_id TEXT, topic_id TEXT, weight REAL, evidence TEXT, rationale TEXT, PRIMARY KEY (pub_id, topic_id));
CREATE TABLE IF NOT EXISTS pub_theory (pub_id TEXT, theory_id TEXT, confidence REAL, quote TEXT, PRIMARY KEY (pub_id, theory_id));
CREATE TABLE IF NOT EXISTS pub_method (pub_id TEXT, method_id TEXT, confidence REAL, PRIMARY KEY (pub_id, method_id));
CREATE TABLE IF NOT EXISTS person_topic (person_id TEXT, topic_id TEXT, score REAL, n_pubs INTEGER, is_primary INTEGER, PRIMARY KEY (person_id, topic_id));
CREATE TABLE IF NOT EXISTS person_theory (person_id TEXT, theory_id TEXT, score REAL, PRIMARY KEY (person_id, theory_id));
CREATE TABLE IF NOT EXISTS person_method (person_id TEXT, method_id TEXT, score REAL, PRIMARY KEY (person_id, method_id));

CREATE TABLE IF NOT EXISTS person_edge (
  src_person_id TEXT, dst_person_id TEXT, edge_type TEXT,
  weight REAL, n_evidence INTEGER, evidence_json TEXT, first_year INTEGER, last_year INTEGER,
  PRIMARY KEY (src_person_id, dst_person_id, edge_type)
);

CREATE TABLE IF NOT EXISTS run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT, started_at TEXT, finished_at TEXT, rows INTEGER, notes TEXT
);
