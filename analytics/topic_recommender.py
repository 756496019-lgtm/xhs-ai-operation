"""根据 analyzer 输出 + (可选) benchmark 对标数据，调 qwen-max 出下期选题清单。

输出：
  - data/reports/next_week_prompt_W{N}.md
  - 文件最末段是给 WorkBuddy 直接复制粘贴的"触发话术"，
    粘到 creator/xhs_console_agent/ 里就能起一轮新生产。

设计原则（呼应用户的"AI 用越少越好"哲学）：
  - AI 出 5 条候选，**让用户自己挑**，不强推某条
  - 每条选题附"为什么是这条"的依据，让用户判断
  - 自动跑 fact_check，避免编造数字进 prompt
  - prompt 里明确说"基于本人账号历史数据"，不让 AI 凭空生造
"""

from __future__ import annotations
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from qwen_bridge import chat, fact_check, is_available


SYSTEM_PROMPT = """你是一位资深的小红书账号运营顾问。
用户经营一个游戏垂直内容账号，4 个月从 0 涨到 2982 粉。
现在他/她把本周笔记的真实数据给你（互动率、阅读量、时段分布、标题长度分布、爆款 / 翻车案例），
请你给出**下一期**最值得做的 5 条选题候选。

要求：
1. 选题必须基于用户提供的真实数据做归因，不要凭空想象选题
2. 5 条候选要覆盖不同方向（不要 5 条都是折扣盘点）
3. 每条都说清"为什么是这条"——参考了什么数据 / 哪条历史笔记的成功 / 哪条翻车的反面
4. 对标账号数据如果有，可以参考用作"对方在打但我没打"的方向，但不要直接抄标题
5. 如果某些数据点不足以下结论，宁可少给候选也不要编

输出严格 JSON 格式，不要 markdown 代码块：
{
  "summary": "1-2 句话总结本周表现的核心亮点和遗憾",
  "key_findings": ["数据洞察 1（一句话）", "数据洞察 2", "数据洞察 3"],
  "topics": [
    {
      "title": "选题标题（≤20 字，含一个搜索关键词）",
      "angle": "切入点（1 句话）",
      "rationale": "为什么是这条（参考了哪条历史笔记 / 哪个数据 / 哪个翻车案例）",
      "estimated_strength": "high / medium / low",
      "reasoning_data": "支持理由的具体数据点（例如 'XX 标题阅读 18420，是本周最高'）"
    }
  ]
}
"""


def _format_analysis_for_prompt(analysis: dict[str, Any]) -> str:
    """把 analyzer.analyze() 的 dict 整理成给 qwen 看的 markdown 上下文。"""
    if analysis.get('empty'):
        return '【数据不足】用户库内没有笔记数据。'

    o = analysis['overall']
    parts = [
        '## 整体面板',
        f"- 笔记总数：{o['total_notes']}",
        f"- 总阅读：{o['total_views']:,} ；总点赞 {o['total_likes']:,} / 总收藏 {o['total_saves']:,} / 总评论 {o['total_comments']:,}",
        f"- 整体点赞率 {o['overall_like_rate']}%、收藏率 {o['overall_save_rate']}%、评论率 {o['overall_comment_rate']}%",
        f"- 平均阅读 {o['avg_views_per_note']}/笔",
        '',
        '## 互动率 Top 5（点赞+收藏+评论 / 阅读）',
    ]
    for i, n in enumerate(analysis['top_engagement'], 1):
        parts.append(f"{i}. [{n['engagement']}%] {n['title']}（阅读 {n['views']} / 赞 {n['likes']} / 收 {n['saves']}）")

    if analysis.get('top_save_rate'):
        parts.append('\n## 收藏率 Top（小红书长尾搜索关键指标）')
        for i, n in enumerate(analysis['top_save_rate'], 1):
            parts.append(f"{i}. [{n['save_rate']}% 收藏率] {n['title']}（阅读 {n['views']} / 收 {n['saves']}）")

    if analysis.get('hour_perf'):
        parts.append('\n## 发布时段表现')
        best = max(analysis['hour_perf'], key=lambda x: x['avg_engagement'])
        for h in analysis['hour_perf']:
            tag = '   ←本周最佳' if h['hour'] == best['hour'] else ''
            parts.append(f"- {h['hour']:02d}:00（{h['note_count']} 笔，平均互动 {h['avg_engagement']}%）{tag}")

    if analysis.get('title_len_perf'):
        parts.append('\n## 标题长度 vs 表现')
        for tl in analysis['title_len_perf']:
            parts.append(f"- {tl['length']}（{tl['note_count']} 笔，平均互动 {tl['avg_engagement']}%）")

    if analysis.get('bottom_engagement'):
        parts.append('\n## 互动率最低 3 条（反面案例）')
        for i, n in enumerate(analysis['bottom_engagement'], 1):
            parts.append(f"{i}. [{n['engagement']}%] {n['title']}（阅读 {n['views']}）")

    return '\n'.join(parts)


def _format_benchmark_for_prompt(benchmark_notes: Optional[list[dict]]) -> str:
    """整理对标账号最近笔记列表给 qwen。"""
    if not benchmark_notes:
        return ''
    parts = ['\n## 对标账号最近笔记（仅参考，不抄）']
    for n in benchmark_notes[:10]:
        title = n.get('title', '')
        likes = n.get('likes', 0)
        comments = n.get('comments', 0)
        parts.append(f"- {title}（{likes} 赞 / {comments} 评）")
    return '\n'.join(parts)


def _parse_qwen_json(raw: str) -> dict[str, Any]:
    """qwen 偶尔会带 ```json 包裹；剥掉。"""
    s = raw.strip()
    s = re.sub(r'^```(?:json)?\s*', '', s)
    s = re.sub(r'\s*```$', '', s)
    return json.loads(s)


def _week_label(d: Optional[date] = None) -> str:
    d = d or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    return f'{iso_year}-W{iso_week:02d}'


def recommend_topics(
    analysis: dict[str, Any],
    benchmark_notes: Optional[list[dict]] = None,
    week_label: Optional[str] = None,
) -> dict[str, Any]:
    """主入口：调 qwen-max 出选题清单 + 自动 fact_check。

    返回 dict 结构同 SYSTEM_PROMPT 里描述。失败抛异常。
    """
    avail, reason = is_available()
    if not avail:
        raise RuntimeError(reason)

    if week_label is None:
        week_label = _week_label()

    user_prompt = f"# 本周（{week_label}）数据复盘\n\n"
    user_prompt += _format_analysis_for_prompt(analysis)
    user_prompt += _format_benchmark_for_prompt(benchmark_notes)
    user_prompt += '\n\n请基于上述真实数据给出下期选题候选（严格 JSON）。'

    raw = chat(SYSTEM_PROMPT, user_prompt, model='qwen-max')
    try:
        result = _parse_qwen_json(raw)
    except Exception as e:
        raise RuntimeError(f'qwen 输出解析失败：{e}\n原始输出：\n{raw[:500]}')

    fact_text = (result.get('summary', '') + '\n'
                 + '\n'.join(result.get('key_findings', []))
                 + '\n'
                 + '\n'.join(t.get('reasoning_data', '') for t in result.get('topics', [])))
    if fact_text.strip():
        result['_fact_check'] = fact_check(fact_text)
    else:
        result['_fact_check'] = {'passed': True, 'issues': [], 'summary': '无可核查内容'}

    result['_meta'] = {
        'week_label': week_label,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'note_count': analysis.get('overall', {}).get('total_notes', 0),
        'has_benchmark': bool(benchmark_notes),
    }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    """把 recommend_topics 的 dict 输出渲染成 markdown 文件内容。

    最后一段是给 WorkBuddy 直接复制粘贴的"触发话术"。
    """
    meta = result.get('_meta', {})
    week = meta.get('week_label', _week_label())
    note_count = meta.get('note_count', 0)

    lines = [
        f'# 下期选题建议｜{week}',
        '',
        f'> 基于本周 {note_count} 条笔记的数据复盘自动生成。WorkBuddy 触发话术见文末。',
        f'> 生成时间：{meta.get("generated_at", "")}',
        '',
        '## 本周复盘',
        '',
        result.get('summary', '（无）'),
        '',
        '### 核心数据洞察',
        '',
    ]
    for f in result.get('key_findings', []):
        lines.append(f'- {f}')
    lines.append('')

    fc = result.get('_fact_check', {})
    if fc and not fc.get('passed', True):
        lines.append('### 事实核查警告')
        lines.append('')
        lines.append(f'> {fc.get("summary", "")}')
        for issue in fc.get('issues', [])[:3]:
            lines.append(f'- 「{issue.get("claim", "")}」— {issue.get("reason", "")}')
        lines.append('')
        lines.append('上述断言已自动 flag，决定执行选题前请人工核实。')
        lines.append('')

    lines.append('## 5 条候选选题')
    lines.append('')
    for i, t in enumerate(result.get('topics', []), 1):
        lines.append(f'### {i}. {t.get("title", "")}')
        lines.append('')
        lines.append(f'- **预估表现**：{t.get("estimated_strength", "")}')
        lines.append(f'- **切入角度**：{t.get("angle", "")}')
        lines.append(f'- **数据依据**：{t.get("reasoning_data", "")}')
        lines.append(f'- **为什么是这条**：{t.get("rationale", "")}')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## WorkBuddy 触发话术（复制下面整段到 creator/xhs_console_agent/ 对话）')
    lines.append('')
    lines.append('```')
    if result.get('topics'):
        top1 = result['topics'][0]
        lines.append(f'帮我做一条小红书图文，标题方向是「{top1.get("title", "")}」，')
        lines.append(f'切入角度：{top1.get("angle", "")}。')
        lines.append('参考本周复盘文件：')
        lines.append(f'D:/project/xhs-yunying/analytics/data/reports/next_week_prompt_{week}.md')
        lines.append('')
        lines.append(f'数据依据：{top1.get("reasoning_data", "")}')
        lines.append('请先读 skills/02-script-writer/SKILL.md 再写。')
    lines.append('```')
    lines.append('')
    lines.append('> 这个触发话术对接 `creator/xhs_console_agent/skills/02-script-writer/`。')
    lines.append('> 如果想换其他候选选题（第 2-5 条），把上面的"标题方向"和"切入角度"替换即可。')
    return '\n'.join(lines)


def save(result: dict[str, Any], output_dir: str | Path) -> Path:
    """渲染 + 写入到 data/reports/next_week_prompt_W{N}.md，返回路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    week = result.get('_meta', {}).get('week_label', _week_label())
    out_path = output_dir / f'next_week_prompt_{week}.md'
    out_path.write_text(render_markdown(result), encoding='utf-8')

    raw_path = output_dir / f'next_week_prompt_{week}_raw.json'
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return out_path
