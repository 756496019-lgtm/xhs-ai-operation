"""小红书账号笔记抓取器（基于 playwright）。

设计理念：
  - **不逆向 sign**：让浏览器自己算（小红书 sign 算法每隔几个月会变，逆向不可持续）
  - **被动监听 XHR**：访问 user 主页时，监听 page.on('response')，匹配 XHR 路径，直接拿 JSON
  - **持久 chrome profile**：登录态保存在本地目录，首次手动登录后续静默
  - **stealth 配置**：复用 content-monitor/browser_pool.py 的反检测脚本

参考来源（仅参考思路，不引入任何外部依赖）：
  - D:/project/content-monitor/browser_pool.py（stealth args + init script）
  - https://github.com/Panniantong/Agent-Reach（OpenCLI/MCP 路线）
  - https://github.com/ReaJason/xhs（逆向 API 路线）

依赖：playwright >= 1.40（content-monitor requirements 已装 1.58）
"""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any


_STEALTH_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-infobars',
    '--disable-dev-shm-usage',
    '--exclude-switches=enable-automation',
    '--lang=zh-CN',
]

_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
  get: () => ({
    query: (p) => Promise.resolve({ state: p.name === 'notifications' ? 'denied' : 'granted' })
  })
});
"""


def resolve_profile_dir(custom: str | None = None) -> Path:
    """profile 优先级：CLI 参数 > 环境变量 > 已有的 gongsi-weeklyreport 登录态 > 本仓 fallback。"""
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)
        return p
    env = os.environ.get('XHS_CHROME_PROFILE')
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    candidates = [
        Path(r'D:/project/gongsi-weeklyreport/playwright_chrome_profile'),
        Path(r'D:/project/content-monitor/playwright_chrome_profile'),
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return c
    fallback = Path(__file__).resolve().parent / 'chrome_profile'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def normalize_user_url(s: str) -> str:
    """把 'user_id' / 'user/profile/...' / 'https://...' 统一成完整 URL。"""
    if s.startswith('http'):
        return s
    s = s.lstrip('/')
    if s.startswith('user/'):
        return f'https://www.xiaohongshu.com/{s}'
    return f'https://www.xiaohongshu.com/user/profile/{s}'


def _extract_notes_from_response(data: Any, limit: int = 999) -> list[dict[str, Any]]:
    """探测各种可能的字段嵌套路径，提取笔记列表。"""
    notes: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return notes

    candidates: list[Any] = []
    if 'data' in data and isinstance(data['data'], dict):
        d = data['data']
        for key in ('notes', 'items', 'feeds', 'list'):
            if key in d and isinstance(d[key], list):
                candidates.extend(d[key])
    for key in ('notes', 'items', 'feeds', 'list'):
        if key in data and isinstance(data[key], list):
            candidates.extend(data[key])

    for item in candidates:
        if not isinstance(item, dict):
            continue
        n = _normalize_note(item)
        if n.get('title') or n.get('note_id'):
            notes.append(n)
            if len(notes) >= limit:
                break
    return notes


def _normalize_note(raw: dict[str, Any]) -> dict[str, Any]:
    """适配 user_posted / feed / note_card 三种常见嵌套结构。

    小红书 user_posted 列表 API 故意把 note_id 留空（反爬），靠 xsec_token 定位。
    若 note_id 空则用 xsec_token 头 16 字符作伪 ID（保证去重 & 跨周可对比）。
    """
    nc = raw.get('note_card') if isinstance(raw.get('note_card'), dict) else raw
    interact = nc.get('interact_info', {}) if isinstance(nc.get('interact_info'), dict) else {}
    user = nc.get('user', {}) if isinstance(nc.get('user'), dict) else {}
    cover = nc.get('cover', {}) if isinstance(nc.get('cover'), dict) else {}

    nid = raw.get('id') or raw.get('note_id') or nc.get('note_id') or ''
    xsec = raw.get('xsec_token') or nc.get('xsec_token') or ''
    cover_url = cover.get('url_default') or cover.get('url') or cover.get('url_pre') or ''
    if not nid and cover_url:
        tail = cover_url.split('/')[-1].split('!')[0]
        if tail:
            nid = f'cover:{tail[:40]}'
    if not nid and xsec:
        nid = f'xsec:{xsec[:16]}'

    return {
        'note_id': nid,
        'xsec_token': xsec,
        'title': nc.get('display_title') or nc.get('title') or '',
        'desc': (nc.get('desc') or '')[:300],
        'note_type': nc.get('type') or nc.get('note_type') or '',
        'liked_count': _to_int(interact.get('liked_count') or nc.get('liked_count') or 0),
        'collected_count': _to_int(interact.get('collected_count') or 0),
        'comment_count': _to_int(interact.get('comment_count') or 0),
        'shared_count': _to_int(interact.get('shared_count') or interact.get('share_count') or 0),
        'sticky': bool(interact.get('sticky', False)),
        'cover_url': cover_url,
        'publish_time': nc.get('time') or nc.get('publish_time') or '',
        'user_id': user.get('user_id') or user.get('id') or '',
        'user_nickname': user.get('nickname') or user.get('nick_name') or '',
        'note_url': (
            f'https://www.xiaohongshu.com/explore/{nid}?xsec_token={xsec}&xsec_source=pc_user'
            if xsec and not nid.startswith('xsec:')
            else (f'https://www.xiaohongshu.com/user/profile/{user.get("user_id", "")}' if user.get('user_id') else '')
        ),
    }


def _to_int(v: Any) -> int:
    """容错：'1234' / '1.2万' / 1234 / None -> int。"""
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v).strip().replace(',', '').replace(' ', '')
    if not s or s in ('-', '--', 'N/A'):
        return 0
    if s.endswith('万'):
        try:
            return int(float(s[:-1]) * 10000)
        except ValueError:
            return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def fetch_user_notes(
    user_url_or_id: str,
    limit: int = 20,
    profile_dir: str | None = None,
    headless: bool = False,
    debug_dump_dir: str | None = None,
    scroll_rounds: int = 3,
    scroll_pause: float = 2.0,
    use_fresh_context: bool = True,
    wait_for_data_seconds: int = 30,
) -> dict[str, Any]:
    """主入口：访问指定用户的小红书主页，监听 XHR 拿笔记列表。

    Args:
        user_url_or_id: user_id 字符串 / user/profile/... 路径 / 完整 URL，三选一
        limit:          笔记上限
        profile_dir:    chrome profile 目录（仅 use_fresh_context=False 时生效）
        headless:       是否无头
        debug_dump_dir: 把所有 XHR 响应 dump 到这里供调试（无论成功失败）
        scroll_rounds:  下滚多少轮触发懒加载
        scroll_pause:   每轮间隔秒数
        use_fresh_context: True = 每次新 context（避免 profile 被风控标记）。
                          推荐打开。False 时复用 profile_dir 持久化登录态。
        wait_for_data_seconds: 主动 polling 等首条 user_posted 成功响应的最长秒数。

    Returns:
        {
          'user_url': str,
          'profile_dir': str,
          'notes': list[dict],
          'xhr_endpoints_seen': list[str],
          'login_required': bool,
          'success_response_seen': bool,    # XHR 里见到至少一个 code=0 user_posted
        }
    """
    from playwright.sync_api import sync_playwright

    profile = resolve_profile_dir(profile_dir) if not use_fresh_context else None
    user_url = normalize_user_url(user_url_or_id)

    captured: list[dict[str, Any]] = []
    seen_endpoints: list[str] = []

    INTERESTING = ('user_posted', 'note_feed', 'feed/user', '/feed', '/api/sns/web', 'note/explore', 'homefeed')

    with sync_playwright() as pw:
        browser = None
        ctx = None
        if use_fresh_context:
            try:
                browser = pw.chromium.launch(
                    channel='chrome',
                    headless=headless,
                    args=_STEALTH_ARGS,
                    ignore_default_args=['--enable-automation'],
                )
            except Exception as e:
                print(f'[xhs] Chrome 失败，降级 Chromium: {e}')
                browser = pw.chromium.launch(
                    headless=headless,
                    args=_STEALTH_ARGS,
                    ignore_default_args=['--enable-automation'],
                )
            ctx = browser.new_context(
                viewport={'width': 1280, 'height': 900},
                locale='zh-CN',
                user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                            'AppleWebKit/537.36 (KHTML, like Gecko) '
                            'Chrome/120.0.0.0 Safari/537.36'),
            )
        else:
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(profile),
                    channel='chrome',
                    headless=headless,
                    args=_STEALTH_ARGS,
                    ignore_default_args=['--enable-automation'],
                    viewport={'width': 1280, 'height': 900},
                    locale='zh-CN',
                )
            except Exception as e:
                print(f'[xhs] Chrome 启动失败，降级 Chromium: {e}')
                ctx = pw.chromium.launch_persistent_context(
                    str(profile),
                    headless=headless,
                    args=_STEALTH_ARGS,
                    ignore_default_args=['--enable-automation'],
                    viewport={'width': 1280, 'height': 900},
                    locale='zh-CN',
                )

        page = ctx.new_page()
        page.add_init_script(_STEALTH_INIT_SCRIPT)

        def on_response(response):
            url = response.url
            if 'xiaohongshu.com' not in url and 'xhscdn' not in url:
                return
            if not any(kw in url for kw in INTERESTING):
                return
            seen_endpoints.append(url)
            try:
                data = response.json()
                captured.append({'url': url, 'data': data})
            except Exception:
                pass

        page.on('response', on_response)

        try:
            page.goto(user_url, wait_until='domcontentloaded', timeout=45000)
        except Exception as e:
            print(f'[xhs] goto 异常（继续）：{e}')

        time.sleep(3)
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass

        page_title = ''
        try:
            page_title = page.title() or ''
        except Exception:
            pass

        success_response_seen = False
        deadline = time.time() + wait_for_data_seconds
        scrolls_done = 0
        while time.time() < deadline:
            for c in captured:
                if 'user_posted' in c['url'] and isinstance(c['data'], dict):
                    if c['data'].get('code') == 0 and c['data'].get('data', {}).get('notes'):
                        success_response_seen = True
                        break
            if success_response_seen:
                break
            if scrolls_done < scroll_rounds:
                try:
                    page.mouse.wheel(0, 1500)
                except Exception:
                    pass
                scrolls_done += 1
            time.sleep(scroll_pause)

        login_required = False
        try:
            html = page.content()
            if '请登录' in html or '登录小红书' in html or 'login_container' in html.lower():
                login_required = True
        except Exception:
            pass

        for c in captured:
            d = c.get('data')
            if isinstance(d, dict):
                code = d.get('code')
                msg = str(d.get('msg', ''))
                if code in (-101, 401) or '登录' in msg or 'login' in msg.lower():
                    if not success_response_seen:
                        login_required = True
                    break

        notes: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for c in captured:
            for n in _extract_notes_from_response(c['data'], limit=limit - len(notes)):
                key = n.get('note_id') or n.get('xsec_token') or n.get('title')
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    notes.append(n)
                    if len(notes) >= limit:
                        break
            if len(notes) >= limit:
                break

        if debug_dump_dir:
            dump_path = Path(debug_dump_dir) / 'xhr_debug.json'
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_payload = []
            for c in captured:
                entry = {
                    'url': c['url'],
                    'top_keys': list(c['data'].keys()) if isinstance(c['data'], dict) else type(c['data']).__name__,
                }
                if 'user_posted' in c['url'] or 'note_feed' in c['url']:
                    entry['data'] = c['data']
                else:
                    entry['sample'] = str(c['data'])[:1500]
                dump_payload.append(entry)
            dump_path.write_text(json.dumps(dump_payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

        try:
            screenshot_dir = Path(debug_dump_dir) if debug_dump_dir else (profile.parent if profile else Path.cwd()) / 'data'
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_dir / 'last_page.png'), full_page=False)
        except Exception:
            pass

        try:
            ctx.close()
        except Exception:
            pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    return {
        'user_url': user_url,
        'profile_dir': str(profile) if profile else 'fresh-context',
        'page_title': page_title,
        'notes': notes,
        'xhr_endpoints_seen': sorted(set(seen_endpoints)),
        'login_required': login_required,
        'success_response_seen': success_response_seen,
    }
