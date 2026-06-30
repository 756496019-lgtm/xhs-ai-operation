"""把 analyzer.analyze() 的结果转成 cards JSON schema，调 render_dual_html() 出双风格 HTML。

输出：
  data/reports/W{N}_dashboard.html

浏览器打开后点"下载全部 JPG"按钮即可导出双风格小红书卡片，
直接发布或发到 PPT / 答辩材料里都行。

设计：
  - 封面卡：本周战绩三件套（笔记数 / 平均互动率 / 最高阅读）
  - 内容卡 1：互动率 Top 3
  - 内容卡 2：最佳发布时段
  - 内容卡 3：标题长度黄金区间
  - 内容卡 4：反面案例（互动率最低 3 条）
  - 内容卡 5（可选）：下期选题反哺（来自 topic_recommender）

视觉规范沿用 xhs-weeklyreport 的双色板：暗黑 #0C1520 + 奶油 #FFFDF9。
"""

from __future__ import annotations
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

_VENDOR = (Path(__file__).resolve().parent / '_vendor').as_posix()
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from render_xhs_cards import render_dual_html  # type: ignore  # noqa: E402


def _week_meta(d: Optional[date] = None) -> dict[str, Any]:
    d = d or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = date.fromisocalendar(iso_year, iso_week, 7)
    return {
        'week_label': f'{week_start.month}.{week_start.day:02d}-{week_end.month}.{week_end.day:02d}',
        'week_code': f'W{iso_week:02d}',
        'year': iso_year,
        'start_date': week_start.isoformat(),
        'end_date': week_end.isoformat(),
    }


def _build_cover(analysis: dict[str, Any], meta: dict) -> dict[str, Any]:
    """封面卡：本周战绩三件套。"""
    o = analysis['overall']
    top1 = analysis['top_engagement'][0] if analysis.get('top_engagement') else None

    summaries = [
        {
            'tag': '笔记数',
            'color': 'orange',
            'text': f'本周 {o["total_notes"]} 条',
            'sub': f'累计阅读 {o["total_views"]:,}',
        },
        {
            'tag': '互动率',
            'color': 'green',
            'text': f'整体 {o["overall_like_rate"] + o["overall_save_rate"]:.1f}%',
            'sub': f'点赞 {o["overall_like_rate"]}% / 收藏 {o["overall_save_rate"]}%',
        },
    ]
    if top1:
        summaries.append({
            'tag': '本周爆款',
            'color': 'gold',
            'text': top1['title'][:18],
            'sub': f'{top1["views"]:,} 阅读 / {top1["engagement"]}% 互动',
        })

    return {
        'title_line1': '本周自分析',
        'title_line2': '账号战绩',
        'subtitle': f'{o["total_notes"]} 条笔记 · 平均阅读 {o["avg_views_per_note"]:.0f} · 数据自分析报告',
        'summaries': summaries,
    }


def _build_top_engagement_card(analysis: dict[str, Any]) -> dict[str, Any]:
    """卡片 1：互动率 Top 3。"""
    items = analysis.get('top_engagement', [])[:3]
    if not items:
        return {}
    body_lines = [
        '<div style="padding:20px 18px 14px;">',
        f'<div style="font-size:11px;letter-spacing:1px;margin-bottom:6px;">数据自分析 · 互动率 Top 3</div>',
        '<div style="font-size:22px;font-weight:900;line-height:1.25;margin-bottom:14px;">爆款笔记<br>互动率前三</div>',
    ]
    for i, n in enumerate(items, 1):
        title_short = n['title'][:24] + ('...' if len(n['title']) > 24 else '')
        body_lines.append(
            f'<div style="font-size:12px;line-height:1.7;margin-bottom:6px;">'
            f'<strong>{i}. [{n["engagement"]}%]</strong> {title_short}<br>'
            f'<span style="font-size:10px;opacity:0.7;">{n["views"]:,} 阅读 · {n["likes"]} 赞 · {n["saves"]} 收</span>'
            f'</div>'
        )
    body_lines.append('</div>')

    insight = '互动率 = (赞+收+评)/阅读。Top 选题的共同点：搜索关键词清晰、标题有钩子、正文 80-150 字。'
    return {
        'type': 'content',
        'topic_tag': '互动率',
        'topic_color': 'green',
        'date_label': '本周',
        'title': '互动率 Top 3',
        'body_html': '\n'.join(body_lines),
        'insight': insight,
    }


def _build_hour_card(analysis: dict[str, Any]) -> dict[str, Any]:
    """卡片 2：最佳发布时段。"""
    hour_perf = analysis.get('hour_perf', [])
    if not hour_perf:
        return {}
    best = max(hour_perf, key=lambda x: x['avg_engagement'])
    sorted_hours = sorted(hour_perf, key=lambda x: x['avg_engagement'], reverse=True)[:3]

    body_lines = [
        '<div style="padding:20px 18px 14px;">',
        '<div style="font-size:11px;letter-spacing:1px;margin-bottom:6px;">数据自分析 · 最佳发布时段</div>',
        f'<div style="font-size:22px;font-weight:900;line-height:1.25;margin-bottom:14px;">'
        f'晚 <strong>{best["hour"]:02d}:00</strong> 是黄金时段</div>',
        '<div style="font-size:11px;line-height:1.7;">本周表现最好的 3 个时段：</div>',
    ]
    for h in sorted_hours:
        body_lines.append(
            f'<div style="font-size:12px;line-height:1.7;">'
            f'<strong>{h["hour"]:02d}:00</strong> · {h["note_count"]} 笔 · 平均互动 <strong>{h["avg_engagement"]}%</strong>'
            f'</div>'
        )
    body_lines.append('</div>')

    insight = f'下次发笔记尽量挑 {best["hour"]:02d}:00 前后。早上 / 中午发的笔记互动普遍偏低。'
    return {
        'type': 'content',
        'topic_tag': '时段',
        'topic_color': 'blue',
        'date_label': '复盘',
        'title': '最佳发布时段',
        'body_html': '\n'.join(body_lines),
        'insight': insight,
    }


def _build_title_length_card(analysis: dict[str, Any]) -> dict[str, Any]:
    """卡片 3：标题长度黄金区间。"""
    tl_perf = analysis.get('title_len_perf', [])
    if not tl_perf:
        return {}
    best = max(tl_perf, key=lambda x: x['avg_engagement'])

    body_lines = [
        '<div style="padding:20px 18px 14px;">',
        '<div style="font-size:11px;letter-spacing:1px;margin-bottom:6px;">数据自分析 · 标题长度</div>',
        f'<div style="font-size:22px;font-weight:900;line-height:1.25;margin-bottom:14px;">'
        f'<strong>{best["length"]}</strong> 是黄金区间</div>',
    ]
    for tl in tl_perf:
        marker = ' ←最佳' if tl['length'] == best['length'] else ''
        body_lines.append(
            f'<div style="font-size:12px;line-height:1.7;">'
            f'<strong>{tl["length"]}</strong> · {tl["note_count"]} 笔 · 平均互动 <strong>{tl["avg_engagement"]}%</strong>{marker}'
            f'</div>'
        )
    body_lines.append('</div>')

    insight = f'写标题时控制在 {best["length"]}。太短钩子不够，太长被截断。'
    return {
        'type': 'content',
        'topic_tag': '标题',
        'topic_color': 'purple',
        'date_label': '复盘',
        'title': '标题长度甜点区',
        'body_html': '\n'.join(body_lines),
        'insight': insight,
    }


def _build_bottom_card(analysis: dict[str, Any]) -> dict[str, Any]:
    """卡片 4：反面案例。"""
    items = analysis.get('bottom_engagement', [])[:3]
    if not items:
        return {}
    body_lines = [
        '<div style="padding:20px 18px 14px;">',
        '<div style="font-size:11px;letter-spacing:1px;margin-bottom:6px;">数据自分析 · 反面教材</div>',
        '<div style="font-size:22px;font-weight:900;line-height:1.25;margin-bottom:14px;">互动率最低 3 条</div>',
    ]
    for i, n in enumerate(items, 1):
        title_short = n['title'][:24] + ('...' if len(n['title']) > 24 else '')
        body_lines.append(
            f'<div style="font-size:12px;line-height:1.7;margin-bottom:6px;">'
            f'<strong>{i}. [{n["engagement"]}%]</strong> {title_short}<br>'
            f'<span style="font-size:10px;opacity:0.7;">{n["views"]} 阅读</span>'
            f'</div>'
        )
    body_lines.append('</div>')

    insight = '互动率低的笔记往往是：标题缺搜索关键词、综合性话题（不聚焦）、或踩到平台敏感词（如腾讯）。'
    return {
        'type': 'content',
        'topic_tag': '复盘',
        'topic_color': 'red',
        'date_label': '反面',
        'title': '互动率最低 3 条',
        'body_html': '\n'.join(body_lines),
        'insight': insight,
    }


def _build_topic_card(topic_result: dict[str, Any]) -> dict[str, Any]:
    """卡片 5（可选）：下期选题反哺。"""
    topics = topic_result.get('topics', [])[:3]
    if not topics:
        return {}
    body_lines = [
        '<div style="padding:20px 18px 14px;">',
        '<div style="font-size:11px;letter-spacing:1px;margin-bottom:6px;">AI 反哺 · 下期选题候选</div>',
        '<div style="font-size:22px;font-weight:900;line-height:1.25;margin-bottom:14px;">下期可以做什么</div>',
    ]
    for i, t in enumerate(topics, 1):
        title_short = t.get('title', '')[:24] + ('...' if len(t.get('title', '')) > 24 else '')
        body_lines.append(
            f'<div style="font-size:12px;line-height:1.7;margin-bottom:6px;">'
            f'<strong>{i}.</strong> {title_short}<br>'
            f'<span style="font-size:10px;opacity:0.7;">预估表现：{t.get("estimated_strength", "")}</span>'
            f'</div>'
        )
    body_lines.append('</div>')

    insight = '完整 5 条候选 + WorkBuddy 触发话术见 next_week_prompt 文件。AI 出建议，最终选题要人手判。'
    return {
        'type': 'content',
        'topic_tag': '反哺',
        'topic_color': 'gold',
        'date_label': '下期',
        'title': '下期选题候选',
        'body_html': '\n'.join(body_lines),
        'insight': insight,
    }


def build_cards_data(
    analysis: dict[str, Any],
    topic_result: Optional[dict[str, Any]] = None,
    week_label: Optional[str] = None,
) -> dict[str, Any]:
    """主入口：构造 render_xhs_cards 期望的 cards JSON。"""
    if analysis.get('empty'):
        raise ValueError('analysis 为空，无法生成卡片')

    meta = _week_meta()
    if week_label:
        meta['week_label'] = week_label

    cards = []
    for builder in (_build_top_engagement_card, _build_hour_card,
                    _build_title_length_card, _build_bottom_card):
        c = builder(analysis)
        if c:
            cards.append(c)
    if topic_result:
        c = _build_topic_card(topic_result)
        if c:
            cards.append(c)

    return {
        'meta': meta,
        'cover': _build_cover(analysis, meta),
        'cards': cards,
    }


def render_to_html(
    analysis: dict[str, Any],
    output_dir: str | Path,
    topic_result: Optional[dict[str, Any]] = None,
    week_label: Optional[str] = None,
) -> Path:
    """渲染并写盘。返回 HTML 路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cards_data = build_cards_data(analysis, topic_result, week_label)
    html = render_dual_html(cards_data)

    iso_week = datetime.now().isocalendar().week
    out_path = output_dir / f'W{iso_week:02d}_dashboard.html'
    out_path.write_text(html, encoding='utf-8')
    return out_path
