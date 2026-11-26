# HEG Lab News Desk

An informal news desk for members of the Hydro- & Environmental Geophysics Lab (HEG-Lab),
Department of Environmental Sciences, University of Toledo. Not an official university page.

News, research papers and jobs across the lab's themes: soil moisture and salinity, coastal
interfaces and flooding, wetlands and biogeochemistry, plants and trees, groundwater, contamination,
archaeology and forensics, and geophysical methods (ERT, IP, SP, EM, GPR, seismic) with machine learning.

A GitHub Action runs `collector/news_collector.py` twice a day. It reads about 40 public news and
journal feeds and four open job boards (AGU Career Center, Science Careers, Chronicle Jobs,
Conservation Job Board), sorts each item under a heading, and publishes the site with GitHub Pages.
Summaries are the opening lines of each source's own article; every item links to the original.

LinkedIn, Indeed and Handshake do not allow other sites to collect their listings, so the Jobs page
links to the same search on those sites instead.

- Update now: Actions → "Update The Continuum" → Run workflow.
- Add a feed: append to `SOURCES` (news) or `JOB_BOARDS` / `JOB_QUERIES` (jobs) in the collector.
- Headings: keyword rules are in `RULES`. Lab themes: `THEMES` in `collector/heg_body.html`; rebuild the
  page with `python collector/build_template.py <path to the shared news_site.html>`.
- GitHub pauses scheduled workflows in a repository with no activity for 60 days; any commit (or
  re-enabling the workflow on the Actions tab) starts it again.
