"""热门推荐评分：规则打分（不消耗 API）+ 可选 AI 精排。"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 免费/折扣关键词
_FREE_KW = ["免费", "free", "喜加一", "限免", "0元", "限时免费", "白嫖"]

# 高流量热词（每个 +5，合计上限 20）
_HOT_KW = [
    "新版本", "更新", "联动", "新赛季", "新角色", "限定", "公测",
    "首测", "活动", "爆料", "up池", "卡池", "新地图", "新职业",
    "dlc", "大更新", "重磅", "首发", "独家", "破防", "整活",
]


def rule_score(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单条内容进行规则打分（0-100），不消耗 API。

    Returns:
        dict with keys: trending_score (int), trending_reason (str)
    """
    score = 0
    reasons = []

    title = (item.get("title") or "").lower()
    content = (item.get("content") or item.get("summary") or "").lower()
    combined = title + " " + content

    # ── 折扣力度 ──────────────────────────────────────
    discount_str = (item.get("discount") or "").lower()
    m = re.search(r"(\d+)", discount_str)
    if m:
        pct = int(m.group(1))
        if pct >= 100:
            score += 40
            reasons.append("100%折扣(免费)")
        elif pct >= 75:
            score += 30
            reasons.append(f"{pct}%折扣")
        elif pct >= 50:
            score += 20
            reasons.append(f"{pct}%折扣")
        elif pct >= 25:
            score += 10
            reasons.append(f"{pct}%折扣")

    # ── 免费关键词 ─────────────────────────────────────
    for kw in _FREE_KW:
        if kw in combined:
            score += 25
            reasons.append(f"含「{kw}」")
            break  # 只加一次

    # ── 热门关键词 ─────────────────────────────────────
    hot_found = []
    for kw in _HOT_KW:
        if kw in combined:
            hot_found.append(kw)
    if hot_found:
        add = min(len(hot_found) * 5, 20)
        score += add
        reasons.append(f"热词：{'、'.join(hot_found[:4])}")

    # ── Weibo 互动分 ───────────────────────────────────
    weibo_score = item.get("score") or 0
    if isinstance(weibo_score, (int, float)) and weibo_score > 0:
        if weibo_score > 10000:
            score += 20
            reasons.append(f"微博热度{weibo_score:,}")
        elif weibo_score > 1000:
            score += 10
            reasons.append(f"微博热度{weibo_score:,}")
        elif weibo_score > 100:
            score += 5
            reasons.append(f"微博热度{weibo_score:,}")

    # ── Steam Metacritic 评分 ──────────────────────────
    review = (item.get("_review") or item.get("content") or "")
    m2 = re.search(r"metacritic[^\d]*(\d+)", review, re.IGNORECASE)
    if m2 and int(m2.group(1)) >= 80:
        score += 10
        reasons.append(f"Metacritic {m2.group(1)}")

    # ── 来源权重加成 ───────────────────────────────────
    source = item.get("source") or ""
    label = (item.get("label") or "").lower()
    if source == "deals" and label == "epic":
        score += 5   # Epic 免费游戏通常流量大
        reasons.append("Epic免费")

    score = min(score, 100)
    reason_str = "、".join(reasons) if reasons else "暂无明显热点"

    return {
        "trending_score": score,
        "trending_reason": reason_str,
    }


def score_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    批量打分，直接修改每条 item，并按分数降序排列。
    Returns 原列表（已修改）。
    """
    for item in items:
        result = rule_score(item)
        item["trending_score"] = result["trending_score"]
        item["trending_reason"] = result["trending_reason"]

    items.sort(key=lambda x: x.get("trending_score", 0), reverse=True)
    return items
