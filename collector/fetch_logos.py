"""Download each meeting organiser's site icon once into collector/logos/<key>.png (96 x 96).

Run by hand when conferences.json gains a new organiser:  python collector/fetch_logos.py
Picks the largest apple-touch-icon / icon the organiser's home page declares, falling back to
Google's favicon service. The page shows initials if a logo is missing.
"""
import html
import io
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

UA = "Mozilla/5.0 (EPLAS logo fetch)"
OUT = Path(__file__).parent / "logos"
SITES = {  # key -> organiser home page
    "agu": "https://www.agu.org/", "ngwa": "https://www.ngwa.org/", "ams": "https://www.ametsoc.org/",
    "lpi": "https://www.lpi.usra.edu/", "egu": "https://www.egu.eu/", "ssa": "https://www.seismosoc.org/",
    "jpgu": "https://www.jpgu.org/en/", "eage": "https://eage.org/", "goldschmidt": "https://www.geochemsoc.org/",
    "iugg": "https://iugg.org/", "esa": "https://esa.org/", "seg": "https://seg.org/", "gsa": "https://www.geosociety.org/",
    "canvas": "https://www.sciencesocieties.org/", "iugs": "https://www.iugs.org/", "eegs": "https://www.eegs.org/",
    "dps": "https://dps.aas.org/", "aogs": "https://www.asiaoceania.org/", "aeg": "https://www.aegweb.org/",
    # funding agencies
    "nsf": "https://www.nsf.gov/", "nasa": "https://www.nasa.gov/", "noaa": "https://www.noaa.gov/", "usgs": "https://www.usgs.gov/",
    "doe": "https://www.energy.gov/", "epa": "https://www.epa.gov/", "usbr": "https://www.usbr.gov/", "nps": "https://www.nps.gov/",
    "fws": "https://www.fws.gov/",
}
LINK = re.compile(r"<link\b[^>]*>", re.I)


def get(url, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read(limit), response.geturl()


def candidates(home):
    page, final = get(home, 800_000)
    text = page.decode("utf-8", "replace")
    found = []
    for tag in LINK.findall(text):
        rel = re.search(r'rel=["\']([^"\']+)', tag, re.I)
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if not rel or not href or "icon" not in rel.group(1).lower() or "mask" in rel.group(1).lower():
            continue
        sizes = re.search(r'sizes=["\'](\d+)x\d+', tag, re.I)
        size = int(sizes.group(1)) if sizes else (180 if "apple" in rel.group(1).lower() else 32)
        found.append((size, urllib.parse.urljoin(final, html.unescape(href.group(1)))))
    found.sort(reverse=True)
    host = urllib.parse.urlparse(final).netloc
    return [u for _, u in found] + [urllib.parse.urljoin(final, "/apple-touch-icon.png"),
                                    f"https://www.google.com/s2/favicons?domain={host}&sz=128"]


def save(key, home):
    for url in candidates(home):
        try:
            data, _ = get(url)
            if url.lower().endswith(".svg") or data.lstrip()[:5] in (b"<?xml", b"<svg "):
                continue  # Pillow cannot draw SVG; try the next one
            img = Image.open(io.BytesIO(data))
            if hasattr(img, "n_frames") and img.format == "ICO":
                img = max((img.ico.getimage(s) for s in img.ico.sizes()), key=lambda i: i.width)
            img = img.convert("RGBA")
            if img.width < 40:
                continue
            img.thumbnail((96, 96), Image.LANCZOS)
            canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
            canvas.paste(img, ((96 - img.width) // 2, (96 - img.height) // 2), img)
            canvas.save(OUT / f"{key}.png", optimize=True)
            return f"{key}: {img.width}px from {url[:90]}"
        except Exception:
            continue
    return f"{key}: none found"


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    only = set(sys.argv[1:])  # optional: just these keys
    for key, home in SITES.items():
        if only and key not in only:
            continue
        try:
            print(save(key, home))
        except Exception as error:
            print(f"{key}: home page failed ({type(error).__name__})")
    sys.exit(0)
