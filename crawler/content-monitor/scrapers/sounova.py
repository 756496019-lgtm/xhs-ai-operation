"""SouNova 少女星资讯抓取：通过 RSS 获取游戏/动漫/二次元新闻（繁体中文）。"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

import feedparser
import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_RSS_URL = "https://sounova.com/rss"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_time(entry) -> str:
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if t:
        try:
            return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(tz=timezone.utc).isoformat()


def _extract_cover(entry) -> str:
    # enclosure（RSS 标准图片附件）
    for enc in getattr(entry, "enclosures", []) or []:
        url = enc.get("url") or enc.get("href", "")
        if url:
            return url
    # media:thumbnail
    for thumb in getattr(entry, "media_thumbnail", []) or []:
        url = thumb.get("url", "")
        if url:
            return url
    # content:encoded 或 summary 里的第一张 <img>
    for field in ["content", "summary"]:
        raw = ""
        if field == "content":
            for c in getattr(entry, "content", []) or []:
                raw = c.get("value", "") or ""
                if raw:
                    break
        else:
            raw = getattr(entry, "summary", "") or ""
        if raw:
            soup = BeautifulSoup(raw, "lxml")
            img = soup.find("img")
            if img:
                src = img.get("src") or img.get("data-src", "")
                if src:
                    return src
    return ""


def fetch_sounova(limit: int = 20) -> List[Dict[str, Any]]:
    """通过 RSS 抓取 SouNova 少女星最新资讯。"""
    try:
        feed = feedparser.parse(_RSS_URL, request_headers=_HEADERS)
    except Exception as e:
        logger.error("SouNova RSS 抓取失败: %s", e)
        return []

    if not feed.entries:
        logger.warning("SouNova RSS 返回空列表，尝试直接请求")
        try:
            resp = requests.get(_RSS_URL, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.error("SouNova RSS 直接请求失败: %s", e)
            return []

    items = []
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "") or ""
        link  = getattr(entry, "link",  "") or ""
        if not title:
            continue

        # 规范化链接（有时指向内部 CDN）
        if link and not link.startswith("http"):
            link = "https://sounova.com" + link

        # 摘要文本
        summary_html = ""
        for c in getattr(entry, "content", []) or []:
            summary_html = c.get("value", "") or ""
            if summary_html:
                break
        if not summary_html:
            summary_html = getattr(entry, "summary", "") or ""
        content_text = BeautifulSoup(summary_html, "lxml").get_text(separator=" ").strip()

        # 分类标签 → 频道名
        tags = [t.get("term", "") for t in getattr(entry, "tags", []) or [] if t.get("term")]
        channel = "少女星·" + (tags[0] if tags else "资讯")

        items.append({
            "source": "news",
            "label": "sounova",
            "channel": channel,
            "title": title[:80],
            "content": content_text[:500],
            "url": link,
            "time": _parse_time(entry),
            "cover_image": _extract_cover(entry),
        })

    return items
