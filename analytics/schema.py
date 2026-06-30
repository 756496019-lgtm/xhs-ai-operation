"""SQLite schema + 简单连接管理。

三张表：
- notes        ：笔记元数据（一笔一行）
- snapshots    ：每次 CSV 导入的笔记数据快照（追踪同一笔记跨周增长）
- followers    ：粉丝数日级时间序列（独立来源，可选）
"""

import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS notes (
    note_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    publish_time     TIMESTAMP,
    category         TEXT DEFAULT '',
    topic_keywords   TEXT DEFAULT '',
    first_seen       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id          TEXT NOT NULL,
    snapshot_date    DATE NOT NULL,
    views            INTEGER DEFAULT 0,
    likes            INTEGER DEFAULT 0,
    saves            INTEGER DEFAULT 0,
    comments         INTEGER DEFAULT 0,
    shares           INTEGER DEFAULT 0,
    UNIQUE(note_id, snapshot_date),
    FOREIGN KEY (note_id) REFERENCES notes(note_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_note ON snapshots(note_id);

CREATE TABLE IF NOT EXISTS followers (
    date             DATE PRIMARY KEY,
    count            INTEGER NOT NULL,
    net_increase     INTEGER DEFAULT 0
);
"""


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """获取 SQLite 连接，自动建表，返回的连接 row_factory = Row（可按列名访问）。"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


def upsert_note(conn: sqlite3.Connection, note_id: str, title: str,
                publish_time: str | None = None,
                category: str = '', topic_keywords: str = '') -> None:
    """插入或更新笔记元数据。已存在的 note_id 只更新 title/publish_time（如果传入），不覆盖 category/keywords（用户可能手工标了）。"""
    cur = conn.cursor()
    row = cur.execute("SELECT note_id FROM notes WHERE note_id=?", (note_id,)).fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO notes(note_id, title, publish_time, category, topic_keywords) VALUES(?,?,?,?,?)",
            (note_id, title, publish_time, category, topic_keywords),
        )
    else:
        if publish_time:
            cur.execute("UPDATE notes SET title=?, publish_time=? WHERE note_id=?",
                        (title, publish_time, note_id))
        else:
            cur.execute("UPDATE notes SET title=? WHERE note_id=?", (title, note_id))


def upsert_snapshot(conn: sqlite3.Connection, note_id: str, snapshot_date: str,
                    views: int, likes: int, saves: int, comments: int, shares: int) -> None:
    """插入或替换某天的笔记数据快照。"""
    conn.execute(
        """INSERT INTO snapshots(note_id, snapshot_date, views, likes, saves, comments, shares)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(note_id, snapshot_date) DO UPDATE SET
             views=excluded.views, likes=excluded.likes, saves=excluded.saves,
             comments=excluded.comments, shares=excluded.shares""",
        (note_id, snapshot_date, views, likes, saves, comments, shares),
    )


def upsert_follower(conn: sqlite3.Connection, date: str, count: int, net_increase: int = 0) -> None:
    """记录某天的粉丝数。"""
    conn.execute(
        """INSERT INTO followers(date, count, net_increase) VALUES(?,?,?)
           ON CONFLICT(date) DO UPDATE SET count=excluded.count, net_increase=excluded.net_increase""",
        (date, count, net_increase),
    )
