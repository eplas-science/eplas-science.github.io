"""PhD OS News Desk collector.

Reads public RSS/Atom feeds on geoscience, near-surface geophysics, hydrology, ecohydrology, ecology,
climate, water management, environmental policy, conferences and awards; sorts each item under a
heading; writes a short summary (the first sentences of the feed's own description) and the link to
the original article. Output, in the folder given as the first argument:

    news.json   - every story from the last 45 days (read by the PhD OS dashboard ticker)
    jobs.json   - job openings from open job boards (AGU, Science Careers, Chronicle, Conservation Job Board)
    index.html  - the website with the data inside it (open it in any browser)
    publish/    - the same page without data plus the two JSON files, for the shared online version

LinkedIn, Indeed and Handshake forbid automated collection (and Handshake needs a university
login), so the site links to saved searches there instead of scraping them.

Standard library only. Only feed URLs are requested; nothing about the user is sent.
"""
import concurrent.futures as cf
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

KEEP_DAYS = 45
PER_SOURCE = 25
UA = "Mozilla/5.0 (PhD-OS news reader)"

CATEGORIES = [  # id, heading, colour (priority order for the main heading: most specific first)
    ("nsg", "Near-Surface Geophysics", "#7c3aed"),
    ("ecohydrology", "Ecohydrology", "#059669"),
    ("awards", "Awards & Opportunities", "#d97706"),
    ("conferences", "Conferences & Events", "#db2777"),
    ("policy", "Environmental Policy", "#475569"),
    ("hydrology", "Hydrology & Hydrogeology", "#0284c7"),
    ("water", "Water Resources Management", "#0891b2"),
    ("climate", "Climate Change", "#dc2626"),
    ("ecology", "Ecology", "#16a34a"),
    ("planetary", "Planetary Science", "#4338ca"),
    ("geoscience", "Geoscience", "#a16207"),
]
ORDER = [c[0] for c in CATEGORIES]

# name, url, kind (News | Paper), default headings
SOURCES = [
    ("Eos (AGU)", "https://eos.org/feed", "News", ["geoscience"]),
    ("AGU Newsroom", "https://news.agu.org/feed/", "News", ["geoscience"]),
    ("ScienceDaily: Geology", "https://www.sciencedaily.com/rss/earth_climate/geology.xml", "News", ["geoscience"]),
    ("ScienceDaily: Water", "https://www.sciencedaily.com/rss/earth_climate/water.xml", "News", ["hydrology"]),
    ("ScienceDaily: Ecology", "https://www.sciencedaily.com/rss/earth_climate/ecology.xml", "News", ["ecology"]),
    ("ScienceDaily: Climate", "https://www.sciencedaily.com/rss/earth_climate/global_warming.xml", "News", ["climate"]),
    ("ScienceDaily: Environmental Science", "https://www.sciencedaily.com/rss/earth_climate/environmental_policy.xml", "News", []),
    ("Phys.org: Earth Sciences", "https://phys.org/rss-feed/earth-news/earth-sciences/", "News", ["geoscience"]),
    ("Phys.org: Environment", "https://phys.org/rss-feed/earth-news/environment/", "News", []),
    ("Phys.org: Ecology", "https://phys.org/rss-feed/biology-news/ecology/", "News", ["ecology"]),
    ("USGS News", "https://www.usgs.gov/news/all/feed", "News", ["geoscience"]),
    ("NOAA", "https://www.noaa.gov/rss.xml", "News", ["climate"]),
    ("NSF News", "https://www.nsf.gov/rss/rss_www_news.xml", "News", []),
    ("Carbon Brief", "https://www.carbonbrief.org/feed", "News", ["climate"]),
    ("Inside Climate News", "https://insideclimatenews.org/feed/", "News", ["climate"]),
    ("Climate Home News", "https://www.climatechangenews.com/feed/", "News", ["policy"]),
    ("UN News: Climate", "https://news.un.org/feed/subscribe/en/news/topic/climate-change/feed/rss.xml", "News", ["policy"]),
    ("IPCC", "https://www.ipcc.ch/feed/", "News", ["climate"]),
    ("The Guardian: Climate", "https://www.theguardian.com/environment/climate-crisis/rss", "News", ["climate"]),
    ("The Guardian: Water", "https://www.theguardian.com/environment/water/rss", "News", ["water"]),
    ("Grist", "https://grist.org/feed/", "News", ["climate"]),
    ("Mongabay", "https://news.mongabay.com/feed/", "News", ["ecology"]),
    ("Ecological Society of America", "https://www.esa.org/feed/", "News", ["ecology"]),
    ("Circle of Blue", "https://www.circleofblue.org/feed/", "News", ["water"]),
    ("Global Water Forum", "https://www.globalwaterforum.org/feed/", "News", ["water"]),
    ("Water Canada", "https://www.watercanada.net/feed/", "News", ["water"]),
    ("Nature Geoscience", "https://www.nature.com/ngeo.rss", "Paper", ["geoscience"]),
    ("Nature Climate Change", "https://www.nature.com/nclimate.rss", "Paper", ["climate"]),
    ("Nature Water", "https://www.nature.com/natwater.rss", "Paper", ["water"]),
    ("Nature Sustainability", "https://www.nature.com/natsustain.rss", "Paper", ["policy"]),
    ("Hydrology and Earth System Sciences", "https://hess.copernicus.org/xml/rss2_0.xml", "Paper", ["hydrology"]),
    ("Biogeosciences", "https://bg.copernicus.org/xml/rss2_0.xml", "Paper", ["ecology"]),
    ("SOIL", "https://soil.copernicus.org/xml/rss2_0.xml", "Paper", ["geoscience"]),
    ("Water Resources Research", "https://agupubs.onlinelibrary.wiley.com/feed/19447973/most-recent", "Paper", ["hydrology"]),
    ("Geophysical Research Letters", "https://agupubs.onlinelibrary.wiley.com/feed/19448007/most-recent", "Paper", ["geoscience"]),
    ("JGR Biogeosciences", "https://agupubs.onlinelibrary.wiley.com/feed/21698961/most-recent", "Paper", ["ecology"]),
    ("Ecohydrology", "https://onlinelibrary.wiley.com/feed/19360592/most-recent", "Paper", ["ecohydrology"]),
    ("Near Surface Geophysics", "https://onlinelibrary.wiley.com/feed/18730604/most-recent", "Paper", ["nsg"]),
    ("Groundwater", "https://ngwa.onlinelibrary.wiley.com/feed/17456584/most-recent", "Paper", ["hydrology"]),
    ("Vadose Zone Journal", "https://acsess.onlinelibrary.wiley.com/feed/15391663/most-recent", "Paper", ["hydrology"]),
    ("Journal of Applied Geophysics", "https://rss.sciencedirect.com/publication/science/09269851", "Paper", ["nsg"]),
    ("Journal of Hydrology", "https://rss.sciencedirect.com/publication/science/00221694", "Paper", ["hydrology"]),
    ("Science of the Total Environment", "https://rss.sciencedirect.com/publication/science/00489697", "Paper", ["ecology"]),
    # Earth and planetary science, added 2026-11-26 (each feed tested before adding)
    ("NASA News", "https://www.nasa.gov/news-release/feed/", "News", []),
    ("The Planetary Society", "https://www.planetary.org/rss/articles", "News", ["planetary"]),
    ("USGS Significant Earthquakes", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.atom", "News", ["geoscience"]),
    ("Smithsonian Weekly Volcanic Activity", "https://volcano.si.edu/news/WeeklyVolcanoRSS.xml", "News", ["geoscience"]),
    ("ScienceDaily: Earthquakes", "https://www.sciencedaily.com/rss/earth_climate/earthquakes.xml", "News", ["geoscience"]),
    ("ScienceDaily: Volcanoes", "https://www.sciencedaily.com/rss/earth_climate/volcanoes.xml", "News", ["geoscience"]),
    ("ScienceDaily: Fossils", "https://www.sciencedaily.com/rss/fossils_ruins/fossils.xml", "News", ["geoscience"]),
    ("ScienceDaily: Paleontology", "https://www.sciencedaily.com/rss/fossils_ruins/paleontology.xml", "News", ["geoscience"]),
    ("ScienceDaily: Geography", "https://www.sciencedaily.com/rss/earth_climate/geography.xml", "News", ["geoscience"]),
    ("ScienceDaily: Mars", "https://www.sciencedaily.com/rss/space_time/mars.xml", "News", ["planetary"]),
    ("ScienceDaily: Solar System", "https://www.sciencedaily.com/rss/space_time/solar_system.xml", "News", ["planetary"]),
    ("Phys.org: Planetary Sciences", "https://phys.org/rss-feed/space-news/planetary-sciences/", "News", ["planetary"]),
    ("Phys.org: Paleontology", "https://phys.org/rss-feed/biology-news/paleontology-fossils/", "News", ["geoscience"]),
    ("Earth and Planetary Science Letters", "https://rss.sciencedirect.com/publication/science/0012821X", "Paper", ["geoscience"]),
    ("Icarus", "https://rss.sciencedirect.com/publication/science/00191035", "Paper", ["planetary"]),
    ("JGR Planets", "https://agupubs.onlinelibrary.wiley.com/feed/21699100/most-recent", "Paper", ["planetary"]),
    ("JGR Solid Earth", "https://agupubs.onlinelibrary.wiley.com/feed/21699356/most-recent", "Paper", ["geoscience"]),
    ("JGR Earth Surface", "https://agupubs.onlinelibrary.wiley.com/feed/21699011/most-recent", "Paper", ["geoscience"]),
    ("Tectonics", "https://agupubs.onlinelibrary.wiley.com/feed/19449194/most-recent", "Paper", ["geoscience"]),
    ("Geochemistry, Geophysics, Geosystems", "https://agupubs.onlinelibrary.wiley.com/feed/15252027/most-recent", "Paper", ["geoscience"]),
    ("Tectonophysics", "https://rss.sciencedirect.com/publication/science/00401951", "Paper", ["geoscience"]),
    ("Chemical Geology", "https://rss.sciencedirect.com/publication/science/00092541", "Paper", ["geoscience"]),
    ("Sedimentary Geology", "https://rss.sciencedirect.com/publication/science/00370738", "Paper", ["geoscience"]),
    ("Geomorphology", "https://rss.sciencedirect.com/publication/science/0169555X", "Paper", ["geoscience"]),
    ("Engineering Geology", "https://rss.sciencedirect.com/publication/science/00137952", "Paper", ["geoscience"]),
    ("Ore Geology Reviews", "https://rss.sciencedirect.com/publication/science/01691368", "Paper", ["geoscience"]),
    ("J. Volcanology & Geothermal Research", "https://rss.sciencedirect.com/publication/science/03770273", "Paper", ["geoscience"]),
    ("Palaeogeography, Palaeoclimatology, Palaeoecology", "https://rss.sciencedirect.com/publication/science/00310182", "Paper", ["geoscience"]),
    ("Solid Earth (EGU)", "https://se.copernicus.org/xml/rss2_0.xml", "Paper", ["geoscience"]),
    ("Earth Surface Dynamics (EGU)", "https://esurf.copernicus.org/xml/rss2_0.xml", "Paper", ["geoscience"]),
    ("Natural Hazards and Earth System Sciences", "https://nhess.copernicus.org/xml/rss2_0.xml", "Paper", ["geoscience"]),
    ("Climate of the Past", "https://cp.copernicus.org/xml/rss2_0.xml", "Paper", ["climate"]),
]

NO_DESC = {"AGU Newsroom"}  # its feed description is a site-wide banner, not the story

RULES = {
    "nsg": r"resistivity|\bERT\b|induced polari[sz]ation|self[- ]potential|ground[- ]penetrating radar|\bGPR\b|electromagnetic induction|seismic refraction|near[- ]surface|geophysic|geoelectric|magnetotelluric|electrical imaging|tomograph",
    "ecohydrology": r"ecohydrolog|sap ?flow|transpiration|root water uptake|plant water|xylem|tree water|stomata|soil[- ]plant|vegetation water|canopy water",
    "awards": r"\baward|medal|\bprize|fellowship|\bhonou?red\b|named (?:a )?fellow|recipients?\b|scholarship|call for nominations|nominations? (?:open|are open)|early[- ]career grant",
    "conferences": r"conference|annual meeting|fall meeting|general assembly|call for (?:abstracts|papers|sessions)|abstract deadline|symposium|workshop|webinar|summer school",
    "policy": r"\bpolic(?:y|ies)\b|regulat|legislat|\blaw\b|\bEPA\b|agreement|government|ministr|congress|senate|treaty|\bCOP\d*\b|lawsuit|court|executive order|funding cut",
    "hydrology": r"groundwater|aquifer|hydrolog|streamflow|discharge|runoff|flood|drought|soil moisture|infiltration|recharge|watershed|catchment|vadose|snowpack|river",
    "water": r"water (?:management|resources?|supply|security|quality|use|rights|utilit)|irrigation|reservoir|drinking water|wastewater|desalination|nutrient load|algal bloom|\bdam\b|lake erie",
    "climate": r"climate|global warming|greenhouse|carbon dioxide|\bCO2\b|emission|warming|\bIPCC\b|heat ?wave|sea[- ]level|net[- ]zero|decarboni",
    "ecology": r"ecolog|biodiversity|species|ecosystem|forest|wildlife|habitat|\bplants?\b|microb|wetland|pollinat|coral",
    "planetary": r"\bmars\b|martian|lunar|\bthe moon\b|moon's|asteroid|comet|meteorit|planetary|solar system|exoplanet|\bvenus\b|jupiter|saturn|europa|enceladus|\btitan\b|rover|impact crater",
    "geoscience": r"geolog|earthquake|volcan|tectonic|sediment|mineral|\brocks?\b|mantle|\bfaults?\b|erosion|glacier|permafrost|\bsoils?\b|landslide|geochem",
}
PHD = r"\btrees?\b|\bstems?\b|trunk|\broots?\b|soil[- ]plant|soil moisture|sap ?flow|transpiration|resistivity|induced polari|self[- ]potential|critical zone|machine learning|deep learning|neural network|biogeochem|ecohydrolog|vadose|lake erie|maumee|great lakes|electrical"
RX = {k: re.compile(v, re.I) for k, v in RULES.items()}
RX_PHD = re.compile(PHD, re.I)
ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def summarize(text, title):
    """First one or two sentences of the feed description, without journal boilerplate."""
    t = clean(text)
    if title and t.lower().startswith(title.lower()):  # Copernicus and NOAA repeat the title first
        t = t[len(title):].strip()
    m = re.search(r"https://doi\.org/\S+, \d{4}\s+", t[:700])  # Copernicus: authors + citation line
    if m:
        t = t[m.end():]
    t = re.sub(r"^[\w &:-]+, EarlyView\.?\s*", "", t)  # Wiley early-view stub
    m = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}\s+", t[:400])
    if m and "Image credit" in t[:m.start()]:  # NOAA: image caption + dateline before the story
        t = t[m.end():]
    t = re.sub(r"^(?:ABSTRACT|Abstract|Summary)\s*", "", t)
    t = re.sub(r"Publication date:.*?(?:Author\(s\):[^.]*\.?|$)", "", t)  # ScienceDirect header
    t = re.sub(r"^[A-Z][\w &:,-]+, Volume \d+, Issue \d+,[^.]*\.\s*", "", t)  # Wiley header
    t = re.sub(r"^(?:Nature [\w ]+|Hydrology and Earth System Sciences|Biogeosciences|SOIL), Published online:[^.]*\.?\s*", "", t)
    t = re.sub(r"(?:The post .* appeared first on .*|Continue reading\.*|Read more\.*)$", "", t).strip()
    if not t or t.lower().startswith(title.lower()[:40]) and len(t) < len(title) + 20:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"])", t)
    out = ""
    for s in sentences:
        if len(out) + len(s) > 330 and out:
            break
        out = f"{out} {s}".strip()
        if len(out) > 160:
            break
    return out if len(out) <= 360 else out[:350].rsplit(" ", 1)[0] + "…"


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
            d = dt.datetime.fromisoformat(m.group(1)) if m else None
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def text_of(el, *names):
    for n in names:
        v = el.find(n)
        if v is not None:
            if n.startswith(ATOM) and v.get("href"):
                return v.get("href")
            if (v.text or "").strip():
                return v.text
    return ""


def fetch(source):
    name, url, kind, defaults = source
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=25).read()
    if raw.lstrip()[:15].lower().startswith(b"<!doctype html"):
        raise RuntimeError("the site answered with a web page (bot check) instead of its feed")
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(f".//{RSS1}item") or root.findall(f".//{ATOM}entry")
    out = []
    for it in items[:PER_SOURCE]:
        title = clean(text_of(it, "title", f"{RSS1}title", f"{ATOM}title"))
        link = ""
        for l in it.findall(f"{ATOM}link"):
            if l.get("rel", "alternate") == "alternate":
                link = l.get("href", "")
                break
        link = (link or text_of(it, "link", f"{RSS1}link", "guid")).strip()
        title = re.sub(r"^\d{1,2}/\d{1,2}/\d{4}:\s*", "", title)  # "11/25/2026: " (AGU Newsroom)
        fields = ("description", f"{DC}description", f"{RSS1}description", f"{ATOM}summary", f"{ATOM}content", f"{CONTENT}encoded")
        descs = [text_of(it, n) for n in fields]
        if name in NO_DESC:
            descs = []
        desc = next((d for d in descs if len(summarize(d, title)) > 60), next((d for d in descs if d), ""))
        date = parse_date(text_of(it, "pubDate", f"{DC}date", f"{ATOM}updated", f"{ATOM}published", "date"))
        if date is None:  # ScienceDirect: "Publication date: Available online 24 November 2026"
            m = re.search(r"Publication date:\D*?(\d{1,2} [A-Z][a-z]+ \d{4})", clean(desc))
            date = dt.datetime.strptime(m.group(1), "%d %B %Y").replace(tzinfo=dt.timezone.utc) if m else None
        if title and link.startswith("http"):
            labels = " ".join(clean(c.text) for c in it.findall("category") if c.text)  # the site's own topic labels
            out.append({"title": title, "link": link, "description": desc, "labels": labels, "date": date, "source": name,
                        "kind": kind, "defaults": defaults, "image": image_of(it, descs if name not in NO_DESC else [desc])})
    return out


def image_of(it, descs):
    """The story's picture: media:content / media:thumbnail / enclosure, else the first <img> in its text."""
    best, width = "", -1
    for tag in (f"{MEDIA}content", f"{MEDIA}thumbnail", f"{MEDIA}group/{MEDIA}content", "enclosure"):
        for m in it.findall(tag):
            url, kind = m.get("url", ""), m.get("type", "") or m.get("medium", "")
            if url.startswith("http") and ("image" in kind or not kind or re.search(r"\.(jpe?g|png|webp)", url, re.I)):
                w = int(m.get("width", "0") or 0)
                if w > width:
                    best, width = url, w
    if best:
        return best
    for d in descs:
        m = re.search(r"<img[^>]+src=[\"']([^\"']+)", d or "")
        if m and m.group(1).startswith("http"):
            return html.unescape(m.group(1))
    return ""


# ------------------------------------------------------------------------------------------------
# Jobs: open job boards that publish RSS. Searches cover every branch of Earth and planetary
# science; results are de-duplicated.
JOB_BOARDS = [
    ("AGU Career Center", "https://findajob.agu.org/jobsrss/?keywords={q}"),
    ("Science Careers", "https://jobs.sciencecareers.org/jobsrss/?keywords={q}"),
    ("Chronicle Jobs", "https://jobs.chronicle.com/jobsrss/?keywords={q}"),
]
JOB_QUERIES = ["geology", "geologist", "geoscience", "earth+science", "geophysics", "hydrology", "hydrogeology",
               "groundwater", "soil+science", "geochemistry", "seismology", "volcanology", "sedimentology",
               "paleontology", "geomorphology", "structural+geology", "petrology", "mineralogy", "planetary+science",
               "engineering+geology", "mining+geology", "petroleum+geology", "remote+sensing", "GIS", "oceanography",
               "glaciology", "atmospheric+science", "climate", "ecology", "biogeochemistry", "ecohydrology",
               "environmental+science", "water+resources", "geoscience+internship", "postdoctoral+geoscience"]
OPEN_BOARDS = [("Conservation Job Board", "https://www.conservationjobboard.com/rss")] + [
    ("ASCE Civil Engineering Jobs", f"https://careers.asce.org/jobsrss/?keywords={q}")
    for q in ("geotechnical", "engineering+geologist", "hydrogeologist", "geologist")]
# These boards publish the full posting as structured data (JSON-LD); the others refuse page reads.
DESC_BOARDS = {"Science Careers", "Chronicle Jobs", "Conservation Job Board"}
DESC_PER_RUN = 500
RX_EARTH = re.compile(r"geo|earth|hydro|soil|climat|ecolog|environment|ocean|atmospher|planet|mars\b|lunar|mineral|"
                      r"petrol|seism|volcan|sediment|paleo|glaci|water|\bgis\b|remote sensing|mining|tecton|"
                      r"coast|wetland|watershed|forest|conservation|natural resource", re.I)

# Career level: read from the title first, then from the years of experience the posting asks for.
JOB_LEVELS = [  # first match on the title wins
    ("Internship & student", r"\bintern(?:ship)?s?\b|co-?op\b|summer (?:student|position|research)|undergraduate|\bREU\b"),
    ("Graduate (MS/PhD)", r"\bph\.?d\b.*(?:opportunit|position|student|assistantship|fellowship)|graduate (?:research |teaching )?assistant|graduate student|m\.?s\.? (?:student|position)|studentship|assistantship|doctoral (?:student|position|candidate)"),
    ("Postdoc", r"post-?doc|postdoctoral"),
    ("Faculty", r"professor|faculty|lecturer|tenure|instructor|\bchair\b"),
    ("Senior & lead", r"\bsenior\b|\bsr\.?\b|principal|\blead\b|director|\bhead\b|chief|manager|supervis|\b(?:III|IV|V)\b"),
    ("Entry level", r"entry[- ]level|junior|\bjr\.?\b|trainee|technician|\btech\b|early[- ]career|recent graduate|"
                    r"\b(?:I|1)\b|assistant (?!professor)|staff (?:geolog|engineer|scientist|hydro)|field (?:geolog|scientist|crew)|seasonal"),
]
LEVEL_ORDER = ["Internship & student", "Entry level", "Mid-career", "Senior & lead", "Graduate (MS/PhD)", "Postdoc", "Faculty"]
RX_YEARS = re.compile(r"(\d{1,2})\s*(?:\+|or more|to \d+|-\s*\d+)?\s*years?(?: of)?(?: \w+){0,4}? (?:experience|work)", re.I)

# Sector: read from the employer first, then from the posting.
JOB_SECTORS = [
    ("Government", r"\busgs\b|\bnoaa\b|\bepa\b|\bnasa\b|\bblm\b|\busda\b|geological survey|department of|dept\.? of|"
                   r"state of|county|city of|federal|agency|national park|forest service|bureau|ministry|commonwealth|army corps|"
                   r"water (?:district|authority)|public (?:works|utilit)|government|\bstate\b.*(?:division|office)"),
    ("Academia", r"universit|college|school of|polytechnic|institute of technology|\bmit\b|caltech|academ"),
    ("Research institute", r"national laborator|\blab(?:oratory)?\b|institut|observatory|museum|smithsonian|research (?:center|centre|foundation)|"
                           r"\bjpl\b|\bncar\b|\bwhoi\b|\bmbari\b|consortium|\bunavco\b|earthscope|\biris\b"),
    ("Non-profit", r"conservancy|unlimited|foundation|\btrust\b|society|non-?profit|alliance|council|association|audubon|land trust|"
                   r"wildlife federation|\bwwf\b|watershed (?:council|association)|\bfriends of\b|coalition"),
]

# Skills the posting asks for, read from the whole posting where the board publishes it.
JOB_SKILLS = [
    ("GIS", r"\bgis\b|arcgis|arcmap|qgis|geospatial|spatial analys"),
    ("Python", r"\bpython\b"),
    ("R", r"\bR\b(?: ?(?i:programming|statistical|language|studio|packages?)|,| or| and)|(?i:\brstudio\b)"),
    ("MATLAB", r"matlab"),
    ("Programming", r"\bc\+\+|fortran|\bjulia\b|\bjava\b|\bsql\b|programming|scripting|software develop"),
    ("Data science & ML", r"machine learning|deep learning|data scien|artificial intelligence|\bAI\b|statistic|big data|neural net"),
    ("Numerical modelling", r"model(?:l)?ing|simulation|numerical|modflow|finite element|hec-ras|swat\b|parflow|\bcfd\b"),
    ("Remote sensing", r"remote sensing|satellite|lidar|\binsar\b|imagery|hyperspectral|\buav\b|drone"),
    ("Field work & mapping", r"field ?work|field (?:work|mapping|campaign|investigation|program|sampling|data collection)|geologic(?:al)? mapping|"
                             r"site characteri|core logging|sample collection"),
    ("Geophysics", r"geophysic|seismic|\bgpr\b|ground[- ]penetrating|resistivity|electromagnetic|magnetotelluric|gravity|\bert\b"),
    ("Lab & geochemistry", r"geochemi|laboratory|\blab\b|mass spectrom|icp-?ms|\bxrd\b|\bsem\b|isotop|microscop|analytical chemistry"),
    ("Drilling & logging", r"drilling|borehole|well logg|core (?:logging|description)|\bwell installation|mud logg|subsurface investigation"),
    ("Hydrology & water", r"hydrolog|hydrogeolog|groundwater|aquifer|water quality|watershed|stormwater|surface water"),
    ("Geotechnical", r"geotechnic|slope stability|foundation (?:design|engineering)|soil mechanic|rock mechanic|landslide"),
    ("CAD & surveying", r"autocad|\bcad\b|civil 3d|surveying|\bgnss\b|\bgps\b|total station"),
    ("Regulatory & permitting", r"regulat|permit|compliance|\bnepa\b|\bcercla\b|\brcra\b|environmental assessment|remediation"),
    ("Teaching", r"teach|instruct(?:ion|or)|curriculum|course(?:s|work)? (?:in|on)|mentor students|pedagog"),
    ("Project management", r"project management|manage projects|budget|proposal writing|client|supervis"),
    ("Grant & scientific writing", r"grant|publication|peer-reviewed|manuscript|scientific writing|publish"),
    ("Licensure (PG/PE)", r"(?i:professional geologist|licens|registered geologist)|\bP\.G\.|\bPG\b|\bP\.E\.|\bPE\b|\bEIT\b|\bGIT\b"),
]
JOB_SKILLS = [(name, re.compile(rx, re.I if name not in ("R", "Licensure (PG/PE)") else 0)) for name, rx in JOB_SKILLS]
JOB_KEEP_DAYS = 75
JOB_TYPES = [  # first match wins
    ("PhD & MS", r"\bph\.?d\b.*(?:opportunit|position|student|assistantship|fellowship)|graduate (?:research )?assistant|graduate student|m\.?s\.? (?:student|position)|studentship|assistantship"),
    ("Postdoc", r"post-?doc|postdoctoral"),
    ("Faculty", r"professor|faculty|lecturer|tenure|instructor"),
    ("Government", r"\busgs\b|\bnoaa\b|\bepa\b|department of|state of|county|city of|federal|national laborator|\bnasa\b|agency"),
    ("Research staff", r"scientist|researcher|research associate|technician|specialist|analyst|engineer|manager|coordinator|director"),
]
JOB_MATCH = r"hydro|groundwater|aquifer|geophys|resistiv|electrical|soil|ecohydro|vadose|critical zone|water|tree|forest|plant|biogeochem|machine learning|data scien|remote sensing|wetland|watershed|climate"
RX_JOB_MATCH = re.compile(JOB_MATCH, re.I)
RX_RELEVANT = re.compile(r"hydro|water|soil|geolog|geophys|ecolog|climate|wetland|watershed|scientist|research|data|gis|model|biogeochem|lab(?:oratory)? tech", re.I)
STATES = "alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi missouri montana nebraska nevada new-hampshire new-jersey new-mexico new-york north-carolina north-dakota ohio oklahoma oregon pennsylvania rhode-island south-carolina south-dakota tennessee texas utah vermont virginia washington west-virginia wisconsin wyoming remote".split()


def fetch_jobs(board, url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=25).read()
    if raw.lstrip()[:15].lower().startswith(b"<!doctype html"):
        raise RuntimeError("the site answered with a web page instead of its feed")
    out = []
    for it in ET.fromstring(raw).findall(".//item"):
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        raw_desc = it.findtext("description") or ""
        lines = [clean(l) for l in re.split(r"<br\s*/?>|\n", raw_desc) if clean(l)]
        employer, role = "", title
        if ": " in title and board != "Conservation Job Board":
            employer, role = title.split(": ", 1)
        location, salary = "", ""
        if board == "Conservation Job Board":  # "<title><br>$pay -- Employer"
            for l in lines:
                if " -- " in l:
                    salary, employer = [s.strip() for s in l.split(" -- ", 1)]
            slug = re.sub(r"/\d+$", "", link).rsplit("/", 1)[-1]
            state = next((s for s in sorted(STATES, key=len, reverse=True) if slug.endswith("-" + s)), "")
            location = state.replace("-", " ").title()
        else:
            lines = [l for l in lines if l.rstrip(":") != employer and not l.endswith(":")]
            if len(lines) >= 2:
                location = lines[-1] if len(lines[-1]) < 70 else ""
                lines = lines[:-1] if location else lines
            if lines and re.match(r"^(?:\$|USD|Commensurate|Salary|Competitive|Negotiable|\d)", lines[0]):
                salary = lines[0].rstrip(":")
                lines = lines[1:]
        summary = " ".join(lines)[:260]
        if board == "Conservation Job Board":
            summary = ""
        out.append({"title": role.strip(), "employer": employer.strip(), "location": location, "salary": salary,
                    "summary": summary, "link": link, "date": parse_date(it.findtext("pubDate")), "board": board})
    return out


def posting_text(url):
    """The full description a board publishes as JSON-LD JobPosting, as plain text ('' if none)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as response:
        page = response.read(600_000).decode("utf-8", "replace")
    for block in re.findall(r"(?s)<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return clean(html.unescape(d.get("description", "")))
    return ""


def job_level(j):
    title = j["title"]
    for name, rx in JOB_LEVELS:
        if re.search(rx, title, re.I):
            return name
    years = j.get("years")
    if years is not None:
        return "Entry level" if years <= 2 else "Senior & lead" if years >= 8 else "Mid-career"
    hay = f"{j['summary']} {j.get('desc', '')[:1500]}"
    for name, rx in JOB_LEVELS[:4]:  # student, graduate, postdoc and faculty jobs often say so only in the text
        if re.search(rx, hay, re.I):
            return name
    return "Mid-career"


def job_sector(j):
    for text in (j["employer"], f"{j['title']} {j['summary']} {j.get('desc', '')[:800]}"):
        for name, rx in JOB_SECTORS:
            if re.search(rx, text, re.I):
                return name
    return "Industry" if j["employer"] else "Other"


def job_skills(j):
    hay = f"{j['title']} {j['summary']} {j.get('desc', '')}"
    return [name for name, rx in JOB_SKILLS if rx.search(hay)]


def job_years(desc):
    found = [int(m.group(1)) for m in RX_YEARS.finditer(desc) if 0 < int(m.group(1)) < 30]
    return min(found) if found else None


def describe_jobs(jobs):
    """Read the full posting once per job (where the board allows) and keep only the tags."""
    todo = [j for j in jobs if "skills" not in j or (not j.get("described") and j["board"] in DESC_BOARDS)]
    fetch = [j for j in todo if not j.get("described") and j["board"] in DESC_BOARDS][:DESC_PER_RUN]
    texts = {}
    with cf.ThreadPoolExecutor(12) as ex:
        futures = {ex.submit(posting_text, j["link"]): j for j in fetch}
        for f in cf.as_completed(futures):
            j = futures[f]
            j["described"] = True
            try:
                texts[j["id"]] = f.result()
            except Exception:  # page refused: tags come from the title and summary
                pass
    for j in todo:
        desc = texts.get(j["id"], "")
        work = dict(j, desc=desc)
        if desc:
            j["years"] = job_years(desc)
        work["years"] = j.get("years")
        j["skills"] = sorted(set(j.get("skills", [])) | set(job_skills(work)), key=[n for n, _ in JOB_SKILLS].index)
        j["level"] = job_level(work)
        j["sector"] = job_sector(work)
    return len(texts)


def job_type(j):
    hay = f"{j['title']} {j['summary']}"
    for name, rx in JOB_TYPES:
        if re.search(rx, hay if name != "Government" else f"{j['employer']} {hay}", re.I):
            return name
    return "Other"


def collect_jobs(out, now):
    store = out / "jobs.json"
    old = {}
    if store.exists():
        try:
            old = {j["id"]: j for j in json.loads(store.read_text(encoding="utf-8")).get("items", [])}
        except (ValueError, KeyError):
            old = {}
    tasks = [(b, u.format(q=q)) for b, u in JOB_BOARDS for q in JOB_QUERIES] + OPEN_BOARDS
    status, fresh = {}, []
    with cf.ThreadPoolExecutor(10) as ex:
        futures = {ex.submit(fetch_jobs, b, u): b for b, u in tasks}
        for f in cf.as_completed(futures):
            b = futures[f]
            s = status.setdefault(b, {"source": b, "ok": False, "count": 0})
            try:
                got = f.result()
                fresh += got
                s["ok"] = True
                s["count"] += len(got)
            except Exception as e:
                s.setdefault("error", f"{type(e).__name__}: {str(e)[:100]}")
    jobs, added = dict(old), 0
    seen = {norm(f"{j['title']} {j['employer']}") for j in old.values()}  # the same job on two boards
    cutoff = now - dt.timedelta(days=JOB_KEEP_DAYS)
    for j in fresh:
        d = j["date"] or now
        if d < cutoff:
            continue
        clean_link = re.sub(r"\?.*$", "", j["link"])
        key = hashlib.sha1(clean_link.encode()).hexdigest()[:16]
        same = norm(f"{j['title']} {j['employer']}")
        if key in jobs or same in seen:
            continue
        hay = f"{j['title']} {j['employer']} {j['summary']}"
        if j["board"] == "Conservation Job Board" and not RX_RELEVANT.search(j["title"]):
            continue
        if not RX_EARTH.search(hay):  # broad searches also return unrelated jobs
            continue
        topics = [k for k in ORDER if k not in ("awards", "conferences", "policy") and RX[k].search(hay)]
        jobs[key] = {"id": key, "title": j["title"], "employer": j["employer"], "location": j["location"],
                     "salary": j["salary"], "summary": j["summary"], "link": j["link"], "board": j["board"],
                     "date": d.astimezone(dt.timezone.utc).isoformat(timespec="minutes"), "type": job_type(j),
                     "topics": topics, "match": len(set(m.group(0).lower() for m in RX_JOB_MATCH.finditer(hay))),
                     "firstSeen": now.isoformat(timespec="minutes")}
        seen.add(same)
        added += 1
    keep = sorted((j for j in jobs.values() if parse_date(j["date"]) >= cutoff), key=lambda j: j["date"], reverse=True)
    described = describe_jobs(keep)
    data = {"updated": now.isoformat(timespec="minutes"), "added": added, "described": described, "sources": sorted(status.values(), key=lambda s: s["source"]), "items": keep}
    store.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def classify(item):
    hay = f"{item['title']} {clean(item['description'])[:600]} {item.get('labels', '')}"
    found = [k for k in ORDER if RX[k].search(hay)]
    if item["kind"] == "Paper":  # papers are research, not events or prizes; "agreement" etc. is not policy there
        found = [k for k in found if k not in ("awards", "conferences") and (k != "policy" or re.search(r"\bpolic", hay, re.I))]
    cats = [k for k in ORDER if k in found or k in item["defaults"]]
    if not cats:
        cats = ["geoscience"]
    main = next((k for k in ORDER if k in item["defaults"] and k in ("nsg", "ecohydrology")), None) or cats[0]
    phd = len(set(m.group(0).lower() for m in RX_PHD.finditer(hay)))
    return main, cats, phd


# Stories whose feed has no picture: use the picture the publisher sets for sharing (og:image),
# read once per story. These publishers refuse automated page reads, so they are skipped.
OG_SKIP = re.compile(r"sciencedirect\.com|onlinelibrary\.wiley\.com|agupubs\.|nature\.com|ipcc\.ch|noaa\.gov|volcano\.si\.edu|usgs\.gov|esa\.org", re.I)
OG_RX = re.compile(r"""<meta[^>]+(?:property|name)=["'](?:og:image(?::secure_url)?|twitter:image(?::src)?)["'][^>]*content=["']([^"']+)|<meta[^>]+content=["']([^"']+)["'][^>]*(?:property|name)=["'](?:og:image|twitter:image)["']""", re.I)
OG_PER_RUN = 300


def og_image(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=10) as response:
        page = response.read(300_000).decode("utf-8", "replace")
    m = OG_RX.search(page)
    found = html.unescape(m.group(1) or m.group(2)) if m else ""
    return found if found.startswith("https://") else ""


def add_share_images(items):
    todo = [i for i in items if not i.get("image") and not i.get("imageTried") and not OG_SKIP.search(i["link"])][:OG_PER_RUN]
    found = 0
    with cf.ThreadPoolExecutor(16) as ex:
        futures = {ex.submit(og_image, i["link"]): i for i in todo}
        for f in cf.as_completed(futures):
            item = futures[f]
            item["imageTried"] = True
            try:
                url = f.result()
            except Exception:  # unreachable page: keep the stand-in card
                continue
            if url:
                item["image"] = url
                found += 1
    return found


def norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def main(out_dir, template=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store = out / "news.json"
    old = {}
    if store.exists():
        try:
            old = {i["id"]: i for i in json.loads(store.read_text(encoding="utf-8")).get("items", [])}
        except (ValueError, KeyError):
            old = {}
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    status, fresh = [], []
    with cf.ThreadPoolExecutor(12) as ex:
        futures = {ex.submit(fetch, s): s for s in SOURCES}
        for f in cf.as_completed(futures):
            s = futures[f]
            try:
                got = f.result()
                fresh += got
                status.append({"source": s[0], "ok": True, "count": len(got)})
            except Exception as e:  # one broken feed never stops the others
                status.append({"source": s[0], "ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"})
    items, seen_titles = dict(old), {norm(i["title"]) for i in old.values()}
    added = 0
    for it in fresh:
        d = it["date"] or now
        if d < cutoff or d > now + dt.timedelta(days=2):
            continue
        key = hashlib.sha1(it["link"].encode()).hexdigest()[:16]
        nt = norm(it["title"])
        if key in items or nt in seen_titles:
            continue
        main_cat, cats, phd = classify(it)
        items[key] = {"id": key, "title": it["title"], "link": it["link"], "source": it["source"], "kind": it["kind"],
                      "date": d.astimezone(dt.timezone.utc).isoformat(timespec="minutes"),
                      "summary": summarize(it["description"], it["title"]), "category": main_cat, "tags": cats,
                      "phd": phd, "image": it.get("image", ""), "firstSeen": now.isoformat(timespec="minutes")}
        seen_titles.add(nt)
        added += 1
    keep = [i for i in items.values() if parse_date(i["date"]) >= cutoff]
    keep.sort(key=lambda i: i["date"], reverse=True)
    images_added = add_share_images(keep)
    data = {"updated": now.isoformat(timespec="minutes"), "added": added,
            "categories": [{"id": c, "label": l, "color": col} for c, l, col in CATEGORIES],
            "sources": sorted(status, key=lambda s: s["source"]), "items": keep}
    store.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    jobs = collect_jobs(out, now)
    page = Path(template or Path(__file__).with_name("news_site.html")).read_text(encoding="utf-8")
    embed = lambda d: json.dumps(d, ensure_ascii=False).replace("<", "\\u003c")
    (out / "index.html").write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n' + page.replace("/*__NEWS_DATA__*/null", embed(data)).replace("/*__JOBS_DATA__*/null", embed(jobs)), encoding="utf-8")
    pub = out / "publish"  # the shared online page reads its data from these files
    pub.mkdir(exist_ok=True)
    (pub / "index.html").write_text(page, encoding="utf-8")
    (pub / "news.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (pub / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for s in status if s["ok"])
    print(json.dumps({"ok": True, "added": added, "total": len(keep), "sources_ok": ok, "sources": len(status), "jobs": len(jobs["items"]), "jobs_added": jobs["added"], "images_added": images_added, "updated": data["updated"]}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".", sys.argv[2] if len(sys.argv) > 2 else None)
