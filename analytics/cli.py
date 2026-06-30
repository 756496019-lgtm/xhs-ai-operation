"""xhs-yunying analytics CLI

使用：
    python cli.py --import examples/sample_export.csv          # 导入 CSV
    python cli.py --analyze                                     # 跑分析（终端打印）
    python cli.py --suggest                                     # 出下期选题 prompt（阶段 C）
    python cli.py --render                                      # 出双风格卡片报告（阶段 D）
    python cli.py --import xxx.csv --analyze                    # 串起来做

阶段 B：当前已实现 --import 和 --analyze。
阶段 C/D：--suggest / --render 待 topic_recommender.py / report_renderer.py 接入。
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Windows 终端默认 GBK，中文标题打印会乱码；强制 UTF-8 输出。
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from csv_importer import import_csv  # noqa: E402
from analyzer import analyze, print_report  # noqa: E402
from schema import get_conn  # noqa: E402


DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'analytics.db'


def cmd_import(csv_path: str, db_path: Path, snapshot_date: str | None) -> None:
    print(f"[import] CSV={csv_path}")
    print(f"[import] DB ={db_path}")
    if snapshot_date:
        print(f"[import] 快照日期={snapshot_date}")

    result = import_csv(csv_path, db_path, snapshot_date=snapshot_date)
    print(f"[import] 检测到的字段映射: {result['detected_columns']}")
    print(f"[import] 导入笔记 {result['n_notes']} 条；快照 {result['n_snapshots']} 条；跳过 {result['n_skipped']} 行")


def cmd_analyze(db_path: Path, json_out: bool = False) -> None:
    if not db_path.exists():
        print(f"[analyze] 找不到 DB：{db_path}\n请先 --import 一份 CSV。")
        sys.exit(1)
    conn = get_conn(db_path)
    result = analyze(conn)
    conn.close()
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)


def cmd_suggest(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[suggest] 找不到 DB：{db_path}\n请先 --import 一份 CSV。")
        sys.exit(1)
    from analyzer import analyze
    from topic_recommender import recommend_topics, save
    from qwen_bridge import is_available

    avail, reason = is_available()
    if not avail:
        print(f'[suggest] {reason}')
        sys.exit(1)

    conn = get_conn(db_path)
    analysis = analyze(conn)
    conn.close()
    if analysis.get('empty'):
        print(f'[suggest] {analysis["message"]}')
        return

    print('[suggest] 调用 qwen-max 生成下期选题候选 ...')
    result = recommend_topics(analysis)
    fc = result.get('_fact_check', {})
    if not fc.get('passed', True):
        print(f'[suggest] 事实核查 ⚠ 有疑问：{fc.get("summary", "")}')
        for issue in fc.get('issues', [])[:3]:
            print(f'  - 「{issue.get("claim", "")}」— {issue.get("reason", "")}')
    else:
        print(f'[suggest] 事实核查 ✓ {fc.get("summary", "")}')

    output_dir = Path(__file__).resolve().parent / 'data' / 'reports'
    out_path = save(result, output_dir)
    print(f'[suggest] 已写入 {out_path}')
    print(f'[suggest] 文件末段是 WorkBuddy 触发话术，复制粘贴到 creator/xhs_console_agent/ 即可起新一轮生产')


def cmd_render(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[render] 找不到 DB：{db_path}\n请先 --import 一份 CSV。")
        sys.exit(1)
    from analyzer import analyze
    from report_renderer import render_to_html

    conn = get_conn(db_path)
    analysis = analyze(conn)
    conn.close()
    if analysis.get('empty'):
        print(f'[render] {analysis["message"]}')
        return

    # 如果上一次跑过 --suggest，把选题反哺也放进卡片
    output_dir = Path(__file__).resolve().parent / 'data' / 'reports'
    topic_result = None
    raw_jsons = sorted(output_dir.glob('next_week_prompt_*_raw.json'))
    if raw_jsons:
        try:
            topic_result = json.loads(raw_jsons[-1].read_text(encoding='utf-8'))
            print(f'[render] 检测到选题反哺数据：{raw_jsons[-1].name}')
        except Exception as e:
            print(f'[render] 解析选题数据失败（跳过）: {e}')

    out_path = render_to_html(analysis, output_dir, topic_result=topic_result)
    print(f'[render] 已写入 {out_path}')
    print(f'[render] 浏览器打开后点"下载全部 JPG"按钮，可导出双风格小红书卡片')


def main() -> None:
    p = argparse.ArgumentParser(description='xhs-yunying analytics — 小红书自分析数据回收闭环')
    p.add_argument('--import', dest='import_csv', metavar='CSV',
                   help='从小红书创作中心导出的 CSV 文件路径')
    p.add_argument('--analyze', action='store_true', help='跑分析（终端打印结果）')
    p.add_argument('--suggest', action='store_true', help='出下期选题建议（阶段 C，待接入）')
    p.add_argument('--render', action='store_true', help='出双风格卡片报告（阶段 D，待接入）')
    p.add_argument('--db', default=str(DEFAULT_DB), help=f'SQLite 路径，默认 {DEFAULT_DB}')
    p.add_argument('--snapshot-date', help='本次导入对应的快照日期 (YYYY-MM-DD)，默认今天')
    p.add_argument('--json', action='store_true', help='--analyze 改输出 JSON')
    args = p.parse_args()

    db_path = Path(args.db)

    if not any([args.import_csv, args.analyze, args.suggest, args.render]):
        p.print_help()
        return

    if args.import_csv:
        cmd_import(args.import_csv, db_path, args.snapshot_date)
    if args.analyze:
        cmd_analyze(db_path, json_out=args.json)
    if args.suggest:
        cmd_suggest(db_path)
    if args.render:
        cmd_render(db_path)


if __name__ == '__main__':
    main()
