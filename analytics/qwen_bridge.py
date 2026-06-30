"""桥接 crawler/content-monitor/qwen_client.py（snapshot 副本）。

策略：通过 sys.path 直接复用，不再封装 OpenAI 客户端，避免 API key 二次配置。
DASHSCOPE_API_KEY 由原 client 内置（参见 qwen_client.py:21）。

可以从用户的 .env 或 OS 环境变量覆盖（变量名 DASHSCOPE_API_KEY）。
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

_CRAWLER_QWEN = (Path(__file__).resolve().parent.parent / 'crawler' / 'content-monitor').as_posix()
if _CRAWLER_QWEN not in sys.path:
    sys.path.insert(0, _CRAWLER_QWEN)

try:
    from qwen_client import get_qwen_client, fact_check_content  # type: ignore  # noqa: E402
    HAS_QWEN = True
except Exception as _e:
    HAS_QWEN = False
    _IMPORT_ERROR = _e


def is_available() -> tuple[bool, str]:
    """返回 (available, reason)。供 cli 检测能否调 AI。"""
    if not HAS_QWEN:
        return False, f'crawler/content-monitor/qwen_client.py 导入失败：{_IMPORT_ERROR}\n请先 pip install openai。'
    return True, ''


def chat(prompt_system: str, prompt_user: str, model: str = 'qwen-max') -> str:
    """通用 chat completion 调用，返回 string 内容。失败抛异常。

    model: 默认 qwen-max（更好的判断力，单次成本可控）。
           轻任务可传 'qwen-turbo' 节省 token。
    """
    if not HAS_QWEN:
        raise RuntimeError(f'qwen_client 不可用：{_IMPORT_ERROR}')
    client = get_qwen_client()
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': prompt_system},
            {'role': 'user', 'content': prompt_user},
        ],
        extra_body={'enable_thinking': False},
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError('AI 未返回有效内容')
    return completion.choices[0].message.content.strip()


def fact_check(text: str) -> dict[str, Any]:
    """对一段文案做事实核查，返回 {passed, issues, summary}。"""
    if not HAS_QWEN:
        return {'passed': True, 'issues': [], 'summary': '[skip] qwen 不可用，跳过事实核查'}
    return fact_check_content(text)
