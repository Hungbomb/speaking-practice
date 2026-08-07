#!/usr/bin/env python3
"""重新生成 6/09–6/20，用 yt-dlp 字幕取得精確時間戳。
生成結果先存到 JSON（避免 Gemini 處理浪費），再嘗試寫入 Supabase。
若 Supabase 停用/DNS 失敗，之後可用 --write-only 從 JSON 一次補寫。"""
import os, sys, time, json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from generate_challenges import get_video_title, analyze_video, upsert_challenge
from supabase import create_client

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "rerun_jun09_20_results.json")
WRITE_ONLY = "--write-only" in sys.argv

gemini_key = os.getenv("GEMINI_API_KEY")

TARGETS = [
    ("2026-06-09", "GREaEG_0Xcw"),
    ("2026-06-10", "tz23G_UXCGA"),
    ("2026-06-11", "DVhEJ4Wwlf8"),
    ("2026-06-12", "hoTTWm2R-wA"),
    ("2026-06-13", "2NK0wBBZZ24"),
    ("2026-06-14", "Dkqzqw8rxXI"),
    ("2026-06-15", "ZewlcJsfbn8"),
    ("2026-06-16", "mzlZ5GF1CXI"),
    ("2026-06-17", "iJqXFUDB66k"),
    ("2026-06-18", "1PBRhm5ZnjU"),
    ("2026-06-19", "NxZOBBenmZM"),
    ("2026-06-20", "hIOW2HKgzPk"),
]


def make_sb():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))


def try_write(sb, date_str, vid, data):
    try:
        upsert_challenge(sb, date_str, vid, data["title"], data["channel"], data["sentences"])
        print(f"  {date_str} ✓ 已寫入 Supabase\n", flush=True)
        return True
    except Exception as e:
        print(f"  {date_str} ✗ 寫入失敗：{e}\n", flush=True)
        return False


# ── --write-only：從 JSON 補寫（Supabase 復活後用）────────────────────────
if WRITE_ONLY:
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)
    sb = make_sb()
    ok = 0
    print(f"從 JSON 補寫 {len(results)} 天\n", flush=True)
    for date_str, data in results.items():
        vid = data["video_id"]
        if try_write(sb, date_str, vid, data):
            ok += 1
    print(f"完成！成功 {ok}/{len(results)} 天", flush=True)
    sys.exit(0)


# ── 正常流程：生成 → 存 JSON → 嘗試寫入 ──────────────────────────────────
results = {}
if os.path.exists(RESULTS_PATH):
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)

sb = None
try:
    sb = make_sb()
except Exception:
    sb = None

cache = {}
print(f"重新生成 6/09–6/20（共 {len(TARGETS)} 天）\n", flush=True)

for date_str, vid in TARGETS:
    if vid not in cache:
        title, channel = get_video_title(vid)
        print(f"  分析 {vid}  [{channel}]  {title[:48]}", flush=True)
        try:
            sentences = analyze_video(vid, gemini_key)
            cache[vid] = {"title": title, "channel": channel, "sentences": sentences}
            print(f"  ✓ 選出 {len(sentences)} 句", flush=True)
            for s in sentences:
                wc = len(s["text"].split())
                print(f"     [{s['start']}–{s['end']}s | {wc}字] {s['text'][:58]}", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"  ✗ 失敗：{e}", flush=True)
            cache[vid] = None

    data = cache.get(vid)
    if data is None:
        print(f"  {date_str} ✗ 跳過\n", flush=True)
        continue

    # 先存 JSON（不論寫入是否成功都保留）
    results[date_str] = {"video_id": vid, **data}
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if sb is not None:
        try_write(sb, date_str, vid, data)
    else:
        print(f"  {date_str} 💾 已存 JSON（Supabase 未連線）\n", flush=True)

print("完成！", flush=True)
print(f"結果已存：{RESULTS_PATH}", flush=True)
print("Supabase 復活後執行：python3.11 rerun_jun09_20.py --write-only", flush=True)
