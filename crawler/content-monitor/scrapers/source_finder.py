"""多来源搜索：给定游戏新闻标题，优先从知名媒体站点搜索，不足时用 Bing 兜底。"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 搜索时排除的域（本站 + 社交媒体 + 视频平台）
_EXCLUDE_DOMAINS = {
    "gamersky.com", "weibo.com", "twitter.com", "x.com",
    "youtube.com", "bilibili.com", "douyin.com", "zhihu.com",
    "tiktok.com", "instagram.com", "facebook.com",
    "baidu.com", "tieba.baidu.com", "wenku.baidu.com",
    "duckduckgo.com", "bing.com", "google.com",
}

# 优先搜索的知名游戏媒体（不含 gamersky，因为它通常是改写源头）
_PRIORITY_DOMAINS = [
    ("gcores.com",       "机核"),
    ("youxichaguan.com", "游戏茶馆"),
    ("ign.com.cn",       "IGN中文"),
    ("news.yxrb.net",    "游戏日报"),
]


def _search_ddg(query: str, max_results: int = 10) -> List[Dict]:
    """通过 DuckDuckGo HTML lite 搜索，返回 [{title, url, domain}]。"""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=_HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.select("a.result__a"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            # DDG 有时包含重定向链接，解码真实 URL
            if "uddg=" in href:
                import urllib.parse
                href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
            if not href.startswith("http") or not title:
                continue
            domain = re.sub(r"https?://(www\.)?", "", href).split("/")[0].lower()
            if any(d in domain for d in _EXCLUDE_DOMAINS):
                continue
            results.append({"title": title, "url": href, "domain": domain})
            if len(results) >= max_results:
                break
        logger.info("DuckDuckGo 搜索 '%s'，找到 %d 条候选", query, len(results))
        return results
    except Exception as e:
        logger.error("DuckDuckGo 搜索失败: %s", e)
        return []


def _search_bing(query: str, max_results: int = 10) -> List[Dict]:
    """Bing 搜索（页面抓取），返回 [{title, url, domain}]。"""
    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "zh-CN", "cc": "CN"},
            headers={**_HEADERS, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=12,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if not a:
                continue
            url = a.get("href", "")
            title = a.get_text(strip=True)
            if not url.startswith("http") or not title:
                continue
            domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0].lower()
            if any(d in domain for d in _EXCLUDE_DOMAINS):
                continue
            results.append({"title": title, "url": url, "domain": domain})
            if len(results) >= max_results:
                break
        logger.info("Bing 搜索 '%s'，找到 %d 条候选", query, len(results))
        return results
    except Exception as e:
        logger.error("Bing 搜索失败: %s", e)
        return []


def _fetch_article(url: str, max_chars: int = 1500) -> str:
    """抓取 URL 的文章正文，返回纯文本（最多 max_chars 字符）。"""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        if not resp.ok:
            return ""
        soup = BeautifulSoup(resp.content, "html.parser")  # bytes → BS4自动从meta读编码
        # 移除干扰元素
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "iframe", "noscript", "figure", "form"]):
            tag.decompose()
        # 优先取语义化容器
        body = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|article|post|entry|story", re.I))
            or soup.body
        )
        if not body:
            return ""
        text = body.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text[:max_chars]
    except Exception as e:
        logger.warning("文章抓取失败 (%s): %s", url, e)
        return ""


def _extract_images_from_html(html: str, base_url: str) -> List[Dict]:
    """从页面 HTML 中提取图片列表，过滤图标/广告/小图等噪声。"""
    from urllib.parse import urljoin

    SKIP_RE = re.compile(
        r"(icon|logo|sprite|banner|background|avatar|ad[_\-]|ads[_\-/]|pixel|spacer|"
        r"blank|loading|button|arrow|share|badge|star|rating|close|play|pause|"
        r"next|prev|nav|thumb\.gif|\.svg|\.ico)",
        re.I,
    )

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()

    images: List[Dict] = []
    seen: set = set()

    for img in soup.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or ""
        ).strip()
        if not src or src.startswith("data:"):
            continue

        src = urljoin(base_url, src)
        if not src.startswith("http") or src in seen:
            continue

        path_lower = src.split("?")[0].lower()
        if SKIP_RE.search(path_lower):
            continue
        if re.search(r"\.(gif|svg|ico)(\?|$)", path_lower):
            continue

        # 过滤 HTML 中明确标注的小图
        try:
            if int(img.get("width", 9999))  < 200: continue
            if int(img.get("height", 9999)) < 150: continue
        except (ValueError, TypeError):
            pass

        seen.add(src)
        alt = (img.get("alt") or img.get("title") or "").strip()
        images.append({"url": src, "alt": alt})

    return images


def fetch_images_from_pages(urls: List[str], max_per_page: int = 10) -> List[Dict]:
    """从多个页面 URL 提取图片，去重后返回。
    返回格式：[{"url": str, "alt": str}]
    """
    all_images: List[Dict] = []
    seen: set = set()

    for page_url in urls:
        try:
            resp = requests.get(page_url, headers=_HEADERS, timeout=10, allow_redirects=True)
            if not resp.ok:
                continue
            imgs = _extract_images_from_html(resp.text, page_url)
            for img in imgs[:max_per_page]:
                if img["url"] not in seen:
                    seen.add(img["url"])
                    all_images.append(img)
            time.sleep(0.2)
        except Exception as e:
            logger.warning("图片页面抓取失败 (%s): %s", page_url, e)

    logger.info("图片提取完成：共 %d 张（从 %d 个页面）", len(all_images), len(urls))
    return all_images


def fetch_url_content(url: str) -> Dict:
    """抓取单个 URL 的标题和正文，返回 {title, url, domain, content}。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12, allow_redirects=True)
        if not resp.ok:
            return {"title": url, "url": url, "domain": domain, "content": ""}
        soup = BeautifulSoup(resp.content, "html.parser")
        title_el = soup.find("title")
        page_title = title_el.get_text(strip=True) if title_el else url
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "iframe", "noscript", "form"]):
            tag.decompose()
        body = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|article|post|entry|story", re.I))
            or soup.body
        )
        if not body:
            return {"title": page_title, "url": url, "domain": domain, "content": ""}
        text = body.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return {"title": page_title, "url": url, "domain": domain, "content": text[:1500]}
    except Exception as e:
        logger.warning("URL 内容抓取失败 (%s): %s", url, e)
        return {"title": url, "url": url, "domain": domain, "content": ""}


def find_related_sources(title: str, num: int = 3) -> List[Dict]:
    """
    给定游戏新闻标题，优先从知名媒体站点搜索相关来源，不足时用 Bing 补充。

    返回格式：[{"title": str, "url": str, "domain": str, "content": str}]
    """
    sources: List[Dict] = []
    seen_urls: set = set()

    # Step 1: 优先从知名媒体站点搜索
    for domain, site_name in _PRIORITY_DOMAINS:
        if len(sources) >= num:
            break
        query = f"{title} site:{domain}"
        site_results = _search_ddg(query, max_results=2)
        if not site_results:
            time.sleep(0.3)
            site_results = _search_bing(query, max_results=2)
        # site_search 返回的 domain 字段可能为搜索引擎域名，修正一下
        for c in site_results:
            if len(sources) >= num:
                break
            url = c["url"]
            if url in seen_urls or domain.lstrip("www.") not in url:
                continue
            content = _fetch_article(url)
            if len(content) < 100:
                continue
            seen_urls.add(url)
            sources.append({
                "title":   c["title"],
                "url":     url,
                "domain":  domain,
                "content": content,
            })
            time.sleep(0.2)
        logger.info("[%s] 找到 %d 个有效来源", site_name, len([s for s in sources if domain in s["domain"]]))

    # Step 2: 不足时先尝试 DDG 通用搜索，再用 Bing
    if len(sources) < num:
        candidates = _search_ddg(title, max_results=12)
        if not candidates:
            time.sleep(0.5)
            candidates = _search_bing(title, max_results=12)
        for c in candidates:
            if len(sources) >= num:
                break
            if c["url"] in seen_urls:
                continue
            content = _fetch_article(c["url"])
            if len(content) < 100:
                continue
            seen_urls.add(c["url"])
            sources.append({
                "title":   c["title"],
                "url":     c["url"],
                "domain":  c["domain"],
                "content": content,
            })
            time.sleep(0.3)

    logger.info("多来源搜索完成：找到 %d 个有效来源（标题：%s）", len(sources), title)
    return sources
