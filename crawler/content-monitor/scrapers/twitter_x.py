"""Twitter/X 热帖抓取：通过 twikit 库使用 Cookie 登录，搜索游戏/二次元话题。

依赖：pip install twikit
需要在 Cookie 弹窗中填入 Twitter Cookie（auth_token + ct0 字段）。
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 话题 → 搜索关键词映射
TWITTER_TOPICS: Dict[str, Dict[str, str]] = {
    "genshin":    {"name": "原神",          "query": "#GenshinImpact OR #原神 lang:ja OR lang:zh OR lang:en"},
    "hsr":        {"name": "崩坏星穹铁道",  "query": "#HonkaiStarRail OR #崩坏星穹铁道 lang:ja OR lang:zh OR lang:en"},
    "arknights":  {"name": "明日方舟",      "query": "#Arknights OR #明日方舟 lang:ja OR lang:zh OR lang:en"},
    "wuwa":       {"name": "鸣潮",          "query": "#WutheringWaves OR #鸣潮 lang:ja OR lang:zh OR lang:en"},
    "bluearchive":{"name": "碧蓝档案",      "query": "#BlueArchive OR #碧蓝档案 lang:ja OR lang:zh OR lang:en"},
    "anime":      {"name": "动漫",          "query": "#anime OR #二次元 lang:ja OR lang:zh OR lang:en"},
    "gaming":     {"name": "游戏",          "query": "#gaming OR #GameNews lang:en"},
}

# 简单内存缓存，避免短时间重复请求（30分钟 TTL）
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}
_CACHE_TTL = 1800


def _parse_cookie_string(cookie_str: str) -> dict:
    """解析 'key=value; key2=value2' 格式的 Cookie 字符串。"""
    result = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _build_twikit_cookies(cookie_str: str) -> dict:
    """从原始 Cookie 字符串提取 twikit 所需的关键字段。"""
    raw = _parse_cookie_string(cookie_str)
    needed = ["auth_token", "ct0", "twid", "guest_id", "kdt", "_twitter_sess"]
    return {k: raw[k] for k in needed if k in raw}


async def _search_tweets_async(query: str, limit: int, cookies: dict) -> list:
    """异步搜索推文（twikit）。"""
    try:
        from twikit import Client
    except ImportError:
        logger.error("twikit 未安装，请运行: pip install twikit")
        return []

    client = Client(language="zh-CN")

    # 通过 Cookie 字典设置认证
    try:
        # twikit 支持直接设置 cookies
        client.set_cookies(cookies)
    except Exception as e:
        logger.error("设置 Twitter Cookie 失败: %s", e)
        return []

    try:
        # 搜索最新推文（Latest 模式，按时间排序）
        tweets = await client.search_tweet(query, product="Latest", count=limit)
        return list(tweets) if tweets else []
    except Exception as e:
        logger.warning("Twitter 搜索失败 (query=%s): %s", query[:40], e)
        return []


def _tweet_to_item(tweet, topic_key: str, topic_name: str) -> Dict[str, Any]:
    """将 twikit Tweet 对象转换为统一格式。"""
    try:
        user = tweet.user
        author = getattr(user, "screen_name", "") or getattr(user, "name", "")
        text = getattr(tweet, "full_text", "") or getattr(tweet, "text", "") or ""
        tweet_id = getattr(tweet, "id", "") or ""
        created_at = getattr(tweet, "created_at", "") or ""
        favorite_count = getattr(tweet, "favorite_count", 0) or 0
        retweet_count = getattr(tweet, "retweet_count", 0) or 0

        # 解析时间
        try:
            # Twitter 时间格式: "Tue Mar 05 10:23:45 +0000 2024"
            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            iso_time = dt.isoformat()
        except Exception:
            iso_time = datetime.now(tz=timezone.utc).isoformat()

        # 封面图
        cover_image = ""
        media = getattr(tweet, "media", None) or []
        for m in media:
            m_type = getattr(m, "type", "")
            if m_type == "photo":
                cover_image = getattr(m, "media_url_https", "") or getattr(m, "url", "")
                break

        tweet_url = f"https://twitter.com/{author}/status/{tweet_id}" if tweet_id else ""

        return {
            "source": "twitter",
            "label": topic_key,
            "channel": f"Twitter·{topic_name}",
            "title": text[:80],
            "content": text[:300],
            "url": tweet_url,
            "time": iso_time,
            "cover_image": cover_image,
            "author": author,
            "likes": favorite_count,
            "retweets": retweet_count,
        }
    except Exception as e:
        logger.warning("推文解析失败: %s", e)
        return {}


def fetch_twitter_topic(topic_key: str, query: str, topic_name: str, limit: int, cookies: dict) -> List[Dict[str, Any]]:
    """抓取单个话题的热帖。"""
    cache_key = f"twitter_{topic_key}"
    now = time.time()
    if cache_key in _cache and now - _cache_ts.get(cache_key, 0) < _CACHE_TTL:
        logger.info("Twitter 话题 %s 使用缓存", topic_key)
        return _cache[cache_key]

    try:
        tweets = asyncio.run(_search_tweets_async(query, limit, cookies))
    except RuntimeError:
        # 已有 event loop（如在 Flask 中）时的处理
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tweets = loop.run_until_complete(_search_tweets_async(query, limit, cookies))
        except Exception as e:
            logger.error("Twitter 异步执行失败: %s", e)
            return []

    items = []
    for tweet in tweets:
        item = _tweet_to_item(tweet, topic_key, topic_name)
        if item:
            items.append(item)

    # 按点赞数排序
    items.sort(key=lambda x: x.get("likes", 0), reverse=True)
    result = items[:limit]

    _cache[cache_key] = result
    _cache_ts[cache_key] = now
    return result


def run_twitter_monitor(topic_keys: List[str], per_topic: int = 15) -> List[Dict[str, Any]]:
    """统一的 Twitter/X 抓取入口。

    需要环境变量 TWITTER_COOKIE 已设置（通过 Cookie 弹窗传入）。
    """
    cookie_str = os.getenv("TWITTER_COOKIE", "").strip()
    if not cookie_str:
        logger.warning("未提供 Twitter Cookie，跳过抓取。请在 Cookie 弹窗中填入 Twitter Cookie。")
        return []

    cookies = _build_twikit_cookies(cookie_str)
    if not cookies.get("auth_token"):
        logger.warning("Twitter Cookie 中缺少 auth_token，无法认证")
        return []

    if not topic_keys:
        topic_keys = list(TWITTER_TOPICS.keys())

    all_items: List[Dict[str, Any]] = []
    for key in topic_keys:
        info = TWITTER_TOPICS.get(key)
        if not info:
            continue
        logger.info("抓取 Twitter 话题: %s", info["name"])
        items = fetch_twitter_topic(key, info["query"], info["name"], per_topic, cookies)
        all_items.extend(items)
        time.sleep(2)  # 避免请求过快

    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return all_items
