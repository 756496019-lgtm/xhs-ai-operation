"""微信公众号文章爬取。
通过搜狗微信搜索获取指定公众号的最新文章列表，再从 mp.weixin.qq.com 直链提取正文。
"""

import logging
import re
import time
import random
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 目标公众号配置 ──────────────────────────────────────────
WECHAT_ACCOUNTS = [
    {"id": "yxcg",   "name": "游戏茶馆",  "query": "游戏茶馆"},
    {"id": "yxpt",   "name": "游戏葡萄",  "query": "游戏葡萄"},
    {"id": "jinghe", "name": "竞核",      "query": "竞核"},
    {"id": "jijia",  "name": "机核",      "query": "机核网"},
    {"id": "gamersky_wx", "name": "游民星空", "query": "游民星空"},
]

_SOGOU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://weixin.sogou.com/",
}

_WX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.weixin.qq.com/",
}


def _sogou_search(account_query: str, num: int = 6) -> list[dict]:
    """搜狗微信搜索，返回 [{title, sogou_url, account_name, date_str}]。"""
    try:
        resp = requests.get(
            "https://weixin.sogou.com/weixin",
            params={"type": "2", "query": account_query, "ie": "utf8"},
            headers=_SOGOU_HEADERS,
            timeout=12,
        )
        if not resp.ok:
            logger.warning("搜狗返回非 200: %s", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 检查是否被验证码拦截
        if "请输入验证码" in resp.text or "sogou.com/antispider" in resp.url:
            logger.warning("搜狗触发反爬验证码，账号: %s", account_query)
            return []

        results = []
        # 搜狗微信结果可能用 .news-list li 或 .news-box li
        items = soup.select(".news-list li") or soup.select(".news-box li")
        for item in items:
            a = item.select_one("h3 a") or item.select_one(".txt-box a")
            if not a:
                continue
            href = a.get("href", "")
            if not href:
                continue
            # 补全相对 URL
            if href.startswith("/link"):
                href = "https://weixin.sogou.com" + href

            title = a.get_text(strip=True)
            account_el = item.select_one(".account, .s-p")
            account_name = account_el.get_text(strip=True) if account_el else ""
            date_el = item.select_one(".s-p, .time")
            date_str = date_el.get_text(strip=True) if date_el else ""

            results.append({
                "title":        title,
                "sogou_url":    href,
                "account_name": account_name,
                "date_str":     date_str,
            })
            if len(results) >= num:
                break

        logger.info("搜狗 [%s] 找到 %d 篇文章", account_query, len(results))
        return results
    except Exception as e:
        logger.warning("搜狗搜索失败 (%s): %s", account_query, e)
        return []


def _resolve_sogou_url(sogou_url: str) -> str:
    """将搜狗跳转链接解析为 mp.weixin.qq.com 直链。
    先尝试从 URL 参数解码，失败则跟随跳转。
    """
    try:
        parsed = urlparse(sogou_url)
        qs = parse_qs(parsed.query)
        # 搜狗有时把真实 URL 放在 url 参数里
        if "url" in qs:
            real = unquote(qs["url"][0])
            if real.startswith("http"):
                return real
        # 否则跟随跳转
        resp = requests.get(
            sogou_url,
            headers=_SOGOU_HEADERS,
            timeout=10,
            allow_redirects=True,
        )
        final = resp.url
        if "mp.weixin.qq.com" in final:
            return final
        # 有时 302 跳到微信 URL 嵌在 HTML meta refresh 里
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
        if meta:
            content = meta.get("content", "")
            m = re.search(r"url=(.+)", content, re.I)
            if m:
                return unquote(m.group(1).strip("'\""))
    except Exception as e:
        logger.warning("解析搜狗跳转失败 (%s): %s", sogou_url, e)
    return ""


def _fetch_wx_article(wx_url: str, max_chars: int = 4000) -> dict:
    """从 mp.weixin.qq.com 文章直链提取标题、正文、封面图 URL。"""
    try:
        resp = requests.get(wx_url, headers=_WX_HEADERS, timeout=15, allow_redirects=True)
        if not resp.ok:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")

        # 标题
        title_el = (soup.select_one("#activity-name")
                    or soup.select_one(".rich_media_title"))
        title = title_el.get_text(strip=True) if title_el else ""

        # 正文
        content_el = soup.select_one("#js_content")
        if not content_el:
            return {}

        # 封面图（微信图片用 data-src 懒加载）
        cover = ""
        first_img = content_el.find("img")
        if first_img:
            cover = first_img.get("data-src") or first_img.get("src") or ""

        # 清理正文
        for tag in content_el(["script", "style"]):
            tag.decompose()
        text = content_el.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return {
            "title":   title,
            "content": text[:max_chars],
            "cover":   cover,
        }
    except Exception as e:
        logger.warning("微信文章提取失败 (%s): %s", wx_url, e)
        return {}


def fetch_wechat_articles(account_ids: list[str], num_per_account: int = 5) -> list[dict]:
    """获取指定公众号的最新文章，返回标准结构供评测页使用。

    Returns:
        list of {source_id, source_name, title, url, content, content_preview, cover}
    """
    # 过滤出请求的账号
    targets = [a for a in WECHAT_ACCOUNTS if a["id"] in account_ids] if account_ids else WECHAT_ACCOUNTS

    results = []
    for i, acct in enumerate(targets):
        if i > 0:
            time.sleep(random.uniform(1.5, 2.5))  # 搜狗限速防护

        raw_list = _sogou_search(acct["query"], num=num_per_account)
        for j, item in enumerate(raw_list):
            if j > 0:
                time.sleep(random.uniform(0.5, 1.0))

            # 解析真实 URL
            wx_url = _resolve_sogou_url(item["sogou_url"])
            if not wx_url:
                logger.warning("无法解析跳转 URL: %s", item["sogou_url"])
                continue

            # 提取文章内容
            article = _fetch_wx_article(wx_url)
            if not article or len(article.get("content", "")) < 100:
                continue

            title = article["title"] or item["title"]
            results.append({
                "source_id":       acct["id"],
                "source_name":     acct["name"],
                "title":           title,
                "url":             wx_url,
                "content":         article["content"],
                "content_preview": article["content"][:200].replace("\n", " "),
                "cover":           article.get("cover", ""),
                "date_str":        item.get("date_str", ""),
                "badge":           "wechat",
            })

    return results
