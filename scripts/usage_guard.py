#!/usr/bin/env python3
"""Usage guard: estimate 5-hour-window utilization and pick an action tier.

The official usage-limit API is not reachable from this environment, so we
approximate: every session records its own token consumption (parsed from its
local transcript) into research/usage-log.json, which lives in the repo and is
shared across sessions via git. Utilization = weighted units consumed in the
rolling window / ceiling.

Known limits (documented in BRAIN.md): the user's own interactive sessions are
not in the ledger, and crashed sessions don't record. The ceiling is a guess
until calibrated — when a real usage-limit error is observed, run
`usage_guard.py limit-hit` to set the ceiling to the observed window total.

Commands:
  check      print utilization estimate and the tier to run (also exit code 0-3)
  record     append this session's consumption to the ledger (run before final commit)
  limit-hit  calibrate: set ceiling to current window total
"""

import glob
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "research/usage-log.json"
CONFIG = ROOT / "config/usage.json"
RETENTION_SEC = 14 * 86400

DEFAULT_CONFIG = {
    "window_hours": 5,
    "ceiling_units": 20_000_000,
    "ceiling_calibrated": False,
    "weekly": {
        "window_hours": 168,
        "ceiling_units": 150_000_000,
        "ceiling_calibrated": False,
        "spend_target_pct": 85,
        "tiers": [
            {"max_pct": 60, "tier": 0, "name": "制限なし",
             "do": "5時間窓のTIERに従う"},
            {"max_pct": 75, "tier": 1, "name": "週次セーブ",
             "do": "実測検証・敵対的レビュー・夜間メニューをスキップ(週の残りを守る)"},
            {"max_pct": 85, "tier": 2, "name": "週次最小",
             "do": "x_research.py+最小ログ+コミットのみ"},
            {"max_pct": 100, "tier": 3, "name": "週次スキップ",
             "do": "recordのみして即終了。残りはユーザーの手動利用のために温存"},
        ],
    },
    "night": {
        "jst_hours": [0, 5],
        "spend_target_pct": 90,
        "tiers": [
            {"max_pct": 90, "tier": 0, "name": "夜間フル実行",
             "do": "全手順+BRAIN.md第2部の夜間メニューで予算(90%)を使い切る。残り予算に応じて深さを調整"},
            {"max_pct": 95, "tier": 2, "name": "最小",
             "do": "x_research.py実行と日次ログへの最小追記+コミットのみ"},
            {"max_pct": 100, "tier": 3, "name": "スキップ",
             "do": "recordのみして即終了"},
        ],
    },
    "tiers": [
        {"max_pct": 50, "tier": 0, "name": "フル実行",
         "do": "全手順(Xリサーチ+記事+評価+実測検証+knowledge整理+ループ+改善)"},
        {"max_pct": 75, "tier": 1, "name": "標準",
         "do": "Xリサーチ+記事+評価+記録+軽いknowledge更新。実測検証と敵対的レビューはスキップ"},
        {"max_pct": 90, "tier": 2, "name": "最小",
         "do": "x_research.py実行と日次ログへの最小追記+コミットのみ。分析・整理はしない"},
        {"max_pct": 100, "tier": 3, "name": "スキップ",
         "do": "何もせず即終了(記録もrecordのみ)。次回に持ち越す"},
    ],
}


def weighted_units(u):
    return (u.get("input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
            + 5 * u.get("output_tokens", 0)
            + 0.1 * u.get("cache_read_input_tokens", 0))


def own_session_units():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl")) or \
        sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")),
               key=os.path.getmtime, reverse=True)[:1]
    total = 0.0
    for p in paths:
        for line in open(p, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            u = (d.get("message") or {}).get("usage")
            if u:
                total += weighted_units(u)
    return total, (paths[0] if paths else None)


def load(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def window_total(ledger, hours, now, exclude_session=None):
    horizon = now - hours * 3600
    return sum(e["units"] for e in ledger
               if e["ts"] >= horizon and e.get("session") != exclude_session)


def pick_tier(tiers, pct):
    return next(t for t in tiers if pct <= t["max_pct"] or t["max_pct"] >= 100)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    cfg = load(CONFIG, DEFAULT_CONFIG)
    ledger = load(LEDGER, [])
    now = time.time()
    ledger = [e for e in ledger if e["ts"] >= now - RETENTION_SEC]

    if cmd == "record":
        units, path = own_session_units()
        sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown")
        ledger = [e for e in ledger if e.get("session") != sid]
        ledger.append({"ts": now, "session": sid, "units": round(units)})
        LEDGER.write_text(json.dumps(ledger, indent=1))
        print(f"recorded {round(units):,} units for session {sid[:8]}… "
              f"(transcript: {path})")
        return

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown")

    if cmd == "limit-hit":
        which = sys.argv[2] if len(sys.argv) > 2 else "5h"
        own, _ = own_session_units()
        if which == "weekly":
            total = window_total(ledger, cfg["weekly"]["window_hours"], now,
                                 exclude_session=sid) + own
            cfg["weekly"]["ceiling_units"] = round(total)
            cfg["weekly"]["ceiling_calibrated"] = True
        else:
            total = window_total(ledger, cfg["window_hours"], now,
                                 exclude_session=sid) + own
            cfg["ceiling_units"] = round(total)
            cfg["ceiling_calibrated"] = True
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        print(f"{which} ceiling calibrated to {round(total):,} units")
        return

    # check
    own, _ = own_session_units()
    total5 = window_total(ledger, cfg["window_hours"], now, exclude_session=sid) + own
    pct5 = 100.0 * total5 / cfg["ceiling_units"]

    wk = cfg.get("weekly", {})
    totalw = window_total(ledger, wk.get("window_hours", 168), now,
                          exclude_session=sid) + own
    pctw = 100.0 * totalw / wk.get("ceiling_units", 150_000_000)

    hour = datetime.fromtimestamp(now, JST).hour
    night = cfg.get("night", {})
    nh = night.get("jst_hours", [0, 5])
    is_night = nh[0] <= hour < nh[1] and "tiers" in night
    mode = f"🌙夜間モード(JST {nh[0]}時〜{nh[1]}時)" if is_night else "☀️昼間モード"

    tier5 = pick_tier(night["tiers"] if is_night else cfg["tiers"], pct5)
    tierw = pick_tier(wk["tiers"], pctw) if wk.get("tiers") else {"tier": 0}
    # 週次 > 5時間: 厳しい方を採用
    tier = tierw if tierw["tier"] > tier5["tier"] else tier5
    limited_by = "週次制限" if tierw["tier"] > tier5["tier"] else "5時間制限"

    calib5 = "校正済" if cfg.get("ceiling_calibrated") else "未校正"
    calibw = "校正済" if wk.get("ceiling_calibrated") else "未校正"
    print(f"📅 週次(直近7日): {round(totalw):,} / {wk.get('ceiling_units', 0):,} units "
          f"= {pctw:.1f}% ({calibw}) → 週次TIER {tierw['tier']}")
    print(f"{mode} 直近{cfg['window_hours']}時間: {round(total5):,} / "
          f"{cfg['ceiling_units']:,} units = {pct5:.1f}% ({calib5}) "
          f"→ TIER {tier5['tier']}")
    print(f"→ 最終TIER {tier['tier']}({limited_by}が支配): "
          f"{tier['name']} — {tier['do']}")
    if is_night and tier["tier"] == 0:
        budget5 = cfg["ceiling_units"] * night.get("spend_target_pct", 90) / 100 - total5
        budgetw = (wk.get("ceiling_units", 0)
                   * wk.get("spend_target_pct", 85) / 100 - totalw)
        budget = min(budget5, budgetw)
        src = "週次" if budgetw < budget5 else "5時間"
        print(f"💰 夜間の残り予算: 約{max(0, round(budget)):,} units({src}窓が上限) "
              f"— この予算内で夜間メニューを実行。"
              f"参考: 標準的なフル実行1回 ≈ 4,000,000〜5,000,000 units")
    sys.exit(tier["tier"])


if __name__ == "__main__":
    main()
