"""多来源游戏评测搜索与正文抓取。
优先从5个知名游戏媒体爬取，不足时用 Bing 兜底。
编码处理：一律传 resp.content (bytes) 给 BeautifulSoup，让其从 <meta charset> 自动识别。
"""

import logging
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote, quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 优先爬取的知名游戏媒体（按优先顺序）
REVIEW_SOURCES = [
    {"id": "gcores",       "name": "机核",    "domain": "gcores.com"},
    {"id": "youxichaguan", "name": "游戏茶馆", "domain": "youxichaguan.com"},
    {"id": "gamersky",     "name": "游民星空", "domain": "gamersky.com"},
    {"id": "ign",          "name": "IGN中文",  "domain": "ign.com.cn"},
    {"id": "yxrb",         "name": "游戏日报", "domain": "news.yxrb.net"},
    {"id": "vgn",          "name": "游戏动力", "domain": "game.vgn.cn"},
]

# SSL 证书有问题的域名（跳过验证）
_SSL_SKIP_DOMAINS = {"game.vgn.cn"}

# 各站点正文 CSS 选择器（从精确到宽泛）
_SITE_SELECTORS = {
    "gcores.com":       [".story-content", ".markdown-styles_styles__wrapper__jzMMF",
                         ".article-body", ".content-wrapper", "article"],
    "youxichaguan.com": [".article-detail", ".detail-con", ".article-content",
                         ".post-content", "article"],
    "gamersky.com":     [".MidLcon", ".Mid2L_ctt", ".Mid2_L", ".Mid_L", ".Mid8Cont"],
    "ign.com.cn":       [".article-section", ".article-content", "#id_text", "article"],
    "news.yxrb.net":    [".article-content", ".detail-content", ".post-content",
                         ".content", "article", "main"],
    "3dmgame.com":      [".Content_L", ".dj_chinesemode", ".content", "article"],
    # CSS Modules 类名含 hash，用 *= 属性选择器匹配前缀
    "game.vgn.cn":      ['[class*="contentBox"]', '[class*="articleBlock"]',
                         '[class*="mainContent"]', "article", "main"],
}

_GENERIC_SELECTORS = ["article", ".article-content", ".content", "#content", "main"]


# ── 搜索引擎 ──────────────────────────────────────────────────

def _ddg_search(query: str, num: int = 3) -> list[dict]:
    """DuckDuckGo HTML 版搜索，返回 [{title, url}]。"""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=_HEADERS,
            timeout=12,
        )
        soup = BeautifulSoup(resp.content, "html.parser")
        results = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                href = unquote(href.split("uddg=")[-1].split("&")[0])
            if not href.startswith("http"):
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            results.append({"title": title, "url": href})
            if len(results) >= num:
                break
        return results
    except Exception as e:
        logger.warning("DDG 搜索失败 (%s): %s", query, e)
        return []


def _bing_search(query: str, num: int = 3) -> list[dict]:
    """Bing 搜索（页面抓取），返回 [{title, url}]。"""
    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "zh-CN", "cc": "CN"},
            headers={**_HEADERS, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=12,
        )
        soup = BeautifulSoup(resp.content, "html.parser")
        results = []
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if not a:
                continue
            url = a.get("href", "")
            title = a.get_text(strip=True)
            if not url.startswith("http") or not title:
                continue
            results.append({"title": title, "url": url})
            if len(results) >= num:
                break
        logger.info("Bing 搜索 '%s'，找到 %d 条", query, len(results))
        return results
    except Exception as e:
        logger.warning("Bing 搜索失败 (%s): %s", query, e)
        return []


# ── 各站专属搜索 ───────────────────────────────────────────────

def _gcores_rss_search(game_name: str, num: int = 2) -> list[dict]:
    """通过机核 RSS 订阅搜索相关文章（绕过阿里云 WAF）。
    RSS 只含最新 ~20 篇，按游戏名过滤标题；内容取 RSS description 摘要。
    """
    try:
        resp = requests.get(
            "https://www.gcores.com/rss.xml",
            headers={**_HEADERS, "Accept": "application/rss+xml, application/xml, */*"},
            timeout=12,
        )
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")
        kw_lower = game_name.lower()
        results = []
        for item in items:
            title_el = item.find("title")
            link_el  = item.find("link")
            desc_el  = item.find("description")
            if not title_el or not link_el:
                continue
            title = title_el.get_text(strip=True)
            url   = link_el.get_text(strip=True)
            # 标题或摘要包含关键词
            desc_text = BeautifulSoup(desc_el.get_text() if desc_el else "", "html.parser").get_text(strip=True)
            if game_name in title or kw_lower in title.lower() or game_name in desc_text:
                results.append({
                    "title":   title,
                    "url":     url,
                    "_rss_content": desc_text,  # 暂存摘要供后续使用
                })
            if len(results) >= num:
                break
        logger.info("机核 RSS 搜索 '%s'，找到 %d 篇", game_name, len(results))
        return results
    except Exception as e:
        logger.warning("机核 RSS 搜索失败: %s", e)
        return []


def _youxichaguan_direct_search(game_name: str, num: int = 2) -> list[dict]:
    """直接调用游戏茶馆站内搜索 /?s=KEYWORD。"""
    try:
        resp = requests.get(
            "https://youxichaguan.com/",
            params={"s": game_name},
            headers=_HEADERS,
            timeout=12,
            allow_redirects=True,
        )
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        results = []
        seen: set = set()
        for a in soup.find_all("a", href=True):
            url = a.get("href", "")
            title = a.get_text(strip=True)
            if ("youxichaguan.com/archives/" in url
                    and url not in seen and len(title) > 5):
                seen.add(url)
                results.append({"title": title, "url": url})
            if len(results) >= num:
                break
        logger.info("游戏茶馆直接搜索 '%s'，找到 %d 篇", game_name, len(results))
        return results
    except Exception as e:
        logger.warning("游戏茶馆直接搜索失败: %s", e)
        return []


def _yxrb_search(game_name: str, num: int = 2) -> list[dict]:
    """游戏日报站内搜索：GET /index.php?m=search&typeid=1&q=KEYWORD。
    文章链接为相对路径 /YYYY/MMDD/NNNN.html，自动补全为绝对 URL。
    """
    try:
        resp = requests.get(
            "http://news.yxrb.net/index.php",
            params={"m": "search", "typeid": "1", "q": game_name},
            headers=_HEADERS,
            timeout=12,
        )
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        results = []
        seen: set = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            # 文章链接格式：/YYYY/MMDD/NNNN.html 或完整 URL
            is_article = (
                re.match(r"^/\d{4}/\d+/\d+\.html$", href)
                or ("news.yxrb.net" in href and re.search(r"/\d{4}/\d+/\d+\.html", href))
            )
            if is_article and len(title) > 8 and href not in seen:
                seen.add(href)
                # 相对路径补全
                if href.startswith("/"):
                    full_url = "http://news.yxrb.net" + href
                else:
                    full_url = href
                results.append({"title": title, "url": full_url})
            if len(results) >= num:
                break
        logger.info("游戏日报搜索 '%s'，找到 %d 篇", game_name, len(results))
        return results
    except Exception as e:
        logger.warning("游戏日报搜索失败: %s", e)
        return []


def _vgn_search(game_name: str, num: int = 2) -> list[dict]:
    """游戏动力站内搜索：通过后端 API 获取最新文章，按关键词过滤标题/关键词/正文。
    官方搜索 API（Elasticsearch）当前存在 IPv6 连通性故障，改用首页文章列表接口。
    API 直接返回完整正文，存入 _rss_content 字段供 _extract_text 降级使用。
    """
    try:
        resp = requests.get(
            "https://api.atkgear.com/apiv2/v4/home/article",
            params={"pageNum": 1, "pageSize": 20},
            headers={**_HEADERS, "Accept": "application/json",
                     "Referer": "https://game.vgn.cn/"},
            timeout=12,
        )
        if not resp.ok:
            return []
        items = (resp.json().get("data") or [])
        kw_lower = game_name.lower()
        results = []
        for item in items:
            title    = str(item.get("title") or "")
            content  = str(item.get("content") or "")
            keywords = str(item.get("keywords") or "")
            if (game_name in title or kw_lower in title.lower()
                    or game_name in keywords or game_name in content[:500]):
                results.append({
                    "title":        title,
                    "url":          f"https://game.vgn.cn/article/news/{item['id']}",
                    "_rss_content": content,   # API 直接给出正文，作为降级内容
                })
            if len(results) >= num:
                break
        logger.info("游戏动力 API 搜索 '%s'，找到 %d 篇", game_name, len(results))
        return results
    except Exception as e:
        logger.warning("游戏动力 API 搜索失败: %s", e)
        return []


def _site_search(game_name: str, src: dict, num: int = 2) -> list[dict]:
    """在指定站点内搜索文章：各站优先用直接方式，失败时 DDG/Bing 兜底。"""
    domain = src["domain"]
    sid = src["id"]

    if sid == "gcores":
        return _gcores_rss_search(game_name, num)

    if sid == "youxichaguan":
        results = _youxichaguan_direct_search(game_name, num)
        if results:
            return results

    if sid == "yxrb":
        results = _yxrb_search(game_name, num)
        if results:
            return results

    if sid == "vgn":
        return _vgn_search(game_name, num)

    # 通用：DDG site: → Bing site: 兜底
    query = f"{game_name} site:{domain}"
    results = _ddg_search(query, num=num)
    if not results:
        time.sleep(0.5)
        results = _bing_search(query, num=num)
    domain_bare = domain.lstrip("www.")
    return [r for r in results if domain_bare in r.get("url", "")]


# ── 正文提取 ───────────────────────────────────────────────────

def _extract_text(url: str, rss_content: str = "", max_chars: int = 4000) -> str:
    """从 URL 提取文章正文；gcores 文章 WAF 阻止时降级使用 RSS 摘要。
    关键：传 resp.content (bytes) 给 BS4，让其从 <meta charset> 自动识别编码。
    SSL 证书过期的域名自动降级为 verify=False。
    """
    import warnings
    try:
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        domain = parsed.netloc.replace("www.", "")
        verify_ssl = domain not in _SSL_SKIP_DOMAINS

        req_kwargs = dict(
            headers={**_HEADERS, "Referer": referer},
            timeout=15,
            allow_redirects=True,
            verify=verify_ssl,
        )
        try:
            resp = requests.get(url, **req_kwargs)
        except requests.exceptions.SSLError:
            # SSL 证书问题，降级为跳过验证
            warnings.filterwarnings("ignore", message="Unverified HTTPS")
            resp = requests.get(url, **{**req_kwargs, "verify": False})
        if not resp.ok:
            # gcores 文章被 WAF 拦截，退回 RSS 摘要
            return rss_content[:max_chars] if rss_content else ""

        soup = BeautifulSoup(resp.content, "html.parser")  # bytes → meta charset 自动识别

        # 判断是否 WAF 拦截页（机核）
        if b"aliyun_waf" in resp.content and domain == "gcores.com":
            return rss_content[:max_chars] if rss_content else ""

        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        selectors = _SITE_SELECTORS.get(domain, []) + _GENERIC_SELECTORS
        el = None
        for sel in selectors:
            matches = soup.select(sel)
            if not matches:
                continue
            best = max(matches, key=lambda e: len(e.get_text(strip=True)))
            if len(best.get_text(strip=True)) > 200:
                el = best
                break

        if not el:
            el = soup.body
        if not el:
            return rss_content[:max_chars] if rss_content else ""

        text = el.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception as e:
        logger.warning("正文提取失败 (%s): %s", url, e)
        return rss_content[:max_chars] if rss_content else ""


# ── 主入口 ─────────────────────────────────────────────────────

def search_game_reviews(game_name: str, per_source: int = 2) -> list[dict]:
    """搜索多来源游戏评测：优先从5个知名媒体爬取，不足时用 Bing 兜底。

    Returns:
        list of {source_id, source_name, title, url, content, content_preview}
    """
    candidates = []
    seen_urls: set = set()

    # Step 1: 逐个优先站点搜索（间隔避免 DDG 限速）
    for i, src in enumerate(REVIEW_SOURCES):
        if i > 0:
            time.sleep(random.uniform(1.0, 2.0))
        results = _site_search(game_name, src, num=per_source)
        for r in results:
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            candidates.append({
                "source_id":       src["id"],
                "source_name":     src["name"],
                "title":           r["title"],
                "url":             r["url"],
                "_rss_content":    r.get("_rss_content", ""),
                "content":         "",
                "content_preview": "",
            })
        logger.info("[%s] 找到 %d 篇候选", src["name"], len(results))

    # Step 2: 候选不足时用 Bing 通用搜索补充
    if len(candidates) < 3:
        logger.info("候选不足，启用 Bing 通用搜索补充")
        time.sleep(1.0)
        extra = _bing_search(f"{game_name} 游戏 评测 攻略", num=6)
        for r in extra:
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            parsed = urlparse(r["url"])
            domain = parsed.netloc.replace("www.", "")
            candidates.append({
                "source_id":    "bing",
                "source_name":  domain,
                "title":        r["title"],
                "url":          r["url"],
                "_rss_content": "",
                "content":      "",
                "content_preview": "",
            })

    if not candidates:
        return []

    # Step 3: 并发抓取正文
    def _fetch(item: dict) -> dict:
        item["content"] = _extract_text(item["url"], rss_content=item.get("_rss_content", ""))
        item["content_preview"] = item["content"][:200].replace("\n", " ")
        return item

    with ThreadPoolExecutor(max_workers=6) as ex:
        final = list(ex.map(_fetch, candidates))

    # 清理临时字段，过滤正文过短的
    for r in final:
        r.pop("_rss_content", None)

    return [r for r in final if len(r["content"]) > 100]
