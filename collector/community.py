"""Write <site>/community.json: the newest threads from the site's GitHub Discussions forum.

Run in the update workflow with GITHUB_TOKEN set (the workflow's own token, discussions: read).
Without a token, or if GitHub cannot be reached, it writes an empty list and the page simply
shows the ways to start a discussion.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

OWNER, NAME = "continuum-news", "continuum-news.github.io"
QUERY = """query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussionCategories(first: 25) { nodes { name slug emoji description isAnswerable } }
    discussions(first: 60, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        number title url createdAt updatedAt upvoteCount isAnswered
        bodyText
        author { login avatarUrl(size: 64) }
        category { name slug emoji }
        labels(first: 6) { nodes { name color } }
        comments { totalCount }
      }
    }
  }
}"""
EMOJI = {":mega:": "📣", ":speech_balloon:": "💬", ":bulb:": "💡", ":ballot_box:": "🗳️", ":pray:": "🙏", ":raised_hands:": "🙌"}


def fetch(token):
    body = json.dumps({"query": QUERY, "variables": {"owner": OWNER, "name": NAME}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "eplas-community"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", "GraphQL error"))
    return data["data"]["repository"]


def main(site):
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "forum": f"https://github.com/{OWNER}/{NAME}/discussions", "ok": False, "total": 0, "categories": [], "items": []}
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        if not token:
            raise RuntimeError("no GITHUB_TOKEN")
        repo = fetch(token)
        out["ok"] = True
        out["categories"] = [{"name": c["name"], "slug": c["slug"], "emoji": EMOJI.get(c["emoji"], ""), "about": c["description"] or "",
                              "answerable": c["isAnswerable"]} for c in repo["discussionCategories"]["nodes"]]
        d = repo["discussions"]
        out["total"] = d["totalCount"]
        out["items"] = [{
            "number": n["number"], "title": n["title"], "url": n["url"], "created": n["createdAt"], "updated": n["updatedAt"],
            "excerpt": " ".join((n["bodyText"] or "").split())[:220], "votes": n["upvoteCount"], "answered": n["isAnswered"],
            "replies": n["comments"]["totalCount"], "author": (n["author"] or {}).get("login", "ghost"),
            "avatar": (n["author"] or {}).get("avatarUrl", ""), "category": n["category"]["name"], "categorySlug": n["category"]["slug"],
            "emoji": EMOJI.get(n["category"]["emoji"], ""), "labels": [l["name"] for l in n["labels"]["nodes"]],
        } for n in d["nodes"]]
    except Exception as error:  # the page still works without threads
        out["error"] = f"{type(error).__name__}: {str(error)[:120]}"
    Path(site, "community.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"community: {len(out['items'])} threads" + (f" ({out['error']})" if "error" in out else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
