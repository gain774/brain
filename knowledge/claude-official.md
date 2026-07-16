# 🏢 Claude/Anthropic 公式情報(一次記録)

> 毎回のルーチンでWebSearch(公式ドメイン限定)で取得する公式アップデートの記録。
> Xの噂より優先される一次情報。各項目に「この脳への応用」を併記する。
> 公式ソース: [Claude Code What's new](https://code.claude.com/docs/en/whats-new) / [Anthropic Newsroom](https://www.anthropic.com/news) / [Release notes](https://support.claude.com/en/articles/12138966-release-notes) / [Platform release notes](https://platform.claude.com/docs/en/release-notes/overview)

## 2026-07-16 取得分

### モデル
- **Claude Opus 4.7 GA**: SWE・長時間コーディング改善、高解像度画像認識(vision強化)。※Opus 4.8はさらに新しい(この脳の現行モデル)
- **Claude Sonnet 5**: Pro/Team/Enterpriseの新デフォルト。ネイティブ1Mコンテキスト、adaptive thinkingデフォルトON、Sonnet価格。Sonnet 4.6からのドロップイン。**破壊的変更3点**: ①adaptive thinkingがデフォルトON ②手動extended thinkingは400エラー ③サンプリングパラメータを非デフォルト値にすると400エラー。最大出力128kトークン
  - **この脳への応用**: エージェント用途のコスパ最良。将来この脳のサブエージェント(敵対的レビュー等)をSonnet 5に回せばコスト削減の可能性 → labで要検証

### 新プロダクト・機能
- **Claude Design**(Anthropic Labs): デザイン・プロトタイプ・スライド・1pagerをClaudeと共同生成
- **Claude Cowork** GA(macOS/Windows、Claude Desktop経由): Analytics APIにも展開。**この脳への応用**: Coworkの自律作業パターンは要調査
- **Claude in Chrome** GA(全Anthropic直販プラン)
- **サブアージェントがデフォルトでバックグラウンド実行**: Claudeは待たずに作業継続 → **この脳への応用: 既にサブエージェントを敵対的レビュー等で活用中。バックグラウンド化で並列リサーチ+整理が可能かlabで検証する価値あり**
- **Claude Desktop on Linux** ベータ(Ubuntu/Debian)

### 非推奨・削除
- **Opus 4.7のfast modeは非推奨、2026-07-24削除予定** → Opus 4.8のfast modeへ移行(この脳はOpus 4.8なので影響は軽微だが留意)

### この脳の進化アクション候補(→ lab/queue.mdへ)
1. サブエージェントのバックグラウンド並列実行で、リサーチと整理を同時進行できないか
2. 敵対的レビュー等の補助タスクをSonnet 5に回してコスト削減できないか

## 2026-07-16 追加取得分(Claude Code Week 28: 7/6-10)

- **`/doctor`コマンドが強化**: インストール健全性チェックに加え、**「使われていないSkill・MCPサーバー・pluginをコンテキストコスト対比で検出」「ローカルCLAUDE.mdの重複排除」「遅いhookの検出」**が可能に。→ **この脳への応用(高価値)**: この脳が抱えるSkill/MCP/設定のうち、コンテキストコストに見合わないものを`/doctor`で定期的に棚卸しして削れる。効率化に直結 → lab候補Fへ
- **Claude Codeデスクトップにブラウザ内蔵**(既知のK-A4を公式で確認、サンドボックス+安全分類器つき)
- **バックグラウンドエージェントが更新後に自動でバージョン更新**、エージェントビューが色付き状態語+分類器生成の見出し表示に
- **auto modeのtranscript保護強化**、Opus 4.8での`/code-review`品質改善
- 出典: [Claude Code What's new W28](https://code.claude.com/docs/en/whats-new/2026-w28)、[Opus 4.8発表](https://www.anthropic.com/news/claude-opus-4-8)、[Claude Codeの自律化](https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously)
