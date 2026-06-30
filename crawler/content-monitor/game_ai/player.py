"""AI 玩家模块：负责启动游戏、执行脚本动作、视觉引导操控。

支持两种模式：
1. script  - 用户预设的固定动作序列（点击 / 按键 / 等待）
2. vision  - 用 Qwen-VL 识别当前画面，自动决策下一步
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pyautogui
import pygetwindow as gw

logger = logging.getLogger(__name__)

# pyautogui 全局安全设置
# 关闭 fail-safe：游戏操控需要点击任意坐标（含边角），不能因为移到角落就中断
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class Action:
    """单个玩家动作。"""
    type: str                           # click / key / hotkey / move / scroll / wait / screenshot / repeat_click
    x: Optional[int] = None            # 屏幕绝对坐标 或 窗口内相对坐标（当 relative=True）
    y: Optional[int] = None
    relative: bool = True              # 坐标是否相对于游戏窗口左上角
    key: Optional[str] = None          # pyautogui 键名，如 "space", "enter", "left"
    keys: Optional[List[str]] = None   # hotkey 组合键
    duration: float = 0.0              # 鼠标移动耗时（秒）
    delay: float = 0.5                 # 动作后等待（秒）
    scroll_amount: int = 3             # 滚轮格数
    button: str = "left"               # 鼠标按键
    label: str = ""                    # 日志 / 字幕标记
    repeat: int = 1                    # 重复执行次数（>=1），配合 delay 控制间隔
    repeat_interval: float = 0.0       # repeat 模式下每次点击之间的额外间隔（秒）
    total_duration: float = 0.0        # repeat_click 专用：持续点击总秒数（>0 时忽略 repeat）


@dataclass
class GameConfig:
    """游戏配置。"""
    name: str                          # 游戏名称（用于展示）
    exe_path: str                      # 可执行文件路径
    window_title: str = ""             # 窗口标题关键词（为空则自动检测）
    launch_wait: float = 5.0           # 启动等待秒数
    actions: List[Dict] = field(default_factory=list)   # 预设脚本
    vision_mode: bool = False          # 是否启用视觉引导模式
    vision_prompt: str = ""            # 视觉引导的背景提示词
    max_duration: int = 120            # 最长试玩秒数


# ─────────────────────────────────────────────
# 窗口工具
# ─────────────────────────────────────────────

def find_game_window(title_keyword: str, timeout: float = 10.0) -> Optional[object]:
    """按标题关键词查找游戏窗口，返回 pygetwindow 窗口对象。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = gw.getWindowsWithTitle(title_keyword)
        if wins:
            return wins[0]
        time.sleep(0.5)
    return None


def get_window_rect(win) -> Tuple[int, int, int, int]:
    """返回 (left, top, width, height)。"""
    return win.left, win.top, win.width, win.height


def focus_window(win):
    """将游戏窗口带到前台，若最小化则先还原。"""
    try:
        # 最小化状态（坐标为 -32000）则先还原
        if win.left <= -30000 or win.top <= -30000:
            win.restore()
            time.sleep(0.3)
        win.activate()
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"窗口激活失败: {e}")


# ─────────────────────────────────────────────
# 核心玩家
# ─────────────────────────────────────────────

class ScriptPlayer:
    """执行预设脚本的 AI 玩家。"""

    def __init__(self, config: GameConfig, progress_cb: Optional[Callable] = None):
        self.config = config
        self.progress_cb = progress_cb or (lambda msg: None)
        self._window = None
        self._proc: Optional[subprocess.Popen] = None

    # ── 生命周期 ──────────────────────────────

    def launch(self) -> bool:
        """启动游戏进程，等待窗口出现。若游戏已运行则直接接管已有窗口。"""
        exe = Path(self.config.exe_path)
        keyword = self.config.window_title or self.config.name

        # ── 先检测游戏窗口是否已经存在 ──
        existing_win = find_game_window(keyword, timeout=1.5)
        if existing_win is not None:
            self.progress_cb(f"🎮 检测到游戏已在运行，直接接管窗口: {existing_win.title}")
            self._window = existing_win
            focus_window(self._window)
            left, top, w, h = get_window_rect(self._window)
            self.progress_cb(f"✅ 窗口就绪 [{w}x{h}] @ ({left},{top})")
            return True

        # ── 游戏未运行，正常启动 ──
        if not exe.exists():
            raise FileNotFoundError(f"游戏路径不存在: {exe}")

        self.progress_cb(f"🎮 启动游戏: {self.config.name}")
        self._proc = subprocess.Popen(
            str(exe),
            cwd=str(exe.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )

        # 等待窗口出现
        wait = self.config.launch_wait
        self.progress_cb(f"⏳ 等待游戏启动 {wait:.0f}s ...")
        time.sleep(wait)

        # 查找窗口
        self._window = find_game_window(keyword, timeout=15.0)
        if self._window is None:
            # 宽松匹配：取最近出现的非系统窗口
            self.progress_cb("⚠️ 未找到精确窗口，尝试宽松匹配...")
            self._window = self._fallback_window()

        if self._window:
            focus_window(self._window)
            left, top, w, h = get_window_rect(self._window)
            self.progress_cb(f"✅ 窗口就绪 [{w}x{h}] @ ({left},{top})")
            return True
        else:
            self.progress_cb("❌ 无法找到游戏窗口，将使用全屏模式")
            return False

    def _fallback_window(self):
        """宽松匹配：排除桌面/任务栏，取最近一个可见窗口。"""
        exclude = {"Program Manager", "Windows Shell", "Task Switching"}
        for w in gw.getAllWindows():
            if w.title and w.title not in exclude and w.width > 200:
                return w
        return None

    def get_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if self._window:
            try:
                return get_window_rect(self._window)
            except Exception:
                pass
        return None

    def close(self):
        """关闭游戏进程。"""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception as e:
                logger.warning(f"关闭游戏失败: {e}")
                try:
                    self._proc.kill()
                except Exception:
                    pass

    # ── 动作执行 ──────────────────────────────

    def _resolve_xy(self, action: Action) -> Tuple[int, int]:
        """将相对坐标转为屏幕绝对坐标。"""
        if not action.relative or self._window is None:
            return action.x or 0, action.y or 0
        left, top, w, h = get_window_rect(self._window)
        # 支持 0~1 小数（相对比例）和整数（像素偏移）
        ax = action.x or 0
        ay = action.y or 0
        if isinstance(ax, float) and ax <= 1.0:
            ax = int(left + ax * w)
        else:
            ax = left + int(ax)
        if isinstance(ay, float) and ay <= 1.0:
            ay = int(top + ay * h)
        else:
            ay = top + int(ay)
        return ax, ay

    def execute_action(self, action: Action):
        """执行单个动作。支持 repeat 重复和 total_duration 持续执行。"""
        if action.label:
            self.progress_cb(f"🕹️ {action.label}")

        if action.type == "wait":
            time.sleep(action.delay or 1.0)

        elif action.type == "click":
            x, y = self._resolve_xy(action)
            # total_duration 模式：持续点击指定秒数
            if action.total_duration > 0:
                interval = max(action.repeat_interval, 0.05)
                deadline = time.time() + action.total_duration
                count = 0
                while time.time() < deadline:
                    pyautogui.click(x, y, button=action.button)
                    count += 1
                    time.sleep(interval)
                self.progress_cb(f"   持续点击结束，共 {count} 次")
            else:
                # repeat 模式：重复固定次数
                times = max(action.repeat, 1)
                for i in range(times):
                    pyautogui.click(x, y, button=action.button, duration=action.duration)
                    if i < times - 1:
                        time.sleep(action.repeat_interval if action.repeat_interval > 0 else 0.05)
                time.sleep(action.delay)

        elif action.type == "move":
            x, y = self._resolve_xy(action)
            pyautogui.moveTo(x, y, duration=action.duration)
            time.sleep(action.delay)

        elif action.type == "key":
            times = max(action.repeat, 1)
            for i in range(times):
                pyautogui.press(action.key)
                if i < times - 1:
                    time.sleep(action.repeat_interval if action.repeat_interval > 0 else 0.05)
            time.sleep(action.delay)

        elif action.type == "hotkey":
            pyautogui.hotkey(*action.keys)
            time.sleep(action.delay)

        elif action.type == "scroll":
            x, y = self._resolve_xy(action)
            pyautogui.scroll(action.scroll_amount, x=x, y=y)
            time.sleep(action.delay)

        elif action.type == "screenshot":
            # 占位：在 recorder 里统一截图
            time.sleep(action.delay)

        elif action.type == "drag":
            x, y = self._resolve_xy(action)
            tx = action.x or 0
            ty = action.y or 0
            pyautogui.dragTo(tx, ty, duration=action.duration, button=action.button)
            time.sleep(action.delay)

    def run_script(self, actions: Optional[List[Dict]] = None):
        """执行整个动作脚本列表。"""
        action_list = actions or self.config.actions
        total = len(action_list)
        for i, act_dict in enumerate(action_list):
            action = Action(**act_dict)
            self.progress_cb(f"[{i+1}/{total}] 执行: {action.type} {action.label}")
            try:
                self.execute_action(action)
            except Exception as e:
                logger.error(f"动作执行出错: {e}")
                self.progress_cb(f"⚠️ 动作失败，跳过: {e}")

    # ── 内置预设脚本库 ──────────────────────────

    @staticmethod
    def preset_scripts() -> Dict[str, List[Dict]]:
        """常用预设脚本（休闲/解谜游戏通用）。"""
        return {
            "start_and_explore": [
                {"type": "wait", "delay": 2.0, "label": "等待加载"},
                {"type": "key", "key": "space", "delay": 0.5, "label": "跳过开场"},
                {"type": "click", "x": 0.5, "y": 0.5, "delay": 1.0, "label": "点击屏幕中央开始"},
                {"type": "wait", "delay": 3.0, "label": "观察初始画面"},
                {"type": "key", "key": "right", "delay": 0.3, "label": "向右移动"},
                {"type": "key", "key": "right", "delay": 0.3},
                {"type": "key", "key": "right", "delay": 0.3},
                {"type": "key", "key": "space", "delay": 0.5, "label": "跳跃"},
                {"type": "wait", "delay": 2.0, "label": "观察关卡"},
            ],
            "menu_skip": [
                {"type": "wait", "delay": 3.0, "label": "等待主菜单"},
                {"type": "key", "key": "enter", "delay": 0.5, "label": "确认/开始"},
                {"type": "key", "key": "space", "delay": 0.5},
                {"type": "click", "x": 0.5, "y": 0.6, "delay": 1.0, "label": "点击开始游戏"},
            ],
        }


# ─────────────────────────────────────────────
# 视觉引导玩家（依赖 qwen_client）
# ─────────────────────────────────────────────

class VisionPlayer(ScriptPlayer):
    """
    触发式视觉引导玩家。

    正常情况下执行高频默认动作（如持续点击中央），速度不受影响。
    仅当检测到"画面卡住（连续多次截图差值低于阈值）"时，
    才调用 Qwen-VL 分析画面并决策，处理完毕后恢复默认动作。

    这样 Qwen-VL 只在真正需要时才触发一次，整体延迟极低。
    """

    def __init__(
        self,
        config: GameConfig,
        qwen_client,
        progress_cb=None,
        # ── 卡住检测参数 ──
        stuck_check_interval: int = 8,      # 每执行多少次默认动作后做一次截图比对
        stuck_threshold: int = 3,           # 连续几次"没变化"才认为卡住
        stuck_diff_ratio: float = 0.003,    # 像素差值低于画面总像素的 0.3% 视为"没变化"
        # ── 默认动作参数 ──
        default_action_interval: float = 0.5,   # 默认动作间隔（秒）
        default_action_x: float = 0.5,           # 默认点击 x（比例）
        default_action_y: float = 0.5,           # 默认点击 y（比例）
        # ── 卡住处理参数 ──
        input_name: str = "Player",         # 遇到输入框时自动输入的名字
    ):
        super().__init__(config, progress_cb)
        self._qwen = qwen_client
        self._stuck_check_interval = stuck_check_interval
        self._stuck_threshold = stuck_threshold
        self._stuck_diff_ratio = stuck_diff_ratio
        self._default_interval = default_action_interval
        self._default_x = default_action_x
        self._default_y = default_action_y
        self._input_name = input_name
        self._last_screenshot: Optional[bytes] = None   # 上一次截图的原始字节
        self._stuck_count: int = 0                      # 连续无变化次数

    # ── 本地快速截图（不依赖 recorder）────────────

    def _capture_raw(self) -> Optional[bytes]:
        """截取游戏窗口，返回 JPEG 字节（仅用于差值比对，压缩率高以节省计算）。"""
        try:
            import pyautogui
            import io
            rect = self.get_window_rect()
            if rect:
                left, top, w, h = rect
                shot = pyautogui.screenshot(region=(left, top, w, h))
            else:
                shot = pyautogui.screenshot()
            buf = io.BytesIO()
            # 缩小到 320x180 再压缩，差值比对不需要高分辨率
            shot = shot.resize((320, 180))
            shot.convert("RGB").save(buf, format="JPEG", quality=50)
            return buf.getvalue()
        except Exception as e:
            logger.warning(f"截图失败: {e}")
            return None

    def _capture_b64(self) -> Optional[str]:
        """截取游戏窗口，返回 base64 JPEG（用于传给 Qwen-VL，质量较高）。"""
        try:
            import pyautogui
            import io
            import base64
            rect = self.get_window_rect()
            if rect:
                left, top, w, h = rect
                shot = pyautogui.screenshot(region=(left, top, w, h))
            else:
                shot = pyautogui.screenshot()
            # 缩小到最大 1280 宽，避免高DPI下截图过大浪费 VL token
            w, h = shot.size
            if w > 1280:
                scale = 1280 / w
                shot = shot.resize((1280, int(h * scale)))
            buf = io.BytesIO()
            shot.convert("RGB").save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"截图(b64)失败: {e}")
            return None

    # ── 本地卡住检测 ──────────────────────────

    def _is_stuck(self) -> bool:
        """
        对比前后两帧截图的像素差值。
        差值低于阈值 → 画面没变化 → 累积 stuck_count。
        连续 stuck_threshold 次没变化 → 返回 True（认定卡住）。
        """
        current = self._capture_raw()
        if current is None:
            return False

        stuck = False
        if self._last_screenshot is not None:
            try:
                import io
                from PIL import Image, ImageChops
                import numpy as np
                img_prev = Image.open(io.BytesIO(self._last_screenshot)).convert("RGB")
                img_curr = Image.open(io.BytesIO(current)).convert("RGB")
                diff = ImageChops.difference(img_prev, img_curr)
                arr = np.array(diff, dtype=np.float32)
                # 差值像素占总像素的比例
                diff_ratio = float(arr.mean()) / 255.0
                if diff_ratio < self._stuck_diff_ratio:
                    self._stuck_count += 1
                    self.progress_cb(
                        f"[检测] 画面变化极小(diff={diff_ratio:.4f})，"
                        f"连续{self._stuck_count}次，阈值{self._stuck_threshold}"
                    )
                    stuck = self._stuck_count >= self._stuck_threshold
                else:
                    self._stuck_count = 0   # 画面有变化，重置计数
            except Exception as e:
                logger.warning(f"差值计算失败: {e}")
                self._stuck_count = 0

        self._last_screenshot = current
        return stuck

    # ── Qwen-VL 决策（仅卡住时调用）────────────

    def _vl_decide(self) -> List[Action]:
        """
        截图 → 调用 Qwen-VL → 返回一组动作列表。
        Qwen-VL 返回 JSON 数组，每个元素是一个动作。
        """
        self.progress_cb("🧠 检测到卡住，调用 Qwen-VL 分析画面...")
        screenshot_b64 = self._capture_b64()
        if not screenshot_b64:
            self.progress_cb("⚠️ 截图失败，跳过 VL 分析")
            return []

        system_prompt = (
            "你是一个游戏AI助手，负责分析游戏截图，判断当前卡在什么情况，并给出解决操作序列。\n"
            "常见情况及处理方式：\n"
            "  1. 出现输入框（输入角色名/玩家名）→ 先点击输入框，再输入文字，再按回车\n"
            "  2. 出现弹窗/对话框 → 点击确认/关闭按钮\n"
            "  3. 出现菜单/选项 → 点击目标选项\n"
            "  4. 加载中 → 等待\n\n"
            "请只返回一个 JSON 数组，每个元素是一个操作对象：\n"
            '[\n'
            '  {"type":"click","x":0.5,"y":0.5,"delay":0.3,"label":"点击输入框"},\n'
            '  {"type":"typewrite","text":"PlayerName","delay":0.5,"label":"输入名字"},\n'
            '  {"type":"key","key":"enter","delay":0.5,"label":"确认"}\n'
            ']\n'
            "type 可选值：click / key / typewrite / wait / hotkey\n"
            "  - click: x,y 为 0~1 比例坐标（相对游戏窗口）\n"
            "  - key: key 为 pyautogui 键名（enter/escape/space/backspace等）\n"
            "  - typewrite: text 为要输入的字符串（支持中英文）\n"
            "  - wait: delay 为等待秒数\n"
            "只返回 JSON 数组，不要有任何其他文字。"
        )

        game_context = (
            self.config.vision_prompt
            or f"这是游戏《{self.config.name}》的截图。游戏当前卡住了，请分析原因并给出操作序列。"
            f"如果需要输入名字，请使用：{self._input_name}"
        )

        try:
            result = self._qwen.analyze_game_screenshot(
                screenshot_b64, game_context, system_prompt
            )
            self.progress_cb(f"[VL返回] {result[:200]}")

            # 提取 JSON 数组
            import re
            m = re.search(r'\[.*\]', result, re.DOTALL)
            if not m:
                # 尝试提取单个对象并包装为数组
                m2 = re.search(r'\{.*\}', result, re.DOTALL)
                if m2:
                    actions_raw = [json.loads(m2.group())]
                else:
                    self.progress_cb("⚠️ VL 返回格式无法解析")
                    return []
            else:
                actions_raw = json.loads(m.group())

            actions = []
            for item in actions_raw:
                # typewrite 是扩展类型，Action 原生不支持，先保留为 dict 后处理
                actions.append(item)
            return actions

        except Exception as e:
            logger.warning(f"Qwen-VL 决策失败: {e}")
            return []

    def _execute_vl_actions(self, action_dicts: List[dict]):
        """执行 VL 返回的动作序列，支持 typewrite 扩展类型。"""
        for item in action_dicts:
            action_type = item.get("type", "wait")
            label = item.get("label", "")
            delay = item.get("delay", 0.3)

            self.progress_cb(f"[VL执行] {action_type} - {label}")

            if action_type == "typewrite":
                # 输入文字（支持中英文）
                text = item.get("text", self._input_name)
                try:
                    import pyperclip
                    # 通过剪贴板输入（支持中文）
                    pyperclip.copy(text)
                    pyautogui.hotkey("ctrl", "v")
                    self.progress_cb(f"[VL执行] 粘贴文字: {text}")
                except ImportError:
                    # fallback: typewrite（仅支持英文）
                    pyautogui.typewrite(text, interval=0.05)
                time.sleep(delay)

            else:
                # 其余类型转为 Action 对象执行
                try:
                    # 过滤掉 Action 不认识的字段
                    valid_fields = {f for f in Action.__dataclass_fields__}
                    filtered = {k: v for k, v in item.items() if k in valid_fields}
                    action = Action(**filtered)
                    self.execute_action(action)
                except Exception as e:
                    self.progress_cb(f"⚠️ VL动作执行失败: {e}")

    # ── 主循环 ────────────────────────────────

    def run_smart_loop(
        self,
        total_duration: float = 120.0,
        default_x: Optional[float] = None,
        default_y: Optional[float] = None,
        default_interval: Optional[float] = None,
    ):
        """
        智能游戏循环：

        1. 持续执行默认动作（高频点击，毫秒级）
        2. 每 stuck_check_interval 次动作后做本地截图差值检测
        3. 连续 stuck_threshold 次无变化 → 触发 Qwen-VL 分析（秒级，只触发一次）
        4. 执行 VL 返回的操作序列 → 重置卡住计数 → 回到步骤1

        Args:
            total_duration: 总运行时长（秒）
            default_x/y: 默认点击位置（0~1 比例，覆盖初始化参数）
            default_interval: 默认动作间隔（秒）
        """
        dx = default_x if default_x is not None else self._default_x
        dy = default_y if default_y is not None else self._default_y
        interval = default_interval if default_interval is not None else self._default_interval

        self.progress_cb(
            f"🎮 启动智能循环 | 总时长={total_duration}s | "
            f"默认点击=({dx},{dy}) | 间隔={interval}s | "
            f"卡住检测: 每{self._stuck_check_interval}次检测, 连续{self._stuck_threshold}次无变化触发VL"
        )

        deadline = time.time() + total_duration
        action_count = 0
        vl_trigger_count = 0

        while time.time() < deadline:
            # ── 执行默认动作 ──
            default_act = Action(
                type="click",
                x=dx, y=dy,
                relative=True,
                delay=0.0,   # delay 由下面的 sleep 控制
                label="",
            )
            try:
                focus_window(self._window)
                self.execute_action(default_act)
            except Exception as e:
                # pyautogui fail-safe 或其他异常，不中断循环
                logger.debug(f"默认动作异常(忽略): {e}")

            action_count += 1
            time.sleep(interval)

            # ── 定期卡住检测 ──
            if action_count % self._stuck_check_interval == 0:
                if self._is_stuck():
                    vl_trigger_count += 1
                    self.progress_cb(
                        f"🔔 卡住检测触发！(第{vl_trigger_count}次VL调用, "
                        f"已执行{action_count}次默认动作)"
                    )
                    # 调用 Qwen-VL
                    vl_actions = self._vl_decide()
                    if vl_actions:
                        self._execute_vl_actions(vl_actions)
                    else:
                        # VL 也没给出方案，尝试按 Escape 或 Enter 试试
                        self.progress_cb("⚠️ VL无法解决，尝试按 Escape/Enter 重试")
                        pyautogui.press("escape")
                        time.sleep(0.5)
                        pyautogui.press("enter")
                        time.sleep(0.5)
                    # 重置卡住状态，等画面稳定后重新检测
                    self._stuck_count = 0
                    self._last_screenshot = None
                    time.sleep(1.0)

        elapsed = total_duration
        self.progress_cb(
            f"✅ 智能循环结束 | 执行{action_count}次默认动作 | "
            f"触发{vl_trigger_count}次VL分析 | 耗时{elapsed:.0f}s"
        )

    # ── 兼容旧接口 ────────────────────────────

    def decide_action(self, screenshot_b64: str) -> Optional[Action]:
        """单步 VL 决策（兼容旧调用，建议改用 run_smart_loop）。"""
        system_prompt = (
            "你是一个游戏AI助手，负责分析游戏截图并给出下一步操作建议。\n"
            "请只返回一个JSON对象，格式：\n"
            '{"type":"click|key|wait","x":0.5,"y":0.5,"key":"space","delay":0.5,"label":"操作说明"}\n'
            "坐标使用0~1的比例值（相对于游戏窗口）。type为wait时无需坐标。"
        )
        bg = self.config.vision_prompt or f"这是游戏《{self.config.name}》的截图，请分析并给出最佳下一步操作。"
        try:
            result = self._qwen.analyze_game_screenshot(screenshot_b64, bg, system_prompt)
            import re
            m = re.search(r'\{.*\}', result, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return Action(**data, relative=True)
        except Exception as e:
            logger.warning(f"视觉决策失败: {e}")
        return None

    def run_vision_loop(self, capture_fn: Callable, max_steps: int = 30):
        """每步都调 VL 的旧循环（兼容保留，建议改用 run_smart_loop）。"""
        self.progress_cb("🧠 启动视觉引导模式(旧)...")
        for step in range(max_steps):
            screenshot_b64 = capture_fn()
            if not screenshot_b64:
                self.progress_cb("⚠️ 截图失败，跳过本步")
                time.sleep(1)
                continue
            action = self.decide_action(screenshot_b64)
            if action is None:
                self.progress_cb(f"[{step+1}] AI 无法决策，等待...")
                time.sleep(1.0)
                continue
            self.progress_cb(f"[{step+1}] AI 决策: {action.type} - {action.label}")
            self.execute_action(action)


# ─────────────────────────────────────────────
# 配置加载工具
# ─────────────────────────────────────────────

def load_game_config(config_path: str) -> GameConfig:
    """从 JSON 文件加载游戏配置。"""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return GameConfig(**data)


def save_game_config(config: GameConfig, config_path: str):
    """保存游戏配置到 JSON 文件。"""
    import dataclasses
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(config), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# 内置 Dyping Escape 配置
# ─────────────────────────────────────────────

DYPING_ESCAPE_CONFIG = GameConfig(
    name="Dyping Escape Demo",
    exe_path=r"C:\Program Files (x86)\Steam\steamapps\common\Dyping Escape Demo\DypingEscape.exe",
    window_title="Dyping",
    launch_wait=6.0,
    vision_mode=False,
    max_duration=120,
    actions=[
        # 等待主菜单加载
        {"type": "wait", "delay": 3.0, "label": "等待主菜单"},
        # 持续点击屏幕中央 90 秒（每次点击间隔 0.6s，即约每秒点击 1.6 次）
        {
            "type": "click",
            "x": 0.5, "y": 0.5,
            "total_duration": 90.0,
            "repeat_interval": 0.6,
            "label": "持续点击屏幕中央推进游戏"
        },
        {"type": "wait", "delay": 2.0, "label": "最终等待"},
    ],
)
