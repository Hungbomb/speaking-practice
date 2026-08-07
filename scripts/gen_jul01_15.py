#!/usr/bin/env python3
"""生成 7/01–7/15（AI 講解與多元題材交錯，約 53% AI）。
生成先存 JSON，再嘗試寫入 Supabase；失敗可用 --write-only 從 JSON 補寫。"""
import os, sys, time, json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

from generate_challenges import get_video_title, analyze_video, upsert_challenge
from supabase import create_client

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "gen_jul01_15_results.json")
WRITE_ONLY = "--write-only" in sys.argv
gemini_key = os.getenv("GEMINI_API_KEY")

# (日期, 影片ID, 類別)  —  AI 與多元題材交錯，AI 均勻分佈
TARGETS = [
    ("2026-07-01", "uO5cvkzh3P0", "AI"),   # Two Minute Papers — Real-Time AI
    ("2026-07-02", "AUmHqD0lGHo", "Gen"),  # Veritasium — Random yet Predictable
    ("2026-07-03", "Qw8qVSZEWBc", "AI"),   # IBM Technology — What Is an API?
    ("2026-07-04", "xfyKqOmr7Wk", "Gen"),  # Kurzgesagt — Your Brain Peaked at Birth
    ("2026-07-05", "7B0ydm64cV8", "AI"),   # Fireship — Who invented the internet
    ("2026-07-06", "UzN6eHeaJj4", "Gen"),  # SciShow — Bird Nests
    ("2026-07-07", "mG4SmhWyeFA", "AI"),   # Two Minute Papers — DeepSeek
    ("2026-07-08", "9IYRd5TnC5M", "Gen"),  # Real Engineering — V-22
    ("2026-07-09", "o0gkdZBtwEg", "AI"),   # IBM Technology — KV Cache / LLMs
    ("2026-07-10", "p0cLeC_2uVg", "Gen"),  # Half as Interesting — Longest Flight
    ("2026-07-11", "l72ufA-4SzE", "AI"),   # Two Minute Papers — Inside Claude's Mind
    ("2026-07-12", "2xz20qL3yJc", "Gen"),  # BBC Ideas — Your gut
    ("2026-07-13", "ML3q7Ok4hJg", "AI"),   # Fireship — Every major CS paper
    ("2026-07-14", "p0dX6C_ZSAQ", "Gen"),  # Big Think — Your inner world
    ("2026-07-15", "0GQ2RP-25gM", "AI"),   # Computerphile — AI like Clever Hans
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

print(f"生成 7/01–7/15（共 {len(TARGETS)} 天）\n", flush=True)

for date_str, vid, kind in TARGETS:
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
