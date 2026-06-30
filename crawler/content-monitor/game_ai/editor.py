"""视频剪辑模块：根据 AI 剪辑脚本，用 ffmpeg 切割、拼接、叠加字幕、添加 BGM 和 TTS 解说。"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import imageio_ffmpeg

logger = logging.getLogger(__name__)


class GameVideoEditor:
    """
    根据 AI 生成的剪辑脚本，对录制的游戏视频进行自动剪辑。

    流程：
    1. 按脚本时间戳切割片段
    2. TTS 生成解说音频
    3. 拼接片段
    4. 叠加字幕
    5. 混入 BGM
    6. 导出最终视频
    """

    # 内置 BGM 路径（相对于 content-monitor 项目根）
    BGM_MAP = {
        "轻松欢快": "static/bgm/happy_light.mp3",
        "像素风": "static/bgm/pixel_chiptune.mp3",
        "悬疑氛围": "static/bgm/mystery_ambient.mp3",
        "史诗冒险": "static/bgm/epic_adventure.mp3",
    }

    def __init__(self, work_dir: Path, project_root: Optional[Path] = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = project_root or Path(__file__).parent.parent
        self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # ── TTS 解说生成 ──────────────────────────

    async def _tts_segment(self, text: str, out_path: Path, voice: str = "zh-CN-XiaoxiaoNeural"):
        """用 edge-tts 生成单段解说音频。"""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    def generate_narrations(
        self,
        segments: List[Dict],
        voice: str = "zh-CN-XiaoxiaoNeural",
        progress_cb=None,
    ) -> List[Optional[Path]]:
        """
        为每个 segment 生成 TTS 音频文件。
        返回音频路径列表（对应 segments 顺序，失败则为 None）。
        """
        progress_cb = progress_cb or (lambda msg: None)
        audio_dir = self.work_dir / "narrations"
        audio_dir.mkdir(exist_ok=True)
        result = []

        async def _run_all():
            tasks = []
            for i, seg in enumerate(segments):
                text = seg.get("narration", "")
                if text:
                    out = audio_dir / f"narration_{i:02d}.mp3"
                    tasks.append((i, text, out))
            for i, text, out in tasks:
                progress_cb(f"🎙️ 生成第{i+1}段解说: {text[:20]}...")
                try:
                    await _tts_segment(self, text, out)
                    result.append(out)
                except Exception as e:
                    logger.warning(f"TTS 第{i}段失败: {e}")
                    result.append(None)

        # 逐个运行避免并发问题
        audio_paths = []
        for i, seg in enumerate(segments):
            text = seg.get("narration", "")
            out = audio_dir / f"narration_{i:02d}.mp3"
            if text:
                progress_cb(f"🎙️ 生成第{i+1}段解说: {text[:20]}...")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    import edge_tts
                    communicate = edge_tts.Communicate(text, voice)
                    loop.run_until_complete(communicate.save(str(out)))
                    loop.close()
                    audio_paths.append(out)
                    logger.info(f"TTS 第{i+1}段完成: {out}")
                except Exception as e:
                    logger.warning(f"TTS 第{i+1}段失败: {e}")
                    audio_paths.append(None)
            else:
                audio_paths.append(None)

        return audio_paths

    # ── 视频片段剪切 ──────────────────────────

    def cut_segments(
        self,
        source_video: Path,
        segments: List[Dict],
        progress_cb=None,
    ) -> List[Path]:
        """
        按脚本切割原始视频的各个片段。
        每段保存为单独的 mp4 文件。
        """
        progress_cb = progress_cb or (lambda msg: None)
        seg_dir = self.work_dir / "segments"
        seg_dir.mkdir(exist_ok=True)
        cut_files = []

        for i, seg in enumerate(segments):
            start = seg.get("start", 0)
            end = seg.get("end", start + 5)
            duration = end - start
            if duration <= 0:
                logger.warning(f"片段{i}时长为0，跳过")
                cut_files.append(None)
                continue

            out_file = seg_dir / f"segment_{i:02d}.mp4"
            progress_cb(f"✂️ 切割片段 {i+1}/{len(segments)} [{start}s-{end}s]")

            cmd = [
                self._ffmpeg, "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", str(source_video),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-an",                  # 去除原始音频
                "-pix_fmt", "yuv420p",
                str(out_file),
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0 and out_file.exists():
                cut_files.append(out_file)
            else:
                logger.error(f"片段{i}切割失败: {result.stderr.decode()[:200]}")
                cut_files.append(None)

        return cut_files

    # ── 为片段添加解说音频 ────────────────────

    def merge_narration_to_segment(
        self,
        video_file: Path,
        audio_file: Optional[Path],
        target_duration: float,
        out_file: Path,
    ) -> Path:
        """
        将解说音频合并到视频片段。
        如果音频比视频长，延长视频；如果视频比音频长，截断。
        """
        if audio_file is None or not audio_file.exists():
            # 无音频：直接用静音填充
            cmd = [
                self._ffmpeg, "-y",
                "-i", str(video_file),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:v", "copy",
                "-c:a", "aac",
                "-t", str(target_duration),
                "-shortest",
                str(out_file),
            ]
        else:
            # 有解说：以解说时长为准，循环/裁剪视频
            cmd = [
                self._ffmpeg, "-y",
                "-stream_loop", "-1",     # 视频循环
                "-i", str(video_file),
                "-i", str(audio_file),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-shortest",              # 以最短流为准
                "-pix_fmt", "yuv420p",
                str(out_file),
            ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            logger.error(f"合并音视频失败: {result.stderr.decode()[:200]}")
            # 退化：直接返回原视频
            shutil.copy(str(video_file), str(out_file))
        return out_file

    # ── 字幕文件生成 ──────────────────────────

    def generate_srt(self, segments: List[Dict], audio_paths: List[Optional[Path]]) -> Path:
        """生成 SRT 字幕文件（每段字幕时长估算）。"""
        srt_file = self.work_dir / "subtitles.srt"
        current_time = 0.0  # 秒

        def sec_to_srt(s: float) -> str:
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

        lines = []
        for i, (seg, audio) in enumerate(zip(segments, audio_paths)):
            text = seg.get("subtitle", seg.get("narration", "")[:10])
            if not text:
                # 估算：按字幕长度 * 0.3s
                narration = seg.get("narration", "")
                text = narration[:12] if narration else ""

            # 估算时长
            if audio and audio.exists():
                dur = self._get_audio_duration(audio)
            else:
                video_dur = seg.get("end", 0) - seg.get("start", 0)
                dur = max(video_dur, 1.5)

            start_str = sec_to_srt(current_time)
            end_str = sec_to_srt(current_time + dur)
            current_time += dur

            if text:
                lines.append(f"{i+1}")
                lines.append(f"{start_str} --> {end_str}")
                lines.append(text)
                lines.append("")

        srt_file.write_text("\n".join(lines), encoding="utf-8")
        return srt_file

    def _get_audio_duration(self, audio_path: Path) -> float:
        """获取音频时长（秒）。"""
        try:
            result = subprocess.run(
                [
                    self._ffmpeg.replace("ffmpeg", "ffprobe"),
                    "-v", "quiet", "-print_format", "json",
                    "-show_format", str(audio_path),
                ],
                capture_output=True, text=True,
            )
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return 3.0

    # ── 拼接所有片段 ──────────────────────────

    def concat_segments(
        self,
        segment_files: List[Optional[Path]],
        output_file: Path,
        progress_cb=None,
    ) -> Optional[Path]:
        """拼接多个视频片段为一个完整视频。"""
        progress_cb = progress_cb or (lambda msg: None)
        valid_files = [f for f in segment_files if f and f.exists()]
        if not valid_files:
            logger.error("没有有效片段可拼接")
            return None

        progress_cb(f"🔗 拼接 {len(valid_files)} 个片段...")

        # 写 concat list
        list_file = self.work_dir / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for seg in valid_files:
                f.write(f"file '{seg.absolute()}'\n")

        cmd = [
            self._ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and output_file.exists():
            progress_cb("✅ 片段拼接完成")
            return output_file
        else:
            logger.error(f"拼接失败: {result.stderr.decode()[:300]}")
            return None

    # ── 叠加字幕 ──────────────────────────────

    def burn_subtitles(
        self,
        video_file: Path,
        srt_file: Path,
        output_file: Path,
        font_size: int = 22,
        progress_cb=None,
    ) -> Path:
        """将 SRT 字幕硬编码到视频。"""
        (progress_cb or (lambda m: None))("📝 叠加字幕...")
        srt_escaped = str(srt_file.absolute()).replace("\\", "/").replace(":", "\\:")

        cmd = [
            self._ffmpeg, "-y",
            "-i", str(video_file),
            "-vf", (
                f"subtitles='{srt_escaped}'"
                f":force_style='FontSize={font_size},PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1'"
            ),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and output_file.exists():
            return output_file
        else:
            logger.warning(f"字幕叠加失败，使用无字幕版本: {result.stderr.decode()[:200]}")
            shutil.copy(str(video_file), str(output_file))
            return output_file

    # ── 混入 BGM ─────────────────────────────

    def mix_bgm(
        self,
        video_file: Path,
        bgm_style: str,
        output_file: Path,
        bgm_volume: float = 0.12,
        progress_cb=None,
    ) -> Path:
        """混入背景音乐。"""
        (progress_cb or (lambda m: None))(f"🎵 混入BGM ({bgm_style})...")

        # 查找 BGM 文件
        bgm_path = None
        rel_path = self.BGM_MAP.get(bgm_style)
        if rel_path:
            bgm_path = self.project_root / rel_path
        if not bgm_path or not bgm_path.exists():
            # 尝试找任意 BGM
            bgm_dir = self.project_root / "static" / "bgm"
            if bgm_dir.exists():
                bgm_files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
                if bgm_files:
                    bgm_path = bgm_files[0]

        if not bgm_path or not bgm_path.exists():
            logger.warning("未找到BGM文件，跳过BGM混音")
            shutil.copy(str(video_file), str(output_file))
            return output_file

        cmd = [
            self._ffmpeg, "-y",
            "-i", str(video_file),
            "-stream_loop", "-1",
            "-i", str(bgm_path),
            "-filter_complex",
            (
                f"[1:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and output_file.exists():
            (progress_cb or (lambda m: None))("✅ BGM混入完成")
            return output_file
        else:
            logger.warning(f"BGM混入失败: {result.stderr.decode()[:200]}")
            shutil.copy(str(video_file), str(output_file))
            return output_file

    # ── 添加开场/结尾画面（可选）────────────────

    def add_intro_text(
        self,
        video_file: Path,
        title: str,
        game_name: str,
        output_file: Path,
        duration: float = 2.0,
    ) -> Path:
        """在视频开头叠加标题文字（fade in）。"""
        try:
            # 使用 drawtext filter 在前2秒叠加标题
            safe_title = title.replace("'", "\\'").replace(":", "\\:")[:30]
            cmd = [
                self._ffmpeg, "-y",
                "-i", str(video_file),
                "-vf", (
                    f"drawtext=text='{safe_title}'"
                    f":fontsize=32:fontcolor=white:x=(w-text_w)/2:y=h*0.1"
                    f":box=1:boxcolor=black@0.5:boxborderw=8"
                    f":enable='between(t,0,{duration})'"
                    f":alpha='if(lt(t,0.5),t/0.5,if(lt(t,{duration-0.5}),1,({duration}-t)/0.5))'"
                ),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "copy",
                str(output_file),
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                return output_file
        except Exception as e:
            logger.warning(f"添加标题失败: {e}")
        shutil.copy(str(video_file), str(output_file))
        return output_file

    # ── 完整编辑流水线 ────────────────────────

    def run_full_pipeline(
        self,
        source_video: Path,
        edit_script: Dict,
        output_filename: str = "final_demo.mp4",
        voice: str = "zh-CN-XiaoxiaoNeural",
        progress_cb=None,
    ) -> Optional[Path]:
        """
        执行完整剪辑流水线：
        cut → tts → merge → concat → subtitle → bgm → title → final

        Returns:
            最终视频路径，失败返回 None
        """
        progress_cb = progress_cb or (lambda msg: None)
        segments = edit_script.get("segments", [])
        if not segments:
            logger.error("剪辑脚本中没有片段")
            return None

        # Step 1: 切割片段
        progress_cb("✂️ Step 1/6: 切割视频片段...")
        cut_files = self.cut_segments(source_video, segments, progress_cb)

        # Step 2: TTS 解说
        progress_cb("🎙️ Step 2/6: 生成TTS解说...")
        narration_files = self.generate_narrations(segments, voice, progress_cb)

        # Step 3: 合并音视频片段
        progress_cb("🔊 Step 3/6: 合并解说与视频...")
        merged_dir = self.work_dir / "merged"
        merged_dir.mkdir(exist_ok=True)
        merged_files = []
        for i, (cut, narr, seg) in enumerate(zip(cut_files, narration_files, segments)):
            if cut is None:
                merged_files.append(None)
                continue
            out = merged_dir / f"merged_{i:02d}.mp4"
            dur = seg.get("end", 0) - seg.get("start", 0)
            merged = self.merge_narration_to_segment(cut, narr, dur, out)
            merged_files.append(merged)

        # Step 4: 拼接
        progress_cb("🔗 Step 4/6: 拼接所有片段...")
        concat_output = self.work_dir / "concat.mp4"
        result = self.concat_segments(merged_files, concat_output, progress_cb)
        if result is None:
            # 回退：直接使用原视频
            progress_cb("⚠️ 拼接失败，使用原始视频简单裁剪")
            total_dur = sum(
                seg.get("end", 0) - seg.get("start", 0) for seg in segments
            )
            cmd = [
                self._ffmpeg, "-y",
                "-ss", str(segments[0].get("start", 0)),
                "-t", str(total_dur),
                "-i", str(source_video),
                "-c", "copy",
                str(concat_output),
            ]
            subprocess.run(cmd, capture_output=True)
            if not concat_output.exists():
                shutil.copy(str(source_video), str(concat_output))

        # Step 5: 字幕
        progress_cb("📝 Step 5/6: 叠加字幕...")
        srt_file = self.generate_srt(segments, narration_files)
        subtitled_output = self.work_dir / "subtitled.mp4"
        subtitled = self.burn_subtitles(concat_output, srt_file, subtitled_output, progress_cb=progress_cb)

        # Step 6: BGM
        progress_cb("🎵 Step 6/6: 混入BGM...")
        bgm_style = edit_script.get("bgm_style", "轻松欢快")
        bgm_output = self.work_dir / "bgm_mixed.mp4"
        mixed = self.mix_bgm(subtitled, bgm_style, bgm_output, progress_cb=progress_cb)

        # 复制到最终输出
        final_output = self.work_dir.parent / output_filename
        shutil.copy(str(mixed), str(final_output))
        progress_cb(f"🎬 剪辑完成: {final_output}")
        return final_output
