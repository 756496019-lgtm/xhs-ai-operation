"""
TapTap 游戏社区帖子爬虫（XHR/fetch 拦截器版）
目标: https://www.taptap.cn/app/720036/topic
功能: 抓取今日（2026-03-17）的所有帖子
用法: python scrapers/taptap_topic_today.py

技术要点:
- TapTap 使用阿里云 WAF，直接 requests 和 Playwright response 监听均被拦截
- 解决方案：向页面注入 fetch/XHR 拦截脚本，拦截页面自己发出的 API 请求结果
- 页面滚动时，TapTap 前端自动发出 feed/v7/by-group 请求，拦截脚本捕获结果并存入全局变量
- Python 定期读取全局变量获取数据
- API 返回结果为"热度"排序，需翻完所有页过滤今日帖子
"""

import asyncio
import json
import logging
import sys
import time as time_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────────────────────
APP_ID          = "720036"
GROUP_ID        = "826375"
TARGET_DATE     = datetime(2026, 3, 17, tzinfo=timezone(timedelta(hours=8)))
TARGET_DATE_STR = "2026-03-17"
OUTPUT_JSON     = f"taptap_{APP_ID}_topic_{TARGET_DATE_STR}.json"
OUTPUT_TXT      = f"taptap_{APP_ID}_topic_{TARGET_DATE_STR}.txt"

# 滚动配置
SCROLL_STEP       = 600    # 每次滚动像素
SCROLL_PAUSE      = 1.2    # 每次滚动后等待（秒）
MAX_SCROLL_ROUNDS = 150    # 最多滚动次数
NO_NEW_TIMEOUT    = 15     # 连续无新数据超时（秒）

PROFILE_DIR = str(Path(__file__).parent.parent / "playwright_chrome_profile")

# 注入到页面的 fetch/XHR 拦截脚本
INTERCEPT_SCRIPT = """
(function() {
    if (window.__tapApiInterceptInstalled__) return;
    window.__tapApiInterceptInstalled__ = true;
    window.__tapApiQueue__ = [];

    // 拦截 fetch
    const _fetch = window.fetch;
    window.fetch = async function(url, options) {
        const resp = await _fetch(url, options);
        if (typeof url === 'string' && url.includes('by-group')) {
            try {
                const cloned = resp.clone();
                cloned.text().then(text => {
                    window.__tapApiQueue__.push({ url: url, body: text });
                }).catch(() => {});
            } catch(e) {}
        }
        return resp;
    };

    // 拦截 XMLHttpRequest
    const _open = XMLHttpRequest.prototype.open;
    const _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
        this.__tapUrl__ = url;
        return _open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
        this.addEventListener('load', function() {
            if (this.__tapUrl__ && this.__tapUrl__.includes('by-group')) {
                try {
                    window.__tapApiQueue__.push({ url: this.__tapUrl__, body: this.responseText });
                } catch(e) {}
            }
        });
        return _send.apply(this, arguments);
    };
})();
"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def ts_to_cst(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))


def strip_html(text: str) -> str:
    if not text:
        return ""
    if "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "html.parser").get_text(separator=" ").strip()


def is_today(ts: int) -> bool:
    return ts_to_cst(ts).date() == TARGET_DATE.date()


# ── 解析帖子 ──────────────────────────────────────────────────────────────────
def parse_moment(entry: Dict) -> Optional[Dict]:
    moment = entry.get("moment") or {}
    if not moment:
        return None

    moment_id = moment.get("id_str") or str(moment.get("id", ""))
    pub_ts = int(moment.get("publish_time") or moment.get("created_time") or 0)
    if not pub_ts:
        return None

    author_obj = moment.get("author") or {}
    if "user" in author_obj:
        u = author_obj["user"]
        author_name = u.get("name") or u.get("nickname") or "匿名"
        author_id   = str(u.get("id", ""))
    elif "app" in author_obj:
        a = author_obj["app"]
        author_name = a.get("title", "官方")
        author_id   = str(a.get("id", ""))
    else:
        author_name = author_obj.get("name") or "匿名"
        author_id   = str(author_obj.get("id", ""))

    topic        = moment.get("topic") or {}
    title        = topic.get("title") or moment.get("title") or ""
    summary      = (topic.get("summary") or moment.get("summary")
                    or moment.get("content") or "")
    content_text = strip_html(summary)

    if not content_text:
        for block in (moment.get("contents") or []):
            if isinstance(block, dict) and block.get("type") == "text":
                content_text += block.get("content", "")

    sharing = moment.get("sharing") or {}
    url = sharing.get("url") or (
        f"https://www.taptap.cn/moment/{moment_id}" if moment_id else ""
    )

    stat          = moment.get("stat") or {}
    like_count    = stat.get("liked_count") or stat.get("like_count") or 0
    comment_count = stat.get("comment_count") or stat.get("comments_count") or 0

    hot_comment = ""
    hc = entry.get("hot_comment") or {}
    if hc:
        hc_txt  = strip_html(hc.get("content") or "")
        hc_user = (hc.get("user") or {}).get("name", "")
        if hc_txt:
            hot_comment = f"{hc_user}: {hc_txt}"

    return {
        "moment_id":     moment_id,
        "title":         (title or "")[:200],
        "content":       content_text[:2000],
        "author":        author_name,
        "author_id":     author_id,
        "url":           url,
        "publish_time":  ts_to_cst(pub_ts).isoformat(),
        "publish_ts":    pub_ts,
        "like_count":    like_count,
        "comment_count": comment_count,
        "hot_comment":   hot_comment,
    }


def process_entries(entries: list, seen_ids: Set[str], today_posts: List[Dict]) -> int:
    added = 0
    for entry in entries:
        post = parse_moment(entry)
        if not post:
            continue
        mid = post["moment_id"]
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        if is_today(post["publish_ts"]):
            today_posts.append(post)
            added += 1
            label = (post["title"] or post["content"])[:50]
            logger.info(
                "  [+] %s | %s | %s",
                post["publish_time"][:16],
                post["author"][:10],
                label,
            )
    return added


# ── 主抓取逻辑 ────────────────────────────────────────────────────────────────
async def scrape_async() -> List[Dict]:
    from playwright.async_api import async_playwright

    today_posts: List[Dict] = []
    seen_ids: Set[str] = set()
    total_scanned = 0

    async with async_playwright() as pw:
        profile = Path(PROFILE_DIR)
        if profile.exists():
            logger.info("使用持久化 Chrome Profile: %s", PROFILE_DIR)
            ctx = await pw.chromium.launch_persistent_context(
                PROFILE_DIR,
                headless=False,   # 必须有头，无头模式下滚动不触发懒加载
                args=["--disable-blink-features=AutomationControlled"],
                locale="zh-CN",
                viewport={"width": 1280, "height": 800},
            )
        else:
            logger.info("无 Profile，使用普通 Chromium（有头）")
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 800})

        page = await ctx.new_page()

        # 注入拦截脚本（在页面加载前）
        await page.add_init_script(INTERCEPT_SCRIPT)

        # 打开页面
        logger.info("打开 TapTap 页面: https://www.taptap.cn/app/%s/topic", APP_ID)
        try:
            await page.goto(
                f"https://www.taptap.cn/app/{APP_ID}/topic",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            logger.warning("页面加载超时（继续）: %s", e)
        await asyncio.sleep(3)

        logger.info("=" * 60)
        logger.info("开始滚动翻页，目标日期: %s", TARGET_DATE_STR)
        logger.info("=" * 60)

        current_scroll = 0
        last_new_data  = time_mod.time()
        processed_count = 0  # 已从队列处理的数量

        for round_num in range(1, MAX_SCROLL_ROUNDS + 1):
            # 读取并清空队列
            queue_items = await page.evaluate("""
                () => {
                    const items = window.__tapApiQueue__.splice(0);
                    return items;
                }
            """)

            if queue_items:
                for item in queue_items:
                    try:
                        raw = json.loads(item["body"])
                    except Exception:
                        continue
                    if not raw.get("success", True):
                        continue
                    inner   = raw.get("data") or {}
                    entries = (inner.get("list") or inner.get("items") or []
                               if isinstance(inner, dict) else [])
                    if not entries:
                        continue

                    total_scanned += len(entries)
                    from_val = "?"
                    if "from=" in item["url"]:
                        from_val = item["url"].split("from=")[1].split("&")[0]
                    logger.info("处理 API 响应 from=%s → %d 条（总 %d）",
                                from_val, len(entries), total_scanned)
                    process_entries(entries, seen_ids, today_posts)
                    last_new_data = time_mod.time()
                    processed_count += 1

            # 检查超时
            elapsed = time_mod.time() - last_new_data
            if elapsed >= NO_NEW_TIMEOUT:
                logger.info("%.1fs 无新数据，总扫描 %d 条，停止", elapsed, total_scanned)
                break

            # 滚动
            current_scroll += SCROLL_STEP
            await page.evaluate(f"window.scrollTo(0, {current_scroll})")
            await asyncio.sleep(SCROLL_PAUSE)

            if round_num % 20 == 0:
                logger.info("已滚动 %d 轮，今日帖子 %d 条，总扫描 %d 条",
                            round_num, len(today_posts), total_scanned)

        # 最后再读一次队列
        queue_items = await page.evaluate("() => window.__tapApiQueue__.splice(0)")
        for item in queue_items:
            try:
                raw = json.loads(item["body"])
                inner = raw.get("data") or {}
                entries = (inner.get("list") or inner.get("items") or []
                           if isinstance(inner, dict) else [])
                if entries:
                    total_scanned += len(entries)
                    process_entries(entries, seen_ids, today_posts)
            except Exception:
                pass

        await ctx.close()

    logger.info("=" * 60)
    logger.info("抓取完成，今日（%s）帖子共 %d 条（共扫描 %d 条）",
                TARGET_DATE_STR, len(today_posts), total_scanned)
    logger.info("=" * 60)
    return today_posts


def scrape_today_topics() -> List[Dict]:
    return asyncio.run(scrape_async())


# ── 输出 ──────────────────────────────────────────────────────────────────────
def save_results(posts: List[Dict]) -> None:
    if not posts:
        logger.warning("无数据，不写入文件")
        return

    posts.sort(key=lambda x: x["publish_ts"], reverse=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    logger.info("JSON 已保存: %s", OUTPUT_JSON)

    lines = [
        f"TapTap app/{APP_ID} 今日帖子（{TARGET_DATE_STR}）",
        f"共 {len(posts)} 条  |  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
    ]
    for i, p in enumerate(posts, 1):
        title_str = p["title"] or "（无标题）"
        lines.append(f"【{i}】{title_str}")
        lines.append(f"    作者: {p['author']}  |  时间: {p['publish_time'][:16]}")
        lines.append(f"    点赞: {p['like_count']}  评论: {p['comment_count']}")
        lines.append(f"    链接: {p['url']}")
        if p["content"]:
            preview = p["content"][:200].replace("\n", " ")
            ellipsis = "..." if len(p["content"]) > 200 else ""
            lines.append(f"    正文: {preview}{ellipsis}")
        if p.get("hot_comment"):
            lines.append(f"    热评: {p['hot_comment'][:100]}")
        lines.append("")

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("文本已保存: %s", OUTPUT_TXT)


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    posts = scrape_today_topics()
    save_results(posts)

    if posts:
        print(f"\n[OK] 共抓取今日帖子 {len(posts)} 条")
        print(f"     JSON: {OUTPUT_JSON}")
        print(f"     文本: {OUTPUT_TXT}")
    else:
        print("\n[WARN] 未找到今日帖子")
        print(f"  当前 group_id={GROUP_ID}")
        print("  如需更新: 用浏览器 DevTools Network 面板查看 feed/v7/by-group 请求")
