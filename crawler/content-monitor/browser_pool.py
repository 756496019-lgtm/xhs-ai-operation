"""Playwright 截图工具。

每次截图在调用线程中直接执行，用 Lock 防止多请求并发使用同一 Chrome profile。
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-extensions-except=",
    "--exclude-switches=enable-automation",
    "--lang=en-US",
]

_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
  get: () => ({
    query: (p) => Promise.resolve({ state: p.name === 'notifications' ? 'denied' : 'granted' })
  })
});
"""


def _get_profile_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "playwright_chrome_profile"
    )


def take_screenshot(url: str, extra_headers: dict = None) -> bytes:
    """截图指定 URL，返回 PNG bytes。线程安全，但同一时间只处理一个截图请求。"""
    from playwright.sync_api import sync_playwright

    profile_dir = _get_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)

    with _lock:
        with sync_playwright() as pw:
            try:
                context = pw.chromium.launch_persistent_context(
                    profile_dir,
                    channel="chrome",
                    headless=False,
                    args=_STEALTH_ARGS,
                    ignore_default_args=["--enable-automation"],
                )
            except Exception as e:
                logger.warning("Chrome 启动失败，回退到 headless Chromium: %s", e)
                context = pw.chromium.launch_persistent_context(
                    profile_dir,
                    headless=True,
                    args=_STEALTH_ARGS,
                    ignore_default_args=["--enable-automation"],
                )

            try:
                page = context.new_page()
                page.add_init_script(_STEALTH_INIT_SCRIPT)
                page.set_viewport_size({"width": 1280, "height": 720})
                if extra_headers:
                    page.set_extra_http_headers(extra_headers)
                # 将 www.reddit.com 转换为 old.reddit.com，规避 Cloudflare 拦截
                old_url = url.replace("www.reddit.com", "old.reddit.com", 1)
                try:
                    page.goto(old_url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    logger.warning("goto 超时，尝试继续截图: %s", e)
                time.sleep(2.0)
                # 关闭登录/注册弹窗（按 ESC、隐藏常见遮罩元素）
                try:
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
                    page.evaluate("""
                        const selectors = [
                            '.overlay', '.modal', '[data-testid="SDSModal"]',
                            '#login_popup', '.modal-content', '.bottom-bar',
                            '[class*="login"]', '[class*="signup"]', '[class*="register"]'
                        ];
                        selectors.forEach(s => {
                            document.querySelectorAll(s).forEach(el => el.remove());
                        });
                        document.body.style.overflow = 'auto';
                    """)
                except Exception:
                    pass
                time.sleep(1.0)
                return page.screenshot(full_page=True)
            finally:
                context.close()


def shutdown():
    pass
