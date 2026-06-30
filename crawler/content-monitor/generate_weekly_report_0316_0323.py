#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏周报生成脚本 —— 2026年3月16日~3月23日

步骤：
  1. 用 qwen-max + enable_search=True 联网搜索本周重大游戏新闻
  2. 读取已爬好的七麦榜单数据（weekly_cache/qimai_raw_0316_0323.json）
  3. 检测榜单异动（新上榜 + 上升≥3名）
  4. 调用 generate_weekly_report_article 生成周报全文
  5. 保存为 weekly_cache/weekly_report_0316_0323.md

用法：
  cd D:/project/content-monitor
  python generate_weekly_report_0316_0323.py
"""

import json
import sys
import re
import logging
from pathlib import Path

# ── UTF-8 控制台输出 ─────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SCRIPT_DIR  = Path(__file__).parent
CACHE_DIR   = SCRIPT_DIR / "weekly_cache"
RAW_JSON    = CACHE_DIR / "qimai_raw_0316_0323.json"
OUTPUT_MD   = CACHE_DIR / "weekly_report_0316_0323.md"

WEEK_LABEL  = "2026年3月第三周（3/16-3/23）"
DATE_START  = "2026-03-16"
DATE_END    = "2026-03-23"
DATE_RANK   = "2026-03-22"   # 榜单只分析到3.22，今天数据未更新完

# ── 目标地区（用于异动检测和周报榜单部分）────────────────────────────────────
REGIONS = {
    "cn": "中国大陆", "hk": "中国香港", "tw": "中国台湾",
    "us": "美国",     "jp": "日本",     "kr": "韩国",
    "gb": "英国",     "de": "德国",     "fr": "法国",
    "sg": "新加坡",   "th": "泰国",     "sa": "沙特",
    "tr": "土耳其",   "br": "巴西",     "in": "印度",
}
CHART_NAMES = {"free": "免费榜", "grossing": "畅销榜"}


# ═════════════════════════════════════════════════════════════════════════════
# 一、联网搜索本周游戏新闻
# ═════════════════════════════════════════════════════════════════════════════

NEWS_TOPICS = [
    "2026年3月 手机游戏 新游发布 上线",
    "2026年3月 游戏行业 大事件 融资 并购 版号",
    "2026年3月 Steam PC游戏 发售 热门",
    "2026年3月 手游 出海 海外市场 收入",
    "2026年3月 腾讯 网易 米哈游 游戏 新消息",
    "2026年3月 电竞 赛事 重大事件",
]


def search_game_news(client) -> list:
    """
    用 qwen-max + enable_search=True 对每个话题联网搜索，
    返回结构化新闻列表：[{title, content, channel}, ...]
    """
    all_news = []

    logger.info("开始联网搜索本周游戏新闻（共 %d 个话题）...", len(NEWS_TOPICS))

    for i, topic in enumerate(NEWS_TOPICS, 1):
        logger.info("  [%d/%d] 搜索: %s", i, len(NEWS_TOPICS), topic)
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个游戏行业新闻助手。请联网搜索用户给出的话题，"
                            "找出2026年3月16日至3月23日期间最重要的3-5条新闻。\n"
                            "对每条新闻，输出以下格式（严格按格式，每条之间用===分隔）：\n"
                            "标题：[新闻标题]\n"
                            "来源：[媒体/平台名称]\n"
                            "摘要：[150字以内的事件摘要，包含关键数据]\n"
                            "===\n"
                            "若该时段内无相关重要新闻，请输出：无相关新闻"
                        ),
                    },
                    {"role": "user", "content": f"请搜索：{topic}"},
                ],
                extra_body={"enable_search": True, "enable_thinking": False},
            )
            raw = (resp.choices[0].message.content or "").strip()
            if "无相关新闻" in raw:
                logger.info("    => 无相关新闻")
                continue

            # 解析结构化输出
            for block in raw.split("==="):
                block = block.strip()
                if not block:
                    continue
                title, source, summary = "", "", ""
                for line in block.split("\n"):
                    line = line.strip()
                    if line.startswith("标题："):
                        title = line[3:].strip()
                    elif line.startswith("来源："):
                        source = line[3:].strip()
                    elif line.startswith("摘要："):
                        summary = line[3:].strip()
                if title and summary:
                    all_news.append({
                        "title":   title,
                        "content": summary,
                        "channel": source or "网络",
                        "topic":   topic,
                    })
            logger.info("    => 收集到 %d 条", sum(1 for n in all_news if n.get("topic") == topic))

        except Exception as e:
            logger.warning("    搜索失败: %s", e)

    # 去重（标题相似度简单判断）
    seen_titles = set()
    unique_news = []
    for n in all_news:
        key = re.sub(r"\s+", "", n["title"])[:20]
        if key not in seen_titles:
            seen_titles.add(key)
            unique_news.append(n)

    logger.info("[done] 共收集 %d 条不重复新闻", len(unique_news))
    return unique_news


# ═════════════════════════════════════════════════════════════════════════════
# 二、从七麦缓存数据中构建榜单快照 & 异动
# ═════════════════════════════════════════════════════════════════════════════

def build_rank_data_from_cache(raw_data: dict) -> dict:
    """
    将 qimai_raw_0316_0323.json 中3月23日的数据，
    转换为与 fetch_multi_region_ranks() 返回值兼容的 rank_data 结构，
    同时检测7天异动（3/16 vs 3/23）。
    """
    rank_data = {"anomalies": [], "fetch_time": DATE_END + "T00:00:00Z"}

    for country, cname in REGIONS.items():
        if country not in raw_data:
            continue
        rank_data[country] = {}

        for ct, chart_name in CHART_NAMES.items():
            if ct not in raw_data.get(country, {}):
                continue

            dates_data = raw_data[country][ct]
            # 以 3/22 为最新快照（3/23 数据未更新完，不具分析意义）
            last_day  = {int(k): v for k, v in dates_data.get(DATE_RANK, {}).items()}
            first_day = {int(k): v for k, v in dates_data.get(DATE_START, {}).items()}

            items = []
            for rank in sorted(last_day.keys()):
                name = last_day[rank]
                if not name:
                    continue
                # 计算涨跌（与第一天对比）
                first_day_names = {v: k for k, v in first_day.items()}  # name->rank
                prev_rank = first_day_names.get(name)
                if prev_rank is None:
                    change_str = "★新"
                elif prev_rank > rank:
                    change_str = f"↑{prev_rank - rank}"
                elif prev_rank < rank:
                    change_str = f"↓{rank - prev_rank}"
                else:
                    change_str = "-"

                items.append({
                    "rank":      rank,
                    "app_name":  name,
                    "change":    change_str,
                    "last_rank": str(prev_rank) if prev_rank else "-",
                    "publisher": "",
                    "genre":     "",
                })

            rank_data[country][ct] = {
                "country":      country,
                "country_name": cname,
                "chart_type":   ct,
                "chart_name":   chart_name,
                "fetch_time":   DATE_RANK,
                "items":        items,
            }

            # 异动检测：7天内上升>=3名 或 新上榜
            for item in items:
                c = item["change"]
                if c == "★新":
                    rank_data["anomalies"].append({
                        "region":    cname,
                        "chart":     chart_name,
                        "app":       item["app_name"],
                        "rank":      item["rank"],
                        "change":    "★新上榜",
                        "last_rank": "-",
                        "country":   country,
                    })
                elif c.startswith("↑"):
                    try:
                        val = int(c[1:])
                        if val >= 3:
                            rank_data["anomalies"].append({
                                "region":    cname,
                                "chart":     chart_name,
                                "app":       item["app_name"],
                                "rank":      item["rank"],
                                "change":    c,
                                "last_rank": item["last_rank"],
                                "country":   country,
                            })
                    except ValueError:
                        pass

    # 异动排序：★新上榜 > ↑N 降序
    def _sort_key(a):
        c = a.get("change", "")
        if c == "★新上榜": return 9999
        if c.startswith("↑"):
            try: return int(c[1:])
            except: return 0
        return 0

    rank_data["anomalies"].sort(key=_sort_key, reverse=True)
    logger.info("异动检测完成：共 %d 条（新上榜+上升>=3名）", len(rank_data["anomalies"]))
    return rank_data


# ═════════════════════════════════════════════════════════════════════════════
# 三、生成周报全文
# ═════════════════════════════════════════════════════════════════════════════

def generate_report(client, news_items: list, rank_data: dict) -> str:
    """调用 qwen-max 生成完整周报 Markdown。"""
    logger.info("开始生成周报全文（qwen-max，超时300s）...")

    # 长文生成需要更长的超时，单独创建客户端
    from openai import OpenAI
    import os
    long_client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=300.0,
    )

    # 构建新闻块
    news_block = ""
    for i, item in enumerate(news_items, 1):
        news_block += (
            f"\n【新闻{i}】来源：{item.get('channel','')}\n"
            f"标题：{item.get('title','')}\n"
            f"内容：{item.get('content','')[:500]}\n"
        )

    # 构建榜单摘要块
    rank_block = ""
    for country, cname in REGIONS.items():
        if country not in rank_data:
            continue
        for ct, chart_name in CHART_NAMES.items():
            chart = rank_data[country].get(ct, {})
            top5 = chart.get("items", [])[:5]
            if not top5:
                continue
            tops = ", ".join(f"#{it['rank']}{it['app_name']}" for it in top5)
            rank_block += f"{cname}{chart_name}TOP5：{tops}\n"

    # 构建异动块
    anomalies = rank_data.get("anomalies", [])
    anomaly_block = "\n".join(
        f"- {a['region']} {a['chart']}：《{a['app']}》{a['change']}，现排名#{a['rank']}"
        for a in anomalies[:20]
    ) or "暂无"

    system_text = (
        "你是一个在小红书上运营游戏行业观察账号的博主，账号名「游戏雷达局」。\n"
        "你的定位：稍专业但不晦涩——懂行的人觉得有料，不懂行的人也能读懂、感兴趣。\n"
        "语气像一个真正懂游戏的朋友在给你讲这周发生了什么，有观点、有态度，不只是播报。\n\n"
        "请根据本周游戏新闻，撰写一篇游戏行业周报。\n\n"
        "━━━ 结构要求 ━━━\n\n"
        f"# 游戏周报｜{WEEK_LABEL}\n\n"
        "开头写 1-2 句吸引人的导语，点出本周最有看头的 1-2 件事，让人想继续读。\n\n"
        "## 本周大事件\n"
        "将提供的所有新闻每条都写到，第一条必须是 BLG 夺冠，每条格式：\n"
        "### 标题（20字以内，点出核心，可带情绪色彩，禁止在标题前加任何 emoji）\n"
        "正文 200-300 字：先说清楚发生了什么，然后给出你的观点或分析。\n"
        "每条必须写完整，不允许用省略号结尾，不允许截断，必须有完整结论或观点。\n"
        "关键数据必须保留，用**加粗**强调核心信息。\n"
        "每条结尾可选加一句「> 划重点：xxx」作为金句提炼（不强制每条都加）。\n\n"
        "结尾写 1-2 句本周总结或对下周的展望，轻松收尾。\n\n"
        "━━━ 写作规范 ━━━\n"
        "1. 口语化但不低俗，像朋友聊天，不像论文也不像公关稿\n"
        "2. 有观点敢说话，遇到争议话题可以明确表态\n"
        "3. 关键数据必须保留（如具体金额、排名、百分比）\n"
        "4. 不要写来源链接或网址\n"
        "5. Markdown 格式\n"
        "6. 正文中禁止使用任何 emoji，包括标题前后\n"
        "7. 不需要单独写榜单看点章节，榜单数据仅供参考背景，不要单独分析\n"
        "━━━ 写作规范 ━━━\n"
        "1. 口语化但不低俗，像朋友聊天，不像论文也不像公关稿\n"
        "2. 有观点敢说话，遇到争议话题可以明确表态\n"
        "3. 关键数据必须保留（如具体金额、排名、百分比）\n"
        "4. 不要写来源链接或网址\n"
        "5. 全文 1500-2200 字，Markdown 格式\n"
        "6. 正文中禁止使用任何 emoji，包括标题前后\n"
    )

    user_text = (
        f"本周新闻（共{len(news_items)}条，请全部纳入分析）：\n{news_block}\n\n"
        f"本周各地区榜单 TOP5（3月23日快照）：\n{rank_block}\n\n"
        f"七天榜单异动（3月16日→3月23日，新上榜或上升≥3名，请在榜单看点中重点分析）：\n{anomaly_block}\n"
    )

    resp = long_client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user",   "content": user_text},
        ],
        extra_body={"enable_thinking": False},
        max_tokens=4096,
    )
    article = (resp.choices[0].message.content or "").strip()

    # 追加完整榜单表格
    table_md = _build_rank_tables(rank_data)
    if table_md:
        article += "\n\n---\n\n" + table_md

    return article


def _build_rank_tables(rank_data: dict) -> str:
    """将所有地区榜单转为 Markdown 表格（附于周报末尾）。"""
    flag_map = {
        "cn": "🇨🇳", "hk": "🇭🇰", "tw": "🇹🇼", "us": "🇺🇸", "jp": "🇯🇵",
        "kr": "🇰🇷", "gb": "🇬🇧", "de": "🇩🇪", "fr": "🇫🇷", "sg": "🇸🇬",
        "th": "🇹🇭", "sa": "🇸🇦", "tr": "🇹🇷", "br": "🇧🇷", "in": "🇮🇳",
    }
    lines = ["## 附：本周各地区榜单数据（3月23日）\n"]
    for country, cname in REGIONS.items():
        if country not in rank_data:
            continue
        flag = flag_map.get(country, "")
        for ct, chart_name in CHART_NAMES.items():
            chart = rank_data[country].get(ct, {})
            items = chart.get("items", [])
            if not items:
                continue
            lines.append(f"### {flag} {cname} · {chart_name} TOP10\n")
            lines.append("| 排名 | 游戏名称 | 7天涨跌 | 3/16排名 |")
            lines.append("|------|----------|---------|---------|")
            for it in items[:10]:
                lines.append(
                    f"| {it['rank']} | {it['app_name']} | {it['change']} | {it['last_rank']} |"
                )
            lines.append("")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  游戏周报生成  2026-03-16 ~ 03-23")
    print("=" * 60)

    # 初始化 Qwen 客户端
    sys.path.insert(0, str(SCRIPT_DIR))
    from qwen_client import get_qwen_client
    client = get_qwen_client()

    # Step 1: 联网搜索新闻（支持缓存，避免重复调用API）
    print("\n--- Step 1/3: 联网搜索本周游戏新闻 ---")
    NEWS_CACHE = CACHE_DIR / "news_0316_0323.json"
    if NEWS_CACHE.exists():
        news_items = json.load(open(NEWS_CACHE, encoding="utf-8"))
        print(f"  => 使用缓存，共 {len(news_items)} 条新闻（如需重新搜索请删除 {NEWS_CACHE.name}）")
    else:
        news_items = search_game_news(client)
        json.dump(news_items, open(NEWS_CACHE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"  => 共收集 {len(news_items)} 条新闻，已缓存")
    for n in news_items:
        print(f"     [{n['channel']}] {n['title']}")

    if not news_items:
        print("[warn] 未搜到新闻，将仅基于榜单数据生成周报")

    # Step 2: 加载榜单数据
    print("\n--- Step 2/3: 加载榜单数据 ---")
    if not RAW_JSON.exists():
        print(f"[error] 找不到榜单缓存文件: {RAW_JSON}")
        print("请先运行 fetch_weekly_0316_0323.py")
        sys.exit(1)

    raw_data = json.load(open(RAW_JSON, encoding="utf-8"))
    rank_data = build_rank_data_from_cache(raw_data)
    print(f"  => 已加载 {len([k for k in rank_data if k not in ('anomalies','fetch_time')])} 个地区榜单")
    print(f"  => 检测到 {len(rank_data['anomalies'])} 条七天异动")

    # Step 3: 生成周报
    print("\n--- Step 3/3: 生成周报全文 ---")
    article = generate_report(client, news_items, rank_data)

    # 保存
    OUTPUT_MD.write_text(article, encoding="utf-8")
    print(f"\n[done] 周报已保存: {OUTPUT_MD}")
    print(f"  字数约: {len(article)} 字符")

    # Step 4: 生成微信 + 小红书 HTML
    print("\n--- Step 4/4: 生成微信 & 小红书 HTML ---")
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from weekly_output_builder import (
            build_wechat_html, build_xhs_html,
            read_sheet_rows,
            xhs_card, xhs_h2, xhs_h3, xhs_para, xhs_quote, anomaly_li, rank_table, section_label,
        )
        import openpyxl

        WEEK_SHORT  = "2026年第12周"
        DATE_RANGE  = "3月16日-3月23日"
        ISSUE       = "12"
        EXCEL_V2    = CACHE_DIR / "七麦榜单_0316-0323_v2.xlsx"
        EXCEL_PATH  = CACHE_DIR / "七麦榜单_0316-0323.xlsx"
        excel_file  = EXCEL_V2 if EXCEL_V2.exists() else (EXCEL_PATH if EXCEL_PATH.exists() else None)

        # ── 微信 HTML ──────────────────────────────────────────────────────
        wechat_html = build_wechat_html(article, WEEK_LABEL, WEEK_SHORT, DATE_RANGE, ISSUE)
        wechat_out  = CACHE_DIR / "output_wechat_0316_0323.html"
        wechat_out.write_text(wechat_html, encoding="utf-8")
        print(f"  [ok] 微信版: {wechat_out}")

        # ── 小红书卡片 ─────────────────────────────────────────────────────
        import re as _re

        def strip_md(text):
            text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = _re.sub(r'\*(.+?)\*',   r'\1', text)
            text = _re.sub(r'^#+\s*',       '',    text)
            text = _re.sub(r'^>\s*',        '',    text)
            return text.strip()

        def extract_sections(md):
            """按 ### 提取各大事件，返回 [(title, body_text), ...]
            只处理第一个 '---' 分隔符之前的内容，避免把附录榜单标题也提取进来。
            """
            # 只取 --- 之前的主体部分
            main_body = md.split('\n---\n')[0]
            sections = []
            cur_title, cur_body = None, []
            for line in main_body.split('\n'):
                m = _re.match(r'^### (.+)', line)
                if m:
                    if cur_title:
                        sections.append((cur_title, ' '.join(cur_body).strip()))
                    cur_title = strip_md(m.group(1))
                    cur_body  = []
                elif cur_title and line.strip() and not _re.match(r'^##', line):
                    cur_body.append(strip_md(line))
            if cur_title:
                sections.append((cur_title, ' '.join(cur_body).strip()))
            return sections

        sections = extract_sections(article)

        # 读取 Excel 榜单数据（若存在）—— 数据截止 3/22
        RANK_DATE_LABEL = "3月16日 - 3月22日"
        cn_free_rows = cn_gross_rows = []
        us_free_rows = us_gross_rows = []
        jp_free_rows = jp_gross_rows = []
        kr_free_rows = kr_gross_rows = []
        if excel_file:
            wb = openpyxl.load_workbook(excel_file, read_only=True, data_only=True)
            cn_free_rows  = read_sheet_rows(wb, '中国大陆_免费榜')
            cn_gross_rows = read_sheet_rows(wb, '中国大陆_畅销榜')
            us_free_rows  = read_sheet_rows(wb, '美国_免费榜')
            us_gross_rows = read_sheet_rows(wb, '美国_畅销榜')
            jp_free_rows  = read_sheet_rows(wb, '日本_免费榜')
            jp_gross_rows = read_sheet_rows(wb, '日本_畅销榜')
            kr_free_rows  = read_sheet_rows(wb, '韩国_免费榜')
            kr_gross_rows = read_sheet_rows(wb, '韩国_畅销榜')

        # 异动（3/16→3/22）
        anomalies = rank_data.get('anomalies', [])

        cards = []

        # --- 卡片1：封面 ---
        intro_lines = [l for l in article.split('\n') if l.strip() and not l.startswith('#')][:2]
        intro_text  = strip_md(' '.join(intro_lines))[:130]
        all_titles  = [s[0][:24] for s in sections]
        body1 = (
            xhs_h2('W12', '游戏行业周报')
            + xhs_para('3月16日 - 3月22日')
            + '<div style="height:8px;"></div>'
            + xhs_para(intro_text)
            + '<div style="height:10px;"></div>'
            + xhs_h3('本期重点')
            + ''.join(xhs_para(f'· {t}') for t in all_titles)
        )
        cards.append(xhs_card(1, '第12期', body1))

        # --- 卡片2起：每两条大事件合并一张 ---
        pairs = [sections[i:i+2] for i in range(0, len(sections), 2)]
        for pair_idx, pair in enumerate(pairs, 1):
            body = ''
            for local_idx, (title, body_text) in enumerate(pair):
                global_idx = (pair_idx - 1) * 2 + local_idx + 1
                body += xhs_h2(f'{global_idx:02d}', title)
                body += xhs_para(body_text)
                if local_idx == 0 and len(pair) == 2:
                    body += '<div style="height:10px;border-top:1px solid rgba(255,255,255,0.12);margin:10px 0;"></div>'
            tag = f'事件 {(pair_idx-1)*2+1}{"–"+str(min(pair_idx*2,len(sections))) if len(pair)==2 else ""}/{len(sections)}'
            cards.append(xhs_card(pair_idx + 1, tag, body))

        # --- 榜单卡片：中国大陆 ---
        import math
        card_n = math.ceil(len(sections) / 2) + 2
        body_cn = xhs_h2(f'{card_n:02d}', '中国大陆榜单 TOP10')
        if cn_free_rows:
            body_cn += xhs_h3('免费榜')
            body_cn += rank_table(cn_free_rows)
        if cn_gross_rows:
            body_cn += xhs_h3('畅销榜')
            body_cn += rank_table(cn_gross_rows)
        body_cn += xhs_quote('数据截止', f'七麦数据 · {RANK_DATE_LABEL}')
        cards.append(xhs_card(card_n, '国内榜单', body_cn))

        # --- 榜单卡片：美国 ---
        card_n += 1
        body_us = xhs_h2(f'{card_n:02d}', '美国榜单 TOP10')
        if us_free_rows:
            body_us += xhs_h3('免费榜')
            body_us += rank_table(us_free_rows)
        if us_gross_rows:
            body_us += xhs_h3('畅销榜')
            body_us += rank_table(us_gross_rows)
        body_us += xhs_quote('数据截止', f'七麦数据 · {RANK_DATE_LABEL}')
        cards.append(xhs_card(card_n, '美国榜单', body_us))

        # --- 榜单卡片：日本 + 韩国 ---
        card_n += 1
        body_jpkr = xhs_h2(f'{card_n:02d}', '日韩榜单 TOP10')
        if jp_free_rows:
            body_jpkr += xhs_h3('日本 免费榜')
            body_jpkr += rank_table(jp_free_rows)
        if jp_gross_rows:
            body_jpkr += xhs_h3('日本 畅销榜')
            body_jpkr += rank_table(jp_gross_rows)
        if kr_free_rows:
            body_jpkr += xhs_h3('韩国 免费榜')
            body_jpkr += rank_table(kr_free_rows)
        if kr_gross_rows:
            body_jpkr += xhs_h3('韩国 畅销榜')
            body_jpkr += rank_table(kr_gross_rows)
        body_jpkr += xhs_quote('数据截止', f'七麦数据 · {RANK_DATE_LABEL}')
        cards.append(xhs_card(card_n, '日韩榜单', body_jpkr))

        xhs_html = build_xhs_html(cards)
        xhs_out  = CACHE_DIR / "output_xhs_0316_0323.html"
        xhs_out.write_text(xhs_html, encoding="utf-8")
        print(f"  [ok] 小红书版 ({len(cards)}张卡片，含{len(sections)}条大事件{f'/{math.ceil(len(sections)/2)}张事件卡'}+3张榜单): {xhs_out}")

    except Exception as e:
        import traceback
        print(f"  [warn] HTML生成失败: {e}")
        traceback.print_exc()

    print()
    print("=" * 60)
    print(article[:600] + "\n...(截取前600字符预览)")
    print("=" * 60)


if __name__ == "__main__":
    main()
