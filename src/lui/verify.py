"""Print data-quality invariants and coverage for every stage."""
from __future__ import annotations

from .db import connect

CHECKS = [
    ("persons listed", "SELECT COUNT(*) FROM person WHERE is_listed=1", 628),
    ("  academic", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND staff_type='academic'", 464),
    ("  admin", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND staff_type='admin'", 164),
    ("  with unit", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND unit_id IS NOT NULL", 628),
    ("  with bio (nb or en)", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND (bio_nb IS NOT NULL OR bio_en IS NOT NULL)", None),
    ("  resolved to Cristin", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND cristin_person_id IS NOT NULL", None),
    ("  with ORCID", "SELECT COUNT(*) FROM person WHERE is_listed=1 AND orcid IS NOT NULL", None),
    ("  with >=1 publication", "SELECT COUNT(DISTINCT person_id) FROM publication_author WHERE person_id IN (SELECT person_id FROM person WHERE is_listed=1)", None),
    ("persons unlisted (cristin only)", "SELECT COUNT(*) FROM person WHERE is_listed=0 AND resolved_by='cristin_only'", None),
    ("coauthor nodes: former LUI", "SELECT COUNT(*) FROM person WHERE staff_type='former_lui'", None),
    ("coauthor nodes: other OsloMet", "SELECT COUNT(*) FROM person WHERE staff_type='oslomet'", None),
    ("coauthor nodes: external", "SELECT COUNT(*) FROM person WHERE staff_type='external'", None),
    ("cristin persons", "SELECT COUNT(*) FROM cristin_person", 785),
    ("research groups", "SELECT COUNT(*) FROM research_group", None),
    ("  memberships", "SELECT COUNT(*) FROM group_member", None),
    ("projects (web)", "SELECT COUNT(*) FROM project WHERE project_id LIKE 'web:%'", None),
    ("projects (cristin)", "SELECT COUNT(*) FROM project WHERE project_id LIKE 'cristin:%'", None),
    ("  participants", "SELECT COUNT(*) FROM project_participant", None),
    ("publications", "SELECT COUNT(*) FROM publication", None),
    ("  core", "SELECT COUNT(*) FROM publication WHERE is_core=1", None),
    ("  with DOI", "SELECT COUNT(*) FROM publication WHERE doi IS NOT NULL", None),
    ("  with NVA id", "SELECT COUNT(*) FROM publication WHERE nva_id IS NOT NULL", None),
    ("  with OpenAlex id", "SELECT COUNT(*) FROM publication WHERE openalex_work_id IS NOT NULL", None),
    ("  core with abstract", "SELECT COUNT(DISTINCT p.pub_id) FROM publication p JOIN publication_text t ON t.pub_id=p.pub_id AND t.kind='abstract' WHERE p.is_core=1", None),
    ("  core with intro/conclusion", "SELECT COUNT(DISTINCT p.pub_id) FROM publication p JOIN publication_text t ON t.pub_id=p.pub_id AND t.kind IN ('intro','conclusion') WHERE p.is_core=1", None),
    ("  pubs without any author row", "SELECT COUNT(*) FROM publication p WHERE NOT EXISTS (SELECT 1 FROM publication_author a WHERE a.pub_id=p.pub_id)", 0),
    ("author rows", "SELECT COUNT(*) FROM publication_author", None),
    ("  internal", "SELECT COUNT(*) FROM publication_author WHERE is_internal=1", None),
    ("  linked to person", "SELECT COUNT(*) FROM publication_author WHERE person_id IS NOT NULL", None),
    ("keywords (nva/openalex/cristin)", "SELECT COUNT(*) FROM publication_keyword", None),
    ("openalex topics", "SELECT COUNT(*) FROM openalex_topic", None),
    ("internal citations", "SELECT COUNT(*) FROM citation", None),
    ("pdf files downloaded", "SELECT COUNT(*) FROM publication_file WHERE local_path IS NOT NULL", None),
    ("  sections extracted", "SELECT COUNT(*) FROM publication_file WHERE extracted_ok=1", None),
]


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    print(f"{'check':40s} {'value':>8s}  expected")
    for label, sql, expected in CHECKS:
        v = con.execute(sql).fetchone()[0]
        flag = "" if expected is None or v == expected else "  <-- differs"
        print(f"{label:40s} {v:>8d}  {expected if expected is not None else ''}{flag}")
    print("\npublications by group / core:")
    for g, n, c in con.execute("SELECT category_group, COUNT(*), SUM(is_core) FROM publication GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {g:10s} {n:6d}  core {c}")
    print("\nlisted persons by unit:")
    for u, n in con.execute("SELECT COALESCE(short_code,'?'), COUNT(*) FROM person LEFT JOIN unit USING(unit_id) WHERE is_listed=1 GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {u:6s} {n}")
    print("\nrun log:")
    for r in con.execute("SELECT stage, finished_at, rows, notes FROM run_log ORDER BY id DESC LIMIT 8"):
        print(f"  {r[0]:16s} {r[1][:19]} rows={r[2]} {r[3]}")
