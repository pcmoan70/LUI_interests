"""Resolve OsloMet usernames <-> Cristin person ids, then propagate person_id everywhere."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict

from .db import connect, run_log, upsert
from .paths import CONFIG_DIR, DERIVED_DIR

OVERRIDES = CONFIG_DIR / "identity_overrides.csv"   # columns: username,cristin_person_id


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("-", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def tokens(s: str | None) -> list[str]:
    return norm(s).split()


def name_score(web_name: str, first: str, last: str) -> float:
    """1.0 exact token set; 0.8 same last token + same first token; else 0."""
    w = tokens(web_name)
    c = tokens(first) + tokens(last)
    if not w or not c:
        return 0.0
    if set(w) == set(c):
        return 1.0
    if w[-1] == c[-1] and w[0] == c[0]:
        return 0.85
    # web form may contain the Cristin surname fully (e.g. double surnames)
    if tokens(last) and all(t in w for t in tokens(last)) and w[0] == c[0]:
        return 0.8
    return 0.0


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    cps = [dict(r) for r in con.execute("SELECT * FROM cristin_person")]
    by_email = {c["email"]: c for c in cps if c.get("email")}
    persons = [dict(r) for r in con.execute("SELECT * FROM person WHERE is_listed=1")]

    overrides: dict[str, str] = {}
    if OVERRIDES.exists():
        with OVERRIDES.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("username") and row.get("cristin_person_id"):
                    overrides[row["username"].strip()] = row["cristin_person_id"].strip()

    # DOI overlap: username -> {doi}, cristin -> {doi}
    web_dois: dict[str, set[str]] = defaultdict(set)
    for u, doi in con.execute("SELECT username, doi FROM profile_publication WHERE doi IS NOT NULL"):
        web_dois[u].add(doi.lower().replace("https://doi.org/", ""))
    cr_dois: dict[str, set[str]] = defaultdict(set)
    for cid, doi in con.execute("""SELECT pa.cristin_person_id, p.doi FROM publication_author pa
                                   JOIN publication p ON p.pub_id=pa.pub_id
                                   WHERE pa.cristin_person_id IS NOT NULL AND p.doi IS NOT NULL"""):
        cr_dois[cid].add(doi)

    with run_log(con, "identity") as log:
        used: dict[str, str] = {}     # cristin id -> username
        how = Counter()
        unresolved = []
        for p in persons:
            u = p["username"]
            match, method, conf = None, None, 0.0
            if u in overrides:
                match, method, conf = overrides[u], "manual", 1.0
            elif p.get("email") and p["email"] in by_email:
                match, method, conf = by_email[p["email"]]["cristin_person_id"], "email", 0.99
            else:
                scored = sorted(((name_score(p["name_full"], c["first_name"], c["surname"]), c) for c in cps),
                                key=lambda x: -x[0])
                best = [c for sc, c in scored if sc >= 0.8 and sc == scored[0][0]]
                if len(best) == 1 and scored[0][0] >= 0.8:
                    match, method, conf = best[0]["cristin_person_id"], "name", scored[0][0]
                elif len(best) > 1:
                    # tie-break with DOI overlap
                    ov = [(len(web_dois[u] & cr_dois[c["cristin_person_id"]]), c) for c in best]
                    ov.sort(key=lambda x: -x[0])
                    if ov[0][0] > 0:
                        match, method, conf = ov[0][1]["cristin_person_id"], "name+doi", 0.95
                if not match and web_dois[u]:
                    ov = sorted(((len(web_dois[u] & cr_dois[c["cristin_person_id"]]), c) for c in cps), key=lambda x: -x[0])
                    n, c = ov[0]
                    if n >= 2 and tokens(c["surname"]) and tokens(p["name_full"])[-1] == tokens(c["surname"])[-1]:
                        match, method, conf = c["cristin_person_id"], "doi", 0.9
            if match and match in used and used[match] != u:
                unresolved.append((u, p["name_full"], f"cristin {match} already used by {used[match]}"))
                match = None
            if match:
                used[match] = u
                c = next(x for x in cps if x["cristin_person_id"] == match)
                how[method] += 1
                con.execute("""UPDATE person SET cristin_person_id=?, orcid=COALESCE(orcid,?), email=COALESCE(email,?),
                               cristin_background=?, resolved_by=?, resolution_confidence=?,
                               unit_id=COALESCE(unit_id,?) WHERE person_id=?""",
                            (match, c.get("orcid"), c.get("email"), c.get("background"), method, conf, c.get("unit_id"), u))
                for kw in json.loads(c.get("keywords_json") or "[]"):
                    if kw:
                        upsert(con, "person_keyword", {"person_id": u, "keyword": kw, "source": "cristin"})
            else:
                how["unresolved"] += 1
                unresolved.append((u, p["name_full"], "no match"))

        # Cristin persons with LUI results but no listed profile -> unlisted person nodes
        n_unlisted = 0
        for c in cps:
            if c["cristin_person_id"] in used or not (c.get("n_results") or 0):
                continue
            pid = f"cristin:{c['cristin_person_id']}"
            upsert(con, "person", {
                "person_id": pid, "cristin_person_id": c["cristin_person_id"],
                "name_full": f"{c['first_name']} {c['surname']}".strip(), "name_first": c["first_name"], "name_last": c["surname"],
                "title_en": c.get("position"), "unit_id": c.get("unit_id"), "orcid": c.get("orcid"), "email": c.get("email"),
                "cristin_background": c.get("background"), "resolved_by": "cristin_only", "resolution_confidence": 1.0,
                "is_listed": 0, "staff_type": None,
            }, keys=["person_id"])
            for kw in json.loads(c.get("keywords_json") or "[]"):
                if kw:
                    upsert(con, "person_keyword", {"person_id": pid, "keyword": kw, "source": "cristin"})
            n_unlisted += 1

        # propagate person_id
        con.execute("""UPDATE publication_author SET person_id=(SELECT person_id FROM person WHERE person.cristin_person_id=publication_author.cristin_person_id)
                       WHERE cristin_person_id IS NOT NULL""")
        con.execute("""UPDATE project_participant SET person_id=(SELECT person_id FROM person WHERE person.cristin_person_id=project_participant.cristin_person_id)
                       WHERE cristin_person_id IS NOT NULL AND person_id IS NULL""")
        con.execute("UPDATE group_member SET person_id=username WHERE username IS NOT NULL AND person_id IS NULL")
        con.commit()

        DERIVED_DIR.mkdir(exist_ok=True)
        with (DERIVED_DIR / "identity_unresolved.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["username", "name_full", "reason"])
            w.writerows(unresolved)
        log["rows"] = len(persons)
        log["notes"] = f"{dict(how)}; unlisted cristin persons added: {n_unlisted}"
    print("identity:", log["notes"])
    print(f"unresolved list: {DERIVED_DIR / 'identity_unresolved.csv'}")
