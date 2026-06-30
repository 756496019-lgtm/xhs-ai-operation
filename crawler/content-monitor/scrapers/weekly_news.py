"""游戏行业周报新闻爬虫：36kr / gamelook / 游戏茶馆"""

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

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


# ─────────────────── 工具函数 ───────────────────

def _is_within_days(dt: datetime, days: int) -> bool:
    """判断 datetime 是否在最近 N 天内（含今天）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return dt >= cutoff


def _parse_relative_time(s: str) -> datetime:
    """
    解析「3小时前」「1天前」「2分钟前」「刚刚」等相对时间字符串。
    返回 UTC datetime。
    """
    now = datetime.now(tz=timezone.utc)
    if not s:
        return now
    s = s.strip()
    m = re.search(r'(\d+)\s*小时前', s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r'(\d+)\s*天前', s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r'(\d+)\s*分钟前', s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    if '刚刚' in s or 'just' in s.lower():
        return now
    # 尝试 yyyy-mm-dd 或 mm-dd 格式
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except Exception:
            pass
    m = re.search(r'(\d{2})-(\d{2})', s)
    if m:
        try:
            year = now.year
            month, day = int(m.group(1)), int(m.group(2))
            return datetime(year, month, day, tzinfo=timezone.utc)
        except Exception:
            pass
    return now


# ─────────────────── gamelook ───────────────────

def fetch_gamelook(days: int = 7, limit: int = 30) -> List[Dict[str, Any]]:
    """
    爬取 gamelook.com.cn 首页文章列表。
    只返回最近 days 天内的新闻。
    """
    results = []
    try:
        resp = requests.get("http://www.gamelook.com.cn/", headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("li.item")
        for item in items[:limit * 2]:
            # 从 img a 的 title 属性或 href 取标题和链接
            img_a = item.select_one("div.item-img a[title]")
            title = (img_a.get("title", "") if img_a else "").strip()
            href = (img_a.get("href", "") if img_a else "").strip()

            if not title or not href:
                # 备用：找第一个 a[href*=gamelook]
                for a in item.select("a"):
                    h = a.get("href", "")
                    if "gamelook.com.cn" in h and "/20" in h:
                        title = a.get("title") or a.get_text(strip=True)
                        href = h
                        break

            if not title or not href:
                continue

            # 时间
            time_el = item.select_one("time, .date, .post-date")
            time_str = time_el.get_text(strip=True) if time_el else ""
            pub_dt = _parse_relative_time(time_str) if time_str else datetime.now(tz=timezone.utc)

            if not _is_within_days(pub_dt, days):
                continue

            # 封面图
            img_el = item.select_one("img[data-original]")
            cover = img_el.get("data-original", "") if img_el else ""
            if not cover:
                img_el2 = item.select_one("img[src]")
                cover = img_el2.get("src", "") if img_el2 else ""

            # 摘要
            summary_el = item.select_one("p.desc, .summary, .excerpt")
            summary = summary_el.get_text(strip=True) if summary_el else ""

            results.append({
                "source": "weekly_news",
                "label": "gamelook",
                "channel": "GameLook",
                "title": title[:120],
                "content": summary[:500],
                "url": href,
                "time": pub_dt.isoformat(),
                "cover_image": cover,
            })

            if len(results) >= limit:
                break

    except Exception as e:
        logger.error("gamelook 抓取失败: %s", e)

    logger.info("gamelook: 抓取到 %d 条新闻", len(results))
    return results


# ─────────────────── 游戏茶馆 ───────────────────

def fetch_youxichaguan(days: int = 7, limit: int = 30) -> List[Dict[str, Any]]:
    """
    爬取游戏茶馆 youxichaguan.com 首页文章列表。
    """
    results = []
    try:
        resp = requests.get("https://www.youxichaguan.com/", headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen = set()
        for h3 in soup.select("h3"):
            title = h3.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # 找链接
            a = h3.select_one("a")
            if not a:
                parent = h3.find_parent()
                a = parent.select_one("a") if parent else None
            if not a:
                # 向上找
                parent = h3.find_parent("article") or h3.find_parent(class_=True)
                a = parent.select_one("a") if parent else None

            href = a.get("href", "").strip() if a else ""
            if not href or href in seen:
                continue
            seen.add(href)
            if not href.startswith("http"):
                href = "https://www.youxichaguan.com" + href

            # 找时间
            container = h3.find_parent("article") or h3.find_parent(class_=True) or h3.parent
            time_el = container.select_one("time, .date, .post-date, .entry-date") if container else None
            time_str = time_el.get_text(strip=True) if time_el else ""
            pub_dt = _parse_relative_time(time_str)

            if not _is_within_days(pub_dt, days):
                continue

            # 封面图
            img_el = container.select_one("img") if container else None
            cover = img_el.get("src", "") or img_el.get("data-src", "") if img_el else ""

            # 摘要
            p_el = container.select_one("p.excerpt, p.summary, .entry-summary, p") if container else None
            summary = ""
            if p_el:
                t = p_el.get_text(strip=True)
                if t != title and len(t) > 10:
                    summary = t[:400]

            results.append({
                "source": "weekly_news",
                "label": "youxichaguan",
                "channel": "游戏茶馆",
                "title": title[:120],
                "content": summary,
                "url": href,
                "time": pub_dt.isoformat(),
                "cover_image": cover,
            })

            if len(results) >= limit:
                break

    except Exception as e:
        logger.error("游戏茶馆抓取失败: %s", e)

    logger.info("游戏茶馆: 抓取到 %d 条新闻", len(results))
    return results


# ─────────────────── 36kr (Playwright) ───────────────────

def _get_profile_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "playwright_chrome_profile"
    )


_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--lang=zh-CN",
]
_STEALTH_INIT = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
)


def fetch_36kr(days: int = 7, limit: int = 30) -> List[Dict[str, Any]]:
    """
    用 Playwright persistent Chrome profile 爬取 36kr 游戏圈文章。
    URL: https://36kr.com/motif/327687553025
    """
    results = []
    try:
        from playwright.sync_api import sync_playwright
        profile_dir = _get_profile_dir()
        os.makedirs(profile_dir, exist_ok=True)

        with sync_playwright() as pw:
            try:
                ctx = pw.chromium.launch_persistent_context(
                    profile_dir, channel="chrome", headless=False,
                    args=_STEALTH_ARGS,
                    ignore_default_args=["--enable-automation"],
                    viewport={"width": 1280, "height": 800},
                )
            except Exception:
                ctx = pw.chromium.launch_persistent_context(
                    profile_dir, headless=True,
                    args=_STEALTH_ARGS,
                    ignore_default_args=["--enable-automation"],
                )

            try:
                page = ctx.new_page()
                page.add_init_script(_STEALTH_INIT)
                page.goto(
                    "https://36kr.com/motif/327687553025",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                time.sleep(5)

                # 滚动加载更多
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

                # 提取文章信息（链接 + 标题 + 时间）
                items = page.evaluate("""
                    () => {
                        const seen = new Set();
                        const results = [];
                        document.querySelectorAll('a[href*="/p/"]').forEach(a => {
                            const href = a.href;
                            if (!href || seen.has(href)) return;
                            const text = (a.innerText || a.textContent || '').trim();
                            if (text.length < 5) return;
                            seen.add(href);
                            // 尝试找时间：向上找父容器里的 time 元素
                            let timeStr = '';
                            let el = a;
                            for (let i = 0; i < 8; i++) {
                                el = el.parentElement;
                                if (!el) break;
                                const t = el.querySelector('time, [class*="time"], [class*="date"]');
                                if (t) { timeStr = t.textContent.trim(); break; }
                            }
                            // 封面图
                            let coverImg = '';
                            let elImg = a;
                            for (let i = 0; i < 8; i++) {
                                elImg = elImg.parentElement;
                                if (!elImg) break;
                                const img = elImg.querySelector('img[src*="http"]');
                                if (img) { coverImg = img.src; break; }
                            }
                            results.push({href, text, timeStr, coverImg});
                        });
                        return results;
                    }
                """)

                seen_href = set()
                for item in (items or []):
                    href = item.get("href", "")
                    text = item.get("text", "").strip()
                    if not href or not text or len(text) < 5:
                        continue
                    if href in seen_href:
                        continue
                    seen_href.add(href)

                    time_str = item.get("timeStr", "")
                    pub_dt = _parse_relative_time(time_str) if time_str else datetime.now(tz=timezone.utc)

                    results.append({
                        "source": "weekly_news",
                        "label": "36kr",
                        "channel": "36氪游戏",
                        "title": text[:120],
                        "content": "",
                        "url": href,
                        "time": pub_dt.isoformat(),
                        "cover_image": item.get("coverImg", ""),
                    })

                    if len(results) >= limit:
                        break
            finally:
                ctx.close()

    except Exception as e:
        logger.error("36kr 抓取失败: %s", e)

    logger.info("36kr: 抓取到 %d 条新闻", len(results))
    return results


# ─────────────────── 统一入口 ───────────────────

def fetch_weekly_news(
    sources: List[str] = None,
    days: int = 7,
    per_source: int = 30,
) -> List[Dict[str, Any]]:
    """
    抓取游戏行业周报新闻。
    sources: ['36kr', 'gamelook', 'youxichaguan']，为空则抓全部。
    days: 只返回最近 days 天的新闻。
    """
    if not sources:
        sources = ["36kr", "gamelook", "youxichaguan"]

    all_items = []
    seen_urls = set()

    fetch_map = {
        "36kr": lambda: fetch_36kr(days=days, limit=per_source),
        "gamelook": lambda: fetch_gamelook(days=days, limit=per_source),
        "youxichaguan": lambda: fetch_youxichaguan(days=days, limit=per_source),
    }

    for src in sources:
        fn = fetch_map.get(src)
        if not fn:
            continue
        try:
            items = fn()
            for item in items:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_items.append(item)
        except Exception as e:
            logger.error("周报新闻来源 %s 抓取异常: %s", src, e)

    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return all_items
