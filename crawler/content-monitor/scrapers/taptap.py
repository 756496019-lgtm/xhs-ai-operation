"""TapTap 游戏动态/资讯监控：抓取指定游戏的官方动态和平台热门资讯。"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

# TapTap 游戏 app_id 映射（从游戏页面 URL 获取）
TAPTAP_GAMES: Dict[str, Dict[str, str]] = {
    "genshin":        {"name": "原神",         "app_id": "168332"},
    "honkai_star":    {"name": "崩坏星穹铁道",  "app_id": "187153"},
    "wuthering":      {"name": "鸣潮",          "app_id": "207936"},
    "blue_archive":   {"name": "碧蓝档案",      "app_id": "208524"},
    "reverse1999":    {"name": "逆水寒手游",    "app_id": "198858"},
    "arknights":      {"name": "明日方舟",      "app_id": "140533"},
}

_API_BASE = "https://www.taptap.cn/webapiv2"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "X-UA": "V=1&PN=TapTap&LANG=zh_CN&VN=3.22.0&VC=31400&OS=Android&OSV=11.0",
    "Referer": "https://www.taptap.cn/",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 简单内存缓存：30 分钟
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}
_CACHE_TTL = 1800  # 30 min


def _cached(key: str, fetch_fn):
    """带 TTL 的简单内存缓存。"""
    now = time.time()
    if key in _cache and now - _cache_ts.get(key, 0) < _CACHE_TTL:
        return _cache[key]
    result = fetch_fn()
    _cache[key] = result
    _cache_ts[key] = now
    return result


def _ts_to_iso(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now().isoformat()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "lxml").get_text(separator=" ").strip()


def fetch_taptap_game_news(game_key: str, app_id: str, game_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """抓取指定游戏的 TapTap 官方动态。"""
    def _fetch():
        url = f"{_API_BASE}/feed/v7/for-app-detail"
        params = {
            "app_id": app_id,
            "from": 0,
            "limit": limit,
        }
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("TapTap 游戏 %s 动态抓取失败: %s", game_name, e)
            return None

    data = _cached(f"taptap_game_{app_id}", _fetch)
    if not data:
        return []

    moment_list = data.get("data", {}).get("list") or []
    items: List[Dict[str, Any]] = []

    for entry in moment_list:
        moment = entry.get("moment") or {}
        moment_id = moment.get("id_str") or moment.get("id") or ""
        topic = moment.get("topic") or {}
        title = topic.get("title") or moment.get("title") or ""
        summary = topic.get("summary") or ""
        pub_ts = moment.get("publish_time") or moment.get("created_time") or 0
        sharing = moment.get("sharing") or {}
        url = sharing.get("url") or (f"https://www.taptap.cn/moment/{moment_id}" if moment_id else "https://www.taptap.cn")
        # cover 字段结构：moment.cover.image.original_url
        cover_obj = moment.get("cover") or {}
        cover_img_obj = cover_obj.get("image") or {}
        cover_url = (
            cover_img_obj.get("original_url")
            or cover_img_obj.get("url")
            or cover_obj.get("original_url")
            or cover_obj.get("url")
            or (topic.get("images") or [{}])[0].get("original_url", "") if topic.get("images") else ""
        )

        content_text = _strip_html(summary)
        if not title and not content_text:
            continue

        items.append({
            "source": "taptap",
            "label": game_key,
            "game": game_name,
            "title": (title or content_text[:60])[:80],
            "content": content_text[:500],
            "url": url,
            "time": _ts_to_iso(pub_ts),
            "cover_image": cover_url,
        })

    return items[:limit]


def fetch_taptap_all_news(limit: int = 20) -> List[Dict[str, Any]]:
    """抓取 TapTap 平台综合热门资讯（发现页）。"""
    def _fetch():
        # 尝试综合 feed 接口
        for path, params in [
            (f"{_API_BASE}/moment/v2/feed", {"from": 0, "limit": limit}),
            (f"{_API_BASE}/feed/v7/for-app-detail", {"app_id": "168332", "from": 0, "limit": limit}),
        ]:
            try:
                resp = requests.get(path, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                result = resp.json()
                if (result.get("data") or {}).get("list"):
                    return result
            except Exception as e:
                logger.warning("TapTap 综合资讯 %s 失败: %s", path, e)
        return None

    data = _cached("taptap_all_hot", _fetch)
    if not data:
        return []

    moment_list = data.get("data", {}).get("list") or []
    items: List[Dict[str, Any]] = []

    for entry in moment_list:
        moment = entry.get("moment") or {}
        moment_id = moment.get("id_str") or moment.get("id") or ""
        topic = moment.get("topic") or {}
        title = topic.get("title") or moment.get("title") or ""
        summary = topic.get("summary") or ""
        pub_ts = moment.get("publish_time") or moment.get("created_time") or 0
        sharing = moment.get("sharing") or {}
        url = sharing.get("url") or (f"https://www.taptap.cn/moment/{moment_id}" if moment_id else "https://www.taptap.cn")
        cover_obj = moment.get("cover") or {}
        cover_img_obj = cover_obj.get("image") or {}
        cover_url = (
            cover_img_obj.get("original_url")
            or cover_img_obj.get("url")
            or cover_obj.get("original_url")
            or cover_obj.get("url")
            or ""
        )
        content_text = _strip_html(summary)

        if not title and not content_text:
            continue

        items.append({
            "source": "taptap",
            "label": "taptap_hot",
            "game": "综合",
            "title": (title or content_text[:60])[:80],
            "content": content_text[:500],
            "url": url,
            "time": _ts_to_iso(pub_ts),
            "cover_image": cover_url,
        })

    return items[:limit]


def run_taptap_monitor(game_keys: List[str], per_game: int = 20) -> List[Dict[str, Any]]:
    """统一的 TapTap 抓取入口。"""
    if not game_keys:
        game_keys = list(TAPTAP_GAMES.keys())

    all_items: List[Dict[str, Any]] = []
    for key in game_keys:
        info = TAPTAP_GAMES.get(key)
        if not info:
            continue
        logger.info("抓取 TapTap: %s (app_id=%s)", info["name"], info["app_id"])
        items = fetch_taptap_game_news(key, info["app_id"], info["name"], limit=per_game)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY)

    all_items.sort(key=lambda x: x["time"], reverse=True)
    return all_items
