#!/usr/bin/env python3
"""
每日口說挑戰 — 內容自動生成腳本（Gemini 原生 YouTube 理解）
用法：
  python generate_challenges.py --videos "videoId1 videoId2 ..." --start 2026-06-01 --count 30

參數：
  --videos      YouTube 影片 ID，空格分隔（可省略 → 讀 video_ids.txt）
  --start       起始日期 YYYY-MM-DD（預設：明天）
  --count       要填充的天數（預設：30）
  --dry-run     只印出，不寫入 Supabase
  --skip-existing  跳過 Supabase 已有資料的日期
"""

import os, sys, json, argparse, textwrap, re, time, random
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    sys.exit("請先安裝依賴：pip install -r scripts/requirements.txt")

try:
    from supabase import create_client
except ImportError:
    sys.exit("請先安裝依賴：pip install -r scripts/requirements.txt")


# ── YouTube oEmbed（取標題，不需 API key） ──────────────────────────────────

def get_video_title(video_id: str) -> tuple[str, str]:
    import urllib.request
    url = f"https://www.youtube.com/oembed?url=https://youtu.be/{video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data.get("title", video_id), data.get("author_name", "YouTube")
    except Exception:
        return video_id, "YouTube"


# ── Gemini 直接讀 YouTube 影片 ─────────────────────────────────────────────

GEMINI_PROMPT = """\
你是英語口說練習教材設計師。請仔細觀看這段 YouTube 影片。

從影片中挑選 **3 個** 適合中等英語學習者（B2 程度）練習口說的句子，標準：
1. 句子完整、語意清楚，不依賴前後文也能理解
2. 包含一個以上值得學習的片語或用法
3. **長度：35–50 個英文單字**（這點非常重要，太短的句子不適合練習）
4. 分布在影片不同段落（開頭、中段、後段各一）
5. 如果原文句子太短，可以把相鄰的兩句合併成一個練習句

**時間戳格式（非常重要）**：
- 單位是「秒」，不是分鐘
- 例如：第 2 分 15 秒 = 135.0（不是 2.25）
- 例如：第 45 秒 = 45.0
- end 必須比 start 多至少 3 秒（一句話至少說 3 秒）

只輸出以下 JSON，不要任何說明文字：

```json
[
  {{
    "idx": 1,
    "start": <開始秒數，例如 45.0>,
    "end": <結束秒數，例如 52.5>,
    "text": "<完整英文句子，字數 10–25 字>",
    "zh": "<自然流暢的繁體中文翻譯>",
    "kw": [
      {{"w": "<關鍵片語>", "zh": "<中文解釋>"}},
      {{"w": "<關鍵片語2>", "zh": "<中文解釋2>"}}
    ]
  }},
  ...
]
```
"""


def analyze_video(video_id: str, api_key: str, retries: int = 3) -> list[dict]:
    """讓 Gemini 直接觀看 YouTube 影片，回傳 3 個練習句子"""
    client = genai.Client(api_key=api_key)

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai_types.Content(parts=[
                        genai_types.Part(file_data=genai_types.FileData(
                            file_uri=f"https://www.youtube.com/watch?v={video_id}",
                            mime_type="video/mp4",
                        )),
                        genai_types.Part(text=GEMINI_PROMPT),
                    ])
                ],
            )
            raw = response.text.strip()
            break
        except Exception as e:
            err = str(e)
            if attempt < retries - 1 and any(x in err for x in ["503", "UNAVAILABLE", "429", "quota"]):
                wait = 15 * (attempt + 1)
                print(f"    ⏳ Gemini 暫時無法回應，{wait}s 後重試（{attempt+1}/{retries}）…")
                time.sleep(wait)
            else:
                raise

    # 解析 JSON
    match = re.search(r"```json\s*([\s\S]+?)```", raw)
    raw_json = match.group(1).strip() if match else raw.strip("`").strip()
    sentences = json.loads(raw_json)
    for i, s in enumerate(sentences):
        s["idx"] = i + 1

    # 時間戳單位修正：若任何句子 end-start < 2 秒，很可能是以分鐘為單位
    if sentences and any((s["end"] - s["start"]) < 2.0 for s in sentences):
        print(f"    ⚠️  偵測到分鐘制時間戳，自動乘以 60")
        for s in sentences:
            s["start"] = round(s["start"] * 60, 1)
            s["end"]   = round(s["end"]   * 60, 1)

    return sentences


# ── Supabase ────────────────────────────────────────────────────────────────

def upsert_challenge(client, target_date: str, video_id: str,
                     title: str, channel: str, sentences: list):
    client.table("daily_challenges").upsert({
        "date": target_date,
        "video_id": video_id,
        "video_title": title,
        "video_channel": channel,
        "sentences": sentences,
    }).execute()


# ── 主流程 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="為每日口說挑戰 app 批量生成練習內容（Gemini 原生 YouTube 理解）",
        epilog=textwrap.dedent("""\
        範例：
          # 讀取 video_ids.txt，填充 6 月全月
          python scripts/generate_challenges.py --start 2026-06-01 --count 30

          # 直接指定影片
          python scripts/generate_challenges.py --videos "id1 id2 id3" --count 10

          # 只補空白日期
          python scripts/generate_challenges.py --start 2026-06-01 --count 30 --skip-existing
        """)
    )
    parser.add_argument("--videos", type=str, default=None, help="影片 ID 空格分隔")
    parser.add_argument("--start", type=str, default=None, help="起始日期（預設：明天）")
    parser.add_argument("--count", type=int, default=30, help="天數（預設：30）")
    parser.add_argument("--dry-run", action="store_true", help="只印出，不寫入")
    parser.add_argument("--skip-existing", action="store_true", help="跳過已有資料的日期")
    args = parser.parse_args()

    gemini_key    = os.getenv("GEMINI_API_KEY")
    supabase_url  = os.getenv("SUPABASE_URL")
    supabase_key  = os.getenv("SUPABASE_SERVICE_KEY")

    if not gemini_key:
        sys.exit("缺少 GEMINI_API_KEY，請在 scripts/.env 設定")
    if not args.dry_run and (not supabase_url or not supabase_key):
        sys.exit("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY，請在 scripts/.env 設定")

    # 影片清單
    if args.videos:
        video_ids = args.videos.split()
    else:
        ids_file = os.path.join(os.path.dirname(__file__), "video_ids.txt")
        if os.path.exists(ids_file):
            with open(ids_file) as f:
                video_ids = f.read().split()
            print(f"從 video_ids.txt 讀取 {len(video_ids)} 支影片")
        else:
            raw = input("請輸入 YouTube 影片 ID（空格分隔）：").strip()
            video_ids = raw.split()

    if not video_ids:
        sys.exit("沒有提供任何影片 ID")

    # 日期範圍
    start_date = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)
    dates = [start_date + timedelta(days=i) for i in range(args.count)]

    # 把影片隨機分配到各天（每支影片儘量只用一次）
    assigned: list[str] = []
    pool = video_ids.copy()
    random.shuffle(pool)
    for i in range(len(dates)):
        assigned.append(pool[i % len(pool)])
        if (i + 1) % len(pool) == 0:
            random.shuffle(pool)  # 每輪重新洗牌

    print(f"\n將為 {len(dates)} 天（{dates[0]} ～ {dates[-1]}）生成內容")
    print(f"影片池 {len(video_ids)} 支，隨機分配\n")

    # Supabase client
    sb = None
    existing_dates: set[str] = set()
    if not args.dry_run:
        sb = create_client(supabase_url, supabase_key)
        if args.skip_existing:
            rows = sb.table("daily_challenges").select("date").execute()
            existing_dates = {r["date"] for r in (rows.data or [])}
            if existing_dates:
                print(f"  Supabase 已有 {len(existing_dates)} 天，這些日期將跳過\n")

    # 已分析過的影片 cache（同影片只呼叫 Gemini 一次）
    cache: dict[str, dict | None] = {}

    print("正在生成每日挑戰（Gemini 直接讀取 YouTube 影片）：\n")
    for target_date, vid in zip(dates, assigned):
        date_str = str(target_date)

        if date_str in existing_dates:
            print(f"  {date_str}  — 已有資料，跳過")
            continue

        # 取得或分析影片
        if vid not in cache:
            title, channel = get_video_title(vid)
            print(f"  分析影片 {vid}  ·  {title[:50]}")
            print(f"  頻道：{channel}")
            try:
                sentences = analyze_video(vid, gemini_key)
                cache[vid] = {"title": title, "channel": channel, "sentences": sentences}
                print(f"  ✓ 選出 {len(sentences)} 句")
                time.sleep(2)  # 避免 Gemini rate limit
            except Exception as e:
                print(f"  ✗ Gemini 分析失敗：{e}")
                cache[vid] = None

        data = cache.get(vid)
        if data is None:
            print(f"  {date_str}  ✗ 跳過（影片 {vid} 無法處理）")
            continue

        print(f"  {date_str}  →  {data['title'][:50]}")
        if args.dry_run:
            for s in data["sentences"]:
                print(f"           [{s['start']}–{s['end']}s] {s['text'][:55]}")
        else:
            try:
                upsert_challenge(sb, date_str, vid,
                                 data["title"], data["channel"], data["sentences"])
                print(f"           ✓ 已寫入 Supabase")
            except Exception as e:
                print(f"           ✗ 寫入失敗：{e}")

    print("\n完成！")


if __name__ == "__main__":
    main()
