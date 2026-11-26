"""Write <site>/funding.json: open and upcoming Earth and planetary science funding from Grants.gov.

Grants.gov lists every U.S. federal opportunity (NSF, NASA, NOAA, USGS, DOE, EPA, USDA and more). This
searches it for Earth and planetary science keywords, keeps what is posted or forecast and not yet
closed, reads each opportunity's details once (summary, award size, who may apply), and tags it by
type and career stage. Earlier results are kept in the existing funding.json so details are not
fetched again. Usage:  python collector/funding.py site
"""
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

API = "https://api.grants.gov/v1/api"
UA = "EPLAS funding reader (https://eplas-science.github.io)"
KEYWORDS = ["geology", "geoscience", "geophysics", "earth science", "hydrology", "groundwater", "water resources", "soil",
            "seismology", "earthquake", "volcano", "landslide", "mineral resources", "critical minerals", "geochemistry",
            "paleontology", "sedimentary", "tectonics", "glacier", "cryosphere", "climate", "ocean sciences", "coastal",
            "atmospheric", "remote sensing", "planetary science", "mars", "lunar", "critical zone", "watershed",
            "ecosystem", "geospatial", "graduate research fellowship", "postdoctoral fellowship", "research experiences for undergraduates"]
RX_EARTH = re.compile(r"\bgeo(?!int\b)\w*|earth|hydro\w*|ground ?water|soils?\b|seism\w*|earthquake|volcan\w*|landslide|mineral|paleo\w*|"
                      r"sediment\w*|tecton\w*|glaci\w*|cryospher\w*|climat\w*|ocean\w*|coast\w*|atmospher\w*|remote sensing|"
                      r"planetary|\bmars\b|lunar|critical zone|watershed|ecolog\w*|water resource|wetland|river|aquifer|"
                      r"polar|arctic|antarctic|weather|natural hazard", re.I)


def earthy(title, summary):
    """An Earth-science word in the title, or two different ones in the summary."""
    return bool(RX_EARTH.search(title)) or len({m.group(0).lower()[:6] for m in RX_EARTH.finditer(summary)}) >= 2
TYPES = [("Fellowship", r"fellow"), ("Scholarship", r"scholarship"), ("Prize & challenge", r"\bprize|challenge|competition"),
         ("Training & REU", r"research experiences? for undergraduates|\breu\b|internship|traineeship|training program"),
         ("Cooperative agreement", r"cooperative agreement|\bcesu\b")]
STAGES = [("Students", r"undergraduate|graduate (?:student|research)|doctoral|dissertation|\bstudents?\b|\breu\b|trainee"),
          ("Postdocs", r"post-?doc"), ("Early career", r"(?-i:\bCAREER\b)|early[- ]career|new investigator|young investigator|early-stage")]
ROLLING_AFTER_YEARS = 5  # Grants.gov uses far-future close dates for programs that accept proposals any time
# Left out: health agencies (they match words like "climate" or "hazard"), and USGS agreements that only the
# existing partners of a Cooperative Ecosystem Studies Unit may apply for.
SKIP_AGENCY = re.compile(r"^HHS", re.I)
SKIP_TITLE = re.compile(r"cooperative agreement for (?:an )?affiliated partner", re.I)


def post(path, body):
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as response:
        data = json.load(response)
    if data.get("errorcode") not in (0, "0", None):
        raise RuntimeError(data.get("msg", "Grants.gov error"))
    return data["data"]


def search(keyword):
    return post("search2", {"keyword": keyword, "oppStatuses": "forecasted|posted", "rows": 100}).get("oppHits", [])


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return " ".join(text.split())


def details(opp_id):
    d = post("fetchOpportunity", {"opportunityId": int(opp_id)})
    s = d.get("synopsis") or d.get("forecast") or {}
    types = s.get("applicantTypes") or []
    return {"summary": clean(s.get("synopsisDesc") or s.get("forecastDesc"))[:420],
            "ceiling": s.get("awardCeiling") or "", "floor": s.get("awardFloor") or "",
            "individuals": any(str(t.get("id")) == "21" for t in types if isinstance(t, dict)),
            "eligibility": clean(s.get("applicantEligibilityDesc"))[:240],
            "category": (d.get("opportunityCategory") or {}).get("description", "")}


def mdy(value):
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        return None


def tag(rx_list, text, default):
    return next((name for name, rx in rx_list if re.search(rx, text, re.I)), default)


def main(site):
    site = Path(site)
    today = dt.date.today()
    store = site / "funding.json"
    old = {}
    if store.exists():
        try:
            old = {o["id"]: o for o in json.loads(store.read_text(encoding="utf-8")).get("items", [])}
        except (ValueError, KeyError):
            old = {}
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "source": "Grants.gov", "ok": False, "items": []}
    try:
        hits = {}
        with cf.ThreadPoolExecutor(6) as ex:
            for found in ex.map(search, KEYWORDS):
                for h in found:
                    hits.setdefault(h["id"], h)
        keep = []
        for h in hits.values():
            close = mdy(h.get("closeDate"))
            if (close and close < today) or SKIP_AGENCY.search(h.get("agencyCode", "")) or SKIP_TITLE.search(h.get("title", "")):
                continue
            keep.append(h)
        need = [h["id"] for h in keep if h["id"] not in old]
        info = {}
        with cf.ThreadPoolExecutor(8) as ex:
            futures = {ex.submit(details, i): i for i in need}
            for f in cf.as_completed(futures):
                try:
                    info[futures[f]] = f.result()
                except Exception:
                    info[futures[f]] = {"summary": "", "ceiling": "", "floor": "", "individuals": False, "eligibility": "", "category": ""}
        items = []
        for h in keep:
            extra = info.get(h["id"]) or {k: old[h["id"]].get(k, "") for k in ("summary", "ceiling", "floor", "individuals", "eligibility", "category")}
            text = f"{h['title']} {extra['summary']}"
            if not earthy(h["title"], extra["summary"]):
                continue
            close = mdy(h.get("closeDate"))
            rolling = not close or close.year - today.year > ROLLING_AFTER_YEARS
            items.append({
                "id": h["id"], "number": h.get("number", ""), "title": clean(h["title"]), "agency": h.get("agency", ""),
                "agencyCode": h.get("agencyCode", ""), "status": h.get("oppStatus", ""), "opened": str(mdy(h.get("openDate")) or ""),
                "deadline": "" if rolling else close.isoformat(), "rolling": rolling,
                "type": tag(TYPES, h["title"], "Grant"), "stage": tag(STAGES, h["title"], "") or tag(STAGES, text, "Researchers & institutions"),  # the title decides first
                "link": f"https://www.grants.gov/search-results-detail/{h['id']}",
                "firstSeen": old.get(h["id"], {}).get("firstSeen") or out["updated"], **extra})
        items.sort(key=lambda i: (i["rolling"], i["deadline"] or "9999"))
        out.update(ok=True, items=items, searched=len(hits))
    except Exception as error:  # keep the last good list if Grants.gov is down
        out["error"] = f"{type(error).__name__}: {str(error)[:120]}"
        out["items"] = [o for o in old.values() if o.get("rolling") or (o.get("deadline") or "9999") >= today.isoformat()]
    store.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"funding: {len(out['items'])} opportunities" + (f" ({out['error']})" if "error" in out else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
