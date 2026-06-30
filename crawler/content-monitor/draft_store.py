"""小红书定时发布草稿存储（JSON 文件持久化）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List


class DraftStore:
    """简单的线程安全草稿箱，存到本地 JSON 文件。

    草稿结构示例：
    {
        "id": "uuid",
        "title": "标题",
        "source": "xhs" / "cards" / "reddit_screenshot",
        "created_at": "2026-03-03 10:00:00",
        "post_time": "2026-03-03 10:02:00",
        "note_id": "xxxxxxxx",
        "url": "https://www.xiaohongshu.com/explore/xxxx",
        "status": "scheduled"
    }
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def _load(self) -> List[Dict[str, Any]]:
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw or "[]")
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except Exception:
            return []
        return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    def add(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """追加一条草稿记录，返回入库后的草稿。"""
        with self._lock:
            items = self._load()
            items.append(draft)
            # 按发布时间排序，最近要发布的在前
            items.sort(key=lambda d: (d.get("post_time") or "", d.get("created_at") or ""))
            self._save(items)
        return draft

    def list_all(self) -> List[Dict[str, Any]]:
        """返回所有草稿（按计划发布时间升序）。"""
        with self._lock:
            items = self._load()
        items.sort(key=lambda d: (d.get("post_time") or "", d.get("created_at") or ""))
        return items

