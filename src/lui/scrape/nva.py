"""Scrape NVA (Nasjonalt vitenarkiv): all LUI publications, abstracts, tags, files, persons."""
from __future__ import annotations

import json

from ..db import connect, init_db, run_log, upsert
from ..http import Fetcher
from .cristin import CORE_GROUPS, WEIGHTS, norm_lang, norm_year

API = "https://api.nva.unit.no"
FACULTY = "215.4.0.0"
JSON = {"Accept": "application/json"}

TYPE_GROUP = {
    "AcademicArticle": "article", "AcademicLiteratureReview": "article", "JournalReview": "article",
    "AcademicChapter": "chapter", "ChapterArticle": "chapter", "Introduction": "chapter",
    "AcademicMonograph": "monograph", "BookAnthology": "monograph", "Encyclopedia": "monograph",
    "DegreePhd": "phd", "ArtisticDegreePhd": "phd",
    "DegreeMaster": "thesis", "DegreeBachelor": "thesis", "DegreeLicentiate": "thesis",
    "ReportResearch": "report", "ReportWorkingPaper": "report", "ReportPolicy": "report",
    "ReportBasic": "report", "ReportBookOfAbstract": "report", "ConferenceReport": "report",
    "ConferenceLecture": "lecture", "Lecture": "lecture", "ConferencePoster": "lecture",
    "ConferenceAbstract": "lecture", "OtherPresentation": "lecture", "ReportAbstract": "lecture",
    "Textbook": "textbook", "NonFictionMonograph": "textbook", "NonFictionChapter": "textbook",
    "ExhibitionCatalog": "textbook", "ProfessionalArticle": "popular",
    "PopularScienceArticle": "popular", "PopularScienceMonograph": "popular", "PopularScienceChapter": "popular",
    "MediaFeatureArticle": "popular", "JournalLetter": "popular", "JournalLeader": "popular",
    "JournalCorrigendum": "other", "MediaInterview": "media", "MediaParticipationInRadioOrTv": "media",
    "MediaPodcast": "media", "MediaReaderOpinion": "media", "MediaBlogPost": "media",
}


def hit_type(h: dict) -> str | None:
    try:
        return h["entityDescription"]["reference"]["publicationInstance"]["type"]
    except (KeyError, TypeError):
        return None


def ids_of(h: dict) -> tuple[str | None, str | None]:
    """(cristin_result_id, handle) from additionalIdentifiers."""
    cristin = handle = None
    for x in h.get("additionalIdentifiers") or []:
        if x.get("type") == "CristinIdentifier":
            cristin = x.get("value")
        elif x.get("type") == "HandleIdentifier":
            handle = x.get("value")
    return cristin, handle


def search_all(f: Fetcher, limit: int | None):
    url = f"{API}/search/resources?unit={FACULTY}&size=200&aggregation=none&sort=identifier"
    page = 0
    while url:
        d = f.get_json(url, key=f"search_lui_{page:04d}", headers=JSON)
        if not d or not d.get("hits"):
            break
        yield from d["hits"]
        page += 1
        if limit and page * 200 >= limit:
            break
        url = d.get("nextSearchAfterResults") or d.get("nextResults")   # from= paging stops at 10 000


def resolve_pub_id(con, h: dict) -> str:
    cristin_id, _ = ids_of(h)
    nva_id = h["identifier"]
    row = con.execute("SELECT pub_id FROM publication WHERE nva_id=? OR (cristin_result_id IS NOT NULL AND cristin_result_id=?)",
                      (nva_id, cristin_id)).fetchone()
    return row[0] if row else (cristin_id or nva_id)


def store_hit(con, h: dict) -> str:
    """Create/complete a publication row from a search hit."""
    pub_id = resolve_pub_id(con, h)
    cristin_id, handle = ids_of(h)
    ed = h.get("entityDescription") or {}
    t = hit_type(h)
    grp = TYPE_GROUP.get(t or "", "other")
    ref = ed.get("reference") or {}
    ctx = ref.get("publicationContext") or {}
    inst = ref.get("publicationInstance") or {}
    doi = ref.get("doi") or ctx.get("doi") or inst.get("doi")
    if doi:
        doi = doi.lower().replace("https://doi.org/", "")
    year = (ed.get("publicationDate") or {}).get("year")
    lang = norm_lang(ed.get("language"))
    upsert(con, "publication", {
        "pub_id": pub_id, "cristin_result_id": cristin_id, "nva_id": h["identifier"], "doi": doi, "handle": handle,
        "title": ed.get("mainTitle"), "year": norm_year(year), "language": lang,
        "category_code": t, "category_group": grp,
        "venue_name": ctx.get("name") or (ctx.get("publisher") or {}).get("name"),
        "nvi_level": {"LevelOne": "1", "LevelTwo": "2"}.get(ctx.get("scientificValue")),
        "is_core": int(grp in CORE_GROUPS), "weight": WEIGHTS.get(grp, 0.1),
        "n_authors": ed.get("contributorsCount"),
    }, keys=["pub_id"])
    # hits that never get a detail fetch still get their authors from the preview
    if not con.execute("SELECT 1 FROM publication_author WHERE pub_id=?", (pub_id,)).fetchone():
        store_contributors(con, pub_id, ed.get("contributorsPreview") or ed.get("contributors") or [])
    return pub_id


def store_contributors(con, pub_id: str, contributors: list[dict]) -> None:
    for c in contributors:
        ident = c.get("identity") or {}
        cid = (ident.get("id") or "").rsplit("/", 1)[-1] or None
        units = [(a.get("id") or "").rsplit("/", 1)[-1] for a in c.get("affiliations") or [] if a.get("id")]
        upsert(con, "publication_author", {
            "pub_id": pub_id, "author_order": int(c.get("sequence") or 0), "cristin_person_id": cid,
            "name_raw": ident.get("name"),
            "affiliation_unit_id": next((u for u in units if u.startswith("215.")), units[0] if units else None),
            "is_internal": int(any(u.startswith("215.") for u in units)),
        }, keys=["pub_id", "author_order"])


def store_detail(con, pub_id: str, d: dict) -> None:
    ed = d.get("entityDescription") or {}
    lang = norm_lang(ed.get("language"))
    if ed.get("abstract"):
        upsert(con, "publication_text", {"pub_id": pub_id, "kind": "abstract", "source": "nva", "lang": lang,
                                         "text": ed["abstract"], "char_count": len(ed["abstract"])})
        con.execute("UPDATE publication SET is_core=1 WHERE pub_id=? AND category_group='lecture'", (pub_id,))
    for i, (al, txt) in enumerate((ed.get("alternativeAbstracts") or {}).items()):
        if txt:
            upsert(con, "publication_text", {"pub_id": pub_id, "kind": "alt_abstract", "source": "nva", "lang": al,
                                             "text": txt, "char_count": len(txt)})
    for tag in ed.get("tags") or []:
        if tag and tag.strip():
            upsert(con, "publication_keyword", {"pub_id": pub_id, "keyword": tag.strip(), "source": "nva_tag", "score": 1.0})
    # contributors: fill in when Cristin gave us nothing for this publication
    have = con.execute("SELECT COUNT(*) FROM publication_author WHERE pub_id=?", (pub_id,)).fetchone()[0]
    if not have:
        store_contributors(con, pub_id, ed.get("contributors") or [])
    for a in d.get("associatedArtifacts") or []:
        if a.get("type") == "OpenFile" and (a.get("mimeType") or "").startswith("application/pdf"):
            lic = a.get("license")
            upsert(con, "publication_file", {
                "pub_id": pub_id, "file_id": a["identifier"], "licence": lic.get("value") if isinstance(lic, dict) else lic,
                "version": a.get("publisherVersion"), "mime": a.get("mimeType"),
                "size": int(a["size"]) if a.get("size") else None, "source": "nva",
            }, keys=["pub_id", "file_id"])
    for p in d.get("projects") or []:
        cid = (p.get("id") or "").rsplit("/", 1)[-1]
        if cid:
            upsert(con, "project", {"project_id": f"cristin:{cid}", "cristin_project_id": cid, "title_nb": p.get("name"),
                                    "url": f"https://app.cristin.no/projects/show.jsf?id={cid}"}, keys=["project_id"])


def run(refresh=False, max_age=30, limit=None) -> None:
    init_db()
    con = connect()
    f = Fetcher("nva", max_age_days=max_age, refresh=refresh)
    with run_log(con, "scrape-nva") as log:
        n_hits = n_detail = 0
        for h in search_all(f, limit):
            grp = TYPE_GROUP.get(hit_type(h) or "", "other")
            has_files = bool(h.get("associatedArtifacts")) or (h.get("filesStatus") not in (None, "noFiles"))
            d = None
            if grp in CORE_GROUPS or grp == "lecture" or has_files:
                d = f.get_json(f"{API}/publication/{h['identifier']}", key=f"pub_{h['identifier']}", headers=JSON)
            pub_id = store_hit(con, h)
            n_hits += 1
            if d:
                store_detail(con, pub_id, d)
                n_detail += 1
            con.commit()
            if n_hits % 200 == 0:
                print(f"  hits {n_hits}, details {n_detail}  ({f.stats()})", flush=True)
        con.commit()

        # e-mail / orcid for every Cristin person we know
        n_pers = 0
        for (cid,) in con.execute("SELECT cristin_person_id FROM cristin_person").fetchall():
            d = f.get_json(f"{API}/cristin/person/{cid}", key=f"person_{cid}", headers=JSON)
            if not d:
                continue
            orcid = next((x["value"] for x in d.get("identifiers", []) if x.get("type") == "ORCID"), None)
            email = ((d.get("contactDetails") or {}).get("email") or "").lower() or None
            con.execute("UPDATE cristin_person SET orcid=COALESCE(orcid,?), email=COALESCE(email,?) WHERE cristin_person_id=?",
                        (orcid, email, cid))
            con.commit()
            n_pers += 1
        con.commit()
        log["rows"] = n_hits
        log["notes"] = f"{n_hits} hits, {n_detail} details, {n_pers} persons; {f.stats()}"
    print("done:", log["notes"])
