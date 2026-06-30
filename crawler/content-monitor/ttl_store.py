"""线程安全的 TTL 字典，自动过期清理。"""

import threading
import time
from typing import Any, Dict, Optional


class TTLStore:
    """内存 KV 存储，支持自动过期。"""

    def __init__(self, default_ttl: int = 600):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._start_cleanup_thread()

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            self._data[key] = value
            self._expiry[key] = time.monotonic() + (ttl or self._default_ttl)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key not in self._data:
                return default
            if time.monotonic() >= self._expiry.get(key, 0):
                self._data.pop(key, None)
                self._expiry.pop(key, None)
                return default
            return self._data[key]

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._expiry.pop(key, None)
            return self._data.pop(key, default)

    def cleanup_once(self) -> int:
        """单次清理过期条目，返回清理数量。可供测试直接调用。"""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired = [k for k, exp in self._expiry.items() if now >= exp]
            for k in expired:
                self._data.pop(k, None)
                self._expiry.pop(k, None)
                removed += 1
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def _cleanup_loop(self) -> None:
        while True:
            time.sleep(60)
            self.cleanup_once()

    def _start_cleanup_thread(self) -> None:
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()
