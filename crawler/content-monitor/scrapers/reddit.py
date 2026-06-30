"""Reddit RSS 抓取模块。"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import List, Dict, Any

import feedparser

from config import USER_AGENT, REQUEST_DELAY
from qwen_client import translate_title_to_zh

logger = logging.getLogger(__name__)

REDDIT_LABELS: Dict[str, str] = {
    "game":      "gaming",            # r/gaming
    "genshin":   "Genshin_Impact",    # 原神
    "hsr":       "HonkaiStarRail",    # 崩铁
    "arknights": "arknights",         # 明日方舟
    "wuwa":      "WutheringWaves",    # 鸣潮
    "ba":        "BlueArchive",       # 碧蓝档案
    "gacha":     "gachagaming",       # 手游抽卡
    "anime":     "anime",             # 动漫
    "otome":     "otomegames",        # 乙女游戏
}


def fetch_reddit_top_week(label: str, sub_name: str, limit_per_label: int) -> List[Dict[str, Any]]:
    """从指定 subreddit 的 top/week RSS 抓取帖子，按时间取前 N 条。"""
    url = f"https://www.reddit.com/r/{sub_name}/top/.rss?t=week&limit=100"
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
    except Exception as e:
        logger.error("r/%s RSS 请求失败: %s", sub_name, e)
        return []

    entries = list(getattr(feed, "entries", []))

    def get_dt(entry):
        t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if not t:
            return None
        return datetime(*t[:6], tzinfo=UTC)

    rows: List[Dict[str, Any]] = []
    seen_ids = set()

    for entry in entries:
        eid = getattr(entry, "id", None) or getattr(entry, "link", None)
        if not eid or eid in seen_ids:
            continue
        dt = get_dt(entry)
        if not dt:
            continue

        seen_ids.add(eid)
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""
        link = getattr(entry, "link", "") or ""
        author = getattr(entry, "author", None)

        rows.append(
            {
                "source": "reddit",
                "label": label,
                "subreddit": sub_name,
                "title": title,
                "summary": summary,
                "content": summary,
                "url": link,
                "time": dt.isoformat(),
                "author": author,
            }
        )

    rows.sort(key=lambda x: x["time"], reverse=True)
    return rows[:limit_per_label]


def run_reddit_monitor(selected_labels: List[str], per_label: int) -> List[Dict[str, Any]]:
    """统一的 Reddit 抓取入口。"""
    if not selected_labels:
        selected_labels = list(REDDIT_LABELS.keys())

    all_rows: List[Dict[str, Any]] = []

    for label in selected_labels:
        sub = REDDIT_LABELS.get(label)
        if not sub:
            continue
        logger.info("抓取 label=%s, r/%s ...", label, sub)
        rows = fetch_reddit_top_week(label, sub, per_label)

        # 并行翻译所有标题（失败则保留英文）
        def _translate(row):
            title = row.get("title") or ""
            zh = translate_title_to_zh(title)
            if zh:
                row["title_zh"] = zh
            return row

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(_translate, rows))

        all_rows.extend(rows)
        time.sleep(REQUEST_DELAY)

    all_rows.sort(key=lambda x: x["time"], reverse=True)
    return all_rows
