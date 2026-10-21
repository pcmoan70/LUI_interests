"""Scrape oslomet.no: LUI staff listing, profiles, research groups, projects."""
from __future__ import annotations

import json
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup

from ..db import connect, init_db, run_log, upsert
from ..http import Fetcher, safe_key

BASE = "https://www.oslomet.no"
LIST_URL = BASE + "/om/ansatteoversikt?unitcode=lui"

# sectioncode on profile pages -> cristin unit id
SECTION_TO_UNIT = {
    "lui-u-blu": "215.4.2.0", "lui-u-gfu": "215.4.3.0", "lui-u-ist": "215.4.4.0",
    "lui-u-ylu": "215.4.5.0", "lui-u-nafo": "215.4.7.0", "lui-u-fadm": "215.4.1.0",
    "lui-u-adm": "215.4.1.0",
}
UNIT_NAME_TO_ID = {
    "institutt for barnehagelærerutdanning": "215.4.2.0",
    "institutt for grunnskole- og faglærerutdanning": "215.4.3.0",
    "institutt for internasjonale studier og tolkeutdanning": "215.4.4.0",
    "institutt for yrkesfaglærerutdanning": "215.4.5.0",
    "nasjonalt senter for flerkulturell opplæring": "215.4.7.0",
    "fakultetsadministrasjonen": "215.4.1.0",
    "timelønnede lui": "215.4.6.0",
}


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


# ----------------------------------------------------------------------------- listing
def parse_listing(html: str) -> list[dict]:
    out = []
    for a in soup(html).select("a.m-list-item.profile[href^='/om/ansatt/']"):
        username = a["href"].strip("/").split("/")[-1]
        name = text(a.select_one(".a-headline.h4"))
        title = text(a.select_one(".a-headline.h5"))
        email = next((text(li) for li in a.select(".a-metadata-list li") if "@" in text(li)), None)
        out.append({"username": username, "name_full": name, "title_nb": title or None,
                    "email": email.lower() if email else None})
    return out


def scrape_listing(f: Fetcher) -> dict[str, dict]:
    persons: dict[str, dict] = {}
    for typ in ("", "vitenskapelig", "administrativ"):
        page = 1
        while True:
            url = LIST_URL + (f"&type={typ}" if typ else "") + f"&p={page}"
            html = f.get_text(url, key=f"list_{typ or 'all'}_{page:02d}")
            cards = parse_listing(html or "")
            if not cards:
                break
            for c in cards:
                p = persons.setdefault(c["username"], c)
                if typ:
                    p["staff_type"] = "academic" if typ == "vitenskapelig" else "admin"
            if f"p={page + 1}" not in html:
                break
            page += 1
    return persons


# ----------------------------------------------------------------------------- profile
def parse_profile(html: str, username: str) -> dict:
    s = soup(html)
    d: dict = {"username": username, "groups": [], "projects": [], "pubs": []}
    d["name_full"] = text(s.select_one(".page-title")) or None

    for item in s.select(".o-metadata-list-block .m-metadata-list-item"):
        label = text(item.select_one(".a-headline")).lower()
        items = item.select("ul.items > li")
        if label.startswith("stillingstittel"):
            d["title_nb"] = text(items[0]) if items else None
        elif label.startswith("e-post"):
            d["email"] = text(items[0]).lower() if items else None
        elif label.startswith("tilhørighet"):
            links = item.select("a[href*='sectioncode=']")
            d["unit_name_raw"] = " / ".join(text(a) for a in item.select("dd a"))
            for a in links:
                m = re.search(r"sectioncode=([a-z0-9-]+)", a["href"])
                code = m.group(1) if m else ""
                # the department code is the first two dash-groups after 'lui-u-'
                dept = "-".join(code.split("-")[:3])
                if dept in SECTION_TO_UNIT:
                    d["unit_id"] = SECTION_TO_UNIT[dept]
                    break
            if "unit_id" not in d:
                for a in item.select("dd a"):
                    uid = UNIT_NAME_TO_ID.get(text(a).lower())
                    if uid:
                        d["unit_id"] = uid
                        break

    art = s.select_one(".article-content")
    if art:
        # bio = paragraphs directly after the 'Kort om' heading
        h = next((h for h in art.select("h2") if text(h).lower().startswith("kort om")), None)
        if h:
            paras = []
            for sib in h.find_next_siblings():
                if sib.name == "h2" or "o-list-block" in sib.get("class", []) or "tabs-container" in sib.get("class", []):
                    break
                if sib.name in ("p", "ul", "ol", "div") and "o-unordered-list-block" not in sib.get("class", []):
                    paras.append(text(sib))
            d["bio_nb"] = "\n".join(p for p in paras if p) or None

        for a in art.select("a[href^='/forskning/forskningsgrupper/']"):
            d["groups"].append({"slug": a["href"].strip("/").split("/")[-1], "name": text(a)})
        for a in art.select("a[href^='/forskning/forskningsprosjekter/']"):
            blurb = a.find_next_sibling("p")
            d["projects"].append({"slug": a["href"].strip("/").split("/")[-1], "name": text(a),
                                  "blurb": text(blurb) if blurb else None})

        tabs = {a["href"].lstrip("#"): re.sub(r"\s*\(\d+\)\s*$", "", text(a))
                for a in art.select("a[tab-render-content]")}
        for w in art.select("div.tab-content-wrapper"):
            tab = tabs.get(w.get("id", ""), text(w.select_one("h3")))
            for p in w.select("p.a-paragraph"):
                raw = text(p)
                internal = [a["href"].strip("/").split("/")[-1] for a in p.select("a[href^='/om/ansatt/']")]
                doi = next((a["href"] for a in p.select("a.external") if "doi.org" in a["href"]), None)
                handle = next((a["href"] for a in p.select("a.external") if "hdl.handle.net" in a["href"]), None)
                m = re.search(r"\((\d{4})\)\.\s*(.*?)(?:\.\s|$)", raw)
                d["pubs"].append({"tab": tab, "year": int(m.group(1)) if m else None,
                                  "title": m.group(2).strip() if m else None,
                                  "doi": doi, "handle": handle, "internal": internal, "raw": raw})
    return d


# ----------------------------------------------------------------------------- groups
def parse_group(html: str, slug: str) -> dict:
    s = soup(html)
    d = {"group_id": slug, "name": text(s.select_one("h1")),
         "url": f"{BASE}/forskning/forskningsgrupper/{slug}", "leaders": [], "member_action": None}
    art = s.select_one(".article-content") or s
    d["description"] = "\n".join(text(p) for p in art.select("p.a-paragraph")[:40]) or None
    # leaders: links to profiles before the member accordion
    # leaders are embedded as usernames in an ajax employee-block url
    for el in s.select("[data-action*='/ajax/module/employee/block/']"):
        m = re.search(r"/ajax/module/employee/block/[^/]+/([^?\"]+)", el["data-action"])
        if m and "leder" in el["data-action"].lower() or m and "leiar" in el["data-action"].lower():
            d["leaders"] += [{"username": u, "name": None} for u in m.group(1).split(",") if u]
    m = s.select_one("[data-action*='/ajax/module/member/block/']")
    if m:
        d["member_action"] = m["data-action"]
    return d


def parse_members(html: str) -> list[dict]:
    s = soup(html)
    out, role = [], "primary"
    for el in s.find_all(["h2", "h3", "a"]):
        if el.name in ("h2", "h3"):
            t = text(el).lower()
            role = ("leader" if re.search(r"leder|leiar", t) else "secondary" if "sekund" in t
                    else "external" if "ekstern" in t else "primary")
        elif el.get("href", "").startswith("/om/ansatt/"):
            out.append({"username": el["href"].strip("/").split("/")[-1], "name": text(el), "role": role})
        elif el.name == "a" and el.find_parent("li") and "a-link" in el.get("class", []):
            out.append({"username": None, "name": text(el), "role": role})
    return out


def scrape_group(f: Fetcher, slug: str) -> tuple[dict, list[dict]]:
    url = f"{BASE}/forskning/forskningsgrupper/{slug}"
    html = f.get_text(url, key=f"group_{slug}")
    if html is None:
        return {"group_id": slug, "name": None, "url": url}, []
    g = parse_group(html, slug)
    members: list[dict] = []
    if g["member_action"]:
        # token is bound to the page view: load page + ajax in one cookie session
        body_p, meta_p = f._paths(f"group_{slug}_members", "html")
        if f.refresh or not body_p.exists():
            with httpx.Client(headers={"User-Agent": f.client.headers["User-Agent"]}, timeout=60) as c:
                page = c.get(url)
                m = re.search(r'data-action="(/ajax/module/member/block/[^"]+)"', page.text)
                if m:
                    action = m.group(1).replace("&amp;", "&")
                    r = c.get(BASE + action, headers={"Referer": url, "X-Requested-With": "XMLHttpRequest"})
                    f.n_network += 2
                    if r.status_code == 200 and len(r.text) > 100:
                        body_p.write_text(r.text, encoding="utf-8")
                        meta_p.write_text(json.dumps({"url": BASE + action, "status": 200,
                                                      "fetched_ts": time.time()}), encoding="utf-8")
        if body_p.exists():
            members = parse_members(body_p.read_text(encoding="utf-8"))
    return g, members


# ----------------------------------------------------------------------------- projects
def parse_project(html: str, slug: str) -> dict:
    s = soup(html)
    art = s.select_one(".article-content") or s
    d = {"slug": slug, "title_nb": text(s.select_one("h1")),
         "url": f"{BASE}/forskning/forskningsprosjekter/{slug}", "participants": []}
    d["summary"] = "\n".join(text(p) for p in art.select("p.a-paragraph")[:30]) or None
    for a in s.select("a[href^='/om/ansatt/']"):
        d["participants"].append({"username": a["href"].strip("/").split("/")[-1], "name": text(a)})
    md = text(s.select_one(".o-metadata-list-block"))
    m = re.search(r"(\d{4})\s*[-–]\s*(\d{4})", md)
    if m:
        d["start_date"], d["end_date"] = m.group(1), m.group(2)
    return d


# ----------------------------------------------------------------------------- run
def run(refresh=False, max_age=30, limit=None) -> None:
    init_db()
    con = connect()
    f = Fetcher("oslomet", max_age_days=max_age, refresh=refresh)

    with run_log(con, "scrape-oslomet") as log:
        persons = scrape_listing(f)
        print(f"listing: {len(persons)} persons", flush=True)
        usernames = list(persons)[:limit] if limit else list(persons)

        group_slugs: dict[str, str] = {}
        project_slugs: dict[str, str] = {}
        for i, u in enumerate(usernames, 1):
            html = f.get_text(f"{BASE}/om/ansatt/{u}/", key=f"profile_{u}")
            p = dict(persons[u])
            prof = parse_profile(html, u) if html else {"groups": [], "projects": [], "pubs": []}
            for k in ("name_full", "title_nb", "email", "unit_id", "unit_name_raw", "bio_nb"):
                if prof.get(k):
                    p[k] = prof[k]
            if not p.get("bio_nb"):
                en = f.get_text(f"{BASE}/en/about/employee/{u}/", key=f"profile_en_{u}")
                if en:
                    pe = parse_profile(en, u)
                    p["bio_en"] = pe.get("bio_nb")
                    p["title_en"] = pe.get("title_nb")
            # all network done for this person; now write
            for g in prof["groups"]:
                group_slugs[g["slug"]] = g["name"]
            for pr in prof["projects"]:
                project_slugs[pr["slug"]] = pr["name"]
                upsert(con, "project", {"project_id": f"web:{pr['slug']}", "slug": pr["slug"],
                                        "title_nb": pr["name"], "summary": pr["blurb"],
                                        "url": f"{BASE}/forskning/forskningsprosjekter/{pr['slug']}"},
                       keys=["project_id"])
                upsert(con, "project_participant", {"project_id": f"web:{pr['slug']}", "person_id": u,
                                                    "username": u, "name_raw": p["name_full"], "role": "member"})
            for pub in prof["pubs"]:
                upsert(con, "profile_publication", {"username": u, "tab": pub["tab"], "year": pub["year"],
                                                    "title": pub["title"], "doi": pub["doi"], "handle": pub["handle"],
                                                    "internal_usernames": json.dumps(pub["internal"]), "raw": pub["raw"]})
            parts = p["name_full"].split()
            upsert(con, "person", {
                "person_id": u, "username": u, "name_full": p["name_full"],
                "name_first": " ".join(parts[:-1]) or None, "name_last": parts[-1] if parts else None,
                "title_nb": p.get("title_nb"), "title_en": p.get("title_en"), "staff_type": p.get("staff_type"),
                "unit_id": p.get("unit_id") or "215.4.0.0", "unit_name_raw": p.get("unit_name_raw"),
                "bio_nb": p.get("bio_nb"), "bio_en": p.get("bio_en"), "email": p.get("email"),
                "profile_url": f"{BASE}/om/ansatt/{u}/", "is_listed": 1,
            }, keys=["person_id"])
            con.commit()
            if i % 25 == 0:
                print(f"  profiles {i}/{len(usernames)}  ({f.stats()})", flush=True)
        con.commit()

        print(f"groups: {len(group_slugs)}", flush=True)
        for slug in group_slugs:
            g, members = scrape_group(f, slug)
            upsert(con, "research_group", {"group_id": slug, "name": g.get("name") or group_slugs[slug],
                                           "url": g["url"], "description": g.get("description"),
                                           "member_block_id": g.get("member_action")}, keys=["group_id"])
            for l in g.get("leaders", []):
                upsert(con, "group_member", {"group_id": slug, "person_id": l["username"], "username": l["username"],
                                             "name_raw": l["name"], "role": "leader"})
            for m in members:
                upsert(con, "group_member", {"group_id": slug, "person_id": m["username"], "username": m["username"],
                                             "name_raw": m["name"], "role": m["role"]})
            con.commit()
        con.commit()

        print(f"projects: {len(project_slugs)}", flush=True)
        for slug in project_slugs:
            html = f.get_text(f"{BASE}/forskning/forskningsprosjekter/{slug}", key=f"project_{slug}")
            if not html:
                continue
            pr = parse_project(html, slug)
            upsert(con, "project", {"project_id": f"web:{slug}", "slug": slug, "title_nb": pr["title_nb"],
                                    "summary": pr["summary"], "start_date": pr.get("start_date"),
                                    "end_date": pr.get("end_date"), "url": pr["url"]}, keys=["project_id"])
            for pp in pr["participants"]:
                upsert(con, "project_participant", {"project_id": f"web:{slug}", "person_id": pp["username"],
                                                    "username": pp["username"], "name_raw": pp["name"], "role": "member"})
            con.commit()
        con.commit()
        log["rows"] = len(usernames)
        log["notes"] = f.stats()
    print("done:", f.stats())


if __name__ == "__main__":
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
