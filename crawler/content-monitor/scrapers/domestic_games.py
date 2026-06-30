"""国内手游资讯多源聚合：触乐、17173、手游那些事、TapTap综合。"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Dict, Any

import feedparser
import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, REQUEST_DELAY
from scrapers.taptap import fetch_taptap_all_news

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 来源配置
DOMESTIC_SOURCES = {
    "chuapp":   {"name": "触乐",     "rss": "https://www.chuapp.com/?feed=rss2"},
    "17173":    {"name": "17173",    "rss": "https://news.17173.com/rss.html"},
    "sygamer":  {"name": "手游那些事", "rss": "https://www.sygamer.cn/feed"},
    "taptap_hot": {"name": "TapTap热门", "rss": None},  # 非 RSS，用 API
}


def _parse_entry_time(entry) -> str:
    """从 feedparser entry 提取时间。"""
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if t:
        try:
            return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now().isoformat()


def _extract_image(entry) -> str:
    """尝试从 feedparser entry 提取封面图。"""
    # enclosures
    for enc in getattr(entry, "enclosures", []) or []:
        if "image" in enc.get("type", ""):
            return enc.get("href", "")
    # media_thumbnail
    for thumb in getattr(entry, "media_thumbnail", []) or []:
        url = thumb.get("url")
        if url:
            return url
    # summary 中的第一张图
    summary = getattr(entry, "summary", "") or ""
    if summary:
        soup = BeautifulSoup(summary, "lxml")
        img = soup.find("img")
        if img:
            return img.get("src", "")
    return ""


def fetch_rss_source(source_key: str, rss_url: str, source_name: str, limit: int) -> List[Dict[str, Any]]:
    """通用 RSS 抓取。"""
    try:
        feed = feedparser.parse(rss_url, request_headers={"User-Agent": _HEADERS["User-Agent"]})
    except Exception as e:
        logger.error("%s RSS 抓取失败: %s", source_name, e)
        return []

    items = []
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "") or ""
        link  = getattr(entry, "link",  "") or ""
        summary = getattr(entry, "summary", "") or ""
        content_text = BeautifulSoup(summary, "lxml").get_text(separator=" ").strip()

        if not title:
            continue

        items.append({
            "source": "domestic_games",
            "label": source_key,
            "channel": source_name,
            "title": title[:80],
            "content": content_text[:500],
            "url": link,
            "time": _parse_entry_time(entry),
            "cover_image": _extract_image(entry),
        })

    return items


def fetch_chuapp(limit: int = 20) -> List[Dict[str, Any]]:
    """触乐资讯。"""
    for rss_url in ["https://www.chuapp.com/feed", "https://chuapp.com/feed"]:
        items = fetch_rss_source("chuapp", rss_url, "触乐", limit)
        if items:
            return items
    return []


def fetch_17173(limit: int = 20) -> List[Dict[str, Any]]:
    """17173 手游新闻。"""
    # 17173 RSS
    for rss_url in [
        "https://news.17173.com/rss.html",
        "https://www.17173.com/rss/news.xml",
    ]:
        items = fetch_rss_source("17173", rss_url, "17173", limit)
        if items:
            return items

    # HTML 回退：抓首页新闻列表
    try:
        resp = requests.get("https://news.17173.com/", headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        news_items = soup.select("a[href*='/content/']")
        results = []
        seen = set()
        for a in news_items[:limit * 2]:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or not href or href in seen or len(title) < 5:
                continue
            seen.add(href)
            url = href if href.startswith("http") else f"https://news.17173.com{href}"
            results.append({
                "source": "domestic_games",
                "label": "17173",
                "channel": "17173",
                "title": title[:80],
                "content": title,
                "url": url,
                "time": datetime.now().isoformat(),
                "cover_image": "",
            })
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        logger.error("17173 HTML 回退失败: %s", e)
        return []


def fetch_sygamer(limit: int = 20) -> List[Dict[str, Any]]:
    """手游那些事。"""
    for rss_url in [
        "https://www.sygamer.cn/feed",
        "https://sygamer.cn/feed/",
    ]:
        items = fetch_rss_source("sygamer", rss_url, "手游那些事", limit)
        if items:
            return items
    return []


def fetch_taptap_hot_wrapped(limit: int = 20) -> List[Dict[str, Any]]:
    """TapTap 综合热门，适配 domestic_games 格式。"""
    raw = fetch_taptap_all_news(limit=limit)
    result = []
    for item in raw:
        result.append({
            "source": "domestic_games",
            "label": "taptap_hot",
            "channel": "TapTap热门",
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "url": item.get("url", ""),
            "time": item.get("time", ""),
            "cover_image": item.get("cover_image", ""),
        })
    return result


_FETCH_MAP = {
    "chuapp":     fetch_chuapp,
    "17173":      fetch_17173,
    "sygamer":    fetch_sygamer,
    "taptap_hot": fetch_taptap_hot_wrapped,
}


def run_domestic_games_monitor(sources: List[str], per_source: int = 20) -> List[Dict[str, Any]]:
    """统一的国内手游资讯抓取入口，并行抓取多个来源。"""
    if not sources:
        sources = list(_FETCH_MAP.keys())

    all_items: List[Dict[str, Any]] = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(fn, per_source): key
            for key, fn in _FETCH_MAP.items()
            if key in sources
        }
        for future in as_completed(future_map):
            try:
                items = future.result()
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_items.append(item)
            except Exception as e:
                key = future_map[future]
                logger.error("来源 %s 抓取异常: %s", key, e)

    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return all_items
