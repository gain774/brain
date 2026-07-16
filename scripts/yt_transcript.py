#!/usr/bin/env python3
"""YouTube transcript fetcher for the shared brain (video-ingest pipeline).

Fetches a video's watch page, extracts the caption track list from
ytInitialPlayerResponse, downloads the transcript (json3), and prints it
with basic metadata. Saves raw transcript to inbox/videos/ for the
video-analyzer agent.

Notes (documented in capabilities.md):
- Uses YouTube's internal timedtext endpoint — unofficial, may break with
  site changes. Requires youtube.com in the environment network allowlist
  (opened by user on 2026-07-17).
- Works only for videos that have captions (auto-generated included).

Usage: python3 scripts/yt_transcript.py <video_url_or_id> [lang_pref]
       lang_pref default: ja,en (first available wins)
"""

import html
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def curl(url):
    out = subprocess.run(
        ["curl", "-sS", "-L", "-A", UA,
         "-H", "Accept-Language: ja,en;q=0.8", url],
        capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        sys.exit(f"fetch failed: {out.stderr[:300]}")
    return out.stdout


def video_id_from(arg):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", arg)
    return m.group(1) if m else arg.strip()


def extract_player_response(page):
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*(?:var|</script>)",
                  page, re.S)
    if not m:
        sys.exit("ytInitialPlayerResponse not found (page layout changed or blocked)")
    return json.loads(m.group(1))


def pick_track(tracks, prefs):
    for lang in prefs:
        for t in tracks:
            if t.get("languageCode", "").startswith(lang):
                return t
    return tracks[0]


def transcript_from_json3(raw):
    data = json.loads(raw)
    lines = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if text:
            start = ev.get("tStartMs", 0) // 1000
            lines.append(f"[{start//60:02d}:{start%60:02d}] {text}")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: yt_transcript.py <video_url_or_id> [lang_pref e.g. ja,en]")
    vid = video_id_from(sys.argv[1])
    prefs = (sys.argv[2].split(",") if len(sys.argv) > 2 else ["ja", "en"])

    page = curl(f"https://www.youtube.com/watch?v={vid}")
    pr = extract_player_response(page)

    ps = pr.get("playabilityStatus", {})
    if ps.get("status") == "LOGIN_REQUIRED":
        # データセンターIPに対するYouTubeのbot検知(2026-07-17実測)。
        # oEmbedでメタ情報だけ取り、字幕はユーザーの手動コピペ(video-ingest)に誘導する。
        meta = json.loads(curl(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"))
        print(f"タイトル: {meta.get('title')}\nチャンネル: {meta.get('author_name')}\n"
              f"URL: https://www.youtube.com/watch?v={vid}")
        sys.exit("⚠️ YouTubeのbot検知により字幕の自動取得は不可(この環境のIPがブロック対象)。"
                 "動画ページの「文字起こしを表示」からコピーして inbox/videos/ に置いてください")

    details = pr.get("videoDetails", {})
    title = details.get("title", "(不明)")
    channel = details.get("author", "(不明)")
    length_min = int(details.get("lengthSeconds", 0)) // 60

    tracks = (pr.get("captions", {})
              .get("playerCaptionsTracklistRenderer", {})
              .get("captionTracks", []))
    if not tracks:
        sys.exit(f"この動画には字幕トラックがありません: {title}")

    track = pick_track(tracks, prefs)
    kind = "自動生成" if track.get("kind") == "asr" else "手動"
    base = html.unescape(track["baseUrl"]).replace("\\u0026", "&")
    raw = curl(base + "&fmt=json3")
    text = transcript_from_json3(raw)
    if not text.strip():
        sys.exit("字幕の中身が空でした")

    header = (f"タイトル: {title}\nチャンネル: {channel}\n"
              f"URL: https://www.youtube.com/watch?v={vid}\n"
              f"長さ: 約{length_min}分 / 字幕: {track.get('languageCode')}({kind})\n"
              f"取得日: {date.today().isoformat()}\n---\n")

    out_dir = ROOT / "inbox/videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{vid}.txt"
    out_path.write_text(header + text, encoding="utf-8")
    print(header)
    print(f"({len(text.splitlines())}行の字幕を保存: {out_path.relative_to(ROOT)})")
    print("--- 冒頭プレビュー ---")
    print("\n".join(text.splitlines()[:10]))


if __name__ == "__main__":
    main()
