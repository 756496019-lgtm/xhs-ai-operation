"""Steam 玩家评论搜索与抓取。"""

import logging
import time
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def search_steam_game(name: str, max_results: int = 6) -> List[Dict]:
    """在 Steam 商店搜索游戏，返回 [{appid, name, image}]。"""
    try:
        resp = requests.get(
            "https://store.steampowered.com/api/storesearch/",
            params={"term": name, "l": "schinese", "cc": "CN"},
            headers=_HEADERS,
            timeout=10,
        )
        items = resp.json().get("items", [])
        return [
            {
                "appid":  str(item["id"]),
                "name":   item.get("name", ""),
                "image":  item.get("tiny_image", ""),
            }
            for item in items[:max_results]
        ]
    except Exception as e:
        logger.warning("Steam 搜索失败: %s", e)
        return []


def fetch_steam_reviews(appid: str, max_pages: int = 3) -> Dict:
    """
    分页抓取 Steam 玩家评论（每页 100 条，最多 max_pages 页）。
    优先中文，中文不足 30 条时补全语言。
    返回 {summary, reviews, pages_fetched}
    """
    PER_PAGE = 100

    def _fetch_page(language: str, cursor: str) -> Dict:
        resp = requests.get(
            f"https://store.steampowered.com/appreviews/{appid}",
            params={
                "json":          "1",
                "language":      language,
                "num_per_page":  PER_PAGE,
                "filter":        "all",        # 按帮助度排序，最具代表性在前
                "purchase_type": "all",
                "cursor":        cursor,
            },
            headers=_HEADERS,
            timeout=15,
        )
        return resp.json()

    def _collect(language: str, max_p: int) -> tuple[List, Dict]:
        """返回 (reviews_raw, query_summary)"""
        collected, cursor, summary = [], "*", {}
        for page in range(max_p):
            try:
                data = _fetch_page(language, cursor)
            except Exception as e:
                logger.warning("Steam 页面请求失败 (page=%d): %s", page, e)
                break
            if data.get("success") != 1:
                break
            if page == 0:
                summary = data.get("query_summary", {})
            page_reviews = data.get("reviews", [])
            if not page_reviews:
                break
            collected.extend(page_reviews)
            new_cursor = data.get("cursor", "")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
            time.sleep(0.3)   # 避免频率限制
        return collected, summary

    try:
        # Phase 1：中文评论
        raw, summary_data = _collect("schinese", max_pages)

        # Phase 2：中文不足 30 条时补全语言（去重合并）
        if len(raw) < 30:
            raw_all, summary_all = _collect("all", max_pages)
            if summary_all:
                summary_data = summary_all  # 全量 summary 更准确
            existing_ids = {r.get("recommendationid") for r in raw}
            for r in raw_all:
                if r.get("recommendationid") not in existing_ids:
                    raw.append(r)
                    existing_ids.add(r.get("recommendationid"))

        total    = summary_data.get("total_reviews", 0)
        positive = summary_data.get("total_positive", 0)

        reviews = []
        for r in raw:
            text = (r.get("review") or "").strip()
            if len(text) < 8:
                continue
            reviews.append({
                "text":       text[:400],
                "voted_up":   r.get("voted_up", True),
                "votes_up":   r.get("votes_up", 0),
                "playtime_h": round((r.get("author", {}).get("playtime_at_review", 0)) / 60, 1),
            })

        return {
            "summary": {
                "total":          total,
                "positive":       positive,
                "negative":       summary_data.get("total_negative", 0),
                "score_desc":     summary_data.get("review_score_desc", ""),
                "positive_ratio": round(positive / total * 100, 1) if total > 0 else 0,
            },
            "reviews":       reviews,
            "pages_fetched": max_pages,
        }
    except Exception as e:
        logger.warning("Steam 评论抓取失败 (appid=%s): %s", appid, e)
        return {"summary": {}, "reviews": [], "pages_fetched": 0}


def build_stats(reviews: List[Dict]) -> Dict:
    """计算评论玩时分布及各段好评率。"""
    buckets = {
        "casual":   {"label": "轻度体验 (<10h)",    "range": (0,   10),            "pos": 0, "neg": 0},
        "moderate": {"label": "标准游玩 (10-100h)",  "range": (10,  100),           "pos": 0, "neg": 0},
        "veteran":  {"label": "深度玩家 (>100h)",   "range": (100, float("inf")),  "pos": 0, "neg": 0},
    }
    for r in reviews:
        h = r.get("playtime_h", 0)
        for key, b in buckets.items():
            lo, hi = b["range"]
            if lo <= h < hi:
                if r.get("voted_up"):
                    b["pos"] += 1
                else:
                    b["neg"] += 1
                break
    result = {}
    for key, b in buckets.items():
        total = b["pos"] + b["neg"]
        result[key] = {
            "label": b["label"],
            "total": total,
            "pos":   b["pos"],
            "ratio": round(b["pos"] / total * 100) if total else None,
        }
    return result


def chunk_reviews(reviews: List[Dict], size: int = 100) -> List[List[Dict]]:
    """将评论列表切成固定大小批次。"""
    return [reviews[i:i + size] for i in range(0, len(reviews), size)]


def fetch_steam_reviews_bulk(appid: str, helpful_pages: int = 50, recent_pages: int = 10) -> Dict:
    """
    大批量抓取 Steam 评论，双通道：
      - helpful pass (filter=all)：按帮助度，代表社区共识
      - recent pass (filter=recent)：最新评论，代表当前口碑
    两组合并去重，返回 {summary, reviews, sample_count}
    """
    PER_PAGE = 100

    def _fetch_page(language: str, filter_by: str, cursor: str) -> Dict:
        resp = requests.get(
            f"https://store.steampowered.com/appreviews/{appid}",
            params={
                "json":          "1",
                "language":      language,
                "num_per_page":  PER_PAGE,
                "filter":        filter_by,
                "purchase_type": "all",
                "cursor":        cursor,
            },
            headers=_HEADERS,
            timeout=15,
        )
        return resp.json()

    def _collect_pass(filter_by: str, max_p: int, language: str = "schinese") -> tuple:
        collected, cursor, summary = [], "*", {}
        for page in range(max_p):
            try:
                data = _fetch_page(language, filter_by, cursor)
            except Exception as e:
                logger.warning("Steam bulk 请求失败 (filter=%s page=%d): %s", filter_by, page, e)
                break
            if data.get("success") != 1:
                break
            if page == 0:
                summary = data.get("query_summary", {})
            page_reviews = data.get("reviews", [])
            if not page_reviews:
                break
            collected.extend(page_reviews)
            new_cursor = data.get("cursor", "")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
            time.sleep(0.25)
        return collected, summary

    try:
        # Pass 1: 按帮助度（社区共识）
        helpful_raw, summary_data = _collect_pass("all", helpful_pages, "schinese")
        if len(helpful_raw) < 50:
            helpful_raw, summary_data = _collect_pass("all", helpful_pages, "all")

        # Pass 2: 最新评论（近期口碑）
        recent_raw, _ = _collect_pass("recent", recent_pages, "schinese")
        if len(recent_raw) < 20:
            recent_raw_all, _ = _collect_pass("recent", recent_pages, "all")
            if len(recent_raw_all) > len(recent_raw):
                recent_raw = recent_raw_all

        # 合并去重，标记 recent 来源
        recent_ids = {r.get("recommendationid") for r in recent_raw}
        seen_ids   = {r.get("recommendationid") for r in helpful_raw}
        for r in recent_raw:
            if r.get("recommendationid") not in seen_ids:
                helpful_raw.append(r)
                seen_ids.add(r.get("recommendationid"))

        total    = summary_data.get("total_reviews", 0)
        positive = summary_data.get("total_positive", 0)

        reviews = []
        for r in helpful_raw:
            text = (r.get("review") or "").strip()
            if len(text) < 10:
                continue
            reviews.append({
                "text":       text[:500],
                "voted_up":   r.get("voted_up", True),
                "votes_up":   r.get("votes_up", 0),
                "playtime_h": round((r.get("author", {}).get("playtime_at_review", 0)) / 60, 1),
                "is_recent":  r.get("recommendationid") in recent_ids,
            })

        logger.info("Steam bulk 抓取完成：样本 %d 条（总评论 %d）", len(reviews), total)
        return {
            "summary": {
                "total":          total,
                "positive":       positive,
                "negative":       summary_data.get("total_negative", 0),
                "score_desc":     summary_data.get("review_score_desc", ""),
                "positive_ratio": round(positive / total * 100, 1) if total > 0 else 0,
            },
            "reviews":      reviews,
            "sample_count": len(reviews),
        }
    except Exception as e:
        logger.warning("Steam bulk 抓取失败 (appid=%s): %s", appid, e)
        return {"summary": {}, "reviews": [], "sample_count": 0}


def build_stats_block(game_name: str, summary: Dict, reviews: List[Dict]) -> str:
    """生成纯统计摘要块（不含原始评论文本），用于批量 AI 分析流程。"""
    s            = summary
    total_sample = len(reviews)

    block = (
        f"【Steam 统计数据】{game_name}\n"
        f"总评：{s.get('score_desc', '未知')} "
        f"（好评率 {s.get('positive_ratio', 0)}%，全平台 {s.get('total', 0):,} 条）\n"
        f"本次抓取样本：{total_sample} 条\n"
    )

    stats = build_stats(reviews)
    for v in stats.values():
        if v["total"] > 0:
            ratio_str = f"{v['ratio']}% 好评" if v["ratio"] is not None else "无数据"
            block += f"  · {v['label']}：{v['total']} 条，{ratio_str}\n"

    recent = [r for r in reviews if r.get("is_recent")]
    if recent:
        recent_pos   = sum(1 for r in recent if r["voted_up"])
        recent_ratio = round(recent_pos / len(recent) * 100) if recent else 0
        block += f"近期样本（{len(recent)} 条）好评率：{recent_ratio}%\n"

    pos_total = sum(1 for r in reviews if r["voted_up"])
    neg_total = len(reviews) - pos_total
    block += f"样本好评：{pos_total} 条 / 差评：{neg_total} 条\n"

    return block


def format_for_deep_analysis(game_name: str, summary: Dict, reviews: List[Dict],
                              max_pos: int = 25, max_neg: int = 15,
                              max_recent_pos: int = 8, max_recent_neg: int = 5) -> str:
    """格式化供深度 AI 长文生成用的评论文本，含统计 + 帮助度代表评论 + 近期评论。"""
    s           = summary
    total_sample = len(reviews)

    header = (
        f"【Steam深度评论数据】{game_name}\n"
        f"总评：{s.get('score_desc', '未知')} "
        f"（好评率 {s.get('positive_ratio', 0)}%，全平台 {s.get('total', 0):,} 条）\n"
        f"本次抓取样本：{total_sample} 条（帮助度优先 + 最新双通道）\n"
    )

    # 玩时分布
    stats = build_stats(reviews)
    dist_lines = []
    for v in stats.values():
        if v["total"] > 0:
            ratio_str = f"{v['ratio']}% 好评" if v["ratio"] is not None else "无数据"
            dist_lines.append(f"  · {v['label']}：{v['total']} 条，{ratio_str}")
    if dist_lines:
        header += "【玩时分布好评率】\n" + "\n".join(dist_lines) + "\n"

    # 近期趋势
    recent = [r for r in reviews if r.get("is_recent")]
    if recent:
        recent_pos   = sum(1 for r in recent if r["voted_up"])
        recent_ratio = round(recent_pos / len(recent) * 100) if recent else 0
        header += f"【近期口碑（最新样本 {len(recent)} 条）】好评率 {recent_ratio}%\n"

    def fmt(r, max_len=250):
        return f"▲{r['votes_up']} [{r['playtime_h']}h] {r['text'][:max_len]}"

    helpful_pos  = sorted([r for r in reviews if r["voted_up"]  and not r.get("is_recent")], key=lambda r: r["votes_up"], reverse=True)[:max_pos]
    helpful_neg  = sorted([r for r in reviews if not r["voted_up"] and not r.get("is_recent")], key=lambda r: r["votes_up"], reverse=True)[:max_neg]
    recent_pos_r = [r for r in reviews if r.get("is_recent") and     r["voted_up"]][:max_recent_pos]
    recent_neg_r = [r for r in reviews if r.get("is_recent") and not r["voted_up"]][:max_recent_neg]

    sections = [header]
    if helpful_pos:
        sections.append("【最高票好评·社区共识】\n" + "\n".join(fmt(r) for r in helpful_pos))
    if helpful_neg:
        sections.append("【最高票差评·集中槽点】\n" + "\n".join(fmt(r) for r in helpful_neg))
    if recent_pos_r:
        sections.append("【近期好评·最新口碑】\n" + "\n".join(fmt(r, 150) for r in recent_pos_r))
    if recent_neg_r:
        sections.append("【近期差评·最新槽点】\n" + "\n".join(fmt(r, 150) for r in recent_neg_r))

    return "\n\n".join(sections)[:9000]


def format_for_ai(game_name: str, appid: str, summary: Dict, reviews: List[Dict],
                  max_pos: int = 15, max_neg: int = 8) -> str:
    """将 Steam 评论格式化为供 AI 深度分析的文本（含统计信息 + 玩时分布 + 代表性评论）。"""
    s        = summary
    sampled  = len(reviews)
    header   = (
        f"【Steam玩家评价·深度分析】{game_name}\n"
        f"总评：{s.get('score_desc', '未知')} "
        f"（好评率 {s.get('positive_ratio', 0)}%，全平台共 {s.get('total', 0):,} 条评论）\n"
        f"本次抓取样本：{sampled} 条\n"
    )

    # 玩时分布
    stats = build_stats(reviews)
    dist_lines = []
    for v in stats.values():
        if v["total"] > 0:
            ratio_str = f"{v['ratio']}% 好评" if v["ratio"] is not None else "无数据"
            dist_lines.append(f"  · {v['label']}：{v['total']} 条，{ratio_str}")
    if dist_lines:
        header += "【玩时分布好评率】\n" + "\n".join(dist_lines) + "\n"

    pos_reviews = sorted(
        [r for r in reviews if r["voted_up"]],
        key=lambda r: r["votes_up"], reverse=True
    )[:max_pos]
    neg_reviews = sorted(
        [r for r in reviews if not r["voted_up"]],
        key=lambda r: r["votes_up"], reverse=True
    )[:max_neg]

    pos_text = "\n".join(
        f"▲{r['votes_up']} [{r['playtime_h']}h] {r['text'][:200]}" for r in pos_reviews
    ) or "（暂无）"
    neg_text = "\n".join(
        f"▲{r['votes_up']} [{r['playtime_h']}h] {r['text'][:200]}" for r in neg_reviews
    ) or "（暂无）"

    result = f"{header}\n【代表性好评（按有用数排序）】\n{pos_text}\n\n【代表性差评（按有用数排序）】\n{neg_text}"
    return result[:5000]
