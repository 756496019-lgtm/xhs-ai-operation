"""流水线调度器：串联 AI 试玩 → 录制 → 分析 → 剪辑 全流程，任务状态管理。"""

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 全局任务存储 ──────────────────────────────
_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = threading.Lock()

# 输出目录
DEMO_OUTPUT_DIR = Path(__file__).parent.parent / "video_outputs" / "game_demos"
DEMO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# 任务状态
# ─────────────────────────────────────────────

def _new_task(task_id: str, game_name: str) -> Dict:
    return {
        "task_id": task_id,
        "game_name": game_name,
        "status": "pending",   # pending / running / analyzing / editing / done / error
        "stage": "",
        "progress": 0,
        "logs": [],
        "summary": None,       # AI 生成的游戏总结
        "edit_script": None,   # AI 生成的剪辑脚本
        "raw_video": None,     # 原始录制视频路径
        "final_video": None,   # 最终剪辑视频路径
        "keyframes": [],       # 关键帧路径列表
        "error": None,
        "created_at": time.time(),
        "finished_at": None,
    }


def _update(task_id: str, **kwargs):
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


def _log(task_id: str, msg: str):
    logger.info(f"[{task_id[:8]}] {msg}")
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id]["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def get_demo_task(task_id: str) -> Optional[Dict]:
    with _tasks_lock:
        t = _tasks.get(task_id)
        return dict(t) if t else None


def list_demo_tasks() -> List[Dict]:
    with _tasks_lock:
        return [dict(t) for t in _tasks.values()]


# ─────────────────────────────────────────────
# 主调度器
# ─────────────────────────────────────────────

class GameDemoRunner:
    """
    完整 AI 试玩流水线调度器。

    使用方法：
        runner = GameDemoRunner(api_key="sk-...")
        task_id = runner.start(config_dict, options_dict)
        # 轮询 get_demo_task(task_id) 获取进度
    """

    def __init__(self, api_key: str):
        self._api_key = api_key

    def start(
        self,
        game_config_dict: Dict,
        options: Optional[Dict] = None,
    ) -> str:
        """
        启动一个新的 AI 试玩任务，后台异步执行。

        game_config_dict:
            name, exe_path, window_title, launch_wait,
            actions (list), vision_mode, max_duration

        options:
            output_duration (int, 60): 剪辑输出时长（秒）
            style (str): "短视频种草" / "游戏评测" / "搞笑解说"
            voice (str): TTS 声音
            keyframe_count (int, 8): 提取关键帧数量
            skip_play (bool, False): 跳过实际游戏操控，直接分析已有视频
            existing_video (str): skip_play=True 时指定已有视频路径
            custom_actions (list): 覆盖 config 中的 actions
        """
        options = options or {}
        task_id = str(uuid.uuid4())
        game_name = game_config_dict.get("name", "未知游戏")

        with _tasks_lock:
            _tasks[task_id] = _new_task(task_id, game_name)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(task_id, game_config_dict, options),
            daemon=True,
            name=f"GameDemo-{task_id[:8]}",
        )
        thread.start()
        logger.info(f"✅ 任务已启动: {task_id}")
        return task_id

    def _run_pipeline(self, task_id: str, config_dict: Dict, options: Dict):
        """后台执行完整流水线。"""
        try:
            self._pipeline(task_id, config_dict, options)
        except Exception as e:
            logger.exception(f"任务 {task_id} 异常: {e}")
            _update(task_id, status="error", error=str(e), finished_at=time.time())
            _log(task_id, f"❌ 任务失败: {e}")

    def _pipeline(self, task_id: str, config_dict: Dict, options: Dict):
        from .player import GameConfig, ScriptPlayer, VisionPlayer, DYPING_ESCAPE_CONFIG
        from .recorder import GameRecorder
        from .analyzer import GameAnalyzer
        from .editor import GameVideoEditor

        progress_cb = lambda msg: _log(task_id, msg)

        # 读取选项
        output_duration = options.get("output_duration", 60)
        style = options.get("style", "短视频种草")
        voice = options.get("voice", "zh-CN-XiaoxiaoNeural")
        keyframe_count = options.get("keyframe_count", 8)
        skip_play = options.get("skip_play", False)
        existing_video = options.get("existing_video")
        custom_actions = options.get("custom_actions")

        # 智能循环选项
        use_smart_loop = options.get("use_smart_loop", True)   # 默认启用智能循环
        smart_click_x = options.get("smart_click_x", 0.5)
        smart_click_y = options.get("smart_click_y", 0.5)
        smart_click_interval = options.get("smart_click_interval", 0.5)
        smart_input_name = options.get("input_name", "Player")
        stuck_check_interval = options.get("stuck_check_interval", 8)
        stuck_threshold = options.get("stuck_threshold", 3)

        # 工作目录
        work_dir = DEMO_OUTPUT_DIR / task_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # ── 1. 构建游戏配置 ────────────────────
        _update(task_id, status="running", stage="init", progress=5)
        progress_cb("⚙️ 初始化游戏配置...")

        try:
            config = GameConfig(**{
                k: v for k, v in config_dict.items()
                if k in GameConfig.__dataclass_fields__
            })
        except Exception as e:
            raise ValueError(f"游戏配置错误: {e}")

        if custom_actions:
            config.actions = custom_actions

        # ── 2. 录制（或使用已有视频）────────────
        raw_video_path = None

        if skip_play and existing_video:
            raw_video_path = Path(existing_video)
            progress_cb(f"⏭️ 跳过试玩，使用已有视频: {raw_video_path}")
            _update(task_id, raw_video=str(raw_video_path), progress=30)

        else:
            _update(task_id, stage="playing", progress=10)
            progress_cb("🎮 开始 AI 试玩流程...")

            recorder = GameRecorder(
                output_dir=work_dir,
                fps=30,
                quality="ultrafast",
            )

            # ── 选择玩家：智能循环 or 固定脚本 ──
            if use_smart_loop:
                from .analyzer import GameAnalyzer
                analyzer = GameAnalyzer(api_key=self._api_key)
                player = VisionPlayer(
                    config,
                    qwen_client=analyzer,
                    progress_cb=progress_cb,
                    stuck_check_interval=stuck_check_interval,
                    stuck_threshold=stuck_threshold,
                    default_action_interval=smart_click_interval,
                    default_action_x=smart_click_x,
                    default_action_y=smart_click_y,
                    input_name=smart_input_name,
                )
                progress_cb(
                    f"✅ 使用智能循环模式 | 点击({smart_click_x},{smart_click_y}) "
                    f"| 间隔{smart_click_interval}s | 输入名={smart_input_name}"
                )
            else:
                player = ScriptPlayer(config, progress_cb=progress_cb)
                if custom_actions:
                    config.actions = custom_actions
                progress_cb("✅ 使用固定脚本模式")

            try:
                # 启动游戏（已运行则直接接管）
                player.launch()
                window_rect = player.get_window_rect()

                # 开始录制
                progress_cb("🔴 开始录制...")
                raw_video_path = recorder.start(
                    filename="raw_gameplay.mp4",
                    window_rect=window_rect,
                )
                _update(task_id, raw_video=str(raw_video_path), progress=15)

                _update(task_id, stage="playing", progress=20)

                if use_smart_loop:
                    # 智能循环：持续运行 max_duration 秒，遇卡才触发 VL
                    player.run_smart_loop(
                        total_duration=float(config.max_duration),
                        default_x=smart_click_x,
                        default_y=smart_click_y,
                        default_interval=smart_click_interval,
                    )
                else:
                    # 固定脚本模式
                    player.run_script()
                    # 等待剩余录制时间
                    elapsed_target = config.max_duration
                    progress_cb(f"⏳ 等待至 {elapsed_target}s 录制...")
                    time.sleep(max(0, elapsed_target - 5))

            finally:
                # 停止录制、关闭游戏
                recorder.stop()
                try:
                    player.close()
                except Exception:
                    pass

            _update(task_id, progress=35)
            progress_cb("✅ 试玩录制完成")

        if not raw_video_path or not raw_video_path.exists():
            raise RuntimeError("录制视频文件不存在，流水线终止")

        # ── 3. 提取关键帧 ──────────────────────
        _update(task_id, stage="extracting", progress=40)
        progress_cb("🖼️ 提取关键帧...")

        recorder_temp = GameRecorder(output_dir=work_dir)
        frame_paths = recorder_temp.extract_keyframes(
            raw_video_path,
            count=keyframe_count,
            output_dir=work_dir / "keyframes",
        )
        frame_b64_list = recorder_temp.frames_to_base64(frame_paths)
        _update(task_id, keyframes=[str(p) for p in frame_paths], progress=50)

        if not frame_b64_list:
            raise RuntimeError("关键帧提取失败")

        # ── 4. AI 分析 ────────────────────────
        _update(task_id, stage="analyzing", progress=55)
        progress_cb("🧠 AI 分析游戏内容...")

        analyzer = GameAnalyzer(api_key=self._api_key)

        # 逐帧分析
        frame_descs = analyzer.analyze_frames_batch(
            frame_b64_list,
            config.name,
            progress_cb=progress_cb,
        )

        # 获取视频时长
        video_duration = recorder_temp._get_duration(raw_video_path)
        if video_duration <= 0:
            video_duration = config.max_duration

        _update(task_id, progress=65)
        progress_cb("📝 生成游戏总结...")
        summary = analyzer.generate_summary(config.name, frame_descs, int(video_duration))
        _update(task_id, summary=summary, progress=75)

        progress_cb("🎬 生成剪辑脚本...")
        edit_script = analyzer.generate_edit_script(
            config.name,
            frame_descs,
            int(video_duration),
            output_duration=output_duration,
            style=style,
        )
        _update(task_id, edit_script=edit_script, stage="editing", progress=80)

        # 保存分析结果到 JSON
        result_json = work_dir / "analysis_result.json"
        result_json.write_text(
            json.dumps(
                {"summary": summary, "edit_script": edit_script, "frame_descriptions": frame_descs},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ── 5. 视频剪辑 ───────────────────────
        _update(task_id, stage="editing", progress=82)
        progress_cb("✂️ 开始视频剪辑...")

        editor = GameVideoEditor(
            work_dir=work_dir / "edit_workspace",
            project_root=work_dir.parent.parent.parent,  # content-monitor 根目录
        )

        final_video = editor.run_full_pipeline(
            source_video=raw_video_path,
            edit_script=edit_script,
            output_filename="final_demo.mp4",
            voice=voice,
            progress_cb=progress_cb,
        )

        if final_video and final_video.exists():
            _update(
                task_id,
                status="done",
                stage="done",
                progress=100,
                final_video=str(final_video),
                finished_at=time.time(),
            )
            progress_cb(f"🎉 全部完成！最终视频: {final_video}")
        else:
            _update(
                task_id,
                status="error",
                error="剪辑失败，未生成最终视频",
                finished_at=time.time(),
            )
            progress_cb("❌ 剪辑步骤失败")
