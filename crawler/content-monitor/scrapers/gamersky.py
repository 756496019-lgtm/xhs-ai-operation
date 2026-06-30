"""游民星空（Gamersky）新闻抓取模块。"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

# 游民星空新闻列表 AJAX 接口（节点 11007 = 新闻频道首页）
_AJAX_URL = "https://db2.gamersky.com/LabelJsonpAjax.aspx"
_NEWS_NODE_ID = "11007"


class GamerskyScraperLite:
    """基于 GamerskyScraper 做的精简版，只返回列表，不写 Excel。"""

    def __init__(self, target_date: str):
        self.target_date = target_date  # YYYY-MM-DD
        self.base_url = "https://www.gamersky.com/news/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.gamersky.com/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_page(self, url: str):
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.encoding = "utf-8"
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            logger.warning("获取页面失败: %s %s", resp.status_code, url)
        except Exception as e:
            logger.error("获取页面异常: %s", e)
        return None

    def fetch_ajax_page(self, page: int) -> Tuple[Optional[BeautifulSoup], int]:
        """通过 AJAX API 获取新闻列表某页，返回 (soup, total_pages)。
        游民星空改用 JS 动态分页，?page=N 参数无效，必须走此接口。
        """
        jsondata = json.dumps(
            {
                "type": "updatenodelabel",
                "isCache": True,
                "cacheTime": 60,
                "nodeId": _NEWS_NODE_ID,
                "isNodeId": "true",
                "page": page,
            },
            separators=(",", ":"),
        )
        try:
            resp = self.session.get(
                _AJAX_URL,
                params={"jsondata": jsondata, "callback": "cb"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.encoding = "utf-8"
            m = re.search(r"\((\{.*\})\)", resp.text, re.DOTALL)
            if not m:
                logger.warning("AJAX 响应解析失败（page=%d）", page)
                return None, 0
            data = json.loads(m.group(1))
            total = int(data.get("totalPages", 0))
            soup = BeautifulSoup(data.get("body", ""), "html.parser")
            return soup, total
        except Exception as e:
            logger.error("AJAX 请求异常（page=%d）: %s", page, e)
            return None, 0

    def is_target_date(self, text: str) -> bool:
        """沿用原来的日期匹配逻辑（精简版）。"""
        if not text:
            return False
        date_formats = [
            r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
        ]
        target_y, target_m, target_d = self.target_date.split("-")
        target_m = target_m.lstrip("0")
        target_d = target_d.lstrip("0")

        for pat in date_formats:
            m = re.search(pat, text)
            if m:
                y, mo, d = m.groups()
                mo = mo.lstrip("0")
                d = d.lstrip("0")
                if y == target_y and mo == target_m and d == target_d:
                    return True
        return False

    def extract_list(self, soup) -> List[Dict[str, Any]]:
        """提取列表页或 AJAX 返回的 li 中的标题/链接/日期。
        兼容两种场景：
          - 首页 HTML：soup 包含 div.Mid2L_con li
          - AJAX body：soup 直接是 li 集合（父级为 body）
        """
        items = soup.select("div.Mid2L_con li") or soup.find_all("li")
        results = []
        for item in items:
            # AJAX 结构：标题在 div.tit > a.tt，日期在 div.txt em
            a = item.select_one("a.tt") or item.find("a")
            if not a:
                continue
            href = a.get("href", "")
            if not href or not href.startswith("http"):
                continue
            title = a.get("title", "") or a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            text = item.get_text(" ", strip=True)
            m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
            date_text = m.group(1).replace("/", "-") if m else ""
            if not self.is_target_date(date_text):
                continue
            results.append(
                {
                    "title": title,
                    "url": href,
                    "date": date_text or self.target_date,
                }
            )
        return results

    def extract_article_main_content(self, url: str) -> str:
        """提取文章页主体文字内容（简化版）。"""
        soup = self.get_page(url)
        if not soup:
            return ""

        content_div = soup.select_one("div.Mid2L_con") or soup.find("div", class_="Mid2L_con")
        if not content_div:
            return ""

        for tag_name in ["script", "style", "iframe", "img", "figure", "nav", "header", "footer", "aside"]:
            for el in content_div.find_all(tag_name):
                el.decompose()

        texts: List[str] = []
        paragraphs = content_div.find_all("p")
        exclude_keywords = ["广告", "版权", "转载", "来源：", "编辑：", "本文由", "未经允许禁止转载", "游民星空制作发布"]

        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            if any(k in text for k in exclude_keywords):
                continue
            texts.append(text)

        if len(texts) < 2:
            all_text = content_div.get_text("\n", strip=True)
            lines = [ln.strip() for ln in all_text.split("\n") if ln.strip() and len(ln.strip()) > 15]
            for line in lines:
                if any(k in line for k in exclude_keywords):
                    continue
                texts.append(line)

        seen = set()
        uniq: List[str] = []
        for t in texts:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)

        return "\n\n".join(uniq)

    def run(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """抓取指定日期的新闻列表，并尝试抓取正文摘要。
        游民星空已改为 JS 动态分页，?page=N 参数无效，翻页通过 AJAX API 实现。
        第1页仍从首页 HTML 获取（保留原有逻辑），后续页走 AJAX。
        """
        logger.info("开始抓取 %s 的新闻列表 ...", self.target_date)
        all_rows: List[Dict[str, Any]] = []

        # 第1页：从首页 HTML 获取
        page = 1
        logger.info("第 %d 页: %s（HTML）", page, self.base_url)
        soup = self.get_page(self.base_url)
        if soup:
            page_rows = self.extract_list(soup)
            all_rows.extend(page_rows)
            logger.info("第 %d 页命中 %d 条", page, len(page_rows))
            # 若当页已全是目标日期之前的内容，无需继续翻页
            if page_rows:
                pass  # 继续翻页
        else:
            logger.warning("首页获取失败，尝试直接走 AJAX")

        # 后续页：通过 AJAX API 翻页
        for page in range(2, max_pages + 1):
            time.sleep(REQUEST_DELAY)
            logger.info("第 %d 页: AJAX（nodeId=%s）", page, _NEWS_NODE_ID)
            ajax_soup, total_pages = self.fetch_ajax_page(page)
            if not ajax_soup:
                logger.warning("第 %d 页 AJAX 失败，停止翻页", page)
                break
            page_rows = self.extract_list(ajax_soup)
            all_rows.extend(page_rows)
            logger.info("第 %d 页命中 %d 条（共 %d 总页）", page, len(page_rows), total_pages)
            # 如果当页完全没有目标日期的内容，说明已翻过头，停止
            if not page_rows:
                logger.info("第 %d 页无目标日期内容，停止翻页", page)
                break

        # 去重
        seen = set()
        unique_rows: List[Dict[str, Any]] = []
        for row in all_rows:
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            unique_rows.append(row)

        logger.info("去重后共 %d 条，开始并行抓取正文 ...", len(unique_rows))

        # 并行抓取正文
        def _fetch_content(row):
            content = self.extract_article_main_content(row["url"])
            return {
                "source": "gamersky",
                "title": row["title"],
                "url": row["url"],
                "time": row["date"],
                "label": "gamersky",
                "content": content,
            }

        with ThreadPoolExecutor(max_workers=5) as executor:
            final_rows = list(executor.map(_fetch_content, unique_rows))

        return final_rows


def run_gamersky_monitor(target_date: str, max_pages: int) -> List[Dict[str, Any]]:
    scraper = GamerskyScraperLite(target_date=target_date)
    return scraper.run(max_pages=max_pages)
