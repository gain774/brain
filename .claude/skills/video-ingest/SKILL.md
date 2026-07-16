---
name: video-ingest
description: YouTube等のAI関連動画の中身を脳に取り込むパイプライン。ユーザーが文字起こしテキストを渡す(チャットに貼る/inbox/videos/に置く)と、video-analyzerエージェントが構造化解析し、research/videos/に評価つきで保存、knowledge/labへ反映する。「この動画取り込んで」「動画の文字起こし貼るね」等で起動。
---

# 動画取り込みパイプライン(video-ingest)

## 背景(なぜこの形か)
この環境はネットワーク許可リスト制で youtube.com / googleapis.com に接続できず、動画・字幕の自動取得は不可(2026-07-16実測)。音声認識もClaude単体では不可。**入口はユーザー提供のテキスト**とし、解析以降を全自動化する。

## ユーザー側の手順(かんたん)
YouTubeの動画ページ → 概要欄の「**…その他**」→「**文字起こしを表示**」→ 全選択してコピー。それを:
- **方法A**: チャットにそのまま貼る(動画URL・タイトルも一緒に)
- **方法B**: リポジトリの `inbox/videos/` に `.txt` で置いてコミット(ファイル名は自由)

## 脳側の手順
1. 文字起こしテキストを `inbox/videos/<日付>-<slug>.txt` に保存(チャット貼り付けの場合)
2. **video-analyzer** エージェント(Sonnet・安価)に、テキストパス+メタ情報(タイトル/チャンネル/URL)を渡して解析させる
3. 返ってきた構造化markdownを `research/videos/<日付>-<slug>.md` に保存
4. 「この脳へのアクション」に従い、knowledge化・lab/queue追加・fact-checkerでの主張検証を実施
5. 処理済みの `inbox/videos/*.txt` は残してよい(原文アーカイブ)。日次ログに1行記録
6. コミット・プッシュ

## 定期スキャン(取り込みとは別・無料)
登録チャンネル(config/video_channels.json)の新着動画を WebSearch(`allowed_domains:["youtube.com"]`)で週1回スキャンし、タイトル+テーマ+URLを日次ログに記録。「新着が出た」ことをユーザーに伝え、深掘りしたい動画の文字起こし提供を依頼する。

## 将来の自動化(条件が整えば)
- ユーザーがYouTube Data APIキー(環境変数 `YOUTUBE_API_KEY`)+googleapis.comのネットワーク許可を用意すれば、概要欄・統計の自動取得に拡張可能(字幕の自動取得は公式APIでは所有者以外不可のため、文字起こし提供方式は残る)
