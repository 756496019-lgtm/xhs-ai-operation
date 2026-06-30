"""小红书创作中心 CSV 导入器。

策略：autodetect 列名 → 规整化 → 入库。
列名候选支持中英文混合，匹配任意一个都行。

如果 CSV 没有的列（例如 shares），导入时填 0；如果 publish_time 缺失，
当作"匿名笔记"导入（依然能跑互动率分析，但时段分析会被跳过）。
"""

from __future__ import annotations
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from schema import get_conn, upsert_note, upsert_snapshot


COLUMN_ALIASES: dict[str, list[str]] = {
    'note_id':      ['笔记ID', '笔记id', 'note_id', 'noteId', 'id', '作品ID', '作品id'],
    'title':        ['标题', '笔记标题', '作品标题', 'title'],
    'publish_time': ['发布时间', '发布日期', '时间', 'publish_time', 'publishTime', 'created_at'],
    'views':        ['浏览量', '阅读量', '阅读', '观看量', 'views', 'pv', 'view_count'],
    'likes':        ['点赞', '点赞数', '点赞量', 'likes', 'like_count'],
    'saves':        ['收藏', '收藏数', '收藏量', 'saves', 'collect_count', 'collects'],
    'comments':     ['评论', '评论数', '评论量', 'comments', 'comment_count'],
    'shares':       ['分享', '分享数', '转发', 'shares', 'share_count'],
}


def autodetect_columns(headers: list[str]) -> dict[str, str]:
    """返回 {标准字段: CSV 实际列名}。未匹配的字段不出现在结果里。"""
    mapping: dict[str, str] = {}
    norm_headers = {h.strip(): h for h in headers}
    for std, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in norm_headers:
                mapping[std] = norm_headers[alias]
                break
    return mapping


REQUIRED = ['note_id', 'title', 'views']


def _parse_int(s: str) -> int:
    """容错整数解析。'1.2万' / '1,234' / 空 → int。"""
    if s is None:
        return 0
    s = str(s).strip().replace(',', '').replace(' ', '')
    if not s or s in ('-', '--', 'N/A', 'null'):
        return 0
    if s.endswith('万'):
        try:
            return int(float(s[:-1]) * 10000)
        except ValueError:
            return 0
    if s.endswith('w') or s.endswith('W'):
        try:
            return int(float(s[:-1]) * 10000)
        except ValueError:
            return 0
    if s.endswith('k') or s.endswith('K'):
        try:
            return int(float(s[:-1]) * 1000)
        except ValueError:
            return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_datetime(s: str) -> Optional[str]:
    """容错时间解析，输出 ISO 8601 字符串。失败返回 None。"""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in (
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y/%m/%d',
        '%Y.%m.%d %H:%M', '%Y.%m.%d',
    ):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


def import_csv(csv_path: str | Path, db_path: str | Path,
               snapshot_date: Optional[str] = None,
               encoding: str = 'utf-8-sig') -> dict:
    """主入口：读 CSV 入库，返回统计 dict。

    snapshot_date：本次导入对应的"快照日期"，留空用今天。
    encoding：默认 utf-8-sig（小红书后台导出常带 BOM）。
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    if snapshot_date is None:
        snapshot_date = date.today().isoformat()

    with open(csv_path, encoding=encoding, newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = autodetect_columns(headers)

        missing = [k for k in REQUIRED if k not in mapping]
        if missing:
            raise ValueError(
                f'CSV 缺少必需字段：{missing}\n'
                f'  CSV 表头：{headers}\n'
                f'  支持的别名见 csv_importer.COLUMN_ALIASES，可手动加你后台导出的列名。'
            )

        conn = get_conn(db_path)
        n_notes, n_snapshots, n_skipped = 0, 0, 0
        with conn:
            for row in reader:
                note_id = (row.get(mapping['note_id']) or '').strip()
                title = (row.get(mapping['title']) or '').strip()
                if not note_id or not title:
                    n_skipped += 1
                    continue
                publish_time = _parse_datetime(row.get(mapping.get('publish_time', ''), ''))
                views = _parse_int(row.get(mapping['views'], '0'))
                likes = _parse_int(row.get(mapping.get('likes', ''), '0')) if 'likes' in mapping else 0
                saves = _parse_int(row.get(mapping.get('saves', ''), '0')) if 'saves' in mapping else 0
                comments = _parse_int(row.get(mapping.get('comments', ''), '0')) if 'comments' in mapping else 0
                shares = _parse_int(row.get(mapping.get('shares', ''), '0')) if 'shares' in mapping else 0

                upsert_note(conn, note_id, title, publish_time)
                upsert_snapshot(conn, note_id, snapshot_date, views, likes, saves, comments, shares)
                n_notes += 1
                n_snapshots += 1

    return {
        'csv': str(csv_path),
        'snapshot_date': snapshot_date,
        'detected_columns': mapping,
        'n_notes': n_notes,
        'n_snapshots': n_snapshots,
        'n_skipped': n_skipped,
    }
