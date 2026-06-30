"""搞笑/有趣向游戏内容聚合：抓取 B 站搞笑/整活视频、Reddit 游戏梗帖等。"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.bilibili.com/",
}

# 知名搞笑/整活游戏 UP 主 UID
_FUNNY_UIDS = {
    "老番茄":    "13226420",
    "敖厂长":    "2331602",
    "机智的党妹": "7458285",
    "搞笑游戏集锦": "482002963",
}

_ARTICLE_API   = "https://api.bilibili.com/x/space/article"
_VIDEO_LIST_API = "https://api.bilibili.com/x/space/arc/search"

# 搞笑内容关键词检测（用于 Reddit 帖子过滤）
MEME_PATTERNS = [
    "整活", "翻车", "笑死", "绝了", "破防", "名场面",
    "搞笑", "整蛊", "沙雕", "牛逼", "草", "裂开",
    "彩蛋", "bug", "离谱", "抽象", "笑不活",
]


def _ts_to_iso(ts: int) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now().isoformat()


def _get_bili_headers() -> dict:
    h = dict(_HEADERS)
    cookie = os.getenv("BILIBILI_COOKIE", "").strip()
    if cookie:
        h["Cookie"] = cookie
    return h


def _fetch_uid_videos(uid: str, up_name: str, limit: int) -> List[Dict[str, Any]]:
    params = {"mid": uid, "ps": limit, "pn": 1, "order": "pubdate", "jsonp": "jsonp"}
    try:
        resp = requests.get(_VIDEO_LIST_API, params=params, headers=_get_bili_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            logger.warning("B站视频列表 uid=%s code=%s msg=%s", uid, data.get("code"), data.get("message", ""))
            return []
    except Exception as e:
        logger.warning("B站 UP 主 %s 视频拉取失败: %s", up_name, e)
        return []

    vlist = (((data.get("data") or {}).get("list") or {}).get("vlist")) or []
    items = []
    for v in vlist:
        bvid = v.get("bvid") or ""
        aid = v.get("aid") or ""
        title = v.get("title") or ""
        description = v.get("description") or ""
        cover = v.get("pic") or ""
        if cover and cover.startswith("//"):
            cover = "https:" + cover
        play = v.get("play") or 0
        pubdate = v.get("created") or 0
        video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else f"https://www.bilibili.com/video/av{aid}"
        items.append({
            "source": "funny_gaming",
            "label": "bilibili_funny",
            "channel": f"B站·{up_name}",
            "title": title[:80],
            "content": description[:300] or f"播放量：{play}  作者：{up_name}",
            "url": video_url,
            "time": _ts_to_iso(pubdate),
            "cover_image": cover,
            "bvid": bvid,
            "play_count": play,
        })
    return items


def _fetch_uid_articles(uid: str, up_name: str, limit: int) -> List[Dict[str, Any]]:
    """视频 API 失效时降级抓专栏文章。"""
    params = {"mid": uid, "pn": 1, "ps": limit, "sort": "publish_time"}
    try:
        resp = requests.get(_ARTICLE_API, params=params, headers=_get_bili_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            return []
    except Exception as e:
        logger.warning("B站专栏 uid=%s 失败: %s", uid, e)
        return []

    articles = (data.get("data") or {}).get("articles") or []
    items = []
    for art in articles[:limit]:
        art_id = art.get("id") or ""
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        pub_ts = art.get("publish_time") or 0
        cover_image = (art.get("image_urls") or [""])[0] if art.get("image_urls") else ""
        url = f"https://www.bilibili.com/read/cv{art_id}" if art_id else f"https://space.bilibili.com/{uid}"
        items.append({
            "source": "funny_gaming",
            "label": "bilibili_funny",
            "channel": f"B站·{up_name}",
            "title": title[:80],
            "content": summary[:300],
            "url": url,
            "time": _ts_to_iso(pub_ts),
            "cover_image": cover_image,
            "bvid": "",
            "play_count": 0,
        })
    return items


def fetch_bilibili_funny(limit: int = 20) -> List[Dict[str, Any]]:
    """从已知搞笑游戏 UP 主账号拉取最新视频，失败时降级抓专栏文章。"""
    all_items: List[Dict[str, Any]] = []
    seen_urls: set = set()

    for up_name, uid in _FUNNY_UIDS.items():
        items_from_uid = _fetch_uid_videos(uid, up_name, min(limit, 10))
        if not items_from_uid:
            items_from_uid = _fetch_uid_articles(uid, up_name, min(limit, 5))

        for item in items_from_uid:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_items.append(item)

    all_items.sort(key=lambda x: x.get("play_count", 0), reverse=True)
    return all_items[:limit]


def fetch_reddit_gaming_memes(limit: int = 20) -> List[Dict[str, Any]]:
    """抓取 Reddit r/gaming 热帖中的搞笑/梗内容（通过 JSON API，无需 praw）。"""
    url = "https://www.reddit.com/r/gaming/hot.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; content-monitor/1.0)",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, params={"limit": limit * 2}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Reddit r/gaming 梗帖抓取失败: %s", e)
        return []

    posts = data.get("data", {}).get("children") or []
    items = []
    for post in posts:
        p = post.get("data") or {}
        title = p.get("title") or ""
        score = p.get("score") or 0
        comments = p.get("num_comments") or 0
        permalink = p.get("permalink") or ""
        thumbnail = p.get("thumbnail") or ""
        created = p.get("created_utc") or 0
        flair = (p.get("link_flair_text") or "").lower()
        is_video = p.get("is_video", False)

        funny_score = sum(1 for kw in MEME_PATTERNS if kw.lower() in title.lower())
        if score < 500 and funny_score == 0 and "meme" not in flair and "funny" not in flair:
            continue

        post_url = f"https://www.reddit.com{permalink}" if permalink else ""
        if thumbnail and not thumbnail.startswith("http"):
            thumbnail = ""

        items.append({
            "source": "funny_gaming",
            "label": "reddit_meme",
            "channel": "Reddit·r/gaming",
            "title": title[:80],
            "content": f"👍 {score}  💬 {comments}  {'🎬 视频' if is_video else '🖼 图文'}",
            "url": post_url,
            "time": _ts_to_iso(int(created)),
            "cover_image": thumbnail,
            "score": score,
        })

        if len(items) >= limit:
            break

    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items[:limit]


def fetch_bilibili_funny_multi(limit_per_kw: int = 10) -> List[Dict[str, Any]]:
    return fetch_bilibili_funny(limit=limit_per_kw * len(_FUNNY_UIDS))


def run_funny_gaming_monitor(sources: List[str], per_source: int = 20) -> List[Dict[str, Any]]:
    """统一的搞笑游戏内容抓取入口。

    sources 可选：bilibili_funny, reddit_meme（留空则全部）
    """
    if not sources:
        sources = ["bilibili_funny", "reddit_meme"]

    all_items: List[Dict[str, Any]] = []

    if "bilibili_funny" in sources:
        logger.info("抓取 B站搞笑游戏视频...")
        items = fetch_bilibili_funny_multi(limit_per_kw=per_source // 3 + 1)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY)

    if "reddit_meme" in sources:
        logger.info("抓取 Reddit 游戏梗帖...")
        items = fetch_reddit_gaming_memes(limit=per_source)
        all_items.extend(items)

    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return all_items
