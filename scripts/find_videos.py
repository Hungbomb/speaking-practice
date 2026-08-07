#!/usr/bin/env python3
"""
從 YouTube 頻道 RSS 取得近期影片 ID
用法：python find_videos.py [--per-channel N] [--output ids.txt]
"""

import sys, re, time, argparse, urllib.request
import xml.etree.ElementTree as ET

# (顯示名稱, YouTube handle)
CHANNELS = [
    ("Vox",                    "@Vox"),
    ("Kurzgesagt",             "@kurzgesagt"),
    ("Veritasium",             "@veritasium"),
    ("SciShow",                "@SciShow"),
    ("Real Engineering",       "@RealEngineering"),
    ("Wendover Productions",   "@WendoverProductions"),
    ("Half as Interesting",    "@halfasinteresting"),
    ("Big Think",              "@bigthink"),
    ("The Economist",          "@TheEconomist"),
    ("Tom Scott",              "@TomScottGo"),
    ("Fireship",               "@Fireship"),
    ("Two Minute Papers",      "@TwoMinutePapers"),
    ("BBC Ideas",              "@BBCIdeas"),
    ("DW Documentary",         "@DWDocumentary"),
]

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS   = "http://www.youtube.com/xml/schemas/2015"

def fetch(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def get_channel_id(handle: str) -> str | None:
    """從 @handle 頁面抓 channel_id（藏在 RSS link 標籤裡）"""
    url = f"https://www.youtube.com/{handle}"
    try:
        html = fetch(url).decode("utf-8", errors="replace")
        m = re.search(r'channel_id=([A-Za-z0-9_-]{24})', html)
        return m.group(1) if m else None
    except Exception as e:
        return None

def get_videos_from_rss(channel_id: str, n: int = 5) -> list[tuple[str, str]]:
    """回傳 [(video_id, title), ...]，最多 n 筆"""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        root = ET.fromstring(fetch(url))
        results = []
        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            vid  = entry.findtext(f"{{{YT_NS}}}videoId")
            title = entry.findtext(f"{{{ATOM_NS}}}title") or vid
            if vid:
                results.append((vid, title))
            if len(results) >= n:
                break
        return results
    except Exception:
        return []

def main():
    parser = argparse.ArgumentParser(description="從頻道 RSS 抓影片 ID")
    parser.add_argument("--per-channel", type=int, default=3, help="每頻道取幾支（預設 3）")
    parser.add_argument("--output", type=str, default=None, help="輸出到檔案（可選）")
    args = parser.parse_args()

    all_ids: list[str] = []
    print(f"從 {len(CHANNELS)} 個頻道各取 {args.per_channel} 支影片\n")

    for name, handle in CHANNELS:
        print(f"  {name} ({handle})")
        cid = get_channel_id(handle)
        if not cid:
            print(f"    ✗ 無法取得 channel_id")
            time.sleep(0.5)
            continue

        videos = get_videos_from_rss(cid, args.per_channel)
        if not videos:
            print(f"    ✗ RSS 無法讀取")
        for vid, title in videos:
            print(f"    ✓ {vid}  {title[:55]}")
            all_ids.append(vid)
        time.sleep(0.8)   # 避免過快

    print(f"\n共取得 {len(all_ids)} 支影片")
    id_line = " ".join(all_ids)
    print(f"\n影片 ID 清單：\n{id_line}\n")

    if args.output:
        with open(args.output, "w") as f:
            f.write(id_line + "\n")
        print(f"已存到 {args.output}")

if __name__ == "__main__":
    main()
