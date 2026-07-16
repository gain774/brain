# 🧰 この脳が使える全機能カタログ(2026-07-16 実棚卸し)

> ユーザー指示「Claude・API・MCPなど使える機能を全て使え。一覧と機能を作れ」に基づく実測棚卸し。
> 各機能に「状態」と「この脳での活用(実装済み/候補)」を併記。新機能追加時はここを更新。

## 1. Claude公式コネクタ(claude.ai MCP)

| コネクタ | 状態 | この脳での活用 |
|----------|------|----------------|
| **Gmail** | ✅接続済・チャット有効 | 週次ダイジェストのメール配信(候補・要ユーザー承認)。重要な連絡の送信 |
| **Google Calendar** | 導入済・チャット無効 | AI業界の重要イベント(モデルリリース等)を検知してカレンダー登録(候補) |
| **Google Drive** | 導入済・チャット無効 | knowledgeの外部バックアップ、大きな成果物の保管(候補) |
| **Figma** | 導入済・チャット無効 | (この脳の用途では優先度低) |

※「チャット無効」のものは claude.ai のこのチャットのコネクタ設定で有効化が必要。有効化すればツールが使える。

## 2. Claude公式スキル(claude.ai、全て有効)

| スキル | この脳での活用 |
|--------|----------------|
| **pdf** | AI論文・レポートPDFの読み取り・要約 → knowledge化 |
| **docx** | 週次/月次まとめレポートをWord形式で生成(候補) |
| **pptx** | 知見のスライド化(ユーザーへのプレゼン用、候補) |
| **xlsx** | 収集データ・評価スコアの表計算・分析(候補) |

## 3. セッション内MCPサーバー

| サーバー | 主なツール | この脳での活用 |
|----------|-----------|----------------|
| **github** | PR/Issue/CI/Actions/コード検索 | 現状: main反映。候補: knowledgeの重要更新をIssue化、GitHub Actionsで定期実行の冗長化 |
| **Claude Code Remote** | Routine作成、環境/リポジトリ管理、PR購読、send_later | 現状: 日次Routineを運用。候補: 週次まとめ専用Routine、send_laterでの自己リマインド |
| **Gmail** | draft/search/label/thread | 上記コネクタ参照 |

## 4. 組み込みツール(Claude Code harness)

- **Bash**: スクリプト実行(x_research.py, usage_guard.py)。実装済み
- **WebSearch / WebFetch**: 公式情報の最速取得(手順1で実装済み)、裏取り
- **Agent(サブエージェント)**: general-purpose / Explore / Plan 等。バックログ抽出・敵対的レビューで実装済み。**公式でデフォルトbackground実行化 → 並列化候補(lab A)**
- **Artifact**: 成果物をWebページとして公開。候補: この脳のダッシュボード/週次ダイジェストの可視化
- **Skill**: 手順のパッケージ化。`daily-research` を自作(実装済み)
- **Monitor**: 長時間ジョブの監視。候補: 大量リサーチの進捗監視
- **ScheduleWakeup / send_later**: 自己リマインド。候補: X APIのspend cap回復チェック等
- **SendUserFile**: 生成物(レポート・図)をユーザーに直接送る。候補
- **AskUserQuestion**: 選択肢の確認。実装済み(随所)
- **dataviz スキル**: チャート生成。候補: 評価スコアや収集トレンドの可視化

## 5. 自作資産(スクリプト・Skill・役割エージェント)

### スクリプト
- `scripts/x_research.py`: X API収集(dedup・トークンキャッシュ)
- `scripts/usage_guard.py`: 利用率ガード(5時間/週次、calibrate、front_load_floor)
- `scripts/weekly_digest.py`: 週次ダイジェスト生成

### Skill(`.claude/skills/`)
- `daily-research`: 日次ルーチン全体(公式確認→X収集→評価→検証→整理→ループ→push)
- `weekly-digest`: 週次ダイジェスト生成(+承認済みなら配信)

### 役割特化サブエージェント(`.claude/agents/`、全てSonnetで安価)
パイプラインの各段階を専門エージェントに分担。メインは薄いオーケストレーターに徹する(K-A8/A9):
- **signal-extractor**: 生データ→評価スコア付き完成markdown(抽出段階)
- **knowledge-auditor**: knowledgeの鮮度・未確定・出典・重複の機械的棚卸し
- **fact-checker**: 総合8以上/疑義主張の一次情報裏取り(WebSearch)
- **adversarial-reviewer**: knowledge全体の敵対的レビュー(確証バイアス検出)

## 📺 YouTubeリサーチ(2026-07-16 実測)

- **可能**: `WebSearch(allowed_domains:["youtube.com"])` でAI動画のタイトル・チャンネル・投稿時期・**内容の短い要約**を取得できる(X API不要=無料)。「どんな動画が出て何を扱うか」の把握・記録には十分
- **不可**: 動画本体の視聴、字幕・トランスクリプト全文の取得(youtube.com直アクセス/WebFetch/YouTube Data APIすべて403=ネットワーク許可リスト+APIキーなし)
- **深掘りしたい場合の選択肢**: ①ユーザーがYouTube Data APIキーを環境変数で提供 ②有名動画は、その内容を解説したX投稿・ブログをWebSearchで拾う(間接) — いずれもコスト/手間との相談
- **運用方針(候補)**: 週1回など低頻度で「AI系の注目動画」をWebSearchでスキャンし、タイトル+要約+URLをresearchに記録。フル導入はユーザー承認後

## 🚀 これらを使って作る新機能(優先度順・lab/queueと連動)

1. **週次ダイジェストの自動生成**(docx or Artifact + 任意でGmail配信) — 週次でknowledgeのトップ知見をまとめる。外部送信は要ユーザー承認
2. **知見ダッシュボードのArtifact公開** — 評価スコア・収集トレンド・knowledge件数を可視化(dataviz活用)
3. **サブエージェント並列化**(公式background実行) — リサーチ抽出と整理を同時進行(lab A)
4. **補助タスクのSonnet 5委譲** — コスト削減(lab B)
5. **Google Drive/Calendar連携** — 有効化されれば実装(バックアップ/イベント登録)

> 注: 外部への送信・投稿(メール等)や連携の新規有効化は、実行前にユーザーに確認する(BRAIN.md 自己進化の原則④)。
