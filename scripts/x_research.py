#!/usr/bin/env python3
"""Daily X (Twitter) research collector for the shared brain.

Reads queries from config/queries.json, searches the X API v2 recent
search endpoint, and saves raw results to research/raw/.
Prints a ranked digest to stdout for the synthesis step.

Cost control / dedup (BRAIN.md 第1部の方針):
- research/state.json に見たツイートID・本文ハッシュ・クエリごとの since_id を永続化
- since_id により一度取得した範囲はAPIから再取得しない(APIコスト節約)
- 本文の正規化ハッシュでコピペスパム等の実質重複を除外
- 同じ話題でも本文が異なる(=視点や評価が違う)ものは別意見として残す

Auth: app-only bearer token derived from X_API_KEY / X_API_SECRET env vars.
HTTP is done through curl so the environment's proxy/CA setup just works.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "research/state.json"
TOKEN_CACHE = ROOT / "research/.x_token_cache.json"  # never committed (see .gitignore) — holds a credential
API = "https://api.x.com"
SEEN_RETENTION_DAYS = 45


def curl_json(args):
    out = subprocess.run(["curl", "-sS", "-w", "\n%{http_code}"] + args,
                         capture_output=True, text=True, timeout=60)
    body, _, code = out.stdout.rpartition("\n")
    return int(code or 0), (json.loads(body) if body.strip() else {})


def fetch_bearer():
    key, secret = os.environ["X_API_KEY"], os.environ["X_API_SECRET"]
    code, data = curl_json(["-u", f"{key}:{secret}",
                            "--data", "grant_type=client_credentials",
                            f"{API}/oauth2/token"])
    if code != 200:
        sys.exit(f"token request failed: HTTP {code} {data}")
    return data["access_token"]


def get_bearer():
    """App-only bearer tokens don't expire, so cache locally and reuse across
    runs instead of hitting the token endpoint every invocation. main()
    invalidates the cache and calls fetch_bearer() again on a 401."""
    if TOKEN_CACHE.exists():
        try:
            return json.loads(TOKEN_CACHE.read_text())["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass
    token = fetch_bearer()
    TOKEN_CACHE.write_text(json.dumps({"access_token": token}))
    return token


def invalidate_bearer_cache():
    TOKEN_CACHE.unlink(missing_ok=True)


def search(bearer, query, max_results, since_id=None):
    p = {
        "query": query,
        "max_results": max_results,
        "sort_order": "recency",
        "tweet.fields": "public_metrics,created_at,author_id,lang",
        "expansions": "author_id",
        "user.fields": "username,name,public_metrics",
    }
    if since_id:
        p["since_id"] = since_id
    return curl_json(["-H", f"Authorization: Bearer {bearer}",
                      f"{API}/2/tweets/search/recent?{urllib.parse.urlencode(p)}"])


def text_fingerprint(text):
    """Normalized hash so copy-paste spam counts as one item.

    Genuinely different wordings (= different opinions/viewpoints) survive.
    """
    t = re.sub(r"https?://\S+", "", text.lower())
    t = re.sub(r"[^0-9a-zA-Zぁ-んァ-ヶ一-龠]+", "", t)
    return hashlib.sha1(t[:160].encode()).hexdigest()[:16]


def engagement(t):
    m = t.get("public_metrics", {})
    return (m.get("like_count", 0) + 2 * m.get("retweet_count", 0)
            + 2 * m.get("bookmark_count", 0) + m.get("reply_count", 0))


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"since_id": {}, "seen_tweets": {}, "seen_hashes": {}, "seen_articles": {}}


def prune(seen, today):
    cutoff = (today - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
    return {k: v for k, v in seen.items() if v >= cutoff}


def main():
    cfg = json.loads((ROOT / "config/queries.json").read_text())
    state = load_state()
    bearer = get_bearer()
    now = datetime.now()
    today = now.date().isoformat()
    run_id = now.strftime("%Y-%m-%dT%H%M")
    results = {"run": run_id, "queries": []}
    max_results = cfg.get("max_results_per_query", 100)
    dup_skipped = 0

    for q in cfg["queries"]:
        since = state["since_id"].get(q["label"])
        code, data = search(bearer, q["query"], max_results, since)
        if code == 401:
            # cached token stale/invalid — refresh once and retry this query
            invalidate_bearer_cache()
            bearer = get_bearer()
            code, data = search(bearer, q["query"], max_results, since)
        entry = {"label": q["label"], "query": q["query"], "http": code,
                 "since_id_used": since}
        if code == 200:
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            fresh = []
            for t in data.get("data", []):
                if t["id"] in state["seen_tweets"]:
                    dup_skipped += 1
                    continue
                state["seen_tweets"][t["id"]] = today
                fp = text_fingerprint(t.get("text", ""))
                if fp in state["seen_hashes"]:
                    dup_skipped += 1
                    continue
                state["seen_hashes"][fp] = today
                u = users.get(t.get("author_id"), {})
                t["author_username"] = u.get("username")
                t["author_followers"] = u.get("public_metrics", {}).get("followers_count")
                fresh.append(t)
            newest = data.get("meta", {}).get("newest_id")
            if newest:
                state["since_id"][q["label"]] = newest
            entry["tweets"] = fresh
            print(f"[{q['label']}] {len(fresh)} new tweets "
                  f"(fetched {data.get('meta', {}).get('result_count', 0)})")
        else:
            entry["error"] = data
            print(f"[{q['label']}] HTTP {code}: {json.dumps(data)[:200]}", file=sys.stderr)
            if code == 429:
                print("rate limited — stopping further queries", file=sys.stderr)
                results["queries"].append(entry)
                break
        results["queries"].append(entry)
        time.sleep(3)

    d = date.today()
    state["seen_tweets"] = prune(state["seen_tweets"], d)
    state["seen_hashes"] = prune(state["seen_hashes"], d)
    state["seen_articles"] = prune(state.get("seen_articles", {}), d)

    raw_dir = ROOT / "research/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{run_id.replace(':', '')}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"\nsaved: {out_path.relative_to(ROOT)}  (duplicates skipped: {dup_skipped})")

    print("\n===== NEW TWEETS BY ENGAGEMENT =====")
    for entry in results["queries"]:
        tweets = sorted(entry.get("tweets", []), key=engagement, reverse=True)
        print(f"\n--- {entry['label']} ({len(tweets)} new) ---")
        for t in tweets[:15]:
            m = t.get("public_metrics", {})
            print(f"♥{m.get('like_count',0)} RT{m.get('retweet_count',0)} "
                  f"@{t.get('author_username')} (followers:{t.get('author_followers')}) "
                  f"https://x.com/i/status/{t['id']}\n  "
                  + t.get("text", "").replace("\n", " ")[:280])


if __name__ == "__main__":
    main()
