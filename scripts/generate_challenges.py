#!/usr/bin/env python3
"""
每日口說挑戰 — 內容自動生成腳本
用法：
  python generate_challenges.py --videos "arj7oStGLkU eIho2S0ZahI iCvmsMzlF7o" --start 2026-07-01 --count 30

參數：
  --videos   YouTube 影片 ID，空格分隔（可省略 → 互動輸入）
  --start    起始日期，格式 YYYY-MM-DD（預設：明天）
  --count    要填充的天數（預設：30）
  --dry-run  只印出結果，不寫入 Supabase
"""

import os, sys, json, argparse, textwrap, re
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── 依賴確認 ──────────────────────────────────────────────────────────────────
try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
except ImportError:
    sys.exit("請先安裝依賴：pip install -r scripts/requirements.txt")

try:
    import google.generativeai as genai
except ImportError:
    sys.exit("請先安裝依賴：pip install -r scripts/requirements.txt")

try:
    from supabase import create_client
except ImportError:
    sys.exit("請先安裝依賴：pip install -r scripts/requirements.txt")


# ── YouTube 工具 ──────────────────────────────────────────────────────────────

def get_transcript(video_id: str) -> list[dict]:
    """取得字幕，優先英文。回傳 [{text, start, duration}, ...]"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # 優先手動英文，其次自動英文
        try:
            t = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
        except Exception:
            t = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
        return t.fetch()
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        raise RuntimeError(f"影片 {video_id} 無英文字幕：{e}")


def transcript_to_text(entries: list[dict], max_chars=8000) -> str:
    """把字幕轉成帶時間戳的純文字，截斷在 max_chars"""
    lines = []
    for e in entries:
        t = e["start"]
        mins = int(t // 60)
        secs = t % 60
        lines.append(f"[{mins:02d}:{secs:05.2f}] {e['text'].strip()}")
    full = "\n".join(lines)
    return full[:max_chars]


def get_video_title(video_id: str) -> tuple[str, str]:
    """
    用 YouTube oEmbed API 取得標題（不需要 API key）。
    回傳 (title, channel)。
    """
    import urllib.request, urllib.error
    url = f"https://www.youtube.com/oembed?url=https://youtu.be/{video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data.get("title", video_id), data.get("author_name", "YouTube")
    except Exception:
        return video_id, "YouTube"


# ── Gemini 工具 ────────────────────────────────────────────────────────────────

GEMINI_PROMPT = """\
你是英語口說練習教材設計師。以下是一段 YouTube 影片的英文字幕（含時間戳）。

請從中挑選 **3 個** 適合中等英語學習者（B2 程度）練習口說的句子，標準：
1. 句子完整、語意清楚，不依賴前後文也能理解
2. 包含一個以上值得學習的片語或用法
3. 長度適中（10–25 字）
4. 分布在影片不同段落

對每個句子，請輸出以下 JSON（只輸出 JSON，不要任何說明文字）：

```json
[
  {{
    "idx": 1,
    "start": <開始秒數，精確到小數點一位>,
    "end": <結束秒數，精確到小數點一位>,
    "text": "<完整英文句子>",
    "zh": "<自然流暢的繁體中文翻譯>",
    "kw": [
      {{"w": "<關鍵片語>", "zh": "<中文解釋>"}},
      {{"w": "<關鍵片語2>", "zh": "<中文解釋2>"}}
    ]
  }},
  ...
]
```

字幕如下：
---
{transcript}
---
"""


def ask_gemini(transcript_text: str, api_key: str) -> list[dict]:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = GEMINI_PROMPT.format(transcript=transcript_text)
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # 抓出 JSON block
    match = re.search(r"```json\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    else:
        # 嘗試直接解析
        raw = raw.strip("`").strip()

    sentences = json.loads(raw)
    # 確保 idx 正確
    for i, s in enumerate(sentences):
        s["idx"] = i + 1
    return sentences


# ── Supabase 工具 ──────────────────────────────────────────────────────────────

def upsert_challenge(client, target_date: str, video_id: str, title: str, channel: str, sentences: list):
    result = client.table("daily_challenges").upsert({
        "date": target_date,
        "video_id": video_id,
        "video_title": title,
        "video_channel": channel,
        "sentences": sentences,
    }).execute()
    return result


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="為每日口說挑戰 app 批量生成練習內容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        範例：
          # 填充未來 30 天，從三支 TED 影片中輪替
          python scripts/generate_challenges.py \\
            --videos "arj7oStGLkU eIho2S0ZahI iCvmsMzlF7o" \\
            --start 2026-07-01 --count 30

          # 只預覽，不寫入
          python scripts/generate_challenges.py \\
            --videos "arj7oStGLkU" --count 3 --dry-run
        """)
    )
    parser.add_argument("--videos", type=str, help="YouTube 影片 ID，空格分隔")
    parser.add_argument("--start", type=str, default=None, help="起始日期 YYYY-MM-DD（預設：明天）")
    parser.add_argument("--count", type=int, default=30, help="填充天數（預設：30）")
    parser.add_argument("--dry-run", action="store_true", help="只印出，不寫入 Supabase")
    args = parser.parse_args()

    # 讀取 API key
    gemini_key = os.getenv("GEMINI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not gemini_key:
        sys.exit("缺少 GEMINI_API_KEY，請在 scripts/.env 設定")
    if not args.dry_run and (not supabase_url or not supabase_key):
        sys.exit("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY，請在 scripts/.env 設定")

    # 影片清單
    if args.videos:
        video_ids = args.videos.split()
    else:
        raw = input("請輸入 YouTube 影片 ID（空格分隔）：").strip()
        video_ids = raw.split()
    if not video_ids:
        sys.exit("沒有提供任何影片 ID")

    # 日期範圍
    start_date = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)
    dates = [start_date + timedelta(days=i) for i in range(args.count)]

    print(f"\n將為 {len(dates)} 天（{dates[0]} ～ {dates[-1]}）生成內容")
    print(f"影片庫 {len(video_ids)} 支：{video_ids}\n")

    # 預先取得所有影片的字幕 & 標題（避免重複呼叫 API）
    cache: dict[str, dict] = {}
    for vid in video_ids:
        if vid in cache:
            continue
        print(f"  ▸ 取得影片資訊：{vid}")
        try:
            title, channel = get_video_title(vid)
            entries = get_transcript(vid)
            transcript_text = transcript_to_text(entries)
            print(f"    標題：{title}")
            print(f"    字幕長度：{len(transcript_text)} 字元")

            print(f"    呼叫 Gemini 選句中…")
            sentences = ask_gemini(transcript_text, gemini_key)
            print(f"    ✓ 選出 {len(sentences)} 句")

            cache[vid] = {
                "title": title,
                "channel": channel,
                "sentences": sentences,
            }
        except Exception as e:
            print(f"    ✗ 錯誤：{e}")
            cache[vid] = None

    # 建立 Supabase client（非 dry-run）
    sb = None
    if not args.dry_run:
        sb = create_client(supabase_url, supabase_key)

    # 寫入每天
    print("\n寫入每日挑戰：")
    for i, d in enumerate(dates):
        vid = video_ids[i % len(video_ids)]
        data = cache.get(vid)
        if data is None:
            print(f"  {d}  ✗ 跳過（影片 {vid} 無法處理）")
            continue

        print(f"  {d}  →  {data['title'][:50]}")
        if args.dry_run:
            print(f"         [dry-run] sentences: {[s['text'][:40]+'…' for s in data['sentences']]}")
        else:
            try:
                upsert_challenge(sb, str(d), vid, data["title"], data["channel"], data["sentences"])
                print(f"         ✓ 已寫入 Supabase")
            except Exception as e:
                print(f"         ✗ 寫入失敗：{e}")

    print("\n完成！")


if __name__ == "__main__":
    main()
