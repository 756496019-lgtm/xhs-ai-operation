"""小红书账号笔记爬取器（playwright，零外部依赖）。

用法：
    # 第一次跑（推荐）：headful，让你手动确认登录态 + 验证 user_id
    python monitor.py --user-id 5e9b9f5400000000010066b6

    # 完整 URL（最稳）
    python monitor.py --user-url "https://www.xiaohongshu.com/user/profile/5e9b9f5400000000010066b6"

    # 后续静默跑
    python monitor.py --user-id ... --headless

    # 找不到 user_id？开浏览器自己搜
    python monitor.py --browse        # 打开小红书首页，自己导航到 taptap 主页

输出：
    data/{user_nickname}_{YYYYMMDD}.json
    data/last_page.png  （调试用，最后一帧页面截图）
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xhs_scraper import fetch_user_notes, resolve_profile_dir  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent / 'data'


def cmd_monitor(args: argparse.Namespace) -> int:
    user_input = args.user_url or args.user_id
    if not user_input:
        print('错误：必须提供 --user-id 或 --user-url，或用 --browse 手动导航。')
        return 2

    print(f'[monitor] 目标用户: {user_input}')
    print(f'[monitor] profile_dir: {resolve_profile_dir(args.profile)}')
    print(f'[monitor] headless: {args.headless}')
    print(f'[monitor] limit: {args.limit}')

    result = fetch_user_notes(
        user_url_or_id=user_input,
        limit=args.limit,
        profile_dir=args.profile,
        headless=args.headless,
        debug_dump_dir=str(OUT_DIR),
        scroll_rounds=args.scroll_rounds,
        scroll_pause=args.scroll_pause,
    )

    print(f'\n[monitor] 页面标题: {result["page_title"]}')
    print(f'[monitor] 监听到的相关 XHR 端点 ({len(result["xhr_endpoints_seen"])} 个):')
    for ep in result['xhr_endpoints_seen'][:8]:
        print(f'  - {ep[:120]}')

    if result['login_required']:
        print('\n[monitor] ⚠ 检测到登录拦截。')
        print('         请加 --headless 关闭，让浏览器以 headful 模式打开，')
        print('         手动登录小红书后重新跑（登录态会持久化到 profile）。')

    notes = result['notes']
    print(f'\n[monitor] 提取到笔记 {len(notes)} 条')
    if notes:
        print('  样例（前 3 条）:')
        for n in notes[:3]:
            print(f"  - {n['title'][:30]}  ({n['liked_count']} 赞 / {n['collected_count']} 收 / {n['comment_count']} 评)")

    if not notes:
        print('\n[monitor] ⚠ 未提取到笔记。可能原因:')
        print('  1. 登录态未生效（去 chrome profile 浏览器手动访问小红书登录后重试）')
        print('  2. user_id 无效（检查 --user-url 是否能在浏览器打开）')
        print('  3. 触发风控（页面截图见 data/last_page.png 确认）')
        print('  4. 笔记数据嵌套结构与预期不同（看 data/xhr_debug.json）')
        return 1

    user_nick = (notes[0].get('user_nickname') or 'unknown').replace('/', '_').replace(' ', '_')
    today = date.today().strftime('%Y%m%d')
    out_path = OUT_DIR / f'{user_nick}_{today}.json'
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
        'user_url': result['user_url'],
        'user_nickname': user_nick,
        'page_title': result['page_title'],
        'note_count': len(notes),
        'notes': notes,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n[monitor] 已写入 {out_path}')
    return 0


def cmd_browse(args: argparse.Namespace) -> int:
    """打开浏览器，让用户手动导航到目标账号主页（用于第一次找 user_id）。"""
    from playwright.sync_api import sync_playwright

    profile = resolve_profile_dir(args.profile)
    print(f'[browse] 打开小红书，profile={profile}')
    print('[browse] 请在浏览器里：')
    print('         1. 登录小红书（如尚未登录）')
    print('         2. 搜索 taptap，点开账号主页')
    print('         3. 复制地址栏 URL（形如 https://www.xiaohongshu.com/user/profile/...）')
    print('         4. 关闭浏览器后，把 URL 传给 --user-url 重跑 monitor')
    print()

    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(profile), channel='chrome', headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                ignore_default_args=['--enable-automation'],
                viewport={'width': 1280, 'height': 900}, locale='zh-CN',
            )
        except Exception as e:
            print(f'[browse] Chrome 失败，降级 Chromium: {e}')
            ctx = pw.chromium.launch_persistent_context(
                str(profile), headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                ignore_default_args=['--enable-automation'],
                viewport={'width': 1280, 'height': 900}, locale='zh-CN',
            )
        page = ctx.new_page()
        page.goto('https://www.xiaohongshu.com/explore', wait_until='domcontentloaded')
        print('[browse] 浏览器已打开。完成后关闭窗口即可。')
        try:
            page.wait_for_event('close', timeout=600000)
        except Exception:
            pass
        try:
            ctx.close()
        except Exception:
            pass
    return 0


def main() -> int:
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError):
            pass

    p = argparse.ArgumentParser(description='对标小红书账号笔记监控（playwright 直驱）')
    p.add_argument('--user-id', help='小红书 user_id（从 user 主页 URL 复制）')
    p.add_argument('--user-url', help='完整 user 主页 URL（与 --user-id 二选一）')
    p.add_argument('--limit', type=int, default=20, help='拉笔记上限，默认 20')
    p.add_argument('--profile', help='chrome profile 目录（默认 resolve_profile_dir 自动选）')
    p.add_argument('--headless', action='store_true', help='无头模式（首次运行务必关掉，让你手动登录）')
    p.add_argument('--scroll-rounds', type=int, default=3, help='下滚轮数触发懒加载，默认 3')
    p.add_argument('--scroll-pause', type=float, default=2.0, help='每轮下滚后等待秒数，默认 2.0')
    p.add_argument('--browse', action='store_true', help='打开浏览器手动登录 / 找 user_id（不抓数据）')
    args = p.parse_args()

    if args.browse:
        return cmd_browse(args)
    return cmd_monitor(args)


if __name__ == '__main__':
    sys.exit(main())
