#!/usr/bin/env python3
"""生成 8/01–8/15（AI 講解與多元題材交錯，約 53% AI）。
生成先存 JSON，再嘗試寫入 Supabase；失敗可用 --write-only 從 JSON 補寫。

影片全部取自 find_videos.py 抓的最新 RSS，與 6–7 月已用的 38 支零重疊。"""
import os, sys, time, json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from generate_challenges import get_video_title, analyze_video, upsert_challenge
from supabase import create_client

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "gen_aug01_15_results.json")
WRITE_ONLY = "--write-only" in sys.argv
gemini_key = os.getenv("GEMINI_API_KEY")

# (日期, 影片ID, 類別)  —  奇數日 AI、偶數日多元題材
TARGETS = [
    ("2026-08-01", "vO6SWG-jxvE", "AI"),   # Two Minute Papers — DeepMind Changed How AI Sees
    ("2026-08-02", "UiPJbxryrkU", "Gen"),  # Real Engineering — Sagrada Familia
    ("2026-08-03", "jxGJT1weu4w", "AI"),   # Fireship — Did Anthropic kill the indie hacker
    ("2026-08-04", "dzmoALgtB1Q", "Gen"),  # Wendover — Why Texas Wins
    ("2026-08-05", "Zr8KE7c5iKI", "AI"),   # The Economist — China trusts AI more than America
    ("2026-08-06", "SzM1hpnXux4", "Gen"),  # Tom Scott — hidden monorail
    ("2026-08-07", "ppQh4Tc9BmM", "AI"),   # Two Minute Papers — Billion Dollar AI Race
    ("2026-08-08", "h2wnaBny4Ig", "Gen"),  # SciShow — Where Is Love Stored in the Body
    ("2026-08-09", "YP73B9D20V4", "AI"),   # Fireship — Open-weight AI hits 2.8T params
    ("2026-08-10", "sfe0mExhnEg", "Gen"),  # Big Think — The key to better conversations
    ("2026-08-11", "gExsfWU76-Y", "AI"),   # Half as Interesting — Is AI Smarter Than a Person
    ("2026-08-12", "HZwK_wmQEZA", "Gen"),  # BBC Ideas — Wiping out all the mosquitoes
    ("2026-08-13", "bm1BjOjS7sQ", "AI"),   # Two Minute Papers — Another DeepSeek Moment
    ("2026-08-14", "VuliaG_-uao", "Gen"),  # Wendover — Why American Houses Are So Flimsy
    ("2026-08-15", "TugPBKBXIHc", "AI"),   # The Economist — China and America see AI differently
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


if WRITE_ONLY:
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)
    sb = make_sb()
    ok = sum(try_write(sb, d, v["video_id"], v) for d, v in results.items())
    print(f"完成！成功 {ok}/{len(results)} 天", flush=True)
    sys.exit(0)


results = {}
if os.path.exists(RESULTS_PATH):
    with open(RESULTS_PATH, encoding="utf-8") as f:
        results = json.load(f)

try:
    sb = make_sb()
except Exception:
    sb = None

todo = [t for t in TARGETS if t[0] not in results]
print(f"生成 8/01–8/15（共 {len(TARGETS)} 天，待處理 {len(todo)} 天）\n", flush=True)

for date_str, vid, kind in todo:
    title, channel = get_video_title(vid)
    print(f"  [{kind}] 分析 {vid}  [{channel}]  {title[:46]}", flush=True)
    try:
        sentences = analyze_video(vid, gemini_key)
        data = {"title": title, "channel": channel, "sentences": sentences}
        print(f"  ✓ 選出 {len(sentences)} 句", flush=True)
        for s in sentences:
            wc = len(s["text"].split())
            print(f"     [{s['start']}–{s['end']}s | {wc}字] {s['text'][:56]}", flush=True)
    except Exception as e:
        print(f"  {date_str} ✗ 分析失敗：{e}\n", flush=True)
        time.sleep(5)
        continue

    results[date_str] = {"video_id": vid, **data}
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if sb is not None:
        try_write(sb, date_str, vid, data)
    else:
        print(f"  {date_str} 💾 已存 JSON（Supabase 未連線）\n", flush=True)
    time.sleep(5)  # 避免 YouTube/Gemini 雙重限速

print("完成！", flush=True)
print(f"結果已存：{RESULTS_PATH}", flush=True)
print(f"成功 {len(results)}/{len(TARGETS)} 天", flush=True)
