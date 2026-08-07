#!/usr/bin/env python3
"""
每日口說挑戰 — 內容自動生成腳本
流程：yt-dlp 抓字幕 → Gemini 選句（精確時間戳）→ 無字幕時改用 Gemini 直接看影片

用法：
  python generate_challenges.py --start 2026-07-01 --count 31
  python generate_challenges.py --videos "id1 id2" --start 2026-07-01 --count 5
  python generate_challenges.py --start 2026-07-01 --count 31 --skip-existing
  python generate_challenges.py --start 2026-07-01 --count 5 --dry-run
"""

import os, sys, json, argparse, textwrap, re, time, random, subprocess, tempfile, html
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    sys.exit("請先安裝：pip install -r requirements.txt")

try:
    from supabase import create_client
except ImportError:
    sys.exit("請先安裝：pip install -r requirements.txt")


# ── YouTube oEmbed（取標題，不需 API key） ─────────────────────────────────

def get_video_title(video_id: str) -> tuple[str, str]:
    import urllib.request
    url = f"https://www.youtube.com/oembed?url=https://youtu.be/{video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data.get("title", video_id), data.get("author_name", "YouTube")
    except Exception:
        return video_id, "YouTube"


# ── yt-dlp 字幕下載與解析 ─────────────────────────────────────────────────

def vtt_ts_to_sec(ts: str) -> float:
    """HH:MM:SS.mmm → 秒"""
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def ttml_ts_to_sec(ts: str) -> float:
    """TTML 時間格式 HH:MM:SS.mmm 或 SS.mmm → 秒"""
    if ts.count(":") == 2:
        h, m, rest = ts.split(":")
        if "." in rest:
            s, ms = rest.split(".")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000
        return int(h) * 3600 + int(m) * 60 + float(rest)
    return float(ts.rstrip("s"))


def parse_ttml(path: str) -> list[dict]:
    """解析 TTML/XML 字幕，回傳 [{start, end, text}, ...]"""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    segments = []
    # Use regex to avoid XML namespace issues (ttp:profile, xml:lang etc.)
    for m in re.finditer(r'<p\b[^>]+\bbegin="([^"]+)"[^>]+\bend="([^"]+)"[^>]*>([^<]*)</p>', content):
        begin, end, text = m.group(1), m.group(2), m.group(3).strip()
        text = text.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        text = re.sub(r"\s+", " ", text).strip()
        if begin and end and text:
            try:
                segments.append({
                    "start": ttml_ts_to_sec(begin),
                    "end":   ttml_ts_to_sec(end),
                    "text":  text,
                })
            except Exception:
                pass
    return segments


def parse_vtt_words(path: str) -> list[tuple[float, str]]:
    """
    單詞層級解析：YouTube auto-generated VTT 內嵌 <HH:MM:SS.mmm><c>word</c>，
    每個字都有精確發話時刻。以時間戳去重（滾動視窗中同一字時間戳相同）。
    回傳 [(sec, word), ...] 已依時間排序。無單詞層級標籤時回傳 []。
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()

    words_by_ts: dict[float, str] = {}
    for block in re.split(r"\n{2,}", content):
        m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not m:
            continue
        cue_start = vtt_ts_to_sec(m.group(1))
        # 找含單詞層級標籤的那一行（新內容行；前一行是繰り越しの純文字）
        active = None
        for ln in block[m.end():].split("\n"):
            if not ln.strip():
                continue
            if re.search(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", ln):
                active = ln
                break
        if active is None:
            continue
        # 先頭語：第一個時間戳標籤前的純文字，賦予 cue 開始時刻
        first_tag = re.search(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", active)
        head = re.sub(r"<[^>]+>", "", active[:first_tag.start()]).strip()
        if head:
            words_by_ts.setdefault(round(cue_start, 3), head)
        # 其餘帶時間戳的字
        for wm in re.finditer(r"<(\d{2}:\d{2}:\d{2}\.\d{3})><c>\s*([^<]+?)\s*</c>", active):
            ts = round(vtt_ts_to_sec(wm.group(1)), 3)
            word = wm.group(2).strip()
            if word:
                words_by_ts.setdefault(ts, word)

    return sorted(words_by_ts.items())


def build_word_segments(flat: list[tuple[float, str]]) -> list[dict]:
    """
    從單詞流組合句子層級段落。
    start = 首字發話時刻；end = 末字之後下一字的發話時刻（自然邊界，遇長停頓時上限 +0.6s）。
    切段條件：句尾標點、停頓 > 1.2s、或超過 22 字。
    """
    if not flat:
        return []
    segments: list[dict] = []
    cur: list[str] = []
    seg_start = flat[0][0]
    for i, (ts, word) in enumerate(flat):
        cur.append(word)
        next_ts = flat[i + 1][0] if i + 1 < len(flat) else ts + 0.5
        gap = next_ts - ts
        is_end = bool(re.search(r"[.!?]$", word)) or gap > 1.2 or len(cur) >= 22
        if is_end:
            text = re.sub(r"\s+", " ", html.unescape(" ".join(cur))).strip()
            end = min(next_ts, ts + 0.6) if gap > 0.6 else next_ts
            if text:
                segments.append({"start": round(seg_start, 2), "end": round(end, 2), "text": text})
            seg_start = next_ts
            cur = []
    if cur:
        text = re.sub(r"\s+", " ", html.unescape(" ".join(cur))).strip()
        if text:
            segments.append({"start": round(seg_start, 2), "end": round(flat[-1][0] + 0.6, 2), "text": text})
    return segments


def parse_vtt_dedup(path: str) -> list[dict]:
    """
    解析 YouTube auto-generated VTT（無單詞層級標籤時的後備）。
    YouTube 用滾動視窗格式（每格只加 1 個新詞），需要去重才能還原完整文字。
    策略：清除所有 XML tag 後，找出每格相較前一格「新增」的部分。
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()

    # 先把所有 cue 的 start/end/clean_text 讀出來
    raw: list[tuple[float, float, str]] = []
    for block in re.split(r"\n{2,}", content):
        m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not m:
            continue
        start = vtt_ts_to_sec(m.group(1))
        end   = vtt_ts_to_sec(m.group(2))
        # Skip past the timestamp line (which may contain 'align:start position:0%')
        text_start = block.find('\n', m.end())
        if text_start == -1:
            continue
        text  = re.sub(r"<[^>]+>", "", block[text_start:]).strip()
        text  = re.sub(r"\s+", " ", text)
        if text:
            raw.append((start, end, text))

    if not raw:
        return []

    # 去重：找每格與前一格文字的重疊字首，只保留新增部分
    new_words_by_start: dict[float, list[str]] = {}
    for i, (start, end, text) in enumerate(raw):
        curr = text.split()
        if i == 0:
            new_words_by_start.setdefault(start, []).extend(curr)
            continue

        prev = raw[i - 1][2].split()
        # 找 curr 開頭有多少字與 prev 結尾相同（重疊部分）
        overlap = 0
        for size in range(min(len(prev), len(curr)), 0, -1):
            if prev[-size:] == curr[:size]:
                overlap = size
                break
        new = curr[overlap:]
        if new:
            new_words_by_start.setdefault(start, []).extend(new)

    # 把詞流合回段落（遇標點或停頓 > 1.5s 就切段）
    timeline = sorted(new_words_by_start.items())  # [(start_sec, [words])]
    flat: list[tuple[float, str]] = []
    for ts, ws in timeline:
        for w in ws:
            flat.append((ts, w))

    if not flat:
        return []

    segments: list[dict] = []
    seg_words: list[tuple[float, str]] = []
    seg_start = flat[0][0]

    for i, (ts, word) in enumerate(flat):
        seg_words.append((ts, word))
        next_ts = flat[i + 1][0] if i + 1 < len(flat) else ts + 2.0
        is_end  = (
            re.search(r"[.!?]$", word)
            or (next_ts - ts > 1.5)
            or len(seg_words) >= 25
        )
        if is_end:
            segments.append({
                "start": round(seg_start, 2),
                "end":   round(next_ts, 2),
                "text":  " ".join(w for _, w in seg_words),
            })
            seg_start = next_ts
            seg_words = []

    if seg_words:
        segments.append({
            "start": round(seg_start, 2),
            "end":   round(flat[-1][0] + 1.0, 2),
            "text":  " ".join(w for _, w in seg_words),
        })

    return segments


def _yt_dlp_sub(video_id: str, fmt: str, tmpdir: str, retries: int = 3) -> str | None:
    """下載單一格式字幕，回傳檔案路徑或 None。處理 429 限速重試。"""
    base = os.path.join(tmpdir, f"{video_id}.{fmt}")
    for attempt in range(retries):
        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=tv_embedded",
            "--write-auto-subs", "--write-subs",
            "--sub-lang", "en",
            "--sub-format", fmt,
            "--skip-download",
            "--no-warnings",
            "-o", base,
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return None

        if "429" in result.stderr or "Too Many Requests" in result.stderr:
            wait = 60 * (attempt + 1)  # 60s, 120s, 180s
            print(f"    ⏳ YouTube 字幕限速，{wait}s 後重試…")
            time.sleep(wait)
            continue

        found = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.startswith(video_id) and f.endswith(f".{fmt}")
        ]
        return found[0] if found else None
    return None


def download_transcript(video_id: str, retries: int = 3) -> list[dict] | None:
    """
    用 yt-dlp 下載英文字幕，回傳句子層級片段列表，或 None（無字幕）。
    優先序：
      1. VTT 單詞層級（<ts><c>word</c>，時間戳最精確，開始/結束都對得上）
      2. TTML 句子層級（手動上傳字幕無單詞標籤時）
      3. VTT 滾動視窗去重（最後手段）
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1) VTT 單詞層級 —— 首選
        vtt_path = _yt_dlp_sub(video_id, "vtt", tmpdir, retries)
        if vtt_path:
            words = parse_vtt_words(vtt_path)
            segs = build_word_segments(words)
            if len(segs) >= 10:
                print(f"    📝 字幕 (vtt 單詞層級)：{len(segs)} 個片段")
                return segs

        # 2) TTML 句子層級
        ttml_path = _yt_dlp_sub(video_id, "ttml", tmpdir, retries)
        if ttml_path:
            segs = parse_ttml(ttml_path)
            if segs:
                print(f"    📝 字幕 (ttml)：{len(segs)} 個片段")
                return segs

        # 3) VTT 去重（最後手段）
        if vtt_path:
            segs = parse_vtt_dedup(vtt_path)
            if segs:
                print(f"    📝 字幕 (vtt 去重)：{len(segs)} 個片段")
                return segs

    return None


# ── Gemini：從字幕選句（精確時間戳）─────────────────────────────────────

TRANSCRIPT_PROMPT = """\
你是英語口說練習教材設計師。以下是 YouTube 影片的字幕，格式為：
[行號] [開始秒數] 文字

從字幕中挑選 **3 個** 適合中等英語學習者（B2 程度）練習口說的句子：
1. 完整、語意清楚，不依賴前後文也能理解
2. 包含一個以上值得學習的片語或用法
3. **長度：35–50 個英文單字**（如果單一片段太短，請合併相鄰片段）
4. 分布在影片不同段落（開頭、中段、後段各一）

只輸出以下 JSON，不要任何說明文字：

```json
[
  {{
    "idx": 1,
    "seg_start": <第一個片段的行號（整數）>,
    "seg_end": <最後一個片段的行號（整數，只用一行則與 seg_start 相同）>,
    "text": "<35–50 字的完整句子>",
    "zh": "<自然繁體中文翻譯>",
    "kw": [
      {{"w": "<關鍵片語>", "zh": "<中文解釋>"}},
      {{"w": "<關鍵片語2>", "zh": "<中文解釋2>"}}
    ]
  }},
  ...
]
```
"""


def _norm_words(text: str) -> list[str]:
    """正規化為小寫、去標點的詞列（用於文字對齊）"""
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    return text.split()


def align_text_to_segments(segments: list[dict], text: str, hint: int = 0) -> tuple[float, float] | None:
    """
    把 Gemini 回傳的句子文字在字幕串裡實際定位，回傳 (start, end) 真實時刻。
    做法：建立整支影片的 (詞 → 段落起始時刻) 索引，用句首/句尾各數詞作錨點對齊。
    不受 Gemini 索引誤差影響。找不到可靠對齊時回傳 None。
    """
    target = _norm_words(text)
    if len(target) < 4:
        return None

    # 全片詞流：每個詞帶所屬段落的 start，以及該段落 index
    words: list[str] = []
    word_start: list[float] = []
    word_end: list[float] = []
    for s in segments:
        ws = _norm_words(s["text"])
        for w in ws:
            words.append(w)
            word_start.append(s["start"])
            word_end.append(s["end"])
    if not words:
        return None

    def find_all(anchor: list[str]) -> list[int]:
        """回傳 anchor（連續詞）在 words 內所有出現的起始位置"""
        k = len(anchor)
        return [i for i in range(len(words) - k + 1) if words[i:i + k] == anchor]

    def closest(positions: list[int], expected: int) -> int:
        return min(positions, key=lambda p: abs(p - expected)) if positions else -1

    head = target[:4]
    tail = target[-4:]
    # hint 對應的詞位置（用來就近挑選，避免重複片語誤配）
    hint_word = sum(len(_norm_words(segments[j]["text"])) for j in range(min(hint, len(segments))))

    # 句首錨點：挑最接近 hint 的出現點
    hi = closest(find_all(head), hint_word)
    if hi < 0:
        return None
    # 句尾錨點：預期落在 hi + len(target) 附近，挑最接近該處者（避免誤配到後段重複片語）
    expected_tail = hi + len(target) - len(tail)
    tail_positions = [p for p in find_all(tail) if p >= hi]
    ti = closest(tail_positions, expected_tail)
    if ti < 0:
        ti = min(hi + len(target) - 1, len(words) - 1)  # 找不到就用字數估末端
    ti_end = min(ti + len(tail) - 1, len(words) - 1)

    start = word_start[hi]
    end   = word_end[ti_end]

    # 上限：跨度明顯過長（慢於約 65 wpm）代表錨點誤配，改用字數估算合理長度
    wc = len(target)
    if end - start > wc * 0.9:
        end = start + wc * 0.4
    if end <= start:
        return None
    return (round(start, 1), round(end, 1))


def analyze_from_transcript(segments: list[dict], api_key: str, retries: int = 3) -> list[dict]:
    """Gemini 讀字幕文字選出 3 句，回傳含真實時間戳的結果"""
    client = genai.Client(api_key=api_key)

    # 送出整支影片的段落（單詞層級段落較多，上限放寬以涵蓋後段）
    lines = [f"[{i:03d}] [{s['start']:.1f}s] {s['text']}" for i, s in enumerate(segments[:1200])]
    full_prompt = "字幕：\n\n" + "\n".join(lines) + "\n\n" + TRANSCRIPT_PROMPT

    raw = ""
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[genai_types.Content(parts=[genai_types.Part(text=full_prompt)])],
            )
            raw = resp.text.strip()
            break
        except Exception as e:
            err = str(e)
            if attempt < retries - 1 and any(x in err for x in ["503", "UNAVAILABLE", "429", "quota", "disconnected", "Connection"]):
                wait = 15 * (attempt + 1)
                print(f"    ⏳ Gemini 暫時無法回應，{wait}s 後重試（{attempt+1}/{retries}）…")
                time.sleep(wait)
            else:
                raise

    match = re.search(r"```json\s*([\s\S]+?)```", raw)
    raw_json = match.group(1).strip() if match else raw.strip("`").strip()
    result = json.loads(raw_json)

    n = len(segments)
    for i, r in enumerate(result):
        r["idx"] = i + 1
        s_idx = max(0, min(int(r.pop("seg_start")), n - 1))
        e_idx = max(0, min(int(r.pop("seg_end")),   n - 1))
        if e_idx < s_idx:
            s_idx, e_idx = e_idx, s_idx

        # 優先：用 Gemini 回傳的文字在字幕串裡實際定位，取真實時刻（不受索引誤差影響）
        aligned = align_text_to_segments(segments, r.get("text", ""), hint=s_idx)
        if aligned:
            r["start"], r["end"] = aligned
        else:
            r["start"] = round(segments[s_idx]["start"], 1)
            r["end"]   = round(segments[e_idx]["end"],   1)

        # 安全網：僅在時長明顯被切斷時（快於約 330 wpm，物理上不可能）才補正
        wc = len(r.get("text", "").split())
        if wc and r["end"] - r["start"] < wc * 0.18:
            r["end"] = round(r["start"] + wc * 0.33, 1)

    return result


# ── Gemini Fallback：直接看影片（時間戳較不精確）────────────────────────

VIDEO_PROMPT = """\
你是英語口說練習教材設計師。請仔細觀看這段 YouTube 影片。

從影片中挑選 **3 個** 適合中等英語學習者（B2 程度）練習口說的句子：
1. 完整、語意清楚，不依賴前後文也能理解
2. 包含一個以上值得學習的片語或用法
3. **長度：35–50 個英文單字**（如果一句話太短，可把相鄰句子合併）
4. 分布在影片不同段落（開頭、中段、後段各一）

**時間戳格式（非常重要）**：
- 單位是「秒」，不是分鐘
- 例如：第 2 分 15 秒 = 135.0（不是 2.25）
- end 必須比 start 多至少 5 秒

只輸出以下 JSON，不要任何說明文字：

```json
[
  {{
    "idx": 1,
    "start": <開始秒數，例如 45.0>,
    "end": <結束秒數，例如 58.0>,
    "text": "<35–50 字的完整句子>",
    "zh": "<自然繁體中文翻譯>",
    "kw": [
      {{"w": "<關鍵片語>", "zh": "<中文解釋>"}},
      {{"w": "<關鍵片語2>", "zh": "<中文解釋2>"}}
    ]
  }},
  ...
]
```
"""


def analyze_from_video(video_id: str, api_key: str, retries: int = 3) -> list[dict]:
    """Fallback：Gemini 直接看影片（用於沒有字幕的影片）"""
    client = genai.Client(api_key=api_key)

    raw = ""
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[genai_types.Content(parts=[
                    genai_types.Part(file_data=genai_types.FileData(
                        file_uri=f"https://www.youtube.com/watch?v={video_id}",
                        mime_type="video/mp4",
                    )),
                    genai_types.Part(text=VIDEO_PROMPT),
                ])],
            )
            raw = resp.text.strip()
            break
        except Exception as e:
            err = str(e)
            if attempt < retries - 1 and any(x in err for x in ["503", "UNAVAILABLE", "429", "quota", "disconnected", "Connection"]):
                wait = 15 * (attempt + 1)
                print(f"    ⏳ Gemini 暫時無法回應，{wait}s 後重試（{attempt+1}/{retries}）…")
                time.sleep(wait)
            else:
                raise

    match = re.search(r"```json\s*([\s\S]+?)```", raw)
    raw_json = match.group(1).strip() if match else raw.strip("`").strip()
    result = json.loads(raw_json)

    for i, r in enumerate(result):
        r["idx"] = i + 1

    # 偵測分鐘制時間戳，自動修正
    if result and any((r["end"] - r["start"]) < 2.0 for r in result):
        print("    ⚠️  偵測到分鐘制時間戳，自動乘以 60")
        for r in result:
            r["start"] = round(r["start"] * 60, 1)
            r["end"]   = round(r["end"]   * 60, 1)

    return result


def analyze_video(video_id: str, api_key: str) -> list[dict]:
    """主入口：先嘗試字幕，無字幕才用 Gemini 看影片"""
    segments = download_transcript(video_id)
    if segments:
        return analyze_from_transcript(segments, api_key)
    print("    🎬 無字幕，改用 Gemini 直接看影片")
    return analyze_from_video(video_id, api_key)


# ── Supabase ──────────────────────────────────────────────────────────────

def upsert_challenge(client, target_date: str, video_id: str,
                     title: str, channel: str, sentences: list):
    client.table("daily_challenges").upsert({
        "date":          target_date,
        "video_id":      video_id,
        "video_title":   title,
        "video_channel": channel,
        "sentences":     sentences,
    }).execute()


# ── 主流程 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="為每日口說挑戰 app 批量生成練習內容",
        epilog=textwrap.dedent("""\
        範例：
          python generate_challenges.py --start 2026-07-01 --count 31
          python generate_challenges.py --start 2026-07-01 --count 31 --skip-existing
          python generate_challenges.py --videos "id1 id2" --start 2026-07-01 --count 2 --dry-run
        """)
    )
    parser.add_argument("--videos",        type=str, default=None)
    parser.add_argument("--start",         type=str, default=None)
    parser.add_argument("--count",         type=int, default=30)
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    gemini_key   = os.getenv("GEMINI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not gemini_key:
        sys.exit("缺少 GEMINI_API_KEY")
    if not args.dry_run and (not supabase_url or not supabase_key):
        sys.exit("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY")

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
            video_ids = input("請輸入影片 ID（空格分隔）：").strip().split()

    if not video_ids:
        sys.exit("沒有提供影片 ID")

    # 日期範圍
    start_date = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)
    dates = [start_date + timedelta(days=i) for i in range(args.count)]

    # 把影片隨機分配（每支儘量只用一次，每輪重新洗牌）
    assigned: list[str] = []
    pool = video_ids.copy()
    random.shuffle(pool)
    for i in range(len(dates)):
        assigned.append(pool[i % len(pool)])
        if (i + 1) % len(pool) == 0:
            random.shuffle(pool)

    print(f"\n將為 {len(dates)} 天（{dates[0]} ～ {dates[-1]}）生成內容")
    print(f"影片池 {len(video_ids)} 支，隨機分配\n")

    sb = None
    existing_dates: set[str] = set()
    if not args.dry_run:
        sb = create_client(supabase_url, supabase_key)
        if args.skip_existing:
            rows = sb.table("daily_challenges").select("date").execute()
            existing_dates = {r["date"] for r in (rows.data or [])}
            if existing_dates:
                print(f"  Supabase 已有 {len(existing_dates)} 天，這些日期將跳過\n")

    # 已分析過的影片 cache
    cache: dict[str, dict | None] = {}

    print("正在生成每日挑戰：\n")
    for target_date, vid in zip(dates, assigned):
        date_str = str(target_date)
        if date_str in existing_dates:
            print(f"  {date_str}  — 已有資料，跳過")
            continue

        if vid not in cache:
            title, channel = get_video_title(vid)
            print(f"  分析影片 {vid}  ·  {title[:55]}")
            print(f"  頻道：{channel}")
            try:
                sentences = analyze_video(vid, gemini_key)
                cache[vid] = {"title": title, "channel": channel, "sentences": sentences}
                print(f"  ✓ 選出 {len(sentences)} 句")
                time.sleep(5)  # 避免 Gemini + YouTube 雙重限速
            except Exception as e:
                print(f"  ✗ 分析失敗：{e}")
                cache[vid] = None

        data = cache.get(vid)
        if data is None:
            print(f"  {date_str}  ✗ 跳過（影片 {vid} 無法處理）")
            continue

        print(f"  {date_str}  →  {data['title'][:55]}")
        if args.dry_run:
            for s in data["sentences"]:
                wc = len(s["text"].split())
                print(f"           [{s['start']}–{s['end']}s | {wc}字] {s['text'][:60]}")
        else:
            try:
                upsert_challenge(sb, date_str, vid,
                                 data["title"], data["channel"], data["sentences"])
                print("           ✓ 已寫入 Supabase")
            except Exception as e:
                print(f"           ✗ 寫入失敗：{e}")

    print("\n完成！")


if __name__ == "__main__":
    main()
