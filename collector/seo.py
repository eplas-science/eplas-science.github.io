"""Make the published site easy for search engines to read (run after the collector).

- Writes the latest headlines into index.html as plain HTML, so crawlers that don't
  run JavaScript still see real content. The full app removes this list once it loads.
- Writes robots.txt and sitemap.xml.
- Copies the social preview image.

Usage: python collector/seo.py <site folder>
"""
import datetime as dt
import html
import json
import shutil
import sys
from pathlib import Path

BASE = "https://continuum-news.github.io/"
here = Path(__file__).parent
site = Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc)

news = json.loads((site / "news.json").read_text(encoding="utf-8"))
items = sorted(news.get("items", []), key=lambda item: item.get("date") or "", reverse=True)[:80]


def row(item):
    date = (item.get("date") or "")[:10]
    summary = html.escape((item.get("summary") or "").strip()[:280])
    return (
        f'<li><a href="{html.escape(item.get("link", ""), quote=True)}" rel="noopener">{html.escape(item.get("title", ""))}</a>'
        f' <small>{html.escape(item.get("source", ""))} · {html.escape(item.get("kind", ""))} · {date}</small>'
        + (f"<p>{summary}</p>" if summary else "")
        + "</li>"
    )


static = (
    '<section id="seo-headlines" aria-label="Latest headlines" style="max-width:860px;margin:24px auto;padding:0 16px;font-family:system-ui,sans-serif">'
    "<h2>Latest news and research papers</h2>"
    "<p>Earth and planetary science: geology, mineralogy, plate tectonics, volcanoes and earthquakes, geomorphology, hydrology "
    "and hydrogeology, engineering geology, paleontology and Earth history, ecology, geophysics and geochemistry, Mars and "
    "planetary geology, climate and environmental policy, plus research jobs. "
    f"Updated twice a day; last update {now:%d %B %Y}.</p>"
    f"<ul>{''.join(row(item) for item in items)}</ul></section>"
    "<script>window.addEventListener('load',()=>{const s=document.getElementById('seo-headlines');if(s&&document.querySelector('main')&&!document.querySelector('main > .empty'))s.remove();});</script>"
)

index = site / "index.html"
page = index.read_text(encoding="utf-8")
marker = "</body>"
page = page.replace(marker, static + marker, 1) if marker in page else page + static
index.write_text(page, encoding="utf-8")

(site / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n", encoding="utf-8")
(site / "sitemap.xml").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    f"  <url><loc>{BASE}</loc><lastmod>{now:%Y-%m-%d}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n"
    "</urlset>\n",
    encoding="utf-8",
)
for name in ("og-image.png",):
    if (here / name).exists():
        shutil.copy(here / name, site / name)
# Search-engine ownership files (e.g. googleXXXX.html, BingSiteAuth.xml) kept in collector/verify/.
for proof in (here / "verify").glob("*") if (here / "verify").exists() else []:
    shutil.copy(proof, site / proof.name)
print(f"seo: {len(items)} static headlines, robots.txt, sitemap.xml")
