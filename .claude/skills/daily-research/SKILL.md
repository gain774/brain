---
name: daily-research
description: 共有脳(gain774/brain)の日次AIリサーチ・整理・進化ルーチンを実行する。RoutineやユーザーがこのSkillを呼ぶだけで、BRAIN.md第2部の全手順(公式情報確認→Xリサーチ→評価→実測検証→knowledge整理→検証ループ→自己進化→記録→push)を利用率ガードに従って実行する。「日次リサーチ」「brainのルーチン」「リサーチを回して」等で起動。
---

# 共有脳 日次リサーチ・進化ルーチン

このSkillは gain774/brain の1回分の実行をパッケージしたもの。**BRAIN.md 第2部が常に正**であり、このSkillはその実行手順の要約チェックリスト。矛盾があればBRAIN.mdに従い、このSkillを更新する。

## 実行手順

### 0. 同期と利用率チェック(必須・最初に)
```
git fetch origin main && git reset --hard origin/main
python3 scripts/usage_guard.py check   # 終了コード=TIER(0-3)
```
BRAIN.mdを読み直す。表示された**モード(☀️昼/🌙夜)とTIER**、**週次ペース差**に従う:
- **TIER 3**: `python3 scripts/usage_guard.py record` だけ実行して**即終了**(コミット不要ならしない)
- **TIER 2(最小)**: 手順1〜2+日次ログへの最小追記+record+コミットのみ
- **TIER 1(標準)**: 手順1〜3, 6〜9(実測検証・敵対的レビューはスキップ)
- **TIER 0(フル)**: 全手順。夜間TIER0は予算に応じてBRAIN.mdの「夜間メニュー」も

### 1. Claude公式情報を最優先確認(X APIコスト不要)
WebSearchを `allowed_domains: [anthropic.com, docs.anthropic.com, claude.com, code.claude.com]` で実行し、公式の新機能・更新を取得。新機能は「この脳に応用できないか」を即検討し、`knowledge/claude-official.md` に記録。応用候補は `lab/queue.md` へ。

### 2. Xリサーチ
```
python3 scripts/x_research.py   # since_id+既読管理で新着のみ、5クエリ
```
X APIが429/spend-cap等で失敗しても中断せず、失敗を `loop/review-log.md` に記録して続行。

### 3. Webリサーチ(補助・条件付き)
Xで足りない時のみ: ①X障害の代替 ②総合8以上/疑義フラグの裏取り ③文脈不足の深掘り。読んだURLは `research/state.json` の `seen_articles` に記録。

### 4. 日次ログ記録
`research/YYYY/YYYY-MM-DD.md` に追記(同日2回目以降は `## 実行 HH:MM`)。各注目情報に**タイプ(N/K/M/P型)+10段階スコア**を付ける(BRAIN.md評価フレームワーク)。**知名度でなく内容で選別**。生データが多い時はサブエージェント(general-purpose)に抽出させると効率的。

### 5. 実測検証(lab)
`lab/queue.md` から1〜3件(夜間で余裕あれば全件)を**実際に動かして**検証、`lab/YYYY-MM-DD-*.md` に記録、判定(✅/⚠️/❌)を knowledge へ反映。

### 6. knowledge整理
新知見の追加**だけでなく削除・統合も**。異なる評価・見方は「1意見」として併記。各項目に出典と最終検証日。30日以上未検証はループで再検証。

### 7. 検証ループ + 自己進化
`loop/review-log.md` で未回答の問いに答え、新しい問いを最低1つ。日曜は敵対的レビュー(サブエージェント)をknowledge全体に。**自己進化**: 公式新機能・蓄積データの効率化パターンをこの脳自身に適用(BRAIN.md「自己進化の原則」)。小さく刻み、labで実測、失敗は戻す。

### 8. 連絡・記録・push
ユーザーへの連絡事項(必要な設定・コスト・制約)は最終メッセージで明確に。
```
python3 scripts/usage_guard.py record   # コミット前に必ず
git add -A && git commit && git push origin <branch> && git push origin <branch>:main
```
完了したら最重要知見3件(評価スコアつき)と週次ペース状況を要約。

## 不変条件(壊さない)
- BRAIN.md 第1部(目的)は絶対に変更しない
- usage_guardは「差分(デルタ)」方式(累積を直近消費として扱わない)
- コスト増・大構造変更・外部影響のある変更は事前にユーザー確認
