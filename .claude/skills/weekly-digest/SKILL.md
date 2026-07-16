---
name: weekly-digest
description: 共有脳の週次ダイジェストを生成する。knowledge/lab/loop/researchの現状(厳選知見一覧・未回答の問い・ラボ状況・記録日数)をまとめて digests/YYYY-Www.md に出力する。日曜の回、または「週次まとめ」「ダイジェスト作って」で起動。配信(Gmail/Artifact/docx)はユーザー承認済みのフォーマットがある時のみ。
---

# 週次ダイジェスト生成

## 手順
1. 最新mainに同期していることを確認(`git fetch origin main && git reset --hard origin/main`)
2. 生成スクリプトを実行:
   ```
   python3 scripts/weekly_digest.py
   ```
   → `digests/YYYY-Www.md` に、厳選知見一覧・未回答の問い・ラボ状況・記録日数のサマリーが出力される
3. 生成物を確認し、必要なら「今週のハイライト3件」(総合スコア上位)を先頭に手で足す
4. コミット&プッシュ(`digests/` はコミット対象)

## 配信(オプション・ユーザー承認が要る)
ユーザーがフォーマットを指定済みの場合のみ:
- **Gmail配信**: Gmail MCPで ks07shuhei26@gmail.com 宛に本文として送る(外部送信=承認済みフォーマットがある時だけ)
- **docx化**: docxスキルでWord版を生成
- **Artifact公開**: dataviz+Artifactでダッシュボード化(digests の数値を可視化)
※フォーマット未指定なら生成のみで止め、配信はしない。

## 注意
- ダイジェストは「集めたデータのまとめ」なのでX API・重い思考をほぼ使わない(低コスト)
- 専用Routineは作らず、日曜の日次ルーチンに相乗りさせる(固定コストを増やさない)
