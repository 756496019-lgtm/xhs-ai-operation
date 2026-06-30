"""
AI 试玩功能分步测试脚本
运行方式：python test_game_ai.py [步骤编号]

步骤：
  1  - 测试窗口检测（不启动游戏，扫描当前所有窗口）
  2  - 测试启动游戏 + 窗口检测
  3  - 测试单条动作执行（需要游戏已运行）
  4  - 测试截图（需要游戏已运行）
  5  - 运行完整脚本（启动 + 执行所有动作，不录制）
  all - 按顺序运行 1→2→3→4→5
"""

import sys
import time
import json
from pathlib import Path

# 加入项目路径
sys.path.insert(0, str(Path(__file__).parent))

GAME_EXE = r"C:\Program Files (x86)\Steam\steamapps\common\Dyping Escape Demo\DypingEscape.exe"
GAME_NAME = "Dyping Escape Demo"
WINDOW_KEYWORD = "Dyping"

# ─────────────────────────────────────────────
# 步骤 1：扫描当前所有可见窗口
# ─────────────────────────────────────────────
def test_window_scan():
    print("\n[步骤1] 扫描当前所有可见窗口")
    print("-" * 50)
    import pygetwindow as gw
    windows = gw.getAllWindows()
    visible = [(w.title, w.left, w.top, w.width, w.height)
               for w in windows if w.title and w.width > 100]
    print("Found %d windows:" % len(visible))
    for t, l, top, w, h in visible:
        try:
            safe_title = t[:70].encode('ascii', errors='replace').decode('ascii')
        except Exception:
            safe_title = repr(t[:40])
        print("  [%dx%d @ (%d,%d)]  %s" % (w, h, l, top, safe_title))

    # 检测游戏窗口是否已在运行
    matches = [t for t,*_ in visible if WINDOW_KEYWORD.lower() in t.lower()]
    if matches:
        print("\nGame window found: %s" % matches)
    else:
        print("\nGame not running (keyword '%s' not found)" % WINDOW_KEYWORD)
    return bool(matches)


# ─────────────────────────────────────────────
# 步骤 2：启动游戏 + 检测窗口
# ─────────────────────────────────────────────
def test_launch_game():
    print("\n[步骤2] 启动游戏并检测窗口")
    print("-" * 50)
    from game_ai.player import ScriptPlayer, DYPING_ESCAPE_CONFIG

    DYPING_ESCAPE_CONFIG.launch_wait = 8.0  # 给足够时间
    player = ScriptPlayer(DYPING_ESCAPE_CONFIG, progress_cb=print)

    print("启动游戏...")
    success = player.launch()

    rect = player.get_window_rect()
    if rect:
        l, t, w, h = rect
        print(f"\n窗口信息: {w}x{h} @ ({l},{t})")
        print(f"窗口中心: ({l + w//2}, {t + h//2})")
        # 高 DPI 检测
        import pyautogui
        screen_w, screen_h = pyautogui.size()
        print(f"屏幕分辨率: {screen_w}x{screen_h}")
        if screen_w >= 3000:
            print("⚠️  检测到高分辨率屏幕（4K/2K）- 坐标已按实际像素计算，无需额外缩放")
    else:
        print("未获取到窗口矩形")

    print("\n保持游戏运行，等待 3s 后进行下一步测试...")
    time.sleep(3)
    return player, success


# ─────────────────────────────────────────────
# 步骤 3：测试单条动作（在已运行的游戏上）
# ─────────────────────────────────────────────
def test_single_actions(player):
    print("\n[步骤3] 测试单条动作执行")
    print("-" * 50)
    from game_ai.player import Action
    import pygetwindow as gw

    # 先确认窗口仍然存在
    wins = gw.getWindowsWithTitle(WINDOW_KEYWORD)
    if not wins:
        print("游戏窗口未找到，请先启动游戏")
        return

    win = wins[0]
    player._window = win
    from game_ai.player import focus_window, get_window_rect
    focus_window(win)
    l, t, w, h = get_window_rect(win)
    print(f"窗口: {w}x{h} @ ({l},{t})")

    test_actions = [
        {"type": "wait", "delay": 1.0, "label": "等待 1s"},
        {"type": "key", "key": "escape", "delay": 0.5, "label": "按 ESC（测试键盘响应）"},
        {"type": "key", "key": "escape", "delay": 0.5, "label": "再按 ESC（关闭可能弹出的菜单）"},
        {"type": "move", "x": 0.5, "y": 0.5, "delay": 0.3, "label": "移动鼠标到窗口中央"},
        {"type": "click", "x": 0.5, "y": 0.5, "delay": 0.5, "label": "点击窗口中央"},
    ]

    for i, act_dict in enumerate(test_actions):
        a = Action(**act_dict)
        print(f"  [{i+1}/{len(test_actions)}] {a.type}: {a.label}")
        try:
            # 手动计算绝对坐标以便打印
            if a.type in ("click", "move") and a.x is not None:
                ax = l + int((a.x or 0) * w) if a.relative else (a.x or 0)
                ay = t + int((a.y or 0) * h) if a.relative else (a.y or 0)
                print(f"         -> 绝对坐标: ({ax}, {ay})")
            player.execute_action(a)
            print(f"         -> OK")
        except Exception as e:
            print(f"         -> 失败: {e}")

    print("\n动作测试完成")


# ─────────────────────────────────────────────
# 步骤 4：截图测试
# ─────────────────────────────────────────────
def test_screenshot():
    print("\n[步骤4] 截图测试")
    print("-" * 50)
    from game_ai.recorder import GameRecorder
    import pygetwindow as gw

    wins = gw.getWindowsWithTitle(WINDOW_KEYWORD)
    rect = None
    if wins:
        w = wins[0]
        rect = (w.left, w.top, w.width, w.height)
        print(f"游戏窗口: {rect}")
    else:
        print("未找到游戏窗口，将截取全屏")

    recorder = GameRecorder(output_dir=Path("D:/project/content-monitor/video_outputs/test"))

    print("截图中...")
    b64 = recorder.capture_frame(window_rect=rect)
    if b64:
        # 解码保存为文件
        import base64
        img_data = base64.b64decode(b64)
        out = Path("D:/project/content-monitor/video_outputs/test/screenshot_test.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(img_data)
        print(f"截图成功: {out} ({len(img_data)//1024} KB)")
        print(f"base64 长度: {len(b64)} 字符")
    else:
        print("截图失败")
    return b64


# ─────────────────────────────────────────────
# 步骤 5：完整脚本执行（启动 + 全部动作，不录制）
# ─────────────────────────────────────────────
def test_full_script():
    print("\n[步骤5] 完整脚本执行测试（不录制视频）")
    print("-" * 50)
    from game_ai.player import ScriptPlayer, DYPING_ESCAPE_CONFIG
    import pygetwindow as gw

    def progress_cb(msg):
        print(f"  {msg}")

    # 检查游戏是否已经在运行
    wins = gw.getWindowsWithTitle(WINDOW_KEYWORD)
    if wins:
        print("游戏已在运行，直接使用现有窗口执行脚本")
        player = ScriptPlayer(DYPING_ESCAPE_CONFIG, progress_cb=progress_cb)
        player._window = wins[0]
        from game_ai.player import focus_window
        focus_window(wins[0])
        time.sleep(0.5)
    else:
        print("游戏未运行，先启动游戏...")
        player = ScriptPlayer(DYPING_ESCAPE_CONFIG, progress_cb=progress_cb)
        player.launch()

    print(f"\n窗口: {player.get_window_rect()}")
    print(f"\n开始执行 {len(DYPING_ESCAPE_CONFIG.actions)} 条动作脚本...")
    print("（如需中断，将鼠标移到屏幕左上角触发 pyautogui FAILSAFE）\n")

    start = time.time()
    player.run_script()
    elapsed = time.time() - start

    print(f"\n脚本执行完毕，耗时 {elapsed:.1f}s")

    # 最后截一张图
    print("\n执行结束截图...")
    test_screenshot()

    return player


# ─────────────────────────────────────────────
# 步骤 6：录制测试（30秒短录）
# ─────────────────────────────────────────────
def test_recording():
    print("\n[步骤6] 短录制测试（30秒）")
    print("-" * 50)
    from game_ai.recorder import GameRecorder
    import pygetwindow as gw

    wins = gw.getWindowsWithTitle(WINDOW_KEYWORD)
    rect = None
    if wins:
        w = wins[0]
        rect = (w.left, w.top, w.width, w.height)
        print(f"录制区域: {rect}")
    else:
        print("游戏未运行，将录制全屏（建议先启动游戏）")

    out_dir = Path("D:/project/content-monitor/video_outputs/test")
    recorder = GameRecorder(out_dir, fps=30, quality="ultrafast")

    print("开始录制 30 秒...")
    video_path = recorder.start("test_30s.mp4", window_rect=rect)
    time.sleep(30)
    result = recorder.stop()

    if result and result.exists():
        size = result.stat().st_size / 1024 / 1024
        print(f"录制成功: {result} ({size:.1f} MB)")

        # 提取关键帧
        print("提取关键帧...")
        frames = recorder.extract_keyframes(result, count=4)
        print(f"提取了 {len(frames)} 帧: {[str(f) for f in frames]}")
    else:
        print("录制失败或文件不存在")


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "1"

    print("=" * 60)
    print("  AI 游戏试玩 — 分步测试")
    print(f"  步骤: {step}")
    print("=" * 60)

    if step == "1":
        test_window_scan()

    elif step == "2":
        player, ok = test_launch_game()
        if ok:
            print("\n游戏启动成功！可以继续运行步骤 3/4/5")
        else:
            print("\n游戏启动有问题，请检查 exe 路径或手动启动游戏后再测试")

    elif step == "3":
        from game_ai.player import ScriptPlayer, DYPING_ESCAPE_CONFIG
        wins = __import__("pygetwindow").getWindowsWithTitle(WINDOW_KEYWORD)
        if not wins:
            print("请先运行步骤2启动游戏，或手动启动游戏")
        else:
            p = ScriptPlayer(DYPING_ESCAPE_CONFIG, progress_cb=print)
            p._window = wins[0]
            test_single_actions(p)

    elif step == "4":
        test_screenshot()

    elif step == "5":
        test_full_script()

    elif step == "6":
        test_recording()

    elif step == "all":
        print("顺序执行所有步骤...\n")
        test_window_scan()
        player, ok = test_launch_game()
        if ok:
            test_single_actions(player)
            test_screenshot()
        test_full_script()

    else:
        print(__doc__)
