"""新闻聚合入口：游民星空 + SouNova 少女星。"""

import logging
import time
from datetime import date
from typing import List, Dict, Any

from config import REQUEST_DELAY
from scrapers.gamersky import run_gamersky_monitor
from scrapers.sounova import fetch_sounova

logger = logging.getLogger(__name__)

NEWS_SOURCES = {
    "gamersky": "游民星空",
    "sounova":  "少女星",
}


def run_news_monitor(
    sources: List[str],
    target_date: str = "",
    max_pages: int = 5,
    sounova_limit: int = 20,
) -> List[Dict[str, Any]]:
    """统一新闻抓取入口。

    sources: ['gamersky', 'sounova']（留空则全选）
    """
    if not sources:
        sources = list(NEWS_SOURCES.keys())

    if not target_date:
        target_date = date.today().strftime("%Y-%m-%d")

    all_items: List[Dict[str, Any]] = []

    if "gamersky" in sources:
        logger.info("抓取游民星空新闻: %s", target_date)
        items = run_gamersky_monitor(target_date, max_pages)
        # 统一 source 字段
        for item in items:
            item["source"] = "news"
        all_items.extend(items)
        time.sleep(REQUEST_DELAY)

    if "sounova" in sources:
        logger.info("抓取 SouNova 少女星资讯")
        items = fetch_sounova(limit=sounova_limit)
        all_items.extend(items)

    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return all_items
