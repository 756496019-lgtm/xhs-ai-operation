"""微博超话监控：抓取指定话题的热门帖子。"""

import logging
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

# 微博移动端容器 API（公开话题无需登录，高频话题需要 SUB Cookie）
_MOBILE_API = "https://m.weibo.cn/api/container/getIndex"

# 预配置的二次元/女性向话题 containerid（从微博超话页面 URL 或 API 抓取）
WEIBO_TOPICS: Dict[str, Dict[str, str]] = {
    "genshin":      {"name": "原神",       "containerid": "100808ebbdcf4f5d46b359efeb4ab12eb3"},
    "honkai_star":  {"name": "崩坏星穹铁道", "containerid": "1008082a2dc1d0c29e95d2e8f4296bfcdc"},
    "wuthering":    {"name": "鸣潮",        "containerid": "100808fb60db9cdddb0a2218e6dfe9c0a6"},
    "blue_archive": {"name": "碧蓝档案",    "containerid": "1008083c57c53d35b50abebb988bc1accd"},
    "otome":        {"name": "乙女游戏",    "containerid": "100808a22d5db64ea42e04507ef6a8eff1"},
    "gacha":        {"name": "手游抽卡",    "containerid": "100808c13e66e9cd15f3f2901ab3b543bf"},
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20A362 "
        "MicroMessenger/8.0.38 WeChat/8.0.38"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://m.weibo.cn/",
    "MWeibo-Pwa": "1",
    "X-Requested-With": "XMLHttpRequest",
}


def _get_cookie() -> Optional[str]:
    """从环境变量读取微博 Cookie（可选）。"""
    return os.getenv("WEIBO_COOKIE") or None


def _clean_html(text: str) -> str:
    """去除微博正文中的 HTML 标签和多余空白。"""
    text = BeautifulSoup(text, "lxml").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    # 去掉话题标签 #xxx#
    text = re.sub(r"#[^#]+#", "", text).strip()
    return text


def _parse_weibo_time(created_at: str) -> str:
    """将微博时间字符串转为 ISO 格式。"""
    try:
        # 格式如 "Sat Mar 07 10:30:00 +0800 2026"
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return dt.isoformat()
    except Exception:
        return datetime.now().isoformat()


def fetch_weibo_topic(topic_key: str, limit: int = 20) -> List[Dict[str, Any]]:
    """抓取指定超话的热门帖子。"""
    topic = WEIBO_TOPICS.get(topic_key)
    if not topic:
        logger.warning("未知微博话题: %s", topic_key)
        return []

    containerid = topic["containerid"]
    topic_name = topic["name"]

    cookie = _get_cookie()
    if not cookie:
        logger.warning(
            "微博超话 '%s' 需要登录 Cookie（环境变量 WEIBO_COOKIE 未设置）。"
            "请在浏览器登录微博后，将 Cookie 头（含 SUB、SUBP、XSRF-TOKEN）写入 .env 文件：WEIBO_COOKIE=...",
            topic_name,
        )
        return []

    headers = dict(_HEADERS)
    headers["Cookie"] = cookie

    params = {
        "type": "hotflow",
        "containerid": containerid,
    }

    try:
        resp = requests.get(
            _MOBILE_API, params=params, headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok") != 1:
            logger.warning("微博超话 %s 返回非OK: ok=%s", topic_name, data.get("ok"))
            return []
    except Exception as e:
        logger.error("微博超话 %s 抓取失败: %s", topic_name, e)
        return []

    cards = data.get("data", {}).get("cards", [])
    # Expand card_group nesting before iterating to avoid mutation during loop
    expanded = []
    for card in cards:
        if card.get("mblog"):
            expanded.append(card)
        else:
            for sub in card.get("card_group", []):
                if sub.get("mblog"):
                    expanded.append(sub)
    items: List[Dict[str, Any]] = []

    for card in expanded:
        mblog = card.get("mblog")
        if not mblog:
            continue

        uid = mblog.get("user", {}).get("id", "")
        mid = mblog.get("mid") or mblog.get("id", "")
        raw_text = mblog.get("text") or ""
        text = _clean_html(raw_text)
        if not text or len(text) < 5:
            continue

        author = mblog.get("user", {}).get("screen_name", "")
        created_at = mblog.get("created_at", "")
        attitudes = mblog.get("attitudes_count") or 0
        reposts = mblog.get("reposts_count") or 0
        comments = mblog.get("comments_count") or 0

        # 封面图
        cover_image = ""
        pics = mblog.get("pics") or []
        if pics:
            cover_image = pics[0].get("large", {}).get("url") or pics[0].get("url", "")
        if not cover_image:
            page_info = mblog.get("page_info") or {}
            cover_image = (
                page_info.get("page_pic", {}).get("url")
                or page_info.get("pic_url")
                or ""
            )

        url = f"https://weibo.com/{uid}/{mid}" if uid and mid else "https://weibo.com"

        items.append({
            "source": "weibo",
            "label": topic_key,
            "topic": topic_name,
            "title": text[:80],
            "content": text,
            "url": url,
            "time": _parse_weibo_time(created_at),
            "author": author,
            "cover_image": cover_image,
            "score": attitudes + reposts + comments,
        })

        if len(items) >= limit:
            break

    items.sort(key=lambda x: x["score"], reverse=True)
    return items[:limit]


def run_weibo_monitor(topics: List[str], per_topic: int = 20) -> List[Dict[str, Any]]:
    """统一的微博超话抓取入口。"""
    if not topics:
        topics = list(WEIBO_TOPICS.keys())

    all_items: List[Dict[str, Any]] = []
    for topic_key in topics:
        logger.info("抓取微博超话: %s", topic_key)
        items = fetch_weibo_topic(topic_key, limit=per_topic)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY)

    all_items.sort(key=lambda x: x["time"], reverse=True)
    return all_items
