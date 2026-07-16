#!/usr/bin/env python3
"""Usage guard: estimate 5-hour-window utilization and pick an action tier.

The official usage-limit API is not reachable from this environment, so we
approximate: every session records its token consumption (parsed from its
local transcript) into research/usage-log.json, which lives in the repo and is
shared across sessions via git. Utilization = weighted units consumed in the
rolling window / ceiling.

IMPORTANT — this session is persistent (bound to a Routine via
persistent_session_id, so the SAME session/transcript is reused across many
firings spanning days). own_session_units() therefore returns the FULL
CUMULATIVE transcript total, not "recent" usage. We track a per-session
baseline (research/usage-baselines.json) and only ever count the DELTA since
the last record() call — each firing's delta becomes its own ledger entry,
so it ages out of the 5h/weekly windows naturally. Never treat the raw
own_session_units() return value as "current window usage" — it grows
forever for a long-lived persistent session.

Known limits (documented in BRAIN.md): the user's own interactive sessions are
not in the ledger, and crashed sessions don't record. The ceiling is a guess
until calibrated — when a real usage-limit error is observed, run
`usage_guard.py limit-hit [5h|weekly]` to set the ceiling to the observed total.

Commands:
  check      print utilization estimate and the tier to run (also exit code 0-3)
  record     append this run's consumption delta to the ledger (run before final commit)
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
BASELINES = ROOT / "research/usage-baselines.json"
CONFIG = ROOT / "config/usage.json"
RETENTION_SEC = 14 * 86400

DEFAULT_CONFIG = {
    "window_hours": 5,
    "ceiling_units": 20_000_000,
    "ceiling_calibrated": False,
    "weekly": {
        "anchor": {"weekday": 5, "hour_jst": 17},  # 土曜17時JSTリセット(ユーザー観測)
        "ceiling_units": 60_000_000,
        "ceiling_calibrated": False,
        "spend_target_pct": 95,  # リセット時刻にここへ着地させる(ギリギリ攻める)
        "hard_cap_pct": 95,      # これ以上は問答無用でスキップ
        "baseline": None,        # {"ts": epoch, "pct": N} ユーザー申告の外部消費込み実測
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


def window_total(ledger, hours, now):
    """Naive rolling window (last N hours). Used when no real anchor is known."""
    horizon = now - hours * 3600
    return sum(e["units"] for e in ledger if e["ts"] >= horizon)


def anchored_window_start(now, anchor_ts, period_hours):
    """Start of the currently-active fixed-length window, given any ONE known
    real reset instant (anchor_ts, can be past or future) and the period.
    Recurs every period_hours from that anchor — used once the user reports
    an observed real reset time, so our window boundary matches Anthropic's
    actual boundary instead of a naive rolling window."""
    period = period_hours * 3600
    n = (now - anchor_ts) // period
    return anchor_ts + n * period


def window_total_anchored(ledger, now, anchor_ts, period_hours):
    start = anchored_window_start(now, anchor_ts, period_hours)
    return sum(e["units"] for e in ledger if e["ts"] >= start), start


def live_delta(sid, own_full, baselines):
    """Usage in the current run not yet flushed to the ledger by record()."""
    return max(0.0, own_full - baselines.get(sid, 0.0))


def pick_tier(tiers, pct):
    return next(t for t in tiers if pct <= t["max_pct"] or t["max_pct"] >= 100)


def weekly_window_start(now, anchor):
    """Most recent anchor point (e.g. Saturday 17:00 JST) at or before now."""
    dt = datetime.fromtimestamp(now, JST)
    days_back = (dt.weekday() - anchor.get("weekday", 5)) % 7
    cand = (dt - timedelta(days=days_back)).replace(
        hour=anchor.get("hour_jst", 17), minute=0, second=0, microsecond=0)
    if cand > dt:
        cand -= timedelta(days=7)
    return cand.timestamp()


def weekly_state(ledger, wk, now, live):
    """Return (pct, pace_target_pct, consumed, window_end_ts).

    `live` = current run's not-yet-recorded delta (see live_delta()).
    """
    start = weekly_window_start(now, wk.get("anchor", {}))
    end = start + 7 * 86400
    ceiling = wk["ceiling_units"]
    consumed = live + sum(e["units"] for e in ledger if e["ts"] >= start)
    base = wk.get("baseline")
    base_ts = start
    base_pct = 0.0
    if base and start <= base["ts"] < end:
        # 申告時点の実測pctから外部消費(台帳に載らない分)をオフセットとして復元
        ledger_at_base = sum(e["units"] for e in ledger
                             if start <= e["ts"] <= base["ts"])
        external = max(0.0, base["pct"] / 100 * ceiling - ledger_at_base - live)
        consumed += external
        base_ts, base_pct = base["ts"], base["pct"]
    pct = 100.0 * consumed / ceiling
    # ペース目標: 基準点からリセット時刻にspend_targetへ直線着地
    target = wk.get("spend_target_pct", 95)
    frac = min(1.0, max(0.0, (now - base_ts) / max(1.0, end - base_ts)))
    pace = base_pct + (target - base_pct) * frac
    return pct, pace, consumed, end


def weekly_tier_from_pace(pct, pace, hard_cap, floor_pct=5.0):
    # リセット直後は経過時間がほぼ0のためpace目標も0%近辺になり、
    # 1ターン分の消費だけで「ペース超過」と誤判定してしまう。
    # pctがfloor未満のうちはペース判定そのものを免除する(残り予算に十分な余裕があるため)。
    if pct < floor_pct:
        return {"tier": 0, "name": "制限なし(リセット直後の猶予)",
                "do": "ペース判定の対象外(pctがfloor未満)。5時間窓のTIERに従う"}
    diff = pct - pace
    if pct >= hard_cap or diff > 2:
        return {"tier": 3, "name": "週次スキップ(ペース超過)",
                "do": "recordのみして即終了。次スロットでペースが回復していれば再開される"}
    if diff > -2:
        return {"tier": 2, "name": "週次ペース維持(最小)",
                "do": "x_research.py+最小ログ+コミットのみ"}
    if diff > -8:
        return {"tier": 1, "name": "週次セーブ",
                "do": "実測検証・敵対的レビュー・夜間メニューはスキップ(ペースの範囲内で標準作業)"}
    return {"tier": 0, "name": "制限なし",
            "do": "ペースに余裕あり。5時間窓のTIERに従う"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    cfg = load(CONFIG, DEFAULT_CONFIG)
    ledger = load(LEDGER, [])
    now = time.time()
    ledger = [e for e in ledger if e["ts"] >= now - RETENTION_SEC]

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown")
    baselines = load(BASELINES, {})

    if cmd == "record":
        own_full, path = own_session_units()
        delta = live_delta(sid, own_full, baselines)
        baselines[sid] = own_full
        BASELINES.write_text(json.dumps(baselines, indent=1))
        ledger.append({"ts": now, "session": sid, "units": round(delta)})
        LEDGER.write_text(json.dumps(ledger, indent=1))
        print(f"recorded +{round(delta):,} units this run for session {sid[:8]}… "
              f"(session-lifetime cumulative: {round(own_full):,}, transcript: {path})")
        return

    if cmd == "calibrate":
        # ユーザーが実際にClaude側で見えているpct(5hまたはweekly)を報告してきたとき用。
        # baseline方式(外部消費の"加算")と違い、これは自分の重み付けunits式が
        # 実際の計測とどれだけズレているかを直接ceiling_unitsの再計算で吸収する。
        which = sys.argv[2] if len(sys.argv) > 2 else "weekly"
        observed_pct = float(sys.argv[3])
        own_full, _ = own_session_units()
        live = live_delta(sid, own_full, baselines)
        if which == "weekly":
            wk = cfg["weekly"]
            start = weekly_window_start(now, wk.get("anchor", {}))
            consumed = live + sum(e["units"] for e in ledger if e["ts"] >= start)
            wk["ceiling_units"] = round(consumed / (observed_pct / 100))
            wk["ceiling_calibrated"] = True
            wk["baseline"] = {"ts": now, "pct": observed_pct,
                              "note": f"calibrateコマンドで再校正(窓内ledger実測{round(consumed):,}units基準)"}
        else:
            fh = cfg.get("five_hour_anchor")
            if fh and fh.get("anchor_ts"):
                consumed, _ = window_total_anchored(ledger, now, fh["anchor_ts"], cfg["window_hours"])
                consumed += live
            else:
                consumed = window_total(ledger, cfg["window_hours"], now) + live
            cfg["ceiling_units"] = round(consumed / (observed_pct / 100))
            cfg["ceiling_calibrated"] = True
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        print(f"{which} ceiling calibrated to "
              f"{round(cfg['weekly']['ceiling_units'] if which=='weekly' else cfg['ceiling_units']):,} "
              f"units from observed {observed_pct}% (窓内ledger実測: {round(consumed):,})")
        return

    if cmd == "limit-hit":
        which = sys.argv[2] if len(sys.argv) > 2 else "5h"
        own_full, _ = own_session_units()
        live = live_delta(sid, own_full, baselines)
        if which == "weekly":
            _, _, consumed, _ = weekly_state(ledger, cfg["weekly"], now, live)
            cfg["weekly"]["ceiling_units"] = round(consumed)
            cfg["weekly"]["ceiling_calibrated"] = True
            total = consumed
        else:
            fh = cfg.get("five_hour_anchor")
            if fh and fh.get("anchor_ts"):
                raw5, _ = window_total_anchored(ledger, now, fh["anchor_ts"], cfg["window_hours"])
                total = raw5 + live
            else:
                total = window_total(ledger, cfg["window_hours"], now) + live
            cfg["ceiling_units"] = round(total)
            cfg["ceiling_calibrated"] = True
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        print(f"{which} ceiling calibrated to {round(total):,} units")
        return

    # check
    own_full, _ = own_session_units()
    live = live_delta(sid, own_full, baselines)
    fh = cfg.get("five_hour_anchor")
    if fh and fh.get("anchor_ts"):
        raw5, w5start = window_total_anchored(ledger, now, fh["anchor_ts"], cfg["window_hours"])
        total5 = raw5 + live
        five_hour_note = f"実測アンカー校正済(次リセット {datetime.fromtimestamp(w5start + cfg['window_hours']*3600, JST):%H:%M}JST)"
    else:
        total5 = window_total(ledger, cfg["window_hours"], now) + live
        five_hour_note = "ローリング窓(実測アンカー未設定)"
    pct5 = 100.0 * total5 / cfg["ceiling_units"]

    wk = cfg.get("weekly", {})
    pctw, pace, consumedw, wend = weekly_state(ledger, wk, now, live)
    hard_cap = wk.get("hard_cap_pct", 95)

    hour = datetime.fromtimestamp(now, JST).hour
    night = cfg.get("night", {})
    nh = night.get("jst_hours", [0, 5])
    is_night = nh[0] <= hour < nh[1] and "tiers" in night
    mode = f"🌙夜間モード(JST {nh[0]}時〜{nh[1]}時)" if is_night else "☀️昼間モード"

    tier5 = pick_tier(night["tiers"] if is_night else cfg["tiers"], pct5)
    tierw = weekly_tier_from_pace(pctw, pace, hard_cap, wk.get("floor_pct", 5.0))
    # 週次 > 5時間: 厳しい方を採用
    tier = tierw if tierw["tier"] > tier5["tier"] else tier5
    limited_by = "週次制限" if tierw["tier"] > tier5["tier"] else "5時間制限"

    calib5 = "校正済" if cfg.get("ceiling_calibrated") else "未校正"
    calibw = "校正済" if wk.get("ceiling_calibrated") else "未校正"
    reset_dt = datetime.fromtimestamp(wend, JST)
    hours_left = (wend - now) / 3600
    print(f"📅 週次(リセット: {reset_dt:%m/%d %H時JST}・残り{hours_left:.0f}h): "
          f"{round(consumedw):,} / {wk['ceiling_units']:,} units = {pctw:.1f}% "
          f"({calibw}、外部消費オフセット込み)")
    print(f"   ペース目標 {pace:.1f}%(差 {pctw - pace:+.1f}pt)→ 週次TIER {tierw['tier']}")
    print(f"{mode} 直近{cfg['window_hours']}時間({five_hour_note}): {round(total5):,} / "
          f"{cfg['ceiling_units']:,} units = {pct5:.1f}% ({calib5}) "
          f"→ TIER {tier5['tier']}")
    print(f"→ 最終TIER {tier['tier']}({limited_by}が支配): "
          f"{tier['name']} — {tier['do']}")
    if is_night and tier["tier"] == 0:
        budget5 = cfg["ceiling_units"] * night.get("spend_target_pct", 90) / 100 - total5
        budgetw = wk["ceiling_units"] * min(pace + 2, hard_cap) / 100 - consumedw
        budget = min(budget5, budgetw)
        src = "週次ペース" if budgetw < budget5 else "5時間窓"
        print(f"💰 夜間の残り予算: 約{max(0, round(budget)):,} units({src}が上限) "
              f"— この予算内で夜間メニューを実行。"
              f"参考: 標準的なフル実行1回 ≈ 4,000,000〜5,000,000 units")
    sys.exit(tier["tier"])


if __name__ == "__main__":
    main()
