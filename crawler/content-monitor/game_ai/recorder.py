"""录制模块：使用 ffmpeg gdigrab 录制游戏窗口，提取关键帧。"""

import base64
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import imageio_ffmpeg

logger = logging.getLogger(__name__)


class GameRecorder:
    """基于 ffmpeg gdigrab 的 Windows 游戏窗口录制器。"""

    def __init__(
        self,
        output_dir: Path,
        fps: int = 30,
        quality: str = "ultrafast",   # x264 preset
        crf: int = 23,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.quality = quality
        self.crf = crf
        self._proc: Optional[subprocess.Popen] = None
        self._recording = False
        self._output_path: Optional[Path] = None
        self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # ── 录制控制 ──────────────────────────────

    def start(
        self,
        filename: str = "raw_gameplay.mp4",
        window_rect: Optional[Tuple[int, int, int, int]] = None,
    ) -> Path:
        """
        开始录制。
        window_rect: (left, top, width, height) - 仅录制指定区域。
                     None 则录制全屏。
        """
        if self._recording:
            logger.warning("录制已在进行中")
            return self._output_path

        self._output_path = self.output_dir / filename
        cmd = self._build_cmd(window_rect)
        logger.info(f"录制命令: {' '.join(cmd)}")

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._recording = True
        logger.info(f"🔴 开始录制 → {self._output_path}")
        return self._output_path

    def stop(self) -> Optional[Path]:
        """停止录制，返回输出文件路径。"""
        if not self._recording or self._proc is None:
            return self._output_path

        logger.info("⏹️ 停止录制...")
        try:
            # 发送 q 键让 ffmpeg 优雅退出（ffmpeg 需要时间 mux/flush）
            self._proc.stdin.write(b"q")
            self._proc.stdin.flush()
            self._proc.wait(timeout=30)   # 延长至 30s，给 ffmpeg 足够时间写文件
        except Exception:
            # 超时后再等一下，因为 ffmpeg 可能正在写文件末尾
            time.sleep(3)
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
                    self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                    self._proc.wait(timeout=5)
                except Exception:
                    pass

        self._recording = False
        self._proc = None

        if self._output_path and self._output_path.exists():
            size_bytes = self._output_path.stat().st_size
            if size_bytes < 1024:
                logger.error(f"录制文件过小 ({size_bytes} bytes)，可能录制失败")
                return None
            size_mb = size_bytes / 1024 / 1024
            logger.info(f"✅ 录制完成: {self._output_path} ({size_mb:.1f} MB)")
            return self._output_path
        else:
            logger.error("录制文件不存在，可能录制失败")
            return None

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ── ffmpeg 命令构建 ──────────────────────

    def _build_cmd(self, window_rect: Optional[Tuple[int, int, int, int]]) -> List[str]:
        cmd = [self._ffmpeg, "-y"]

        if window_rect:
            left, top, width, height = window_rect
            # 保证宽高为偶数（x264 要求）
            width = width if width % 2 == 0 else width - 1
            height = height if height % 2 == 0 else height - 1
            cmd += [
                "-f", "gdigrab",
                "-framerate", str(self.fps),
                "-offset_x", str(left),
                "-offset_y", str(top),
                "-video_size", f"{width}x{height}",
                "-i", "desktop",
            ]
        else:
            cmd += [
                "-f", "gdigrab",
                "-framerate", str(self.fps),
                "-i", "desktop",
            ]

        cmd += [
            "-c:v", "libx264",
            "-preset", self.quality,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            str(self._output_path),
        ]
        return cmd

    # ── 截图工具 ─────────────────────────────

    def capture_frame(
        self,
        window_rect: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[str]:
        """
        截取当前画面，返回 base64 编码的 JPEG 字符串。
        用于 AI 视觉决策或关键帧分析。
        """
        try:
            import pyautogui
            from PIL import Image
            import io

            if window_rect:
                left, top, w, h = window_rect
                screenshot = pyautogui.screenshot(region=(left, top, w, h))
            else:
                screenshot = pyautogui.screenshot()

            # 压缩为 JPEG 以节省 token
            buf = io.BytesIO()
            screenshot.convert("RGB").save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    # ── 关键帧提取 ────────────────────────────

    def extract_keyframes(
        self,
        video_path: Path,
        count: int = 8,
        output_dir: Optional[Path] = None,
    ) -> List[Path]:
        """
        从录制的视频中均匀提取 N 帧，保存为 JPEG。
        返回帧文件路径列表。
        """
        out_dir = output_dir or (video_path.parent / "keyframes")
        out_dir.mkdir(parents=True, exist_ok=True)

        # 获取视频时长
        duration = self._get_duration(video_path)
        if duration <= 0:
            logger.error("无法获取视频时长")
            return []

        interval = duration / (count + 1)
        frames = []

        for i in range(1, count + 1):
            ts = interval * i
            out_file = out_dir / f"frame_{i:02d}.jpg"
            cmd = [
                self._ffmpeg, "-y",
                "-ss", f"{ts:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(out_file),
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0 and out_file.exists():
                frames.append(out_file)
            else:
                logger.warning(f"第 {i} 帧提取失败 (ts={ts:.1f}s)")

        logger.info(f"提取了 {len(frames)} 个关键帧")
        return frames

    def _get_duration(self, video_path: Path) -> float:
        """获取视频时长（秒）。优先用 ffprobe，不存在时用 ffmpeg 解析。"""
        import json as _json

        # 先尝试同目录下的 ffprobe
        ffprobe_candidates = [
            self._ffmpeg.replace("ffmpeg-win-x86_64", "ffprobe-win-x86_64"),
            self._ffmpeg.replace("ffmpeg", "ffprobe"),
            "ffprobe",
            "ffprobe.exe",
        ]

        for ffprobe in ffprobe_candidates:
            try:
                result = subprocess.run(
                    [
                        ffprobe, "-v", "quiet",
                        "-print_format", "json",
                        "-show_format",
                        str(video_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = _json.loads(result.stdout)
                    return float(data["format"]["duration"])
            except (FileNotFoundError, OSError):
                continue
            except Exception as e:
                logger.warning(f"ffprobe 候选 {ffprobe} 失败: {e}")
                continue

        # ffprobe 全部失败，用 ffmpeg stderr 解析时长
        try:
            result = subprocess.run(
                [self._ffmpeg, "-i", str(video_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            import re
            # ffmpeg -i 会在 stderr 输出 Duration: HH:MM:SS.ss
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
            if m:
                h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                duration = h * 3600 + mi * 60 + s
                logger.info(f"ffmpeg 解析时长: {duration:.1f}s")
                return duration
        except Exception as e:
            logger.error(f"ffmpeg 解析时长失败: {e}")

        logger.error("无法获取视频时长，所有方法均失败")
        return 0.0

    def frames_to_base64(self, frame_paths: List[Path]) -> List[str]:
        """将帧文件列表转为 base64 字符串列表。"""
        result = []
        for p in frame_paths:
            try:
                with open(p, "rb") as f:
                    result.append(base64.b64encode(f.read()).decode("utf-8"))
            except Exception as e:
                logger.warning(f"帧转 base64 失败 {p}: {e}")
        return result
