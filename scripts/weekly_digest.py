#!/usr/bin/env python3
"""Weekly digest generator for the shared brain.

Scans knowledge/, lab/, loop/, research/ and produces a concise Markdown
digest of the brain's current state: top knowledge, open questions, lab
status, and research volume. Output goes to digests/YYYY-Www.md.

This is a capability-composition feature (BRAIN.md "使える全機能を使う"):
the generated digest can be delivered via Gmail (with user approval),
published as an Artifact, or converted to docx/pptx by the respective
Claude skills. This script only builds the source Markdown; delivery is a
separate, user-approved step.

Usage: python3 scripts/weekly_digest.py
"""

import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def count_knowledge_items():
    """Count K-* entries and list their headings per knowledge file."""
    out = {}
    for f in sorted((ROOT / "knowledge").glob("*.md")):
        if f.name == "index.md":
            continue
        heads = re.findall(r"^## (K-\S+:.*)$", f.read_text(), re.M)
        out[f.name] = heads
    return out


def open_loop_questions():
    text = (ROOT / "loop/review-log.md").read_text()
    return re.findall(r"^## (Q\d+ \[open\].*)$", text, re.M)


def lab_status():
    q = (ROOT / "lab/queue.md").read_text()
    waiting = len(re.findall(r"^\d+\.\s\*\*", q, re.M))
    done = len(re.findall(r"^-\s✅|^-\s⚠️", q, re.M))
    return waiting, done


def research_days():
    return sorted(p.stem for p in (ROOT / "research/2026").glob("*.md"))


def main():
    today = date.today()
    year, week, _ = today.isocalendar()
    kn = count_knowledge_items()
    total_k = sum(len(v) for v in kn.values())
    questions = open_loop_questions()
    waiting, done = lab_status()
    days = research_days()

    lines = [
        f"# 🧠 共有脳 週次ダイジェスト — {year}-W{week:02d}（{today.isoformat()}）",
        "",
        "> `scripts/weekly_digest.py` が自動生成。配信(Gmail/Artifact/docx等)は別途ユーザー承認の上で。",
        "",
        "## 📊 サマリー",
        f"- 厳選知見(K-*): **{total_k}件**（{len(kn)}カテゴリ）",
        f"- 検証ループの未回答の問い: **{len(questions)}件**",
        f"- 実測ラボ: 待機 **{waiting}件** / 完了 **{done}件**",
        f"- リサーチ記録日数: **{len(days)}日**（最新: {days[-1] if days else 'なし'}）",
        "",
        "## 📚 現在の厳選知見",
    ]
    for fname, heads in kn.items():
        lines.append(f"\n### {fname}")
        if heads:
            lines += [f"- {h}" for h in heads]
        else:
            lines.append("- (項目なし)")

    lines += ["", "## ❓ 未回答の検証ループ"]
    lines += [f"- {q}" for q in questions] or ["- (なし)"]

    lines += [
        "",
        "## 🔎 次にやること(自動抽出のヒント)",
        "- 上記の未回答の問いに答える",
        f"- 実測ラボの待機{waiting}件を消化する",
        "- 30日以上未検証のknowledgeを再検証する",
        "",
    ]

    out_dir = ROOT / "digests"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{year}-W{week:02d}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"digest written: {out_path.relative_to(ROOT)}")
    print(f"  知見{total_k}件 / 未回答{len(questions)}件 / lab待機{waiting}件 / 記録{len(days)}日")


if __name__ == "__main__":
    main()
