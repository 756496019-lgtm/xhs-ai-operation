"""笔记表现分析器。

输入：SQLite 库（schema.py 创建的）。
输出：dict（结构化分析结果），用于：
  - cli.py 终端打印
  - topic_recommender.py 喂给 qwen 出选题
  - report_renderer.py 渲染卡片报告

分析维度：
  1. 整体面板（总笔记数、总阅读、平均互动率）
  2. 互动率 Top N（按 likes/views 排序）
  3. 收藏率 Top N（按 saves/views 排序，小红书特征指标）
  4. 时段分布（不同发布小时段的平均表现）
  5. 标题长度 vs 表现（10字以内/11-15/16-20/20+）

刻意不用 pandas，stdlib 够用。
"""

from __future__ import annotations
import sqlite3
from collections import defaultdict
from typing import Any


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _hour_bucket(iso: str | None) -> int | None:
    """从 ISO 时间字符串取小时。"""
    if not iso:
        return None
    try:
        return int(iso[11:13])
    except (ValueError, IndexError):
        return None


def _title_length_bucket(title: str) -> str:
    n = len(title)
    if n <= 10:
        return '≤10字'
    if n <= 15:
        return '11-15字'
    if n <= 20:
        return '16-20字'
    return '20+字'


def analyze(conn: sqlite3.Connection, latest_only: bool = True) -> dict[str, Any]:
    """跑全套分析。

    latest_only：True 只取每条笔记的最新一次快照（避免同笔记多次快照重复计数）。
    """
    cur = conn.cursor()
    if latest_only:
        rows = cur.execute("""
            SELECT n.note_id, n.title, n.publish_time, n.category,
                   s.snapshot_date, s.views, s.likes, s.saves, s.comments, s.shares
              FROM notes n
              JOIN snapshots s ON s.note_id = n.note_id
             WHERE s.id = (
                SELECT id FROM snapshots WHERE note_id = n.note_id
                ORDER BY snapshot_date DESC LIMIT 1
             )
        """).fetchall()
    else:
        rows = cur.execute("""
            SELECT n.note_id, n.title, n.publish_time, n.category,
                   s.snapshot_date, s.views, s.likes, s.saves, s.comments, s.shares
              FROM notes n
              JOIN snapshots s ON s.note_id = n.note_id
        """).fetchall()

    if not rows:
        return {'empty': True, 'message': '库内没有数据，请先 --import 一份 CSV。'}

    notes = [dict(r) for r in rows]
    n_total = len(notes)
    sum_views = sum(n['views'] for n in notes)
    sum_likes = sum(n['likes'] for n in notes)
    sum_saves = sum(n['saves'] for n in notes)
    sum_comments = sum(n['comments'] for n in notes)

    overall = {
        'total_notes': n_total,
        'total_views': sum_views,
        'total_likes': sum_likes,
        'total_saves': sum_saves,
        'total_comments': sum_comments,
        'avg_views_per_note': round(_safe_div(sum_views, n_total), 1),
        'overall_like_rate':    round(_safe_div(sum_likes, sum_views) * 100, 2),
        'overall_save_rate':    round(_safe_div(sum_saves, sum_views) * 100, 2),
        'overall_comment_rate': round(_safe_div(sum_comments, sum_views) * 100, 2),
    }

    for n in notes:
        n['like_rate'] = round(_safe_div(n['likes'], n['views']) * 100, 2)
        n['save_rate'] = round(_safe_div(n['saves'], n['views']) * 100, 2)
        n['comment_rate'] = round(_safe_div(n['comments'], n['views']) * 100, 2)
        n['engagement'] = round(_safe_div(n['likes'] + n['saves'] + n['comments'], n['views']) * 100, 2)

    by_engagement = sorted(notes, key=lambda x: x['engagement'], reverse=True)
    by_views = sorted(notes, key=lambda x: x['views'], reverse=True)
    by_save_rate = sorted(notes, key=lambda x: x['save_rate'], reverse=True)

    top_engagement = [
        {'title': n['title'], 'views': n['views'], 'likes': n['likes'], 'saves': n['saves'],
         'engagement': n['engagement']}
        for n in by_engagement[:5]
    ]
    top_views = [
        {'title': n['title'], 'views': n['views'], 'engagement': n['engagement']}
        for n in by_views[:5]
    ]
    top_save_rate = [
        {'title': n['title'], 'views': n['views'], 'saves': n['saves'], 'save_rate': n['save_rate']}
        for n in by_save_rate[:5] if n['views'] >= 100
    ]

    hour_buckets: dict[int, list[float]] = defaultdict(list)
    for n in notes:
        h = _hour_bucket(n['publish_time'])
        if h is not None:
            hour_buckets[h].append(n['engagement'])
    hour_perf = []
    for h in sorted(hour_buckets):
        engs = hour_buckets[h]
        hour_perf.append({
            'hour': h,
            'note_count': len(engs),
            'avg_engagement': round(sum(engs) / len(engs), 2),
        })

    len_buckets: dict[str, list[float]] = defaultdict(list)
    for n in notes:
        len_buckets[_title_length_bucket(n['title'])].append(n['engagement'])
    title_len_perf = []
    for label in ['≤10字', '11-15字', '16-20字', '20+字']:
        engs = len_buckets.get(label, [])
        if engs:
            title_len_perf.append({
                'length': label,
                'note_count': len(engs),
                'avg_engagement': round(sum(engs) / len(engs), 2),
            })

    bottom_engagement = [
        {'title': n['title'], 'views': n['views'], 'engagement': n['engagement']}
        for n in by_engagement[-3:][::-1] if n['views'] >= 50
    ]

    follower_rows = cur.execute(
        "SELECT date, count, net_increase FROM followers ORDER BY date"
    ).fetchall()
    followers = [dict(r) for r in follower_rows] if follower_rows else []

    return {
        'empty': False,
        'overall': overall,
        'top_engagement': top_engagement,
        'top_views': top_views,
        'top_save_rate': top_save_rate,
        'bottom_engagement': bottom_engagement,
        'hour_perf': hour_perf,
        'title_len_perf': title_len_perf,
        'followers': followers,
    }


def print_report(result: dict[str, Any]) -> None:
    """终端友好打印。Windows GBK 兼容（不用 ✓ ✗ 等字符）。"""
    if result.get('empty'):
        print(result['message'])
        return

    o = result['overall']
    print('\n=== 整体面板 ===')
    print(f"笔记总数: {o['total_notes']}")
    print(f"总阅读  : {o['total_views']:,}")
    print(f"总点赞  : {o['total_likes']:,}    总收藏: {o['total_saves']:,}    总评论: {o['total_comments']:,}")
    print(f"平均阅读: {o['avg_views_per_note']}/笔")
    print(f"整体点赞率 {o['overall_like_rate']}%   收藏率 {o['overall_save_rate']}%   评论率 {o['overall_comment_rate']}%")

    print('\n=== 互动率 Top 5（点赞+收藏+评论 / 阅读）===')
    for i, n in enumerate(result['top_engagement'], 1):
        print(f"{i}. [{n['engagement']}%] {n['title']}  ({n['views']} 阅读 / {n['likes']} 赞 / {n['saves']} 收)")

    print('\n=== 阅读量 Top 5 ===')
    for i, n in enumerate(result['top_views'], 1):
        print(f"{i}. [{n['views']:,} 阅读, {n['engagement']}% 互动] {n['title']}")

    if result['top_save_rate']:
        print('\n=== 收藏率 Top（最适合做长尾搜索的选题）===')
        for i, n in enumerate(result['top_save_rate'], 1):
            print(f"{i}. [{n['save_rate']}% 收藏率] {n['title']}  ({n['views']} 阅读 / {n['saves']} 收)")

    if result['hour_perf']:
        print('\n=== 发布时段分布 ===')
        best = max(result['hour_perf'], key=lambda x: x['avg_engagement'])
        for h in result['hour_perf']:
            mark = '   ←最佳' if h['hour'] == best['hour'] else ''
            print(f"{h['hour']:02d}:00  {h['note_count']:>3} 笔  平均互动 {h['avg_engagement']}%{mark}")

    if result['title_len_perf']:
        print('\n=== 标题长度 vs 表现 ===')
        for tl in result['title_len_perf']:
            print(f"{tl['length']:>6}  {tl['note_count']:>3} 笔  平均互动 {tl['avg_engagement']}%")

    if result['bottom_engagement']:
        print('\n=== 互动率最低 3 条（值得复盘的反面案例）===')
        for i, n in enumerate(result['bottom_engagement'], 1):
            print(f"{i}. [{n['engagement']}%] {n['title']}  ({n['views']} 阅读)")

    if result['followers']:
        print('\n=== 粉丝数曲线 ===')
        for r in result['followers'][-7:]:
            sign = '+' if r['net_increase'] >= 0 else ''
            print(f"{r['date']}  {r['count']:>5}  ({sign}{r['net_increase']})")

    print()
