"""Build collector/heg_site.html from heg_body.html plus the shared styles and field drawings.

The shared parts live in the PhD OS copy of the page (news_site.html). Run this after changing either
file:  python collector/build_template.py <path to news_site.html>
"""
import re
import sys
from pathlib import Path

here = Path(__file__).parent
shared = Path(sys.argv[1]).read_text(encoding="utf-8")
body = (here / "heg_body.html").read_text(encoding="utf-8")

css = re.search(r"<style>\n(.*?)</style>", shared, re.S).group(1)
css = re.sub(r"/\* ask \*/.*?(?=\nfooter \{)", "", css, flags=re.S)  # the personal page's chat styles
start = shared.index("function rng(")
end = shared.index("/* ---------- pieces ---------- */")
art = shared[start:end].replace("/* ---------- drawings for stories without a picture ---------- */", "").strip()

page = body.replace("/*__CSS__*/", css.strip()).replace("/*__ART__*/", "/* drawings for stories without a picture */\n" + art)
assert "claude" not in page.lower(), "the lab page must not mention Claude"
(here / "heg_site.html").write_text(page, encoding="utf-8")
print("heg_site.html", len(page), "bytes")
