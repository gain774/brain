#!/usr/bin/env python3
"""YouTube video VISUAL analyzer — uses Gemini API as the "eyes".

The user's goal: understand WHAT IS SHOWN ON SCREEN in AI-dev tutorial
videos (terminal commands, UI operations, file edits) — transcripts are
not enough. This environment cannot fetch YouTube video data (bot wall),
but the Gemini API accepts a YouTube URL directly and watches the video
(visual + audio) on Google's side. This script asks Gemini to narrate the
on-screen operations in detail; the output is then structured by the
video-analyzer agent (video-ingest pipeline).

Requirements (one-time, by user):
  1. GEMINI_API_KEY env var — free key from https://aistudio.google.com/apikey
  2. generativelanguage.googleapis.com added to the environment's network allowlist

Usage: python3 scripts/yt_video_analyze.py <youtube_url> [追加の着目点]
"""

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPT = """あなたはAI開発チュートリアル動画の画面解析者です。この動画の**画面上で実際に行われている操作**を、目で見た事実として時系列で詳細に書き出してください。音声の要約ではなく「画面に何が映り、何を操作したか」が主役です。

各場面について:
- [MM:SS] 画面に映っているツール/アプリ(Claude Code、Cursor、bolt.new、ブラウザ、エディタ等)と画面の状態
- ターミナルに入力されたコマンド・プロンプト(読み取れたものは**原文のまま**)
- 編集・作成されたファイル名と内容の要点
- クリックした設定・ボタン・メニュー等のUI操作
- 画面に表示された結果(エラー、出力、完成物のプレビュー)

最後に:
- 使用ツール一覧(画面で確認できたもの)
- 操作フロー全体の要約(この動画の手順を再現するための番号付きステップ)
- 画面から読み取れた具体的な設定値・プロンプト文のリスト
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: yt_video_analyze.py <youtube_url> [追加の着目点]")
    url = sys.argv[1]
    extra = sys.argv[2] if len(sys.argv) > 2 else ""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY が未設定です。https://aistudio.google.com/apikey で無料発行し、"
                 "環境変数に設定してください(capabilities.md参照)")

    vid_m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    vid = vid_m.group(1) if vid_m else "video"

    body = {
        "contents": [{
            "parts": [
                {"fileData": {"fileUri": url}},
                {"text": PROMPT + (f"\n\n特に注目してほしい点: {extra}" if extra else "")},
            ]
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
    }
    out = subprocess.run(
        ["curl", "-sS", "-X", "POST",
         f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
         "-H", "Content-Type: application/json",
         "-H", f"x-goog-api-key: {key}",
         "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        sys.exit(f"接続失敗(ネットワーク許可に generativelanguage.googleapis.com が必要): {out.stderr[:200]}")
    resp = json.loads(out.stdout)
    if "error" in resp:
        e = resp["error"]
        sys.exit(f"Gemini APIエラー {e.get('code')}: {e.get('message', '')[:300]}")
    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        sys.exit(f"想定外のレスポンス: {out.stdout[:300]}")

    out_dir = ROOT / "inbox/videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{vid}-visual.txt"
    header = f"URL: {url}\n解析: Gemini {MODEL}(映像+音声)\n取得日: {date.today().isoformat()}\n---\n"
    out_path.write_text(header + text, encoding="utf-8")
    print(f"✅ 映像解析を保存: {out_path.relative_to(ROOT)} ({len(text)}文字)")
    print("次: video-analyzerエージェントで構造化 → research/videos/ へ")
    print("\n--- 冒頭プレビュー ---")
    print(text[:600])


if __name__ == "__main__":
    main()
