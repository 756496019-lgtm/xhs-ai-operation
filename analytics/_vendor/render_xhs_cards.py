#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书周报双风格 HTML 渲染器
=============================
读取 Claude 生成的 cards_content.json + 榜单数据 → 输出暗黑雷达局 + 奶油杂志感双风格 HTML。

用法：
  python render_xhs_cards.py --cards weekly_cache/cards_content_0406_0412.json
  python render_xhs_cards.py --cards cards.json --ranks weekly_cache/daily_ranks.json --week "4.06-4.12"
  python render_xhs_cards.py --cards cards.json --output my_output.html

cards_content.json 格式：
{
  "meta": {
    "week_label": "4.06-4.12",      // 周期标签
    "week_code": "W16",              // 第几周
    "year": 2026,
    "start_date": "2026-04-06",
    "end_date": "2026-04-12"
  },
  "cover": {
    "title_line1": "恋与深空",       // 大标题行1
    "title_line2": "破68亿",         // 大标题行2（强调色）
    "subtitle": "手游出海不只靠SLG了，还有6件大事",
    "summaries": [                   // 封面3条摘要
      {"tag": "3月收入榜", "color": "green", "text": "恋与深空破68亿，三七单游戏近11倍爆发"},
      {"tag": "AI×游戏", "color": "orange", "text": "《崇祯》三测留存78.3% · AI乙游上线"},
      {"tag": "国单争议", "color": "red", "text": "《明末》团队爆发劳资争议，双方各执一词"}
    ]
  },
  "cards": [
    {
      "type": "content",             // content | rank | ai
      "topic_tag": "收入榜",
      "topic_color": "gold",         // orange/gold/green/blue/purple/red/cyan
      "date_label": "4.09",
      "subtitle": "Sensor Tower · 2026年3月",
      "title": "3月全球手游收入榜",
      "body_html": "...",            // 卡片主体内容的内联HTML（Claude直接生成）
      "insight": "雷达洞察文本..."   // 底部洞察/观点（可选）
    },
    ...
  ],
  "rank_card": {                     // 可选：榜单异动卡
    "anomalies": [
      {"region": "中国大陆", "chart": "免费榜", "app": "xxx", "change": "↑5", "rank": 3},
      ...
    ]
  }
}
"""
import argparse
import html
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ═══════════════════════════════════════════════════════════════
# 色板
# ═══════════════════════════════════════════════════════════════

DARK = {
    "name": "暗黑雷达局",
    "prefix": "a",
    "bg": "#0C1520",
    "text": "#EAF0F8",
    "text_secondary": "#6A8898",
    "text_muted": "#5A7888",
    "text_dim": "#4A6070",
    "text_dark": "#3A5060",
    "primary": "#E8820C",
    "accent_gold": "#F5B820",
    "accent_green": "#4ADE80",
    "accent_blue": "#4A90D9",
    "accent_purple": "#A78BFA",
    "accent_red": "#E86060",
    "accent_cyan": "#22D3EE",
    "divider": "#1A2D40",
    "data_bg": "#0A1218",
    "card_alt_bg": "#141E2E",
    "insight_bg": "#080F18",
    "insight_border": "#1A2D40",
    "insight_label_color": None,  # 用 topic_color
    "insight_text": "#6A7A90",
    "footer_bg": "#E8820C",
    "footer_text": "#fff",
    "footer_sub": "rgba(255,255,255,0.7)",
    "footer_label": "WEEKLY BRIEF",
    "top_bar_height": "3px",
    "section_class": "section-dark",
}

CREAM = {
    "name": "奶油杂志感",
    "prefix": "b",
    "bg": "#FFFDF9",
    "text": "#2C2C2C",
    "text_secondary": "#5A4F46",
    "text_muted": "#7A6F67",
    "text_dim": "#9A8A80",
    "text_dark": "#C9B99A",
    "primary": "#C0392B",
    "accent_gold": "#E8B86D",
    "accent_green": "#5B8A5A",
    "accent_blue": "#4A90D9",
    "accent_purple": "#8B6CAA",
    "accent_red": "#E8686A",
    "accent_cyan": "#2E8B8B",
    "divider": "#EAE0D0",
    "data_bg": "#FFF8F0",
    "card_alt_bg": "#FFF5F0",
    "insight_bg": "#FFF0E6",
    "insight_border": "#F5E6D0",
    "insight_label_color": None,
    "insight_text": "#7A6F67",
    "footer_bg": "#2C2C2C",
    "footer_text": "#E8B86D",
    "footer_sub": "rgba(232,184,109,0.6)",
    "footer_label": "WEEKLY",
    "top_bar_height": "2px",
    "border": "1px solid #EAE0D0",
    "shadow": "0 4px 16px rgba(0,0,0,0.08)",
    "section_class": "section-cream",
}

# topic_color → 色值映射
def _resolve_color(style: dict, color_name: str) -> str:
    """将 color name 映射到实际色值。"""
    mapping = {
        "orange": style["primary"] if style["prefix"] == "a" else "#C0392B",
        "gold": style["accent_gold"],
        "green": style["accent_green"],
        "blue": style["accent_blue"],
        "purple": style["accent_purple"],
        "red": style["accent_red"],
        "cyan": style["accent_cyan"],
    }
    return mapping.get(color_name, style["primary"])


FONT_STACK = "'PingFang SC','Noto Sans SC','Microsoft YaHei',sans-serif"


# ═══════════════════════════════════════════════════════════════
# 卡片渲染函数
# ═══════════════════════════════════════════════════════════════

def _card_wrapper_open(style: dict, card_id: str, fixed_height: int = 0) -> str:
    """卡片外壳开始标签。"""
    h = f"height:{fixed_height}px;" if fixed_height else ""
    extra = ""
    if style["prefix"] == "b":
        extra = f"border:{style.get('border','')};box-shadow:{style.get('shadow','')};"
    return (
        f'<div id="{card_id}" style="width:375px;{h}background:{style["bg"]};'
        f'overflow:hidden;font-family:{FONT_STACK};{extra}'
        f'display:flex;flex-direction:column;">\n'
    )


def _top_bar(style: dict, color: str) -> str:
    """顶部色条。"""
    if style["prefix"] == "a":
        return f'  <div style="height:{style["top_bar_height"]};background:{color};flex-shrink:0;"></div>\n'
    else:
        return (
            f'  <div style="background-color:{style["data_bg"]};border-bottom:2px solid {color};'
            f'padding:6px 14px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">\n'
            f'    <span style="color:{color};font-size:10px;font-weight:800;letter-spacing:2px;">&#9632; GAME RADAR HQ</span>\n'
            f'    <span style="color:{style["text_dark"]};font-size:10px;letter-spacing:1px;">{{header_right}}</span>\n'
            f'  </div>\n'
        )


def _header_line(style: dict, tag_text: str, tag_color: str, right_text: str) -> str:
    """GAME RADAR · tag 行。"""
    if style["prefix"] == "a":
        return (
            f'  <div style="padding:12px 18px 0;display:flex;justify-content:space-between;'
            f'align-items:center;flex-shrink:0;">\n'
            f'    <span style="font-size:9px;color:{tag_color};font-weight:700;letter-spacing:3px;">'
            f'GAME RADAR · {html.escape(tag_text)}</span>\n'
            f'    <span style="font-size:9px;color:{style["text_dark"]};">{html.escape(right_text)}</span>\n'
            f'  </div>\n'
        )
    else:
        # Cream 用 top_bar 代替 header
        return ""


def _footer(style: dict) -> str:
    """底部品牌栏。"""
    return (
        f'  <div style="background:{style["footer_bg"]};padding:9px 18px;'
        f'display:flex;justify-content:space-between;align-items:center;flex-shrink:0;">\n'
        f'    <span style="color:{style["footer_text"]};font-size:11px;font-weight:800;'
        f'letter-spacing:1px;">游戏雷达局</span>\n'
        f'    <span style="color:{style["footer_sub"]};font-size:9px;'
        f'letter-spacing:3px;">{style["footer_label"]}</span>\n'
        f'  </div>\n'
    )


def _insight_box(style: dict, color: str, text: str) -> str:
    """雷达洞察 / 编辑观点框。"""
    label = "雷达洞察" if style["prefix"] == "a" else "编辑观点"
    if style["prefix"] == "a":
        return (
            f'  <div style="padding:14px 18px;flex-shrink:0;">\n'
            f'    <div style="background:{style["insight_bg"]};border:1px solid {style["insight_border"]};'
            f'padding:10px 12px;">\n'
            f'      <div style="font-size:10px;color:{color};font-weight:700;letter-spacing:1px;'
            f'margin-bottom:5px;">{label}</div>\n'
            f'      <div style="font-size:10px;color:{style["insight_text"]};line-height:1.7;'
            f'font-style:italic;">{text}</div>\n'
            f'    </div>\n'
            f'  </div>\n'
        )
    else:
        return (
            f'  <div style="padding:10px 14px;flex-shrink:0;">\n'
            f'    <table cellpadding="0" cellspacing="0" width="100%"><tr>\n'
            f'      <td width="3" bgcolor="{color}" style="background-color:{color};"> </td>\n'
            f'      <td bgcolor="{style["insight_bg"]}" style="background-color:{style["insight_bg"]};'
            f'padding:6px 9px;border:1px solid {style["insight_border"]}">\n'
            f'        <div style="font-size:9px;color:{color};font-weight:700;margin-bottom:3px;">{label}</div>\n'
            f'        <div style="font-size:10px;color:{style["insight_text"]};line-height:1.6;">{text}</div>\n'
            f'      </td>\n'
            f'    </tr></table>\n'
            f'  </div>\n'
        )


# ── 封面卡 ──

def render_cover_card(style: dict, cover: dict, meta: dict, total_cards: int,
                      footer_fn=None) -> str:
    """渲染封面卡（固定 500px）。"""
    p = style["prefix"]
    card_id = f"card_{p}1"
    color = style["primary"]
    week_code = meta.get("week_code", "W??")
    week_label = meta.get("week_label", "")
    year = meta.get("year", 2026)

    # 超过3条摘要时取消固定高度，让卡片自适应
    n_summaries = len(cover.get("summaries", []))
    cover_h = 0 if n_summaries > 3 else 500
    parts = [_card_wrapper_open(style, card_id, fixed_height=cover_h)]

    # 顶部色条（暗黑用渐变，奶油用品牌栏）
    if p == "a":
        parts.append(
            f'  <div style="height:3px;background:linear-gradient(90deg,{color} 0%,{style["accent_gold"]} 60%,'
            f'transparent 100%);flex-shrink:0;"></div>\n'
        )
        parts.append(
            f'  <div style="padding:16px 18px 0;display:flex;justify-content:space-between;'
            f'align-items:center;flex-shrink:0;">\n'
            f'    <span style="font-size:10px;color:{color};font-weight:800;letter-spacing:3px;">GAME RADAR</span>\n'
            f'    <span style="font-size:10px;color:{style["text_dark"]};letter-spacing:2px;">'
            f'{year} · {week_code}</span>\n'
            f'  </div>\n'
        )
    else:
        parts.append(
            f'  <div style="background-color:{style["data_bg"]};border-bottom:2px solid {color};'
            f'padding:8px 14px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">\n'
            f'    <span style="color:{color};font-size:10px;font-weight:800;letter-spacing:2px;">'
            f'&#9632; GAME RADAR HQ</span>\n'
            f'    <span style="color:{style["text_dark"]};font-size:10px;letter-spacing:1px;">'
            f'{year} · {week_code}</span>\n'
            f'  </div>\n'
        )

    # 标题区（右对齐）
    date_text = f"{week_label} · 游戏行业周报"
    title1 = cover.get("title_line1", "")
    title2 = cover.get("title_line2", "")
    subtitle = cover.get("subtitle", "")
    # compact 模式下缩小标题区
    title_pad = "16px 18px 10px" if n_summaries > 3 else "24px 18px 16px"
    title_sz = "36px" if n_summaries > 3 else "42px"
    sub_sz = "13px" if n_summaries > 3 else "15px"

    if p == "a":
        parts.append(
            f'  <div style="padding:{title_pad};flex-shrink:0;text-align:right;">\n'
            f'    <div style="font-size:11px;color:{style["text_dark"]};letter-spacing:2px;margin-bottom:6px;">'
            f'{html.escape(date_text)}</div>\n'
            f'    <div style="font-size:{title_sz};font-weight:900;color:{style["text"]};'
            f'line-height:1.05;letter-spacing:-1px;">{html.escape(title1)}</div>\n'
            f'    <div style="font-size:{title_sz};font-weight:900;color:{color};'
            f'line-height:1.05;letter-spacing:-1px;">{html.escape(title2)}</div>\n'
            f'    <div style="font-size:{sub_sz};font-weight:700;color:{style["text_secondary"]};'
            f'line-height:1.4;margin-top:8px;">{html.escape(subtitle)}</div>\n'
            f'    <div style="width:40px;height:3px;background:{color};margin-top:8px;margin-left:auto;"></div>\n'
            f'  </div>\n'
        )
    else:
        title_pad_b = "14px 14px 10px" if n_summaries > 3 else "20px 14px 14px"
        title_sz_b = "32px" if n_summaries > 3 else "38px"
        parts.append(
            f'  <div style="padding:{title_pad_b};flex-shrink:0;text-align:right;">\n'
            f'    <div style="font-size:10px;color:{style["text_dim"]};letter-spacing:2px;margin-bottom:6px;">'
            f'{html.escape(date_text)}</div>\n'
            f'    <div style="font-size:{title_sz_b};font-weight:900;color:{style["text"]};'
            f'line-height:1.05;letter-spacing:-1px;">{html.escape(title1)}</div>\n'
            f'    <div style="font-size:{title_sz_b};font-weight:900;color:{color};'
            f'line-height:1.05;letter-spacing:-1px;">{html.escape(title2)}</div>\n'
            f'    <div style="font-size:14px;font-weight:700;color:{style["text_muted"]};'
            f'line-height:1.4;margin-top:10px;">{html.escape(subtitle)}</div>\n'
            f'    <div style="width:40px;height:2px;background:{color};margin-top:10px;margin-left:auto;"></div>\n'
            f'  </div>\n'
        )

    # 摘要条目
    summaries = cover.get("summaries", [])
    # 超过3条时缩小样式以适配封面
    compact = len(summaries) > 3
    gap = "4px" if compact else "6px"
    pad = "6px 10px" if compact else "8px 10px"
    tag_size = "8px" if compact else "9px"
    text_size = "12px" if compact else "13px"
    parts.append(
        f'  <div style="margin:0 18px;flex:1;display:flex;flex-direction:column;'
        f'justify-content:flex-start;gap:{gap};">\n'
    )
    for s in summaries:
        sc = _resolve_color(style, s.get("color", "green"))
        tag = s.get("tag", "")
        text = s.get("text", "")
        sub = s.get("sub", "")
        sub_html = ""
        if sub:
            sub_color = style["text_secondary"] if p == "a" else style["text_muted"]
            sub_html = (
                f'      <div style="font-size:10px;color:{sub_color};'
                f'margin-top:2px;line-height:1.4;">{html.escape(sub)}</div>\n'
            )
        if p == "a":
            parts.append(
                f'    <div style="border-left:3px solid {sc};padding:{pad};'
                f'background:rgba({_hex_to_rgb(sc)},0.06);">\n'
                f'      <div style="font-size:{tag_size};color:{sc};font-weight:700;letter-spacing:2px;'
                f'margin-bottom:2px;">{html.escape(tag)}</div>\n'
                f'      <div style="font-size:{text_size};font-weight:800;color:{style["text"]};'
                f'line-height:1.3;">{html.escape(text)}</div>\n'
                f'{sub_html}'
                f'    </div>\n'
            )
        else:
            parts.append(
                f'    <div style="border-left:3px solid {sc};padding:{pad};'
                f'background:{style["card_alt_bg"]};">\n'
                f'      <div style="font-size:{tag_size};color:{sc};font-weight:700;letter-spacing:2px;'
                f'margin-bottom:2px;">{html.escape(tag)}</div>\n'
                f'      <div style="font-size:{text_size};font-weight:800;color:{style["text"]};'
                f'line-height:1.3;">{html.escape(text)}</div>\n'
                f'{sub_html}'
                f'    </div>\n'
            )
    parts.append('  </div>\n')

    # 左滑引导
    n = total_cards - 1
    parts.append(
        f'  <div style="padding:8px 18px 6px;flex-shrink:0;">\n'
        f'    <div style="font-size:10px;color:{style["text_dark"]};text-align:center;'
        f'letter-spacing:1px;">▸ 左滑查看全部 {n} 张卡片</div>\n'
        f'  </div>\n'
    )

    # 底部
    parts.append((footer_fn or _footer)(style))
    parts.append('</div>\n')
    return "".join(parts)


# ── 内容卡 ──

def render_content_card(style: dict, card_num: int, card: dict,
                        footer_fn=None) -> str:
    """渲染内容卡片。card['body_html'] 是 Claude 生成的内联 HTML 主体。"""
    p = style["prefix"]
    card_id = f"card_{p}{card_num}"
    topic_tag = card.get("topic_tag", "")
    color_name = card.get("topic_color", "orange")
    color = _resolve_color(style, color_name)
    date_label = card.get("date_label", "")
    body_html = card.get("body_html", "")
    insight = card.get("insight", "")

    parts = [_card_wrapper_open(style, card_id)]

    # 顶部
    if p == "a":
        parts.append(f'  <div style="height:3px;background:{color};flex-shrink:0;"></div>\n')
        parts.append(_header_line(style, topic_tag, color, date_label))
    else:
        parts.append(
            f'  <div style="background-color:{style["data_bg"]};border-bottom:2px solid {color};'
            f'padding:6px 14px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">\n'
            f'    <span style="color:{color};font-size:10px;font-weight:800;letter-spacing:2px;">'
            f'&#9632; GAME RADAR HQ</span>\n'
            f'    <span style="color:{style["text_dark"]};font-size:10px;letter-spacing:1px;">'
            f'{html.escape(topic_tag)} · {html.escape(date_label)}</span>\n'
            f'  </div>\n'
        )

    # 主体（Claude 生成的 HTML）
    # 外层注入 color + strong 颜色，body_html 内部不需要写死颜色
    parts.append(f'  <div style="flex:1;color:{style["text"]};">\n')
    # 自动给 <strong> 上色：暗黑用主文字色，奶油用主色
    styled_body = body_html
    strong_color = style["text"] if p == "a" else style["primary"]
    # 给无 style 的 <strong> 添加颜色
    import re as _re
    styled_body = _re.sub(
        r'<strong(?![^>]*style)>',
        f'<strong style="color:{strong_color};">',
        styled_body
    )
    # 修复副文本颜色：font-size:11px 的 div 用 text_muted
    styled_body = styled_body.replace(
        'font-size:11px;line-height:1.7;',
        f'font-size:11px;line-height:1.7;color:{style["text_muted"]};'
    )
    styled_body = styled_body.replace(
        'font-size:11px;line-height:1.9;',
        f'font-size:11px;line-height:1.9;color:{style["text_muted"]};'
    )
    # 修复来源行颜色
    styled_body = styled_body.replace(
        'font-size:11px;letter-spacing:1px;',
        f'font-size:11px;letter-spacing:1px;color:{style["text_secondary"]};'
    )
    parts.append(styled_body)
    parts.append(f'  </div>\n')

    # 洞察
    if insight:
        parts.append(_insight_box(style, color, insight))

    # 底部
    parts.append((footer_fn or _footer)(style))
    parts.append('</div>\n')
    return "".join(parts)


# ── 榜单异动卡 ──

def render_rank_card(style: dict, card_num: int, rank_card: dict,
                     footer_fn=None) -> str:
    """渲染榜单异动卡片。"""
    p = style["prefix"]
    card_id = f"card_{p}{card_num}"
    color = style["accent_gold"]
    anomalies = rank_card.get("anomalies", [])

    if not anomalies:
        return ""

    parts = [_card_wrapper_open(style, card_id)]

    # 顶部
    if p == "a":
        parts.append(f'  <div style="height:3px;background:{color};flex-shrink:0;"></div>\n')
        parts.append(_header_line(style, "榜单异动", color, "七麦数据"))
    else:
        parts.append(
            f'  <div style="background-color:{style["data_bg"]};border-bottom:2px solid {color};'
            f'padding:6px 14px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">\n'
            f'    <span style="color:{color};font-size:10px;font-weight:800;letter-spacing:2px;">'
            f'&#9632; GAME RADAR HQ</span>\n'
            f'    <span style="color:{style["text_dark"]};font-size:10px;letter-spacing:1px;">'
            f'榜单异动 · 七麦数据</span>\n'
            f'  </div>\n'
        )

    # 标题
    if p == "a":
        parts.append(
            f'  <div style="padding:18px 18px 14px;border-bottom:1px solid {style["divider"]};flex-shrink:0;">\n'
            f'    <div style="font-size:22px;font-weight:900;color:{style["text"]};'
            f'line-height:1.2;margin-bottom:6px;">全球七区榜单异动速览</div>\n'
            f'    <div style="font-size:11px;color:{style["text_secondary"]};line-height:1.5;">'
            f'CN/US/JP/KR/BR/TH/IN · 排名变化≥3 或新上榜</div>\n'
            f'  </div>\n'
        )
    else:
        parts.append(
            f'  <div style="padding:14px 14px 10px;border-bottom:1px solid {style["divider"]};flex-shrink:0;">\n'
            f'    <div style="font-size:18px;font-weight:900;color:{style["text"]};'
            f'line-height:1.2;margin-bottom:4px;">全球七区榜单异动速览</div>\n'
            f'    <div style="font-size:10px;color:{style["text_muted"]};line-height:1.5;">'
            f'CN/US/JP/KR/BR/TH/IN · 排名变化≥3 或新上榜</div>\n'
            f'  </div>\n'
        )

    # 异动列表
    parts.append(f'  <div style="padding:10px 18px;flex:1;">\n')
    for i, a in enumerate(anomalies[:12]):
        app = a.get("app", "")
        region = a.get("region", "")
        chart = a.get("chart", "")
        change = a.get("change", "")
        rank = a.get("rank", "?")

        is_new = "新上榜" in change
        change_color = style["accent_purple"] if is_new else style["accent_green"]
        bg = style["card_alt_bg"] if i % 2 == 0 else style["data_bg"]

        if p == "a":
            parts.append(
                f'    <div style="display:flex;align-items:center;gap:6px;padding:5px 8px;'
                f'background:{bg};border-left:2px solid {change_color};margin-bottom:3px;">\n'
                f'      <span style="font-size:10px;color:{change_color};font-weight:800;min-width:50px;">'
                f'{html.escape(change)}</span>\n'
                f'      <span style="font-size:10px;color:{style["text"]};font-weight:700;flex:1;">'
                f'《{html.escape(app)}》</span>\n'
                f'      <span style="font-size:9px;color:{style["text_dim"]};">'
                f'{html.escape(region)} {html.escape(chart)} #{rank}</span>\n'
                f'    </div>\n'
            )
        else:
            parts.append(
                f'    <div style="display:flex;align-items:center;gap:6px;padding:5px 8px;'
                f'background:{bg};border-left:2px solid {change_color};margin-bottom:3px;">\n'
                f'      <span style="font-size:10px;color:{change_color};font-weight:800;min-width:50px;">'
                f'{html.escape(change)}</span>\n'
                f'      <span style="font-size:10px;color:{style["text"]};font-weight:700;flex:1;">'
                f'《{html.escape(app)}》</span>\n'
                f'      <span style="font-size:9px;color:{style["text_dim"]};">'
                f'{html.escape(region)} {html.escape(chart)} #{rank}</span>\n'
                f'    </div>\n'
            )
    parts.append(f'  </div>\n')

    # 底部
    parts.append((footer_fn or _footer)(style))
    parts.append('</div>\n')
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════
# B站动态模式
# ═══════════════════════════════════════════════════════════════

def _footer_bilibili(style: dict) -> str:
    """B站动态专用底部栏。"""
    return (
        f'  <div style="background:{style["footer_bg"]};padding:9px 18px;'
        f'display:flex;justify-content:space-between;align-items:center;flex-shrink:0;">\n'
        f'    <span style="color:{style["footer_text"]};font-size:11px;font-weight:800;'
        f'letter-spacing:1px;">游戏雷达局</span>\n'
        f'    <span style="color:{style["footer_sub"]};font-size:9px;'
        f'letter-spacing:2px;">关注 · 每周更新</span>\n'
        f'  </div>\n'
    )


def render_bilibili_html(data: dict) -> str:
    """
    渲染 B站动态专用 HTML（仅暗黑风格，≤9 张卡片）。

    - 只渲染 DARK 风格
    - 自动检测并合并相邻的榜单内容卡为单张
    - pixelRatio: 4（1500px）
    - 使用 B站专用底栏
    """
    meta = data.get("meta", {})
    cover = data.get("cover", {})
    cards = data.get("cards", [])

    week_label = meta.get("week_label", "")
    parts_ws = week_label.split("-")
    if len(parts_ws) == 2:
        s = parts_ws[0].strip().replace(".", "").zfill(4)
        e = parts_ws[1].strip().replace(".", "").zfill(4)
        week_short = f"{s}_{e}"
    else:
        week_short = week_label.replace(".", "").replace("-", "_")

    sty = DARK
    ffn = _footer_bilibili

    # 合并相邻榜单卡：如果最后两张 topic_tag 都是 "榜单"，合并为一张
    merged_cards = list(cards)
    if (len(merged_cards) >= 2
            and merged_cards[-1].get("topic_tag") == "榜单"
            and merged_cards[-2].get("topic_tag") == "榜单"):
        card_a = merged_cards[-2]
        card_b = merged_cards[-1]
        merged_body = card_a.get("body_html", "") + card_b.get("body_html", "")
        merged_insight = (card_a.get("insight", "") + " " + card_b.get("insight", "")).strip()
        merged_card = {
            "type": "content",
            "topic_tag": "榜单",
            "topic_color": card_a.get("topic_color", "gold"),
            "date_label": card_a.get("date_label", ""),
            "title": "四区 App Store 榜单",
            "body_html": merged_body,
            "insight": merged_insight,
        }
        merged_cards = merged_cards[:-2] + [merged_card]

    total = 1 + len(merged_cards)

    rendered = []
    rendered.append(render_cover_card(sty, cover, meta, total, footer_fn=ffn))
    for i, c in enumerate(merged_cards):
        rendered.append(render_content_card(sty, i + 2, c, footer_fn=ffn))

    return _BILIBILI_HTML_TEMPLATE.format(
        title=f"游戏行业周报 · {week_label} · B站动态",
        week_short=week_short,
        total=total,
        dark_cards="\n\n".join(rendered),
    )


_BILIBILI_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #18181B;
  font-family: 'PingFang SC','Noto Sans SC','Microsoft YaHei',sans-serif;
  padding: 28px 20px 80px;
}}
.tip {{
  text-align: center;
  color: #aaa;
  font-size: 12px;
  background: #27272A;
  padding: 12px 20px;
  border-radius: 8px;
  max-width: 1700px;
  margin: 0 auto 28px;
  line-height: 1.8;
  border: 1px solid #3F3F46;
}}
.section-wrap  {{ max-width: 1700px; margin: 0 auto 40px; }}
.section-title {{
  max-width: 1700px; margin: 0 auto 14px;
  font-size: 13px; font-weight: 800; letter-spacing: 2px;
  padding: 8px 16px; border-radius: 4px;
  display: inline-flex; align-items: center; gap: 8px;
  color: #E8820C; background: #1C1008; border: 1px solid #3A2A10;
}}
.cards-row {{
  display: flex; flex-direction: row; gap: 20px;
  justify-content: flex-start; flex-wrap: wrap;
  align-items: flex-start;
}}
.dl-btn {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; padding: 6px 18px;
  border-radius: 3px; cursor: pointer; border: none;
  letter-spacing: 1px; margin-top: 8px;
  background: #E8820C; color: #fff;
}}
.dl-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
</style>
</head>
<body>

<div class="tip">
  B站动态预览 · 暗黑风格 · {total} 张（限9张）<br>
  <button class="dl-btn" onclick="downloadBili()">下载B站动态图（暗黑风格） {total} 张</button>
</div>

<script>
async function downloadBili() {{
  const btn = document.querySelector('.dl-btn');
  btn.disabled = true;
  btn.textContent = '导出中...';
  try {{
    const cards = document.querySelectorAll('[id^="card_a"]');
    for (let i = 0; i < cards.length; i++) {{
      btn.textContent = '导出 ' + (i+1) + '/' + cards.length + '...';
      const dataUrl = await htmlToImage.toJpeg(cards[i], {{ quality: 0.92, pixelRatio: 4 }});
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = '游戏周报_{week_short}_B站_' + String(i+1).padStart(2,'0') + '.jpg';
      a.click();
      if (i < cards.length - 1) await new Promise(r => setTimeout(r, 500));
    }}
    btn.textContent = '✅ 导出完成！';
  }} catch(e) {{
    btn.textContent = '❌ 导出失败';
    console.error(e);
  }}
  setTimeout(() => {{ btn.disabled = false; btn.textContent = '下载B站动态图（暗黑风格） {total} 张'; }}, 3000);
}}
</script>

<div class="section-wrap">
<div class="section-title"> &nbsp;B站动态 · 暗黑风格 · {total} 张</div>
<div class="cards-row">

{dark_cards}

</div>
</div>

</body>
</html>
"""

def render_dual_html(data: dict) -> str:
    """
    渲染完整的双风格对比 HTML。

    Args:
        data: cards_content.json 解析后的 dict

    Returns:
        完整 HTML 字符串
    """
    meta = data.get("meta", {})
    cover = data.get("cover", {})
    cards = data.get("cards", [])
    rank_card = data.get("rank_card", None)

    week_label = meta.get("week_label", "")
    # "4.06-4.12" → "0406_0412"
    parts_ws = week_label.split("-")
    if len(parts_ws) == 2:
        s = parts_ws[0].strip().replace(".", "").zfill(4)
        e = parts_ws[1].strip().replace(".", "").zfill(4)
        week_short = f"{s}_{e}"
    else:
        week_short = week_label.replace(".", "").replace("-", "_")

    # 计算总卡片数（封面 + 内容卡 + 可选榜单卡）
    total = 1 + len(cards) + (1 if rank_card and rank_card.get("anomalies") else 0)

    # 按 style 渲染
    dark_cards_html = []
    cream_cards_html = []

    for sty in [DARK, CREAM]:
        rendered = []
        # 封面
        rendered.append(render_cover_card(sty, cover, meta, total))
        # 内容卡
        for i, c in enumerate(cards):
            rendered.append(render_content_card(sty, i + 2, c))
        # 榜单卡
        if rank_card and rank_card.get("anomalies"):
            rendered.append(render_rank_card(sty, len(cards) + 2, rank_card))

        if sty["prefix"] == "a":
            dark_cards_html = rendered
        else:
            cream_cards_html = rendered

    # 组装 HTML
    return _FULL_HTML_TEMPLATE.format(
        title=f"游戏行业周报 · {week_label} 双风格对比",
        week_short=week_short,
        total=total,
        dark_cards="\n\n".join(dark_cards_html),
        cream_cards="\n\n".join(cream_cards_html),
    )


_FULL_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #18181B;
  font-family: 'PingFang SC','Noto Sans SC','Microsoft YaHei',sans-serif;
  padding: 28px 20px 80px;
}}
.tip {{
  text-align: center;
  color: #aaa;
  font-size: 12px;
  background: #27272A;
  padding: 12px 20px;
  border-radius: 8px;
  max-width: 1700px;
  margin: 0 auto 28px;
  line-height: 1.8;
  border: 1px solid #3F3F46;
}}
.section-title {{
  max-width: 1700px;
  margin: 0 auto 14px;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 2px;
  padding: 8px 16px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}}
.section-dark  {{ color: #E8820C; background: #1C1008; border: 1px solid #3A2A10; }}
.section-cream {{ color: #C0392B; background: #FFF8F0; border: 1px solid #EAD8C0; }}
.section-wrap  {{ max-width: 1700px; margin: 0 auto 40px; }}
.cards-row {{
  display: flex; flex-direction: row; gap: 20px;
  justify-content: flex-start; flex-wrap: wrap;
  align-items: flex-start;
}}
.dl-btn {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; padding: 6px 18px;
  border-radius: 3px; cursor: pointer; border: none;
  letter-spacing: 1px; margin-top: 8px;
}}
.dl-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.dl-btn-dark  {{ background: #E8820C; color: #fff; }}
.dl-btn-cream {{ background: #C0392B; color: #fff; }}
</style>
</head>
<body>

<div class="tip">
  双风格对比预览 · 每张 375px · 两套风格各 {total} 张<br>
  <button class="dl-btn dl-btn-dark"  onclick="downloadSet('a','暗黑雷达局')">下载暗黑版 {total} 张</button>
  &nbsp;
  <button class="dl-btn dl-btn-cream" onclick="downloadSet('b','奶油杂志感')">下载奶油版 {total} 张</button>
</div>

<script>
async function downloadSet(prefix, label) {{
  const cards = document.querySelectorAll('[id^="card_'+prefix+'"]');
  for (let i = 0; i < cards.length; i++) {{
    const dataUrl = await htmlToImage.toJpeg(cards[i], {{ quality: 0.93, pixelRatio: 3 }});
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = '游戏周报_{week_short}_'+label+'_' + String(i+1).padStart(2,'0') + '.jpg';
    a.click();
    if (i < cards.length - 1) await new Promise(r => setTimeout(r, 500));
  }}
}}
</script>


<!-- ════════════════════════════════════════════════════
     风格一：暗黑雷达局
════════════════════════════════════════════════════ -->
<div class="section-wrap">
<div class="section-title section-dark"> &nbsp;风格一 · 暗黑雷达局</div>
<div class="cards-row">

{dark_cards}

</div>
</div>


<!-- ════════════════════════════════════════════════════
     风格二：奶油杂志感
════════════════════════════════════════════════════ -->
<div class="section-wrap">
<div class="section-title section-cream"> &nbsp;风格二 · 奶油杂志感</div>
<div class="cards-row">

{cream_cards}

</div>
</div>

</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color: str) -> str:
    """#E8820C → '232,130,12'"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "128,128,128"
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


def compute_rank_anomalies(daily_ranks: dict, end_date: str,
                           regions: list = None, top: int = 10) -> list:
    """
    从 daily_ranks.json 数据中计算排行异动。

    Args:
        daily_ranks: {f"{region}_{chart}_{date}": {"1": "game", ...}}
        end_date: "2026-04-12" 格式
        regions: 地区列表，默认 CN/US/JP/KR/BR/TH/IN
        top: 只看前 N 名

    Returns:
        [{"region": "中国大陆", "chart": "免费榜", "app": "xxx", "change": "↑5", "rank": 3}, ...]
    """
    from datetime import datetime, timedelta

    if not regions:
        regions = ["cn", "us", "jp", "kr", "br", "th", "in"]

    region_names = {
        "cn": "中国大陆", "us": "美国", "jp": "日本", "kr": "韩国",
        "br": "巴西", "th": "泰国", "in": "印度",
        "hk": "中国香港", "tw": "中国台湾", "gb": "英国",
    }
    chart_names = {"free": "免费榜", "grossing": "畅销榜"}

    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=6)
    start_str = start_dt.strftime("%Y-%m-%d")

    anomalies = []
    for region in regions:
        for chart_type in ["free", "grossing"]:
            end_key = f"{region}_{chart_type}_{end_date}"
            start_key = f"{region}_{chart_type}_{start_str}"

            end_data = daily_ranks.get(end_key, {})
            start_data = daily_ranks.get(start_key, {})

            if not end_data:
                continue

            for rank_str, game in end_data.items():
                rank = int(rank_str)
                if rank > top:
                    continue

                # 检查是否新上榜
                was_in_start = game in start_data.values()
                if not was_in_start:
                    anomalies.append({
                        "region": region_names.get(region, region),
                        "chart": chart_names.get(chart_type, chart_type),
                        "app": game,
                        "change": "★新上榜",
                        "rank": rank,
                    })
                else:
                    # 检查排名变化
                    old_rank = next((int(k) for k, v in start_data.items() if v == game), None)
                    if old_rank and old_rank - rank >= 3:
                        anomalies.append({
                            "region": region_names.get(region, region),
                            "chart": chart_names.get(chart_type, chart_type),
                            "app": game,
                            "change": f"↑{old_rank - rank}",
                            "rank": rank,
                        })

    # 排序：新上榜优先，然后按变化量降序
    def sort_key(a):
        c = a.get("change", "")
        if "新上榜" in c:
            return 9999
        if c.startswith("↑"):
            try:
                return int(c[1:])
            except ValueError:
                return 0
        return 0

    anomalies.sort(key=sort_key, reverse=True)
    return anomalies


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="小红书周报双风格 HTML 渲染器")
    parser.add_argument("--cards", "-c", required=True,
                        help="cards_content JSON 文件路径")
    parser.add_argument("--ranks", "-r", default=None,
                        help="daily_ranks.json 路径（可选，用于自动生成榜单异动卡）")
    parser.add_argument("--end-date", default=None,
                        help="周报结束日期 YYYY-MM-DD（配合 --ranks 用）")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 HTML 路径")
    parser.add_argument("--platform", "-p", default="xhs",
                        choices=["xhs", "bilibili"],
                        help="目标平台: xhs(默认双风格) / bilibili(仅暗黑+B站优化)")
    args = parser.parse_args()

    cards_path = Path(args.cards)
    if not cards_path.exists():
        print(f"❌ 文件不存在: {cards_path}", file=sys.stderr)
        sys.exit(1)

    with open(cards_path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"📥 读取卡片数据: {cards_path.name}")

    meta = data.get("meta", {})
    cards = data.get("cards", [])
    print(f"  封面: {'✅' if data.get('cover') else '❌'}")
    print(f"  内容卡: {len(cards)} 张")

    # 如果提供了 ranks 且没有 rank_card，自动计算异动
    if args.ranks and not data.get("rank_card"):
        ranks_path = Path(args.ranks)
        if ranks_path.exists():
            with open(ranks_path, encoding="utf-8") as f:
                daily_ranks = json.load(f)
            end_date = args.end_date or meta.get("end_date", "")
            if end_date:
                anomalies = compute_rank_anomalies(daily_ranks, end_date)
                if anomalies:
                    data["rank_card"] = {"anomalies": anomalies}
                    print(f"  榜单异动: {len(anomalies)} 条（自动计算）")
            else:
                print("  ⚠️ 未指定 --end-date，跳过榜单异动")

    has_rank = bool((data.get("rank_card") or {}).get("anomalies"))
    print(f"  榜单卡: {'✅' if has_rank else '无'}")

    # 渲染
    if args.platform == "bilibili":
        n_cards = 1 + len(cards)
        if n_cards > 9:
            print(f"  ⚠️ B站模式: {n_cards}张超出9张限制，榜单卡将自动合并")
        else:
            print(f"  📱 B站模式: {n_cards}张（≤9 ✓）")
        html_str = render_bilibili_html(data)
    else:
        html_str = render_dual_html(data)

    # 输出路径
    if args.output:
        out_path = Path(args.output)
    else:
        week_label = meta.get("week_label", "unknown")
        # "4.06-4.12" → "0406_0412"
        parts = week_label.split("-")
        if len(parts) == 2:
            s = parts[0].strip().replace(".", "").zfill(4)
            e = parts[1].strip().replace(".", "").zfill(4)
            tag = f"{s}_{e}"
        else:
            tag = week_label.replace(" ", "").replace(".", "")
        if args.platform == "bilibili":
            out_path = Path("weekly_cache") / f"output_bilibili_{tag}.html"
        else:
            out_path = Path("weekly_cache") / f"output_xhs_{tag}_dual.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_str)

    size_kb = out_path.stat().st_size / 1024
    print(f"\n✅ 已生成: {out_path} ({size_kb:.1f} KB)")
    print(f"   浏览器打开后可点击下载按钮导出 JPG")


if __name__ == "__main__":
    main()
