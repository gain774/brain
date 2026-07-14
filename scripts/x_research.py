#!/usr/bin/env python3
"""Daily X (Twitter) research collector for the shared brain.

Reads queries from config/queries.json, searches the X API v2 recent
search endpoint, and saves raw results to research/raw/YYYY-MM-DD.json.
Prints a ranked digest to stdout for the daily synthesis step.

Auth: app-only bearer token derived from X_API_KEY / X_API_SECRET env vars.
HTTP is done through curl so the environment's proxy/CA setup just works.
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.x.com"


def curl_json(args):
    out = subprocess.run(["curl", "-sS", "-w", "\n%{http_code}"] + args,
                         capture_output=True, text=True, timeout=60)
    body, _, code = out.stdout.rpartition("\n")
    return int(code or 0), (json.loads(body) if body.strip() else {})


def get_bearer():
    key, secret = os.environ["X_API_KEY"], os.environ["X_API_SECRET"]
    code, data = curl_json(["-u", f"{key}:{secret}",
                            "--data", "grant_type=client_credentials",
                            f"{API}/oauth2/token"])
    if code != 200:
        sys.exit(f"token request failed: HTTP {code} {data}")
    return data["access_token"]


def search(bearer, query, max_results):
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": max_results,
        "sort_order": "relevancy",
        "tweet.fields": "public_metrics,created_at,author_id,lang",
        "expansions": "author_id",
        "user.fields": "username,name,public_metrics",
    })
    return curl_json(["-H", f"Authorization: Bearer {bearer}",
                      f"{API}/2/tweets/search/recent?{params}"])


def engagement(t):
    m = t.get("public_metrics", {})
    return (m.get("like_count", 0) + 2 * m.get("retweet_count", 0)
            + 2 * m.get("bookmark_count", 0) + m.get("reply_count", 0))


def main():
    cfg = json.loads((ROOT / "config/queries.json").read_text())
    bearer = get_bearer()
    today = date.today().isoformat()
    results = {"date": today, "queries": []}

    for q in cfg["queries"]:
        code, data = search(bearer, q["query"], cfg.get("max_results_per_query", 25))
        entry = {"label": q["label"], "query": q["query"], "http": code}
        if code == 200:
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            tweets = data.get("data", [])
            for t in tweets:
                u = users.get(t.get("author_id"), {})
                t["author_username"] = u.get("username")
                t["author_followers"] = u.get("public_metrics", {}).get("followers_count")
            entry["tweets"] = tweets
            print(f"[{q['label']}] {len(tweets)} tweets")
        else:
            entry["error"] = data
            print(f"[{q['label']}] HTTP {code}: {json.dumps(data)[:200]}", file=sys.stderr)
            if code == 429:
                print("rate limited — stopping further queries", file=sys.stderr)
                results["queries"].append(entry)
                break
        results["queries"].append(entry)
        time.sleep(3)

    raw_dir = ROOT / "research/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{today}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\nsaved: {out_path.relative_to(ROOT)}")

    print("\n===== TOP TWEETS BY ENGAGEMENT =====")
    for entry in results["queries"]:
        tweets = sorted(entry.get("tweets", []), key=engagement, reverse=True)
        print(f"\n--- {entry['label']} ---")
        for t in tweets[:8]:
            m = t.get("public_metrics", {})
            print(f"♥{m.get('like_count',0)} RT{m.get('retweet_count',0)} "
                  f"@{t.get('author_username')} (followers:{t.get('author_followers')}) "
                  f"https://x.com/i/status/{t['id']}\n  "
                  + t.get("text", "").replace("\n", " ")[:280])


if __name__ == "__main__":
    main()
