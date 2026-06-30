"""Bilibili 动态监控：抓取指定 UP 主的最新动态/视频更新。"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import feedparser
import requests

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

# 预配置游戏官方 B 站账号 UID
BILIBILI_UIDS: Dict[str, Dict[str, str]] = {
    "genshin_official":      {"name": "原神",         "uid": "401742377"},
    "honkai_star_official":  {"name": "崩坏星穹铁道",  "uid": "1340190487"},
    "wuthering_official":    {"name": "鸣潮",          "uid": "1962143349"},
    "blue_archive_official": {"name": "碧蓝档案",      "uid": "521173602"},
}

_ARTICLE_API = "https://api.bilibili.com/x/space/article"
_VIDEO_API   = "https://api.bilibili.com/x/space/arc/search"

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 一周时间阈值
_ONE_WEEK_AGO = None  # 每次调用动态计算


def _get_headers() -> dict:
    """获取请求头，如有 BILIBILI_COOKIE 则附加。"""
    h = dict(_BASE_HEADERS)
    cookie = os.getenv("BILIBILI_COOKIE", "").strip()
    if cookie:
        h["Cookie"] = cookie
    return h


def _ts_to_iso(ts: int) -> str:
    """Unix 时间戳转 ISO 字符串。"""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now().isoformat()


def _within_week(iso_time: str) -> bool:
    """判断 ISO 时间是否在最近一周内。"""
    try:
        dt = datetime.fromisoformat(iso_time)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(tz=timezone.utc) - timedelta(days=7)
    except Exception:
        return True  # 解析失败时保留


def _fetch_via_rss(uid: str, name: str, limit: int) -> List[Dict[str, Any]]:
    """通过 RSS 抓取（fallback）。"""
    rss_url = f"https://rsshub.app/bilibili/user/dynamic/{uid}"
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        logger.warning("B站 RSS uid=%s 失败: %s", uid, e)
        return []

    items = []
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "") or ""
        link  = getattr(entry, "link",  "") or ""
        summary = getattr(entry, "summary", "") or ""
        published = getattr(entry, "published_parsed", None)
        if published:
            dt_iso = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
        else:
            dt_iso = datetime.now().isoformat()

        if not _within_week(dt_iso):
            continue

        items.append({
            "source": "bilibili",
            "label": f"bilibili_{uid}",
            "up_name": name,
            "title": title[:80],
            "content": summary[:500],
            "url": link,
            "time": dt_iso,
            "cover_image": "",
            "bvid": "",
        })

    return items


def _fetch_articles(uid: str, name: str, uid_key: str, limit: int) -> List[Dict[str, Any]]:
    """用 x/space/article 抓取 UP 主专栏文章（无需登录，稳定）。"""
    params = {"mid": uid, "pn": 1, "ps": limit, "sort": "publish_time"}
    try:
        resp = requests.get(_ARTICLE_API, params=params, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"code={data.get('code')}")
    except Exception as e:
        logger.warning("B站专栏 API uid=%s 失败: %s", uid, e)
        return []

    articles = (data.get("data") or {}).get("articles") or []
    items: List[Dict[str, Any]] = []
    for art in articles[:limit]:
        art_id = art.get("id") or ""
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        pub_ts = art.get("publish_time") or 0
        cover_image = (art.get("image_urls") or [""])[0] if art.get("image_urls") else ""
        url = f"https://www.bilibili.com/read/cv{art_id}" if art_id else f"https://space.bilibili.com/{uid}"
        iso_time = _ts_to_iso(pub_ts)

        if not _within_week(iso_time):
            continue

        items.append({
            "source": "bilibili",
            "label": uid_key,
            "up_name": name,
            "title": title[:80],
            "content": summary[:500],
            "url": url,
            "time": iso_time,
            "cover_image": cover_image,
            "bvid": "",
        })
    return items


def _fetch_videos(uid: str, name: str, uid_key: str, limit: int) -> List[Dict[str, Any]]:
    """用 x/space/arc/search 抓取 UP 主最新视频（需要 Cookie 或受风控影响）。"""
    params = {"mid": uid, "ps": limit, "pn": 1, "order": "pubdate", "jsonp": "jsonp"}
    try:
        resp = requests.get(_VIDEO_API, params=params, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"code={data.get('code')} msg={data.get('message','')}")
    except Exception as e:
        logger.warning("B站视频列表 API uid=%s 失败: %s", uid, e)
        return []

    vlist = (((data.get("data") or {}).get("list") or {}).get("vlist")) or []
    items: List[Dict[str, Any]] = []
    for v in vlist[:limit]:
        bvid = v.get("bvid") or ""
        aid = v.get("aid") or ""
        title = v.get("title") or ""
        description = v.get("description") or ""
        cover = v.get("pic") or ""
        if cover and cover.startswith("//"):
            cover = "https:" + cover
        created = v.get("created") or 0
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else f"https://www.bilibili.com/video/av{aid}"
        iso_time = _ts_to_iso(created)

        if not _within_week(iso_time):
            continue

        items.append({
            "source": "bilibili",
            "label": uid_key,
            "up_name": name,
            "title": title[:80],
            "content": description[:500],
            "url": url,
            "time": iso_time,
            "cover_image": cover,
            "bvid": bvid,
        })
    return items


def fetch_bilibili_dynamics(uid_key: str, uid: str, name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """抓取指定 UP 主的最新视频+专栏，只保留一周内内容。
    优先视频（需 Cookie），无结果时抓专栏文章，再降级 RSS。
    """
    items = _fetch_videos(uid, name, uid_key, limit)
    if not items:
        items = _fetch_articles(uid, name, uid_key, limit)
    if not items:
        logger.info("B站 API 无结果，降级 RSS: uid=%s", uid)
        items = _fetch_via_rss(uid, name, limit)
    return items


def run_bilibili_monitor(uid_keys: List[str], per_uid: int = 20) -> List[Dict[str, Any]]:
    """统一的 B 站动态抓取入口。"""
    if not uid_keys:
        uid_keys = list(BILIBILI_UIDS.keys())

    all_items: List[Dict[str, Any]] = []
    for key in uid_keys:
        info = BILIBILI_UIDS.get(key)
        if not info:
            continue
        logger.info("抓取 B站动态: %s (%s)", info["name"], info["uid"])
        items = fetch_bilibili_dynamics(key, info["uid"], info["name"], limit=per_uid)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY)

    all_items.sort(key=lambda x: x["time"], reverse=True)
    return all_items
