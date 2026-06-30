"""视频生成流水线：文案 → PV下载 → TTS配音 → 剪辑 → 上传小红书。"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Pillow 10 删除了 PIL.Image.ANTIALIAS，moviepy 1.x 的 resize() 依赖它。
# 在此补回，避免 resize 调用崩溃。
try:
    from PIL import Image as _PILImage
    if not hasattr(_PILImage, "ANTIALIAS"):
        _PILImage.ANTIALIAS = _PILImage.LANCZOS
except Exception:
    pass

# 任务存储（内存，重启后通过扫描磁盘恢复已完成任务）
_task_store: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()

# 视频输出目录
VIDEO_OUTPUT_DIR = Path(__file__).parent / "video_outputs"
VIDEO_OUTPUT_DIR.mkdir(exist_ok=True)


def _update_task(task_id: str, **kwargs):
    with _task_lock:
        if task_id in _task_store:
            _task_store[task_id].update(kwargs)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    with _task_lock:
        info = _task_store.get(task_id)
        if info:
            return dict(info)
    # 内存中没有，尝试从磁盘恢复（服务重启后）
    work_dir = VIDEO_OUTPUT_DIR / task_id
    output = work_dir / "final_output.mp4"
    if output.exists():
        recovered = {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "output_path": str(output),
            "game_name": "",
            "error": None,
            "_recovered": True,
        }
        with _task_lock:
            _task_store[task_id] = recovered
        return dict(recovered)
    if work_dir.exists():
        # 目录存在但没有输出文件，说明上次运行失败或仍在运行（进程已死）
        recovered = {
            "task_id": task_id,
            "status": "failed",
            "stage": "unknown",
            "progress": 0,
            "output_path": None,
            "game_name": "",
            "error": "服务已重启，任务状态丢失（视频未生成完成）",
            "_recovered": True,
        }
        with _task_lock:
            _task_store[task_id] = recovered
        return dict(recovered)
    return {}


# ──────────────────────────────────────────────
# Step 1: 解析口播脚本（按行拆分为 segments）
# ──────────────────────────────────────────────
def _step_parse_script_from_text(task_id: str, game_name: str, content: str) -> Optional[Dict]:
    _update_task(task_id, stage="parse_script", progress=15)
    try:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            _update_task(task_id, status="failed", error="脚本内容为空")
            return None

        # 每行约 3 秒，最少 3 秒，最多 8 秒
        segments = []
        for i, line in enumerate(lines):
            # 中文字符大约 3 个字/秒，英文/标点稍短，简单按字数估算
            char_count = len(line)
            dur = max(3.0, min(8.0, round(char_count / 3.5, 1)))
            segments.append({
                "text": line,
                "subtitle": line,
                "duration": dur,
                "scene": f"段落 {i+1}",
            })

        script = {
            "title": game_name or "游戏雷达局 · 今日资讯",
            "segments": segments,
            "tags": ["#游戏", "#手游资讯", "#游戏雷达局"],
        }
        logger.info("[%s] 脚本解析完成，共 %d 段", task_id, len(segments))
        _update_task(task_id, progress=20)
        return script
    except Exception as e:
        logger.error("[%s] 脚本解析失败: %s", task_id, e)
        _update_task(task_id, status="failed", error=f"脚本解析失败: {e}")
        return None


# ──────────────────────────────────────────────
# Step 2: 下载 PV
# ──────────────────────────────────────────────
def _step_download_pv(task_id: str, game_name: str, pv_url: str, work_dir: Path, yt_cookies: str = "") -> Optional[Path]:
    _update_task(task_id, stage="download_pv", progress=25)
    from scrapers.pv_downloader import download_pv, search_game_pv_bilibili

    url = pv_url.strip() if pv_url else ""
    if not url:
        logger.info("[%s] 未提供 PV URL，自动搜索 B站...", task_id)
        url = search_game_pv_bilibili(game_name) or ""

    if url:
        path = download_pv(url, work_dir, filename_stem="pv", max_duration_secs=120, cookies_content=yt_cookies or None)
        if path:
            _update_task(task_id, progress=45, pv_url=url)
            return path
        logger.warning("[%s] PV 下载失败，使用纯色背景", task_id)
    else:
        logger.info("[%s] 未找到 PV，使用纯色背景", task_id)

    _update_task(task_id, progress=45)
    return None


# ──────────────────────────────────────────────
# Step 2.5: AI PV 分析 & 编排规划
# ──────────────────────────────────────────────
def _extract_pv_frames(pv_path: Path, max_frames: int = 30) -> tuple:
    """
    从 PV 提取均匀分布的关键帧。
    Returns: (frame_data, pv_duration_secs)
      frame_data: [{"time": float, "b64": str}]
    """
    import cv2, base64
    cap = cv2.VideoCapture(str(pv_path))
    if not cap.isOpened():
        return [], 0.0
    fps_v = cap.get(cv2.CAP_PROP_FPS) or 24
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_secs = total_frames / fps_v
    cap.release()

    interval = max(1.0, total_secs / max_frames)
    sample_times = []
    t = 0.0
    while t < total_secs - 0.1 and len(sample_times) < max_frames:
        sample_times.append(round(t, 1))
        t += interval

    frame_data = []
    cap = cv2.VideoCapture(str(pv_path))
    for sample_t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, sample_t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        scale = 320 / w if w > 320 else 1.0
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        b64 = base64.b64encode(buf.tobytes()).decode()
        frame_data.append({"time": sample_t, "b64": b64})
    cap.release()
    return frame_data, total_secs


def _step_match_pv_scenes(task_id: str, pv_path: Path, segments: list) -> list:
    """
    单步 AI 分析：将 PV 关键帧（带时间戳）和口播脚本同时发给 qwen-vl-max，
    让模型直接理解动态画面与文字的语义关系，输出每段脚本对应的 PV 时间区间。
    相比原来的「先描述帧→再文字匹配」两步走，减少了一次信息转译损耗，
    且模型能感知帧与帧之间的动作连续性（动态理解），对齐精度更高。
    """
    if not pv_path or not pv_path.exists():
        return segments
    if not segments:
        return segments

    _update_task(task_id, stage="match_pv_scenes", progress=47)
    logger.info("[%s] 开始单步 AI PV 编排分析，共 %d 段脚本", task_id, len(segments))

    try:
        import cv2  # noqa
        import json as _json
    except ImportError as e:
        logger.warning("[%s] cv2 未安装，跳过 AI 分析: %s", task_id, e)
        return segments

    # 抽帧：每 3 秒一帧，最多 40 帧。帧间距小一点，让模型能感知动作连续性
    frame_data, pv_total_secs = _extract_pv_frames(pv_path, max_frames=40)
    if not frame_data:
        logger.warning("[%s] 未提取到有效帧，跳过 AI 分析", task_id)
        return segments

    logger.info("[%s] 提取了 %d 帧（PV时长 %.1fs）", task_id, len(frame_data), pv_total_secs)

    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()
    except Exception as e:
        logger.warning("[%s] 获取 Qwen 客户端失败，跳过 AI 分析: %s", task_id, e)
        return segments

    # ── 构建脚本文本（去括号提示词，只留口播正文）──
    script_lines = []
    for i, seg in enumerate(segments):
        text = _re.sub(r'[（(][^）)]{1,50}[）)]', '', seg.get("text") or "").strip()
        dur = float(seg.get("duration") or 5)
        script_lines.append(f"段落{i+1}（约{dur:.0f}s）：{text}")
    script_text = "\n".join(script_lines)
    total_script_dur = sum(float(seg.get("duration") or 5) for seg in segments)
    n_seg = len(segments)
    n_frames = len(frame_data)

    # ── 构建 multimodal 消息：所有帧 + 脚本 + 任务说明 ──
    # 分批发图：qwen-vl-max 单次最多约 20 张，分批后合并结果
    BATCH = 20
    all_assignments = {}   # {seg_idx: {"start": float, "end": float, "reason": str}}

    for batch_start in range(0, n_frames, BATCH):
        batch = frame_data[batch_start: batch_start + BATCH]
        batch_end = batch_start + len(batch)
        is_last_batch = (batch_end >= n_frames)

        content_parts = []
        # 先放图
        for fd in batch:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{fd['b64']}"},
            })
        # 帧时间戳索引
        frame_index_desc = "  ".join(
            f"帧{batch_start + j + 1}={batch[j]['time']:.1f}s"
            for j in range(len(batch))
        )
        # 任务说明
        batch_note = (
            f"（当前批次为PV第{batch_start+1}-{batch_end}帧，"
            f"PV总时长{pv_total_secs:.0f}s，共{n_frames}帧）"
            if not is_last_batch
            else f"（最后一批，PV第{batch_start+1}-{batch_end}帧，PV总时长{pv_total_secs:.0f}s）"
        )
        prompt = (
            f"以下是游戏PV的连续关键帧（按时间顺序）{batch_note}：\n"
            f"帧时间戳：{frame_index_desc}\n\n"
            f"口播脚本（共{n_seg}段，总时长{total_script_dur:.0f}s，PV总时长{pv_total_secs:.0f}s）：\n{script_text}\n\n"
            "## 任务\n"
            "观察这些帧所展示的动态画面（注意帧间的动作连续性和场景变化），"
            "为每段口播脚本找出 PV 中与其语义最匹配的时间区间 [start_sec, end_sec]。\n\n"
            "## 要求\n"
            "1. 【硬约束】PV时长足够覆盖脚本时，每段必须使用完全不重叠的时间区间，禁止任何两段共享同一PV片段\n"
            "2. 【硬约束】各段时间区间不得交叉或重叠（即上一段的end_sec ≤ 下一段的start_sec）\n"
            "3. 语义匹配优先：脚本说建造，配建造画面；脚本说探索，配探索画面\n"
            "4. 每段时间区间长度应接近该段脚本的时长\n"
            "5. 按脚本顺序从前往后分配PV时间轴，充分利用整段PV\n"
            "6. 仅当脚本总时长 > PV时长时，才需要额外指定适合循环的区间 loop；否则 loop 为 null\n\n"
            "严格输出JSON，不要任何额外文字：\n"
            "{\n"
            '  "segments": [\n'
            '    {"segment": 段落编号, "start_sec": 开始秒, "end_sec": 结束秒, "reason": "匹配理由15字内"}\n'
            "  ],\n"
            '  "loop": {"start_sec": 开始秒, "end_sec": 结束秒} 或 null\n'
            "}\n"
        )
        content_parts.append({"type": "text", "text": prompt})

        try:
            resp = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{"role": "user", "content": content_parts}],
                extra_body={"enable_thinking": False},
            )
            raw = (resp.choices[0].message.content or "").strip()
            import re as _re4
            fence = _re4.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
            if fence:
                raw = fence.group(1).strip()
            obj_m = _re4.search(r'\{[\s\S]*\}', raw)
            if obj_m:
                raw = obj_m.group(0)
            plan = _json.loads(raw)
            for m in (plan.get("segments") or []):
                seg_idx = int(m.get("segment", 0)) - 1
                if not (0 <= seg_idx < n_seg):
                    continue
                # 若已有更好的匹配（来自同一批次），不覆盖；
                # 多批次情况下，最后一批的结果覆盖（画面信息更完整）
                all_assignments[seg_idx] = {
                    "start": float(m.get("start_sec", 0)),
                    "end":   float(m.get("end_sec", 0)),
                    "reason": m.get("reason", ""),
                }
            # loop
            loop_info = plan.get("loop")
            if loop_info and is_last_batch:
                all_assignments["__loop__"] = {
                    "start": float(loop_info.get("start_sec", 0)),
                    "end":   float(loop_info.get("end_sec", 0)),
                }
            logger.info("[%s] 批次帧%d-%d 分析完成，已分配 %d 段",
                        task_id, batch_start+1, batch_end, len(plan.get("segments", [])))
        except Exception as e:
            logger.warning("[%s] AI PV 分析批次%d失败: %s", task_id, batch_start, e)

    # ── 将分配结果写回 segments，并强制去重（代码层硬约束）──
    match_guide = []
    loop_frames_info = []

    # 先按 seg_idx 顺序排序，再做去重
    seg_assignments = sorted(
        [(k, v) for k, v in all_assignments.items() if k != "__loop__" and isinstance(k, int)],
        key=lambda x: x[0]
    )

    # 代码层强制非重叠：若当前段 start < 上一段 end，则顺移到上一段 end
    prev_end = 0.0
    for seg_idx, assign in seg_assignments:
        if not (0 <= seg_idx < n_seg):
            continue
        start_t = max(float(assign["start"]), prev_end)
        start_t = max(0.0, min(start_t, pv_total_secs - 0.5))
        end_t   = max(start_t + 0.5, float(assign["end"]))
        end_t   = min(end_t, pv_total_secs)
        # 若 start 已超过 PV 末尾，顺延到末尾附近（画面不够时兜底）
        if start_t >= pv_total_secs - 0.1:
            start_t = max(0.0, pv_total_secs - 1.0)
            end_t   = pv_total_secs
        prev_end = end_t
        segments[seg_idx]["pv_offset"]     = start_t
        segments[seg_idx]["pv_end_offset"] = end_t
        segments[seg_idx]["pv_scene_desc"] = assign["reason"]
        match_guide.append({
            "segment": seg_idx + 1,
            "text":    (segments[seg_idx].get("text") or "")[:30],
            "pv_time": start_t,
            "pv_end":  end_t,
            "reason":  assign["reason"],
        })

    # loop
    if "__loop__" in all_assignments:
        lf = all_assignments["__loop__"]
        loop_frames_info.append({
            "start": lf["start"],
            "end":   lf["end"],
            "reason": "AI指定循环区间",
        })

    _update_task(
        task_id,
        pv_match_guide=match_guide,
        pv_loop_frames=loop_frames_info,
        pv_total_secs=pv_total_secs,
        progress=49,
    )
    logger.info("[%s] PV 编排完成：%d段匹配，%d个循环区间", task_id, len(match_guide), len(loop_frames_info))
    return segments


# ──────────────────────────────────────────────
# Step 3: TTS 配音（edge-tts）
# ──────────────────────────────────────────────

import re as _re

# 括号提示词 → SSML 片段映射（支持中文全角/半角括号）
_HINT_MAP = [
    # 停顿类（缩短停顿时长，减少 AI 感）
    (r'[（(]长停[)）]',   '<break time="600ms"/>'),
    (r'[（(]停顿[)）]',   '<break time="300ms"/>'),
    (r'[（(]稍停[)）]',   '<break time="150ms"/>'),
    (r'[（(]停[)）]',     '<break time="200ms"/>'),
    # 情绪/语气类
    (r'[（(]叹气[)）]',   '<break time="150ms"/><prosody rate="-10%" pitch="-6%">'),
    (r'[（(]夸张笑[)）]', '<prosody rate="+5%" pitch="+12%">'),
    (r'[（(]笑[)）]',     '<prosody rate="+5%" pitch="+8%">'),
    (r'[（(]兴奋[)）]',   '<prosody rate="+20%" pitch="+10%">'),
    (r'[（(]激动[)）]',   '<prosody rate="+25%" pitch="+12%">'),
    (r'[（(]沉稳[)）]',   '<prosody rate="-5%" pitch="-4%">'),
    (r'[（(]低沉[)）]',   '<prosody rate="-8%" pitch="-10%">'),
    (r'[（(]拖长[)）]',   '<prosody rate="-20%">'),
    (r'[（(]强调[)）]',   '<prosody volume="+15%" rate="-5%">'),
    (r'[（(]结束[)）]',   '</prosody>'),
]

# 仅用于剥除字幕里括号内容（支持最长50字的括号内描述）
_HINT_STRIP_RE = _re.compile(r'[（(][^）)]{1,50}[）)]')


def _parse_tts_text(raw: str) -> str:
    """
    将用户输入的带提示词文本转换为 SSML speak 片段内容。
    括号提示词 → SSML 标签；普通文字保持原样。

    规则：
    - （停顿）/（稍停）/（长停） → <break>
    - （夸张笑）/（笑）/（兴奋）/（激动）/（沉稳）/（低沉）/（拖长）/（强调）/（叹气）
      → 开启 <prosody> 块，持续到下一个提示词或句末，自动闭合
    - （结束） → 手动闭合 </prosody>
    - 其他括号内容 → 静默删除（不朗读）
    """
    text = raw.strip()
    # 先替换已知提示词
    for pattern, replacement in _HINT_MAP[:-1]:   # 跳过最后的通用删除规则
        text = _re.sub(pattern, replacement, text)
    # 剩余未识别括号内容静默删除
    text = _re.sub(r'[（(][^）)]{1,20}[）)]', '', text)

    # 自动闭合未关闭的 <prosody>：统计开/闭标签数量，补齐
    open_count  = text.count('<prosody')
    close_count = text.count('</prosody>')
    if open_count > close_count:
        text += '</prosody>' * (open_count - close_count)

    return text.strip()


def _strip_hints_for_subtitle(raw: str) -> str:
    """剔除括号提示词，返回干净的字幕文本。"""
    return _HINT_STRIP_RE.sub('', raw).strip()


async def _tts_segment(text: str, out_path: Path, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+30%"):
    """生成 TTS 音频，同时收集 SentenceBoundary 时间轴。
    返回 list[{"t": float秒, "text": str}]，每项表示该字幕从 t 秒开始显示。
    rate: edge-tts 全局语速，"+30%" 接近真人播客节奏，减少 AI 腔停顿感。
    """
    import edge_tts, re as _r
    clean = _parse_tts_text(text)
    clean = _r.sub(r'<[^>]+>', '', clean).strip()
    if not clean:
        clean = text.strip()

    communicate = edge_tts.Communicate(clean, voice, rate=rate)
    audio_chunks = []
    boundaries = []   # [{"offset": int(100ns), "duration": int(100ns), "text": str}]

    async for event in communicate.stream():
        etype = event.get("type")
        if etype == "audio":
            audio_chunks.append(event["data"])
        elif etype == "SentenceBoundary":
            boundaries.append({
                "offset":   event.get("offset", 0),
                "duration": event.get("duration", 0),
                "text":     event.get("text", ""),
            })

    # 写音频文件
    out_path.write_bytes(b"".join(audio_chunks))

    # 转换时间轴（100ns → 秒），构建每句字幕的起始时间
    timeline = []
    for b in boundaries:
        t_sec = b["offset"] / 10_000_000.0   # 100ns → s
        sentence = b["text"].strip()
        if sentence:
            timeline.append({"t": round(t_sec, 3), "text": sentence})

    return timeline


def _step_generate_tts(task_id: str, segments: list, work_dir: Path, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+30%") -> list:
    """为每个段落生成 TTS 音频，返回音频文件路径列表。
    同时将各段 duration 更新为实际 TTS 音频时长，并将字幕时间轴存入 seg["subtitle_timeline"]。
    """
    _update_task(task_id, stage="generate_tts", progress=50)

    audio_paths = []
    for i, seg in enumerate(segments):
        text = seg.get("text") or seg.get("subtitle") or ""
        if not text:
            audio_paths.append(None)
            continue
        out_path = work_dir / f"tts_{i:03d}.mp3"
        try:
            loop = asyncio.new_event_loop()
            try:
                timeline = loop.run_until_complete(_tts_segment(text, out_path, voice=voice, rate=rate))
            finally:
                loop.close()
            audio_paths.append(out_path)
            # 存字幕时间轴
            if timeline:
                seg["subtitle_timeline"] = timeline
                logger.debug("[%s] 段落 %d 字幕时间轴: %s", task_id, i, timeline)
            # 用实际音频时长覆盖脚本估算时长（不加缓冲，字幕/画面按真实长度走）
            try:
                from moviepy.editor import AudioFileClip as _AFC
                actual_dur = _AFC(str(out_path)).duration
                if actual_dur > 0.5:
                    seg["duration"] = round(actual_dur, 2)
            except Exception:
                pass
        except Exception as e:
            logger.warning("[%s] TTS 段落 %d 失败: %s", task_id, i, e)
            audio_paths.append(None)

    _update_task(task_id, progress=65)
    return audio_paths


# ──────────────────────────────────────────────
# Step 4: 视频剪辑（MoviePy）
# ──────────────────────────────────────────────
def _load_image_as_clip(img_path: str, W: int, H: int, duration: float):
    """用 Pillow 将图片 cover 缩放到 W×H，返回 ImageClip（规避 Pillow 10 去除 ANTIALIAS 导致 resize 失败）。"""
    from PIL import Image
    import numpy as np
    from moviepy.editor import ImageClip as _ImageClip

    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size
    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    img = img.crop((left, top, left + W, top + H))
    arr = np.array(img)
    return _ImageClip(arr).set_duration(duration).set_fps(30)


def _apply_ken_burns(clip, zoom_start: float = 1.0, zoom_end: float = 1.06,
                     pan_x: float = 0.0, pan_y: float = 0.0):
    """
    对 ImageClip 施加 Ken Burns 效果（缓慢推镜/拉镜 + 微量平移）。
    让静止画面产生运动感，避免画面完全静止的"PPT感"。

    zoom_start/zoom_end: 1.0=原始大小，1.06=放大6%
    pan_x/pan_y: 水平/垂直平移方向（-1~1，表示从左到右或从上到下）
    """
    import numpy as _np2

    W, H = clip.size
    dur = clip.duration

    def make_frame(t):
        frame = clip.get_frame(t)
        progress = t / dur if dur > 0 else 0
        zoom = zoom_start + (zoom_end - zoom_start) * progress

        # 缩放后尺寸
        nw = int(W * zoom)
        nh = int(H * zoom)

        # 用 PIL 缩放（比 cv2 更轻量）
        from PIL import Image as _PI
        img = _PI.fromarray(frame.astype('uint8'))
        img = img.resize((nw, nh), _PI.LANCZOS)
        arr = _np2.array(img)

        # 裁剪中心区域（带平移偏移）
        cx = (nw - W) // 2 + int(pan_x * (nw - W) // 2 * progress)
        cy = (nh - H) // 2 + int(pan_y * (nh - H) // 2 * progress)
        cx = max(0, min(cx, nw - W))
        cy = max(0, min(cy, nh - H))
        return arr[cy:cy + H, cx:cx + W]

    from moviepy.editor import VideoClip as _VC
    return _VC(make_frame, duration=dur).set_fps(clip.fps or 30)


def _get_font() -> str:
    """根据平台返回可用中文字体路径。"""
    if sys.platform == "win32":
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
            r"C:\Windows\Fonts\simhei.ttf",      # 黑体
            r"C:\Windows\Fonts\simsun.ttc",      # 宋体
        ]
        for p in candidates:
            if Path(p).exists():
                return p
    else:
        candidates = [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
    return "Arial"


# ── 游戏雷达局品牌资源路径 ──
_BRAND_AVATAR = Path(__file__).parent / "static" / "img" / "radar_avatar.jpg"
_BRAND_NAME   = "游戏雷达局"
_BRAND_OUTRO_TEXT = "游戏雷达局，替你扫描每一款值得玩的游戏"
_BRAND_SUB    = "关注我，不错过好游戏"


def _add_watermark_and_outro(task_id: str, clip, work_dir: Path, W: int, H: int, fps: int = 30):
    """
    给视频主体添加：
    1. 右下角常驻半透明水印（游戏雷达局）
    2. 结尾 3 秒品牌卡片（黑底 + 头像 + 频道名 + 副标语）
    3. 结尾 TTS 语音（替你扫描每一款值得玩的游戏）
    """
    from moviepy.editor import (
        ColorClip, AudioFileClip, CompositeVideoClip,
        concatenate_videoclips, concatenate_audioclips,
    )
    from PIL import Image as _PILImg, ImageDraw as _PILDraw, ImageFont as _PILFont
    import numpy as _np

    font_path_wm = _get_font()   # 字体路径字符串

    # ── 1. 右下角水印：直接绘制到全帧 W×H 画布，用 fl_image 叠加，避免 ImageClip 定位截断 ──
    wm_margin = 20
    icon_sz = 36
    text_gap = 8
    wm_font_size = 28
    try:
        wm_font = _PILFont.truetype(font_path_wm, wm_font_size)
        _bb = wm_font.getbbox(_BRAND_NAME)
        _text_w = _bb[2] - _bb[0]
        _text_h = _bb[3] - _bb[1]
    except Exception:
        wm_font = _PILFont.load_default()
        _text_w, _text_h = len(_BRAND_NAME) * 18, 28
    wm_content_w = icon_sz + text_gap + _text_w + 16
    wm_content_h = max(icon_sz, _text_h + 12)

    # 在全帧 RGBA 画布上绘制（右下角位置）
    wm_canvas = _PILImg.new("RGBA", (W, H), (0, 0, 0, 0))
    wm_d = _PILDraw.Draw(wm_canvas)
    wx0 = W - wm_content_w - wm_margin
    wy0 = H - wm_content_h - wm_margin
    iy = wy0 + (wm_content_h - icon_sz) // 2
    wm_d.arc([wx0 + 2, iy + 4, wx0 + icon_sz - 4, iy + icon_sz],
             start=200, end=340, fill=(255, 165, 0, 200), width=3)
    wm_d.arc([wx0 + 6, iy + 8, wx0 + icon_sz - 8, iy + icon_sz - 4],
             start=200, end=340, fill=(255, 165, 0, 140), width=2)
    ty_wm = wy0 + (wm_content_h - _text_h) // 2
    wm_d.text((wx0 + icon_sz + text_gap, ty_wm), _BRAND_NAME,
              font=wm_font, fill=(255, 255, 255, 200))

    wm_rgb_full  = _np.array(wm_canvas.convert("RGB"))
    wm_mask_full = _np.array(wm_canvas.split()[3]).astype(_np.float32) / 255.0

    def _apply_watermark(get_frame, t, _wm=wm_rgb_full, _mk=wm_mask_full):
        frame = get_frame(t)
        return _np.where(_mk[:, :, _np.newaxis] > 0.05, _wm, frame).astype(_np.uint8)

    main_dur = clip.duration
    clip_wm = clip.fl(_apply_watermark).set_duration(main_dur)

    # ── 2. 结尾 TTS ──
    outro_dur = 3.5
    outro_tts_path = work_dir / "outro_tts.mp3"
    try:
        import asyncio as _aio
        loop = _aio.new_event_loop()
        try:
            loop.run_until_complete(
                _tts_segment(_BRAND_OUTRO_TEXT, outro_tts_path,
                             voice="zh-CN-YunxiNeural", rate="+25%")
            )
        finally:
            loop.close()
        # 结尾 TTS 时长直接从原始音频获取
        outro_dur = max(AudioFileClip(str(outro_tts_path)).duration + 0.3, 3.0)
    except Exception as e:
        logger.warning("[%s] 结尾 TTS 生成失败: %s", task_id, e)
        outro_tts_path = None

    # ── 3. 结尾品牌卡片帧（PIL 绘制） ──
    card = _PILImg.new("RGB", (W, H), (12, 12, 18))   # 深夜蓝黑底
    draw = _PILDraw.Draw(card)

    # 橙色渐变光晕（近似：多层半透明圆）
    overlay = _PILImg.new("RGBA", (W, H), (0, 0, 0, 0))
    od = _PILDraw.Draw(overlay)
    cx, cy = W // 2, H // 2 - 40
    for r, a in [(260, 18), (200, 30), (140, 50), (90, 80)]:
        od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 140, 0, a))
    card = _PILImg.alpha_composite(card.convert("RGBA"), overlay).convert("RGB")
    draw = _PILDraw.Draw(card)

    # 头像（圆形裁剪）
    avatar_size = min(W // 5, 180)
    if _BRAND_AVATAR.exists():
        try:
            av = _PILImg.open(str(_BRAND_AVATAR)).convert("RGBA").resize(
                (avatar_size, avatar_size), _PILImg.LANCZOS)
            mask = _PILImg.new("L", (avatar_size, avatar_size), 0)
            _PILDraw.Draw(mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)
            av.putalpha(mask)
            av_x = (W - avatar_size) // 2
            av_y = cy - avatar_size // 2
            card.paste(av, (av_x, av_y), av)
            # 橙色圆圈边框
            draw.ellipse(
                [av_x - 4, av_y - 4, av_x + avatar_size + 4, av_y + avatar_size + 4],
                outline=(255, 165, 0), width=3
            )
        except Exception:
            pass

    # 频道大标题
    title_y = cy + avatar_size // 2 + 24
    try:
        big_font = _PILFont.truetype(_get_font_path(), 52)
        sub_font = _PILFont.truetype(_get_font_path(), 28)
    except Exception:
        big_font = sub_font = font
    try:
        bbox = draw.textbbox((0, 0), _BRAND_NAME, font=big_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(_BRAND_NAME) * 52
    draw.text(((W - tw) // 2, title_y), _BRAND_NAME, font=big_font, fill=(255, 255, 255))

    # 副标语
    sub_y = title_y + 70
    try:
        bbox2 = draw.textbbox((0, 0), _BRAND_SUB, font=sub_font)
        sw = bbox2[2] - bbox2[0]
    except Exception:
        sw = len(_BRAND_SUB) * 28
    draw.text(((W - sw) // 2, sub_y), _BRAND_SUB, font=sub_font, fill=(200, 200, 200))

    card_arr = _np.array(card)
    outro_clip = ColorClip(size=(W, H), color=(12, 12, 18), duration=outro_dur)
    outro_clip = outro_clip.fl_image(lambda f: card_arr)

    # 拼上结尾 TTS 音频
    if outro_tts_path and Path(str(outro_tts_path)).exists():
        try:
            outro_audio = AudioFileClip(str(outro_tts_path))
            outro_clip = outro_clip.set_audio(outro_audio)
        except Exception:
            pass

    # ── 4. 拼接：主视频（带水印）+ 结尾卡片 ──
    # 音频保留：clip_wm 继承 clip 的音频；主体末尾 0.5s 淡出，避免与结尾卡片声音重叠
    if clip.audio is not None:
        main_audio = clip.audio
        try:
            fade_dur = min(0.5, main_audio.duration * 0.05)
            main_audio = main_audio.audio_fadeout(fade_dur)
        except Exception:
            pass
        clip_wm = clip_wm.set_audio(main_audio)
    final = concatenate_videoclips([clip_wm, outro_clip], method="compose")
    return final


def _get_font_path() -> str:
    """返回系统中文字体路径（用于大字号）。"""
    for p in [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]:
        if Path(p).exists():
            return p
    return ""


def _step_edit_video(
    task_id: str,
    script: Dict,
    pv_path: Optional[Path],
    audio_paths: list,
    work_dir: Path,
    bgm_path: Optional[Path] = None,
    bgm_volume: float = 0.15,
    tts_volume: float = 1.0,
) -> Optional[Path]:
    _update_task(task_id, stage="edit_video", progress=68)

    try:
        from moviepy.editor import (
            VideoFileClip, ColorClip, AudioFileClip,
            CompositeVideoClip, concatenate_videoclips,
        )
        from PIL import Image as _PILImg, ImageDraw as _PILDraw, ImageFont as _PILFont
        import numpy as _np
    except ImportError as e:
        logger.error("[%s] MoviePy/Pillow 未安装: %s", task_id, e)
        _update_task(task_id, status="failed", error="moviepy/pillow 未安装，请 pip install moviepy pillow")
        return None

    segments = script.get("segments") or []
    if not segments:
        _update_task(task_id, status="failed", error="脚本段落为空")
        return None

    fps = 30
    font = _get_font()

    # ── 加载 PV（保持原始横屏尺寸，不裁剪） ──
    pv_clip = None
    W, H = 1920, 1080  # 默认横屏，加载后覆盖为实际尺寸
    if pv_path and pv_path.exists():
        try:
            pv_clip = VideoFileClip(str(pv_path))
            W, H = pv_clip.size
            logger.info("[%s] PV 原始尺寸: %dx%d", task_id, W, H)
        except Exception as e:
            logger.warning("[%s] PV 加载失败: %s，使用纯色背景", task_id, e)
            pv_clip = None

    # ── 计算脚本总时长 & 确认 PV 覆盖范围 ──
    total_script_dur = sum(float(seg.get("duration") or 5) for seg in segments)

    # 从任务状态取 loop_frames，用于脚本比 PV 长时循环补充
    task_info = {}
    with _task_lock:
        task_info = dict(_task_store.get(task_id, {}))
    loop_frames_info = task_info.get("pv_loop_frames") or []

    if pv_clip:
        pv_raw_dur = pv_clip.duration
        # 计算所有段落最大的 pv_offset + dur 终点
        max_pv_end = 0.0
        for seg in segments:
            offset = float(seg.get("pv_offset", 0))
            dur = float(seg.get("duration") or 5)
            max_pv_end = max(max_pv_end, offset + dur)
        max_pv_end = max(max_pv_end, total_script_dur)

        if pv_raw_dur < max_pv_end:
            # 用 AI 建议的 loop_frames 循环；若没有则循环整段
            try:
                from moviepy.editor import concatenate_videoclips as _ccv
                if loop_frames_info:
                    # 取第一个循环区间
                    lf = loop_frames_info[0]
                    loop_clip = pv_clip.subclip(lf["start"], min(lf["end"], pv_raw_dur))
                    extra_needed = max_pv_end - pv_raw_dur
                    loops_n = int(extra_needed / loop_clip.duration) + 2
                    loop_ext = _ccv([loop_clip] * loops_n).subclip(0, extra_needed + 1)
                    pv_clip = _ccv([pv_clip, loop_ext])
                    logger.info("[%s] 用 AI 指定区间 %.1f-%.1fs 循环补充 %.1fs",
                                task_id, lf["start"], lf["end"], extra_needed)
                else:
                    loops_n = int(max_pv_end / pv_raw_dur) + 1
                    pv_clip = _ccv([pv_clip] * loops_n).subclip(0, max_pv_end)
                    logger.info("[%s] 整段循环 %d 次补充时长", task_id, loops_n)
            except Exception as e:
                logger.warning("[%s] PV 循环失败: %s", task_id, e)

    # ── 逐段构建视频片段 ──
    video_segments = []
    cursor = 0.0           # 顺序播放时的 fallback 偏移

    for i, seg in enumerate(segments):
        dur = float(seg.get("duration") or 5)
        subtitle = _strip_hints_for_subtitle(seg.get("subtitle") or seg.get("text") or "")

        # ── 背景画面 ──
        import random as _rand
        seg_img_path = seg.get("image_path")
        # Ken Burns 参数：每段随机方向，增加节目感
        _kb_zoom_end  = _rand.choice([1.05, 1.07, 1.06])
        _kb_pan_x     = _rand.choice([-0.5, 0.0, 0.5])
        _kb_pan_y     = _rand.choice([-0.3, 0.0, 0.3])

        if seg_img_path and Path(seg_img_path).exists():
            try:
                bg = _load_image_as_clip(seg_img_path, W, H, dur)
                # 配图：完整 Ken Burns（从1.0缓慢推到1.06）
                try:
                    bg = _apply_ken_burns(bg, zoom_start=1.0, zoom_end=_kb_zoom_end,
                                          pan_x=_kb_pan_x, pan_y=_kb_pan_y)
                except Exception:
                    pass
            except Exception as e:
                logger.warning("[%s] 段落配图加载失败 (seg %d): %s", task_id, i, e)
                bg = None
        else:
            bg = None

        if bg is None:
            if pv_clip:
                pv_offset = float(seg.get("pv_offset", cursor))
                # 优先使用 AI 指定的区间终点，否则按脚本时长推算
                pv_end = float(seg.get("pv_end_offset", pv_offset + dur))
                clip_dur = max(pv_end - pv_offset, 0.5)
                safe_start = min(pv_offset, pv_clip.duration - 0.1)
                safe_end = min(pv_offset + clip_dur, pv_clip.duration - 0.01)
                safe_end = max(safe_end, safe_start + 0.1)
                try:
                    pv_seg = pv_clip.subclip(safe_start, safe_end)
                    # PV 区间比脚本段长：直接截短
                    if pv_seg.duration > dur + 0.05:
                        pv_seg = pv_seg.subclip(0, dur)
                    elif pv_seg.duration < dur - 0.1:
                        # PV 区间比脚本段短：仅在 PV 整体时长不足时才允许循环
                        # PV 充足时不循环，避免画面重复——直接延长到 dur（冻结最后一帧）
                        if pv_clip.duration >= total_script_dur - 0.5:
                            # PV 时长足够，不循环，拉伸到所需时长
                            pv_seg = pv_seg.set_duration(dur)
                        else:
                            from moviepy.editor import concatenate_videoclips as _ccvs
                            loops_need = int(dur / pv_seg.duration) + 2
                            pv_seg = _ccvs([pv_seg] * loops_need).subclip(0, dur)
                    bg = pv_seg.set_duration(dur)
                except Exception:
                    bg = ColorClip(size=(W, H), color=(15, 15, 25), duration=dur)
            else:
                bg = ColorClip(size=(W, H), color=(15, 15, 25), duration=dur)

        cursor += dur
        clips = [bg]

        # ── 字幕：按 TTS SentenceBoundary 时间轴精确同步，每句单行轮转 ──
        # timeline = [{"t": float, "text": str}, ...]  由 TTS 生成时写入
        # 若无 timeline（TTS 失败等），退化为整段字幕均分轮转
        sub_overlays = []   # [(overlay_rgb, mask, t_start, t_end), ...]
        if subtitle:
            try:
                font_size = max(36, min(56, int(W / 28)))
                sub_w = int(W * 0.88)
                try:
                    pil_font = _PILFont.truetype(font, font_size)
                except Exception:
                    pil_font = _PILFont.load_default()

                def _render_line(line_text):
                    """渲染单行字幕：微软雅黑白字 + 黑色半透明底条"""
                    pad_x, pad_y = 20, 10
                    single_h = int(font_size * 1.35) + pad_y * 2
                    # 先量文字宽度
                    bbox = pil_font.getbbox(line_text)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                    # 底条宽度 = 文字宽 + 两侧 padding（不铺满全宽，更自然）
                    bar_w = min(text_w + pad_x * 2, sub_w)
                    bar_h = single_h
                    # 绘制底条（黑色半透明）
                    bar = _PILImg.new("RGBA", (bar_w, bar_h), (0, 0, 0, 200))
                    draw = _PILDraw.Draw(bar)
                    # 文字居中于底条
                    tx = (bar_w - text_w) // 2
                    ty = (bar_h - text_h) // 2 - bbox[1]
                    # 白色正文
                    draw.text((tx, ty), line_text, font=pil_font, fill=(255, 255, 255, 255))
                    # 合成到全帧
                    bar_rgb = _PILImg.new("RGB", (bar_w, bar_h), (0, 0, 0))
                    bar_rgb.paste(bar, mask=bar.split()[3])
                    sub_x = (W - bar_w) // 2
                    sub_y = H - int(H * 0.10) - bar_h
                    full = _PILImg.new("RGB", (W, H), (0, 0, 0))
                    full.paste(bar_rgb, (sub_x, sub_y))
                    ov = _np.array(full)
                    mk = _np.zeros((H, W), dtype=_np.float32)
                    alpha = _np.array(bar.split()[3]).astype(_np.float32) / 255.0
                    mk[sub_y:sub_y + bar_h, sub_x:sub_x + bar_w] = alpha
                    return ov, mk

                timeline = seg.get("subtitle_timeline") or []

                if timeline:
                    # 用 TTS SentenceBoundary 精确时间轴
                    # 对超过 15 字的长句再按标点细分（等比例插值时间）
                    for idx, entry in enumerate(timeline):
                        t_start = entry["t"]
                        t_end = timeline[idx + 1]["t"] if idx + 1 < len(timeline) else dur
                        sentence = entry["text"]
                        if len(sentence) > 15:
                            # 按标点切分长句
                            sub_parts = _re.split(r'([，。！？、；：,!?;:])', sentence)
                            subs = []
                            buf = ""
                            for p in sub_parts:
                                buf += p
                                if _re.search(r'[，。！？、；：,!?;:]', p) and buf.strip():
                                    subs.append(buf.strip())
                                    buf = ""
                            if buf.strip():
                                subs.append(buf.strip())
                            if len(subs) > 1:
                                seg_dur = (t_end - t_start) / len(subs)
                                for si, s in enumerate(subs):
                                    ov, mk = _render_line(s)
                                    sub_overlays.append((ov, mk, t_start + si * seg_dur, t_start + (si + 1) * seg_dur))
                                continue
                        ov, mk = _render_line(sentence)
                        sub_overlays.append((ov, mk, t_start, t_end))
                    logger.debug("[%s] seg %d 字幕时间轴 %d 句", task_id, i, len(sub_overlays))
                else:
                    # 退化：把 subtitle 按标点切分，均分时间
                    parts = _re.split(r'([，。！？、；：,\.!?;:])', subtitle)
                    sentences = []
                    buf = ""
                    for p in parts:
                        buf += p
                        if _re.search(r'[，。！？、；：,\.!?;:]', p) and buf.strip():
                            sentences.append(buf.strip())
                            buf = ""
                    if buf.strip():
                        sentences.append(buf.strip())
                    if not sentences:
                        sentences = [subtitle]
                    each = dur / len(sentences)
                    for idx, s in enumerate(sentences):
                        ov, mk = _render_line(s)
                        sub_overlays.append((ov, mk, idx * each, (idx + 1) * each))

            except Exception as e:
                logger.warning("[%s] 字幕生成失败 (seg %d): %s", task_id, i, e)
                sub_overlays = []

        # fl：按时间选择当前句字幕
        if sub_overlays:
            _ovs = sub_overlays
            def _apply_sub(get_frame, t, ovs=_ovs):
                frame = get_frame(t)
                # 找当前时间对应的字幕条目
                current = None
                for ov, mk, t0, t1 in ovs:
                    if t0 <= t < t1:
                        current = (ov, mk)
                        break
                if current is None:
                    return frame
                ov, mk = current
                return _np.where(mk[:, :, _np.newaxis] > 0.05, ov, frame).astype(_np.uint8)
            bg = bg.fl(_apply_sub)

        composite = bg.set_duration(dur)

        # ── 音频：TTS 配音（PV 原声静音） ──
        if i < len(audio_paths) and audio_paths[i] and Path(audio_paths[i]).exists():
            try:
                tts_audio = AudioFileClip(str(audio_paths[i]))
                if tts_audio.duration > dur:
                    tts_audio = tts_audio.subclip(0, dur)
                if tts_volume != 1.0:
                    tts_audio = tts_audio.volumex(tts_volume)
                composite = composite.set_audio(tts_audio)
            except Exception as e:
                logger.warning("[%s] 配音加载失败 (seg %d): %s", task_id, i, e)

        video_segments.append(composite)

    if not video_segments:
        _update_task(task_id, status="failed", error="无有效视频段落")
        return None

    # ── 相邻段落间添加 0.25s 交叉淡入淡出，消除硬切画面闪回 ──
    if len(video_segments) > 1:
        try:
            xfade_dur = 0.25
            faded = []
            for i, seg in enumerate(video_segments):
                if i < len(video_segments) - 1 and seg.duration > xfade_dur + 0.1:
                    seg = seg.fadeout(xfade_dur)
                if i > 0 and seg.duration > xfade_dur + 0.1:
                    seg = seg.fadein(xfade_dur)
                faded.append(seg)
            video_segments = faded
            logger.info("[%s] 已对 %d 段视频添加交叉淡化", task_id, len(video_segments))
        except Exception as e:
            logger.warning("[%s] 交叉淡化失败，使用原始片段: %s", task_id, e)

    final = concatenate_videoclips(video_segments, method="compose")

    # ── 背景配乐混音（仅配音段有效；keep_pv_audio 段的原声已直接嵌入，BGM 音量会叠加） ──
    if bgm_path and bgm_path.exists():
        try:
            from moviepy.editor import AudioFileClip as _AFC, CompositeAudioClip, concatenate_audioclips
            bgm = _AFC(str(bgm_path)).volumex(bgm_volume)
            fd = final.duration
            if bgm.duration < fd:
                loops = int(fd / bgm.duration) + 1
                bgm = concatenate_audioclips([bgm] * loops).subclip(0, fd)
            else:
                bgm = bgm.subclip(0, fd)
            if final.audio:
                mixed = CompositeAudioClip([final.audio, bgm])
                final = final.set_audio(mixed)
            else:
                final = final.set_audio(bgm)
            logger.info("[%s] 背景配乐已混入，音量=%.2f", task_id, bgm_volume)
        except Exception as e:
            logger.warning("[%s] 背景配乐混入失败，忽略: %s", task_id, e)

    output_path = work_dir / "final_output.mp4"
    try:
        # ── 水印 + 结尾卡片 ──
        final = _add_watermark_and_outro(task_id, final, work_dir, W, H, fps)
    except Exception as e:
        logger.warning("[%s] 水印/结尾添加失败，跳过: %s", task_id, e)
        import traceback; traceback.print_exc()

    # 确保 moviepy 能找到 imageio_ffmpeg 自带的 ffmpeg
    try:
        import imageio_ffmpeg as _ioffmpeg
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", _ioffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    try:
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(work_dir / "temp_audio.m4a"),
            remove_temp=True,
            verbose=False,
            logger=None,
            ffmpeg_params=["-movflags", "+faststart"],
        )
    except Exception as e:
        logger.error("[%s] 视频写入失败: %s", task_id, e)
        _update_task(task_id, status="failed", error=f"视频写入失败: {e}")
        return None

    if pv_clip:
        pv_clip.close()
    final.close()

    _update_task(task_id, progress=90)
    logger.info("[%s] 视频剪辑完成: %s", task_id, output_path)
    return output_path


# ──────────────────────────────────────────────
# Step 5: 上传小红书（视频笔记）
# ──────────────────────────────────────────────
def _step_upload_xhs(
    task_id: str,
    script: Dict,
    video_path: Path,
    xhs_cookie: str,
) -> bool:
    _update_task(task_id, stage="upload_xhs", progress=92)
    if not xhs_cookie:
        logger.info("[%s] 未提供 XHS Cookie，跳过上传", task_id)
        _update_task(task_id, progress=100)
        return False

    try:
        from xhs import XhsClient
        client = XhsClient(cookie=xhs_cookie)
        title = script.get("title") or "游戏雷达局 · 今日资讯"
        tags = " ".join(script.get("tags") or ["#游戏", "#手游资讯"])
        desc = f"{title}\n\n{tags}\n\n—— 游戏雷达局，今日情报已送达"

        result = client.create_video_note(
            title=title[:20],
            video_path=str(video_path),
            desc=desc,
            is_private=False,
        )
        logger.info("[%s] XHS 上传成功: %s", task_id, result)
        _update_task(task_id, xhs_result=str(result), progress=100)
        return True
    except Exception as e:
        logger.error("[%s] XHS 上传失败: %s", task_id, e)
        _update_task(task_id, xhs_upload_error=str(e), progress=100)
        return False


# ──────────────────────────────────────────────
# 主流水线
# ──────────────────────────────────────────────
def _run_pipeline(
    task_id: str,
    game_name: str,
    content: str,
    pv_url: str,
    duration_secs: int,
    xhs_cookie: str,
    segment_images: list = None,
    voice: str = "zh-CN-XiaoxiaoNeural",
    bgm_b64: str = "",
    bgm_volume: float = 0.15,
    pv_local_path: str = "",
    yt_cookies: str = "",
    tts_volume: float = 1.0,
    tts_rate: str = "+15%",
):
    work_dir = VIDEO_OUTPUT_DIR / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    _update_task(task_id, status="running", stage="start", progress=0, work_dir=str(work_dir))

    try:
        # Step 1: 按行解析口播脚本为 segments
        script = _step_parse_script_from_text(task_id, game_name, content)
        if not script:
            return

        # 将 segment_images 中的 base64 解码为本地文件，写入 script segments
        if segment_images:
            import base64
            segments = script.get("segments") or []
            for img_info in segment_images:
                idx = img_info.get("index")
                b64 = img_info.get("image_b64") or ""
                if idx is None or not b64 or idx >= len(segments):
                    continue
                try:
                    # strip data URI prefix if present
                    if "," in b64:
                        b64 = b64.split(",", 1)[1]
                    img_bytes = base64.b64decode(b64)
                    img_path = work_dir / f"seg_img_{idx}.jpg"
                    img_path.write_bytes(img_bytes)
                    segments[idx]["image_path"] = str(img_path)
                except Exception as e:
                    logger.warning("[%s] 段落配图解码失败 (idx %d): %s", task_id, idx, e)

        # Step 2: 优先使用本地上传的 PV 文件，否则下载
        if pv_local_path and Path(pv_local_path).exists():
            pv_path = Path(pv_local_path)
            _update_task(task_id, stage="download_pv", progress=45)
            logger.info("[%s] 使用本地 PV 文件: %s", task_id, pv_path)
        else:
            pv_path = _step_download_pv(task_id, game_name, pv_url, work_dir, yt_cookies=yt_cookies)

        # Step 3: TTS 先生成，确定真实 duration（画面匹配依赖准确时长）
        audio_paths = _step_generate_tts(task_id, script.get("segments") or [], work_dir, voice=voice, rate=tts_rate)

        # Step 2.5: AI PV 画面匹配（TTS 之后，duration 已是真实值）
        if pv_path:
            script["segments"] = _step_match_pv_scenes(task_id, pv_path, script.get("segments") or [])

        # 解码背景配乐 base64 → 本地文件
        bgm_path: Optional[Path] = None
        if bgm_b64:
            try:
                import base64 as _b64
                raw = bgm_b64
                if "," in raw:
                    raw = raw.split(",", 1)[1]
                bgm_bytes = _b64.b64decode(raw)
                bgm_path = work_dir / "bgm.mp3"
                bgm_path.write_bytes(bgm_bytes)
                logger.info("[%s] 背景配乐已写入: %s", task_id, bgm_path)
            except Exception as e:
                logger.warning("[%s] 背景配乐解码失败: %s", task_id, e)

        # Step 4
        video_path = _step_edit_video(task_id, script, pv_path, audio_paths, work_dir, bgm_path=bgm_path, bgm_volume=bgm_volume, tts_volume=tts_volume)
        if not video_path:
            return

        # Step 5
        _step_upload_xhs(task_id, script, video_path, xhs_cookie)

        _update_task(
            task_id,
            status="completed",
            stage="done",
            progress=100,
            output_path=str(video_path),
        )
        logger.info("[%s] 流水线全部完成", task_id)

    except Exception as e:
        logger.exception("[%s] 流水线异常: %s", task_id, e)
        _update_task(task_id, status="failed", error=str(e))


def run_video_pipeline(
    game_name: str,
    content: str,
    pv_url: str = "",
    duration_secs: int = 60,
    xhs_cookie: str = "",
    segment_images: list = None,
    voice: str = "zh-CN-XiaoxiaoNeural",
    bgm_b64: str = "",
    bgm_volume: float = 0.15,
    pv_local_path: str = "",
    yt_cookies: str = "",
    tts_volume: float = 1.0,
    tts_rate: str = "+30%",
) -> str:
    """
    启动视频生成流水线（后台线程）。

    content 直接按行拆分为口播段落，不经过 AI 改写。
    bgm_b64: base64 编码的音乐文件（MP3/WAV），为空则不添加背景音乐。
    bgm_volume: 背景音乐音量，0.0-1.0，默认 0.15。

    Returns:
        task_id（用于轮询状态）
    """
    task_id = uuid.uuid4().hex[:12]
    with _task_lock:
        _task_store[task_id] = {
            "task_id": task_id,
            "game_name": game_name,
            "status": "pending",
            "stage": "queued",
            "progress": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "error": None,
            "output_path": None,
        }

    t = threading.Thread(
        target=_run_pipeline,
        args=(task_id, game_name, content, pv_url, duration_secs, xhs_cookie, segment_images or [], voice, bgm_b64, bgm_volume, pv_local_path, yt_cookies, tts_volume, tts_rate),
        daemon=True,
    )
    t.start()
    logger.info("视频流水线已启动，task_id=%s，游戏=%s", task_id, game_name)
    return task_id


# ══════════════════════════════════════════════════════════
# 一键游戏推荐视频工作流
# 只需提供游戏名 + Steam 商店链接，自动完成：
#   1. 爬取 Steam 游戏信息（简介/标签/开发商/上线日期/PV HLS URL）
#   2. 联网搜索玩家评价与媒体资讯
#   3. AI 撰写口播脚本（钩子→世界观→玩法→免费时间→CTA）
#   4. 下载 Steam PV（HLS 流）
#   5. 生成 TTS 配音 + AI PV 画面匹配
#   6. 合成视频 + 游戏雷达局水印 + 结尾品牌卡片
# ══════════════════════════════════════════════════════════

def _fetch_steam_info(steam_url: str) -> Dict:
    """
    从 Steam API 获取游戏基础信息，包括 PV HLS 流地址。
    返回 dict: {game_name, app_id, description, developer, release_date,
                genres, tags, pv_hls_url, pv_mp4_url}
    """
    import re, json as _json
    import urllib.request

    # 从 URL 提取 appid
    m = re.search(r"/app/(\d+)", steam_url)
    if not m:
        return {}
    app_id = m.group(1)

    info: Dict = {"app_id": app_id, "steam_url": steam_url}

    # Steam API
    try:
        api_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=schinese"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        app_data = data.get(str(app_id), {}).get("data", {})
        info["game_name"]    = app_data.get("name", "")
        info["description"]  = app_data.get("short_description", "")
        info["developer"]    = ", ".join(app_data.get("developers") or [])
        info["publisher"]    = ", ".join(app_data.get("publishers") or [])
        info["release_date"] = app_data.get("release_date", {}).get("date", "")
        info["coming_soon"]  = app_data.get("release_date", {}).get("coming_soon", False)
        info["is_free"]      = app_data.get("is_free", False)
        # 价格（付费游戏）
        price_overview = app_data.get("price_overview") or {}
        info["price_formatted"] = price_overview.get("final_formatted", "")
        # 是否有免费 Demo
        info["has_demo"]     = bool(app_data.get("demos"))
        genres = [g.get("description","") for g in (app_data.get("genres") or [])]
        info["genres"]       = genres
        tags = [t.get("description","") for t in (app_data.get("categories") or [])]
        info["tags"]         = tags
        # PV 视频
        movies = app_data.get("movies") or []
        for mv in movies:
            # 新版 Steam API 格式（2024+）：hls_h264, dash_h264, dash_av1
            hls_url = mv.get("hls_h264") or mv.get("hls_vp9") or ""
            if hls_url:
                info["pv_hls_url"] = hls_url
                break
            # 旧版格式：mp4 / webm
            webm = mv.get("webm", {})
            mp4  = mv.get("mp4", {})
            url = mp4.get("480") or mp4.get("max") or webm.get("480") or webm.get("max") or ""
            if url:
                info["pv_mp4_url"] = url
                break
    except Exception as e:
        logger.warning("Steam API 获取失败: %s", e)

    # 若 Steam API 无 HLS/MP4，从原始 JSON 文本中正则搜索
    if not info.get("pv_hls_url") and not info.get("pv_mp4_url"):
        try:
            page_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
            req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            hls = re.search(r'(https://video\.akamai\.steamstatic\.com[^"\']+hls_264_master\.m3u8[^"\']*)', raw)
            if hls:
                info["pv_hls_url"] = hls.group(1)
        except Exception:
            pass

    return info


def _search_game_reviews(game_name: str, steam_url: str) -> str:
    """
    联网搜索游戏相关评测/资讯，返回整合摘要文本。
    使用 qwen-max + enable_search=True 直接联网。
    """
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()
        query = (
            f"请联网搜索游戏《{game_name}》的以下信息并整合成一段摘要：\n"
            f"1. 核心玩法特色（3-5个亮点）\n"
            f"2. 玩家/媒体评价倾向（正面/负面各2-3点）\n"
            f"3. 游戏的目标受众\n"
            f"4. 与哪些知名游戏类似（同类对标）\n"
            f"5. 是否有试玩/免费/上线时间信息\n"
            f"Steam页面：{steam_url}\n"
            f"输出300字以内的中文摘要，不要列表，直接连贯叙述。"
        )
        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": query}],
            extra_body={"enable_search": True},
            max_tokens=600,
            timeout=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("联网搜索评测失败: %s", e)
        return ""


def _build_facts_constraint(steam_info: Dict) -> str:
    """根据 steam_info 构建脚本写作的硬事实约束块。"""
    game_name    = steam_info.get("game_name", "")
    is_free      = steam_info.get("is_free", False)
    has_demo     = steam_info.get("has_demo", False)
    coming_soon  = steam_info.get("coming_soon", False)
    release_date = steam_info.get("release_date", "")
    price        = steam_info.get("price_formatted", "")

    # 发售状态
    if coming_soon:
        release_str = f"尚未发售（预计 {release_date}），禁止写『已上线』『现已发售』等措辞"
    else:
        release_str = f"已正式发售（日期：{release_date}）"

    # 定价
    if is_free:
        price_str = "完全免费"
    elif price:
        price_str = f"付费游戏，售价 {price}"
    else:
        price_str = "付费游戏（售价待确认，禁止捏造具体价格）"

    # Demo
    if has_demo:
        demo_str = "Steam 上有免费 Demo 可下载体验"
    else:
        demo_str = "无免费 Demo，禁止在脚本中提及『试玩』『免费体验』『Demo』等内容"

    lines = [
        "【⚠️ 硬事实约束 — 以下内容必须严格遵守，任何违反均为错误】",
        f"游戏名称：{game_name}（不得改写）",
        f"发售状态：{release_str}",
        f"定价信息：{price_str}",
        f"试玩状态：{demo_str}",
        "以上4条为最高优先级，优先于评测摘要中的任何说法。",
    ]
    return "\n".join(lines)


def _fact_check_and_fix_script(script_text: str, steam_info: Dict) -> str:
    """
    对已生成的口播脚本进行 AI 事实核查并自动修正。
    重点检查：游戏发售状态、Demo 存在性、价格；其余内容也一并检查。
    返回修正后的脚本文本。
    """
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()

        facts_block = _build_facts_constraint(steam_info)

        system = (
            "你是一名专业游戏媒体事实核查编辑。\n"
            "任务：对下方口播脚本进行事实核查，发现错误后直接输出修正后的完整脚本。\n\n"
            "核查重点（按优先级）：\n"
            "1. 【最高优先级】游戏发售状态：是否已发售/尚未发售，禁止与事实矛盾\n"
            "2. 【最高优先级】Demo/试玩：若无Demo，脚本中不得出现任何试玩、免费体验相关表述\n"
            "3. 【最高优先级】价格：禁止捏造或错误引用售价\n"
            "4. 其他内容：检查是否有明显的事实性错误（游戏名、开发商、玩法描述等）\n\n"
            "修正规则：\n"
            "- 只改错误内容，保持脚本结构、语气、字数基本不变\n"
            "- 若某段因事实错误需要删除，用符合上下文的正确内容替代，不留空白\n"
            "- 输出修正后的完整脚本正文，段落间保持空行，不加任何说明或标注\n"
        )

        user = f"{facts_block}\n\n【待核查脚本】\n{script_text}"

        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        fixed = (resp.choices[0].message.content or "").strip()
        if fixed:
            logger.info("事实核查完成，脚本已修正")
            return fixed
        return script_text
    except Exception as e:
        logger.warning("事实核查失败，使用原脚本: %s", e)
        return script_text


def _generate_promo_script(steam_info: Dict, review_summary: str) -> str:
    """
    根据 Steam 信息 + 评测摘要，AI 生成60秒口播脚本，并经事实核查修正后返回。
    """
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()

        game_name    = steam_info.get("game_name", "")
        description  = steam_info.get("description", "")
        developer    = steam_info.get("developer", "")
        is_free      = steam_info.get("is_free", False)
        price        = steam_info.get("price_formatted", "")
        release_date = steam_info.get("release_date", "")
        coming_soon  = steam_info.get("coming_soon", False)
        genres       = "、".join(steam_info.get("genres") or [])

        if is_free:
            price_str = "完全免费"
        elif price:
            price_str = f"售价 {price}"
        else:
            price_str = "付费游戏"

        if coming_soon:
            release_str = f"尚未发售，预计上线日期：{release_date}"
        else:
            release_str = f"已正式发售（{release_date}）"

        facts_block = _build_facts_constraint(steam_info)

        prompt = f"""你是游戏博主「游戏雷达局」，正在为短视频写一期约60秒的游戏推荐口播脚本。

【游戏基础信息】
名称：{game_name}
开发商：{developer}
类型：{genres}
定价：{price_str}
发售状态：{release_str}
官方简介：{description}

{facts_block}

【媒体/评测摘要】
{review_summary}

【写作要求】
1. 目标受众：18-30岁游戏爱好者（关注同类游戏的玩家）
2. 语气：热血、真实、口语化，像博主亲身体验过
3. 结构（严格按顺序）：
   - 钩子（前3秒，强烈悬念/震撼感）
   - 世界观/背景（1-2句）
   - 核心玩法亮点（2-3个，每个一句话，突出差异化）
   - 媒体/评测口碑（引用媒体或评测观点，不要捏造玩家数据）
   - 发售时间与价格（严格按硬事实约束，精确，有紧迫感）
   - CTA结尾（简洁有力，不超过15字）
4. 总计约7段，每段15-35字，总字数约200-220字
5. 不要出现"小伙伴""大家好""点赞关注"等套话
6. 每段之间用【空行】分隔，直接输出脚本正文，不要标注[段落X]

只输出脚本文本，不要任何说明或标注。"""

        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.88,
            max_tokens=700,
        )
        raw_script = (resp.choices[0].message.content or "").strip()
        if not raw_script:
            return ""

        # 事实核查并自动修正
        return _fact_check_and_fix_script(raw_script, steam_info)

    except Exception as e:
        logger.error("脚本生成失败: %s", e)
        return ""


def _download_steam_pv(steam_info: Dict, work_dir: Path) -> Optional[Path]:
    """
    下载 Steam PV。优先用 HLS m3u8（yt-dlp），其次用 mp4 直链。
    返回合并后的本地 MP4 路径，失败返回 None。
    """
    hls_url = steam_info.get("pv_hls_url", "")
    mp4_url = steam_info.get("pv_mp4_url", "")

    # 优先 HLS（清晰度更高）
    if hls_url:
        try:
            import shutil as _sh
            ydl = _sh.which("yt-dlp")
            if not ydl:
                # WinGet 路径
                ydl_candidates = list(Path(os.environ.get("LOCALAPPDATA",""))
                    .glob("Microsoft/WinGet/Links/yt-dlp*"))
                if ydl_candidates:
                    ydl = str(ydl_candidates[0])
            if ydl:
                merged_out = work_dir / "pv_merged.mp4"
                # 一次性下载最佳画质+音频，合并为 mp4（超时放宽至 300s）
                r = subprocess.run(
                    [ydl, "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                     "--merge-output-format", "mp4",
                     hls_url, "-o", str(merged_out), "--no-playlist"],
                    capture_output=True, timeout=300
                )
                if merged_out.exists() and merged_out.stat().st_size > 100000:
                    return merged_out
                # 降级：只下最佳视频流（可能无音，但至少有画面）
                video_out = work_dir / "pv_video.mp4"
                if not video_out.exists() or video_out.stat().st_size < 100000:
                    subprocess.run(
                        [ydl, "-f", "bestvideo", hls_url, "-o", str(video_out),
                         "--no-playlist"],
                        capture_output=True, timeout=300
                    )
                if video_out.exists() and video_out.stat().st_size > 100000:
                    return video_out
        except Exception as e:
            logger.warning("HLS PV 下载失败: %s", e)

    # 降级：直链 mp4
    if mp4_url:
        try:
            import urllib.request
            out = work_dir / "pv_direct.mp4"
            req = urllib.request.Request(mp4_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(out, "wb") as f:
                f.write(resp.read())
            if out.exists() and out.stat().st_size > 100000:
                return out
        except Exception as e:
            logger.warning("直链 PV 下载失败: %s", e)

    return None


def _run_promo_pipeline(
    task_id: str,
    game_name_hint: str,
    steam_url: str,
    voice: str,
    bgm_volume: float,
    tts_volume: float,
    tts_rate: str,
    script_override: str = "",
):
    """一键推荐视频的后台线程实现。"""
    try:
        work_dir = VIDEO_OUTPUT_DIR / task_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: 爬取 Steam 信息
        _update_task(task_id, stage="fetch_steam", progress=5)
        logger.info("[%s] 爬取 Steam 信息: %s", task_id, steam_url)
        steam_info = _fetch_steam_info(steam_url)
        game_name = steam_info.get("game_name") or game_name_hint
        _update_task(task_id, game_name=game_name)
        logger.info("[%s] 游戏名: %s", task_id, game_name)

        # Step 2 & 3: 生成脚本（若用户已提供确认文案则跳过）
        if script_override:
            script_text = script_override
            logger.info("[%s] 使用用户确认文案，跳过 AI 写稿", task_id)
            _update_task(task_id, stage="parse_script", progress=28)
        else:
            # Step 2: 联网搜索评测
            _update_task(task_id, stage="search_reviews", progress=12)
            logger.info("[%s] 联网搜索评测...", task_id)
            review_summary = _search_game_reviews(game_name, steam_url)

            # Step 3: AI 生成脚本
            _update_task(task_id, stage="generate_script", progress=20)
            logger.info("[%s] AI 生成口播脚本...", task_id)
            script_text = _generate_promo_script(steam_info, review_summary)
            if not script_text:
                _update_task(task_id, status="failed", error="脚本生成失败")
                return
            logger.info("[%s] 脚本:\n%s", task_id, script_text)

        # Step 4: 解析脚本为 segments
        _update_task(task_id, stage="parse_script", progress=28)
        script = _step_parse_script_from_text(task_id, game_name, script_text)
        if not script:
            return

        # Step 5: 下载 Steam PV
        _update_task(task_id, stage="download_pv", progress=35)
        logger.info("[%s] 下载 Steam PV...", task_id)
        pv_path = _download_steam_pv(steam_info, work_dir)
        if not pv_path:
            logger.warning("[%s] PV 下载失败，使用纯色背景", task_id)

        # Step 6: TTS 生成
        audio_paths = _step_generate_tts(
            task_id, script.get("segments") or [], work_dir,
            voice=voice, rate=tts_rate
        )

        # Step 7: AI PV 画面匹配
        if pv_path:
            script["segments"] = _step_match_pv_scenes(
                task_id, pv_path, script.get("segments") or []
            )

        # Step 8: 合成视频（含水印+结尾卡片）
        video_path = _step_edit_video(
            task_id, script, pv_path, audio_paths, work_dir,
            bgm_volume=bgm_volume, tts_volume=tts_volume
        )
        if not video_path:
            return

        _update_task(
            task_id,
            status="completed",
            stage="done",
            progress=100,
            output_path=str(video_path),
            script_text=script_text,
        )
        logger.info("[%s] 一键推荐视频完成: %s", task_id, video_path)

    except Exception as e:
        logger.exception("[%s] 一键流水线异常: %s", task_id, e)
        _update_task(task_id, status="failed", error=str(e))


def run_game_promo_pipeline(
    steam_url: str,
    game_name_hint: str = "",
    voice: str = "zh-CN-YunxiNeural",
    bgm_volume: float = 0.12,
    tts_volume: float = 1.0,
    tts_rate: str = "+30%",
    script_override: str = "",
) -> str:

    """
    一键游戏推荐视频工作流。

    只需提供 Steam 商店链接（如 https://store.steampowered.com/app/3810880/...）。
    自动完成：Steam 信息爬取 → 联网搜索评测 → AI 脚本生成 →
              PV 下载 → TTS 配音 → PV 画面匹配 → 合成视频 →
              游戏雷达局水印 + 结尾品牌卡片。

    Returns:
        task_id（用于 /api/video_status/<task_id> 轮询进度）
    """
    task_id = uuid.uuid4().hex[:12]
    with _task_lock:
        _task_store[task_id] = {
            "task_id": task_id,
            "game_name": game_name_hint or "加载中…",
            "status": "pending",
            "stage": "queued",
            "progress": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "error": None,
            "output_path": None,
        }
    t = threading.Thread(
        target=_run_promo_pipeline,
        args=(task_id, game_name_hint, steam_url, voice, bgm_volume, tts_volume, tts_rate, script_override),
        daemon=True,
    )
    t.start()
    logger.info("一键推荐视频已启动，task_id=%s，steam_url=%s", task_id, steam_url)
    return task_id


# ══════════════════════════════════════════════════════════
# Steam 折扣盘点视频流水线
# 输入：多款 Steam 折扣游戏列表
# 输出：合集短视频（开场钩子 + N段游戏片段 + 结尾品牌卡片）
# ══════════════════════════════════════════════════════════

def _extract_steam_appid(item: dict) -> str:
    """从折扣条目中提取 Steam app_id。"""
    import re as _re2
    url = (item.get("url") or "").strip()
    m = _re2.search(r"/app/(\d+)", url)
    return m.group(1) if m else ""


def _fetch_steam_pv_direct(app_id: str, work_dir: Path) -> tuple:
    """
    直接从 Steam API movies 字段获取 mp4 直链并下载。
    优先 mp4.max，其次 mp4.480。
    Returns: (pv_path, success: bool)
    """
    if not app_id:
        return None, False
    import urllib.request, json as _json
    try:
        api_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        app_data = data.get(str(app_id), {}).get("data", {})
        movies = app_data.get("movies") or []
        mp4_url = ""
        hls_url = ""
        for mv in movies:
            # 新版 Steam API：hls_h264/hls_vp9
            hls = mv.get("hls_h264") or mv.get("hls_vp9") or ""
            if hls:
                hls_url = hls
            # 旧版/通用：mp4.max / mp4.480
            mp4 = mv.get("mp4") or {}
            url = mp4.get("max") or mp4.get("480") or ""
            if url:
                mp4_url = url
                break
        # 优先尝试 mp4 直链
        if mp4_url:
            out = work_dir / f"pv_{app_id}.mp4"
            req2 = urllib.request.Request(mp4_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=60) as r, open(out, "wb") as f:
                f.write(r.read())
            if out.exists() and out.stat().st_size > 50000:
                logger.info("Steam 直链 PV 下载成功: app_id=%s, size=%d", app_id, out.stat().st_size)
                return out, True
        # 备选：HLS 用 yt-dlp
        if hls_url:
            import shutil as _sh, subprocess as _sp
            ydl = _sh.which("yt-dlp")
            if not ydl:
                # Python Scripts 目录（最常见安装位置）
                _py_scripts = Path(sys.executable).parent / "Scripts" / "yt-dlp.exe"
                if _py_scripts.exists():
                    ydl = str(_py_scripts)
            if not ydl:
                ydl_candidates = list(Path(os.environ.get("LOCALAPPDATA", ""))
                    .glob("Microsoft/WinGet/Links/yt-dlp*"))
                if ydl_candidates:
                    ydl = str(ydl_candidates[0])
            if ydl:
                out = work_dir / f"pv_{app_id}_hls.mp4"
                # Steam HLS 格式选择：720p视频流（无需合并音频，TTS会覆盖原声）
                r = _sp.run(
                    [ydl,
                     "-f", "2600/1400+audio-Default/2600+audio-Default/1400/1000/best",
                     "--merge-output-format", "mp4",
                     hls_url, "-o", str(out), "--no-playlist"],
                    capture_output=True, timeout=180
                )
                # yt-dlp 在无 ffmpeg 时也会输出视频流文件（扩展名可能不是.mp4）
                # 尝试找生成的文件
                if not (out.exists() and out.stat().st_size > 50000):
                    for candidate in work_dir.glob(f"pv_{app_id}_hls*"):
                        if candidate.stat().st_size > 50000:
                            out = candidate
                            break
                if out.exists() and out.stat().st_size > 50000:
                    return out, True
                logger.warning("yt-dlp 下载后文件不存在或过小 (app_id=%s), rc=%d", app_id, r.returncode)
    except Exception as e:
        logger.warning("Steam PV 直链下载失败 (app_id=%s): %s", app_id, e)
    return None, False


def _generate_deal_segment_script(game: dict) -> str:
    """
    为单款折扣游戏生成约100字口播文案，含游戏亮点介绍+推荐理由+折扣信息。
    风格：口语化、有温度、像博主真实推荐。
    """
    import re as _re_ds
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()
        title         = (game.get("title")          or "").strip()
        # 去掉 【Steam】xxx — xx% OFF 格式，只保留游戏名
        title_clean   = _re_ds.sub(r"^【[^】]+】\s*", "", title).strip()
        title_clean   = _re_ds.sub(r"\s*[—–-]+\s*.+$", "", title_clean).strip() or title_clean
        discount      = (game.get("discount")        or "").strip()
        price_current = (game.get("price_current")   or "").strip()
        price_original= (game.get("price_original")  or "").strip()
        deal_end      = (game.get("deal_end")        or "").strip()
        content       = (game.get("content")         or "")[:400].strip()

        time_hint = f"，折扣截止时间：{deal_end}" if deal_end else ""
        prompt = (
            f"你是游戏博主「游戏雷达局」，正在录一期Steam折扣盘点短视频。\n"
            f"现在介绍：《{title_clean}》\n"
            f"折扣：{discount}，现价：{price_current}，原价：{price_original}{time_hint}\n"
            f"游戏简介：{content}\n\n"
            f"写一段约100字的口播文案，结构如下：\n"
            f"① 开头1-2句：直接抓人——描述玩这款游戏时最爽/最上头的瞬间或独特体验，\n"
            f"   【禁止】不许用「这是一款xx题材游戏」「这款游戏是xxx」等平铺直叙的介绍句\n"
            f"② 中间2-3句：说清楚这游戏哪里好玩、有什么让人记住的特点（结合游戏简介提炼，不要照抄）\n"
            f"③ 结尾1-2句：折扣信息——说清楚省了多少钱或现在多划算，如有截止时间带出紧迫感\n"
            f"整体要求：口语自然、有个人温度，像朋友之间推荐，不用「强烈推荐」「必买」「绝对」等硬推套话\n"
            f"只输出文案正文，不加序号标注或解释。"
        )
        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("单款折扣文案生成失败 (%s): %s", game.get("title"), e)
        return f"《{title_clean}》，{discount}折扣中，现价{price_current}。"


def _generate_deals_hook_script(games: list) -> str:
    """生成开场钩子文案（整期视频第一句话，约20字）。"""
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()
        # 提取精华游戏名（去掉【Steam】前缀）
        import re as _re_hook
        clean_names = []
        for g in games[:5]:
            t = g.get("title", "")
            t = _re_hook.sub(r"^【[^】]+】\s*", "", t).strip()
            t = _re_hook.sub(r"\s*[—–-]+\s*.+$", "", t).strip() or t
            if t:
                clean_names.append(t)
        names = "、".join(clean_names)
        n = len(games)
        prompt = (
            f"你是游戏博主「游戏雷达局」，正在录一期Steam折扣盘点短视频。\n"
            f"本期精选了{n}款折扣游戏，包括：{names}等。\n"
            f"写一句15-25字的开场钩子，要求：\n"
            f"1. 前3秒直接抓住眼球，用具体数字或反常识角度制造惊喜感\n"
            f"   例如「这几款游戏打骨折了，错过要等明年」「我的愿望清单今天全在打折」\n"
            f"2. 口语自然，像突然要分享好消息给朋友\n"
            f"3. 【禁止】不要「大家好」「本期给大家介绍」「今天推荐」等开播套话\n"
            f"只输出这一句话，不加任何标注。"
        )
        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=60,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("开场钩子生成失败: %s", e)
        return f"这周Steam折扣力度超大，我帮你挑了{len(games)}款值得买的！"


def _ai_select_deals(deals: list, max_count: int = 8) -> list:
    """
    AI筛选：从deals中挑选5-8款最值得推荐（折扣大、有口碑、类型多样）。
    """
    if len(deals) <= max_count:
        return deals
    try:
        from qwen_client import get_qwen_client
        client = get_qwen_client()
        import json as _json
        items_text = "\n".join(
            f"{i+1}. {d.get('title','')}  折扣:{d.get('discount','')}  原价:{d.get('price_original','')}  现价:{d.get('price_current','')}  简介:{(d.get('content') or '')[:80]}"
            for i, d in enumerate(deals[:20])
        )
        prompt = (
            f"以下是Steam折扣游戏列表：\n{items_text}\n\n"
            f"请从中挑选{min(max_count, len(deals))}款最适合做视频推荐的游戏，要求：\n"
            f"1. 折扣力度大（优先选打折比例高的）\n"
            f"2. 类型多样（不要全是同类游戏）\n"
            f"3. 有一定知名度或口碑\n"
            f"直接输出被选中游戏的编号，格式：[1,3,5,7,9]，不要其他内容。"
        )
        resp = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        raw = (resp.choices[0].message.content or "").strip()
        import re as _re3
        m = _re3.search(r'\[[\d,\s]+\]', raw)
        if m:
            indices = _json.loads(m.group())
            selected = []
            for idx in indices:
                if 1 <= idx <= len(deals):
                    selected.append(deals[idx - 1])
            if selected:
                return selected[:max_count]
    except Exception as e:
        logger.warning("AI筛选折扣游戏失败: %s", e)
    # fallback：返回前max_count条
    return deals[:max_count]


def _step_edit_deals_video(
    task_id: str,
    segments: list,           # [{title, script, pv_path, duration, subtitle_timeline, ...}]
    audio_paths: list,
    work_dir: Path,
    bgm_path: Optional[Path] = None,
    bgm_volume: float = 0.15,
) -> Optional[Path]:
    """
    合成折扣盘点视频：ffmpeg filter_complex 实现，比 MoviePy 逐帧快 10-20 倍。
    流程：PIL 预渲染每段标签 PNG → ffmpeg 逐段合成 → concat + BGM + 水印+结尾
    """
    import subprocess, shlex, textwrap, re as _re
    from PIL import Image as _PILImg, ImageDraw as _PILDraw, ImageFont as _PILFont

    _update_task(task_id, stage="edit_video", progress=70)

    # ffmpeg 路径
    try:
        import imageio_ffmpeg as _ioff
        FFMPEG = _ioff.get_ffmpeg_exe()
    except Exception:
        FFMPEG = "ffmpeg"

    fps = 30
    W, H = 1920, 1080
    font_path = _get_font_path()

    def _run_ff(*args, check=True):
        cmd = [FFMPEG, "-y"] + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {r.stderr[-600:]}")
        return r

    def _tw(fnt, text):
        try:
            bb = fnt.getbbox(text)
            return bb[2] - bb[0]
        except Exception:
            try: return int(fnt.getlength(text))
            except: return len(text) * 20

    # ── Step A: 为每段预渲染标签 PNG（右上角信息）──
    label_pngs = []
    for i, seg in enumerate(segments):
        png_path = work_dir / f"label_{i:03d}.png"
        try:
            canvas = _PILImg.new("RGBA", (W, H), (0, 0, 0, 0))
            ld = _PILDraw.Draw(canvas)
            title        = seg.get("title") or ""
            discount     = seg.get("discount") or ""
            price_current= seg.get("price_current") or ""
            deal_end     = seg.get("deal_end") or ""
            PAD_X, MR = 16, 20
            ROW1_TOP, ROW1_BOT = 10, 52

            if discount and not seg.get("is_hook"):
                try: bf = _PILFont.truetype(font_path, 28)
                except: bf = _PILFont.load_default()
                bw = _tw(bf, discount) + PAD_X * 2
                bx = W - bw - MR
                ld.rounded_rectangle([bx, ROW1_TOP, bx+bw, ROW1_BOT], radius=10, fill=(255,120,0,220))
                ld.text((bx+PAD_X, ROW1_TOP+6), discount, font=bf, fill=(255,255,255,255))

            if title and not seg.get("is_hook"):
                try: tf = _PILFont.truetype(font_path, 32)
                except: tf = _PILFont.load_default()
                dt = title
                max_w = int(W * 0.80)
                while dt and _tw(tf, dt) > max_w: dt = dt[:-1]
                if dt != title: dt = dt[:-1] + "…"
                tw2 = _tw(tf, dt) + PAD_X * 2
                R2T = ROW1_BOT + 6; R2B = R2T + 42
                tx = W - tw2 - MR
                ld.rounded_rectangle([tx, R2T, W-MR, R2B], radius=8, fill=(0,0,0,180))
                ld.text((tx+PAD_X, R2T+5), dt, font=tf, fill=(255,255,255,240))

                if price_current:
                    try: pf = _PILFont.truetype(font_path, 26)
                    except: pf = _PILFont.load_default()
                    pt = f"现价 {price_current}"
                    if deal_end: pt += f"  ·  截至 {deal_end}"
                    pw2 = _tw(pf, pt) + PAD_X * 2
                    cy = R2B + 4
                    px2 = W - pw2 - MR
                    ld.rounded_rectangle([px2, cy, W-MR, cy+36], radius=6, fill=(0,0,0,160))
                    ld.text((px2+PAD_X, cy+5), pt, font=pf, fill=(255,210,60,230))

            canvas.save(str(png_path))
        except Exception as e:
            logger.warning("[%s] seg %d 标签PNG生成失败: %s", task_id, i, e)
            # 生成空白透明 PNG
            _PILImg.new("RGBA", (W, H), (0,0,0,0)).save(str(png_path))
        label_pngs.append(png_path)

    # ── Step B: 为每段生成字幕 ASS 文件 ──
    def _build_ass(seg, dur, seg_idx):
        """生成 ASS 字幕文件，返回路径（无字幕返回 None）"""
        subtitle = seg.get("subtitle") or seg.get("script") or ""
        if not subtitle:
            return None
        timeline = seg.get("subtitle_timeline") or []
        # 构建 (start_s, end_s, text) 列表
        entries = []
        if timeline:
            for idx2, entry in enumerate(timeline):
                t0 = entry["t"]
                t1 = timeline[idx2+1]["t"] if idx2+1 < len(timeline) else dur
                sent = entry["text"]
                # 长句按标点分割
                if len(sent) > 18:
                    parts = _re.split(r'([，。！？、；：,!?;:])', sent)
                    buf, chunks = "", []
                    for p in parts:
                        buf += p
                        if _re.search(r'[，。！？、；：,!?;:]', p) and buf.strip():
                            chunks.append(buf.strip()); buf = ""
                    if buf.strip(): chunks.append(buf.strip())
                    if len(chunks) > 1:
                        sd = (t1 - t0) / len(chunks)
                        for ci, c in enumerate(chunks):
                            entries.append((t0+ci*sd, t0+(ci+1)*sd, c))
                        continue
                entries.append((t0, t1, sent))
        else:
            # 无时间轴：按标点均匀分段
            parts = _re.split(r'([，。！？、；：,\.!?;:])', subtitle)
            sents, buf = [], ""
            for p in parts:
                buf += p
                if _re.search(r'[，。！？、；：,\.!?;:]', p) and buf.strip():
                    sents.append(buf.strip()); buf = ""
            if buf.strip(): sents.append(buf.strip())
            if not sents: sents = [subtitle]
            each = dur / len(sents)
            for si, s in enumerate(sents):
                entries.append((si*each, (si+1)*each, s))

        def _ts(s):
            h = int(s//3600); m = int((s%3600)//60); sec = s%60
            return f"{h}:{m:02d}:{sec:06.3f}".replace(".", ",")  # ASS 用逗号

        ass_path = work_dir / f"sub_{seg_idx:03d}.ass"
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {W}", f"PlayResY: {H}",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
            "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
            "Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: Default,{_get_font_path()},44,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,"
            f"0,0,0,0,100,100,0,0,1,2,0,2,20,20,60,1",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]
        for t0, t1, text in entries:
            # 转义 ASS 特殊字符
            text_esc = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            lines.append(f"Dialogue: 0,{_ts(t0)},{_ts(t1)},Default,,0,0,0,,{text_esc}")
        ass_path.write_text("\n".join(lines), encoding="utf-8-sig")
        return ass_path

    # ── Step C: 逐段合成（PV裁剪+标签叠加+字幕+TTS音频）→ 生成各段 mp4 ──
    seg_files = []
    for i, seg in enumerate(segments):
        out_seg = work_dir / f"seg_{i:03d}.mp4"
        pv_path = seg.get("pv_path")
        tts_path = audio_paths[i] if i < len(audio_paths) else None
        label_png = label_pngs[i]

        # 计算段落时长
        tts_dur = 0.0
        if tts_path and Path(str(tts_path)).exists():
            try:
                r_dur = subprocess.run(
                    [FFMPEG, "-i", str(tts_path)], capture_output=True, text=True
                )
                m = _re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r_dur.stderr)
                if m:
                    tts_dur = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
            except Exception:
                pass
        dur = tts_dur + 0.5 if tts_dur > 1 else float(seg.get("duration") or 25)

        # 生成字幕 ASS
        ass_path = _build_ass(seg, dur, i)

        try:
            if pv_path and Path(str(pv_path)).exists():
                # 获取 PV 时长
                r_pv = subprocess.run([FFMPEG, "-i", str(pv_path)], capture_output=True, text=True)
                m2 = _re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r_pv.stderr)
                pv_dur = 0.0
                if m2:
                    pv_dur = int(m2.group(1))*3600 + int(m2.group(2))*60 + float(m2.group(3))

                # PV 起始时间：从中段开始，避免黑屏
                if pv_dur > dur:
                    pv_start = max(0, (pv_dur - dur) * 0.3)
                else:
                    pv_start = 0.0

                # 构建 filter_complex
                # 输入: 0=PV, 1=label PNG, [2=TTS audio 可选]
                inputs = ["-i", str(pv_path), "-i", str(label_png)]
                if tts_path and Path(str(tts_path)).exists():
                    inputs += ["-i", str(tts_path)]
                    audio_idx = 2
                else:
                    audio_idx = None

                # video filter：scale→crop→loop处理→叠加标签→字幕
                vf_parts = [
                    # 1. 裁剪起始时间 + 限制时长
                    f"[0:v]trim=start={pv_start:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS",
                    # 2. scale+crop 到 W×H
                    f"scale='if(gt(iw/ih,{W}/{H}),trunc(oh*a/2)*2,{W})':'if(gt(iw/ih,{W}/{H}),{H},trunc(ow/a/2)*2)',crop={W}:{H}",
                    # 3. 循环（如果PV比dur短）
                ]
                if pv_dur > 0 and pv_dur < dur - 0.5:
                    # 用 loop filter 循环
                    loop_count = int(dur / pv_dur) + 2
                    vf_parts.append(f"loop={loop_count}:size=32767:start=0,trim=duration={dur:.3f},setpts=PTS-STARTPTS")

                vf_parts.append(f"fps={fps}[bgv]")
                vf_chain = ",".join(vf_parts)

                filter_complex = (
                    f"{vf_chain};"
                    f"[bgv][1:v]overlay=0:0:format=auto[labeled]"
                )

                # 字幕滤镜（如有）
                if ass_path and ass_path.exists():
                    # ASS 字体路径需要转义反斜杠
                    ass_str = str(ass_path).replace("\\", "/").replace(":", "\\:")
                    filter_complex += f";[labeled]ass='{ass_str}'[outv]"
                    out_label = "[outv]"
                else:
                    out_label = "[labeled]"
                    filter_complex = filter_complex  # 不加字幕时 labeled 就是输出

                # 重新整理 filter_complex 末端
                if not ass_path or not ass_path.exists():
                    filter_complex = filter_complex.replace("[labeled]", "[outv]")
                    out_label = "[outv]"

                cmd = [FFMPEG, "-y"] + inputs + [
                    "-filter_complex", filter_complex,
                    "-map", out_label,
                ]
                if audio_idx is not None:
                    cmd += ["-map", f"{audio_idx}:a", "-shortest"]
                cmd += [
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-ar", "44100",
                    "-t", str(dur),
                    "-movflags", "+faststart",
                    str(out_seg)
                ]
                _run_ff(*cmd[2:])  # 去掉开头的 FFMPEG -y，_run_ff 会加

            else:
                # 无 PV：黑色背景 + 标签 PNG + 字幕
                inputs = ["-f", "lavfi", "-i", f"color=c=0f0f19:size={W}x{H}:rate={fps}",
                          "-i", str(label_png)]
                if tts_path and Path(str(tts_path)).exists():
                    inputs += ["-i", str(tts_path)]
                    audio_idx = 2
                else:
                    audio_idx = None

                filter_complex = f"[0:v][1:v]overlay=0:0:format=auto[labeled]"
                if ass_path and ass_path.exists():
                    ass_str = str(ass_path).replace("\\", "/").replace(":", "\\:")
                    filter_complex += f";[labeled]ass='{ass_str}'[outv]"
                    out_label = "[outv]"
                else:
                    filter_complex = filter_complex.replace("[labeled]", "[outv]")
                    out_label = "[outv]"

                cmd = [FFMPEG, "-y"] + inputs + [
                    "-filter_complex", filter_complex,
                    "-map", out_label,
                ]
                if audio_idx is not None:
                    cmd += ["-map", f"{audio_idx}:a", "-shortest"]
                cmd += [
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-ar", "44100",
                    "-t", str(dur),
                    "-movflags", "+faststart",
                    str(out_seg)
                ]
                _run_ff(*cmd[2:])

            seg_files.append(out_seg)
            logger.info("[%s] 段落 %d 合成完成: %s", task_id, i, out_seg.name)

        except Exception as e:
            logger.error("[%s] 段落 %d 合成失败: %s", task_id, i, e)
            # 降级：生成黑屏占位段
            try:
                _run_ff(
                    "-f", "lavfi", "-i", f"color=c=black:size={W}x{H}:rate={fps}:duration={dur}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-t", str(dur), str(out_seg)
                )
                seg_files.append(out_seg)
            except Exception:
                pass

    if not seg_files:
        _update_task(task_id, status="failed", error="无有效视频段落")
        return None

    # ── Step D: 拼接所有段落 ──
    concat_path = work_dir / "concat_main.mp4"
    concat_list = work_dir / "concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{f.resolve()}'" for f in seg_files), encoding="utf-8"
    )
    try:
        _run_ff(
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-movflags", "+faststart", str(concat_path)
        )
    except Exception as e:
        logger.error("[%s] concat 失败: %s", task_id, e)
        _update_task(task_id, status="failed", error=f"视频拼接失败: {e}")
        return None

    # ── Step E: 加水印（右下角）+ 结尾品牌卡片 ──
    # 用 MoviePy 处理水印和结尾（这部分很短，性能无影响）
    output_path = work_dir / "final_output.mp4"
    try:
        from moviepy.editor import VideoFileClip as _VFC
        main_clip = _VFC(str(concat_path))
        # BGM 混音
        if bgm_path and bgm_path.exists():
            try:
                from moviepy.editor import AudioFileClip as _AFC2, CompositeAudioClip, concatenate_audioclips
                bgm = _AFC2(str(bgm_path)).volumex(bgm_volume)
                fd = main_clip.duration
                if bgm.duration < fd:
                    loops = int(fd / bgm.duration) + 1
                    bgm = concatenate_audioclips([bgm] * loops).subclip(0, fd)
                else:
                    bgm = bgm.subclip(0, fd)
                if main_clip.audio:
                    from moviepy.editor import CompositeAudioClip as _CAC
                    main_clip = main_clip.set_audio(_CAC([main_clip.audio, bgm]))
                else:
                    main_clip = main_clip.set_audio(bgm)
            except Exception as e:
                logger.warning("[%s] BGM混音失败: %s", task_id, e)

        final = _add_watermark_and_outro(task_id, main_clip, work_dir, W, H, fps)
        try:
            import imageio_ffmpeg as _ioffmpeg2
            os.environ.setdefault("IMAGEIO_FFMPEG_EXE", _ioffmpeg2.get_ffmpeg_exe())
        except Exception:
            pass
        final.write_videofile(
            str(output_path), fps=fps, codec="libx264", audio_codec="aac",
            temp_audiofile=str(work_dir / "temp_audio.m4a"),
            remove_temp=True, verbose=False, logger=None,
            ffmpeg_params=["-movflags", "+faststart"],
        )
        final.close()
    except Exception as e:
        logger.error("[%s] 水印/结尾处理失败: %s", task_id, e)
        # 降级：直接用 concat 结果
        import shutil
        shutil.copy2(str(concat_path), str(output_path))

    # 清理中间段落文件
    for f in seg_files:
        try: f.unlink()
        except Exception: pass
    try: concat_path.unlink()
    except Exception: pass

    _update_task(task_id, progress=92)
    return output_path


def _run_deals_video_pipeline(
    task_id: str,
    deals: list,
    voice: str,
    bgm_volume: float,
    resume_pv_map: dict = None,   # {title: local_pv_path} 用户补充的PV
):
    """折扣盘点视频主流程（后台线程）。"""
    work_dir = VIDEO_OUTPUT_DIR / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    resume_pv_map = resume_pv_map or {}

    _update_task(task_id, status="running", stage="ai_select", progress=5, work_dir=str(work_dir))
    try:
        # Step 1: AI筛选 5-8 款最值得推荐的游戏
        logger.info("[%s] Step1: AI筛选折扣游戏，输入 %d 条", task_id, len(deals))
        selected = _ai_select_deals(deals, max_count=8)
        _update_task(task_id, progress=10, selected_count=len(selected))
        logger.info("[%s] AI筛选完成，选中 %d 款", task_id, len(selected))

        # Step 2: 获取每款游戏 PV
        _update_task(task_id, stage="fetch_pv", progress=12)
        game_segments = []
        missing_pv = []

        for game in selected:
            title = (game.get("title") or "").strip()
            app_id = _extract_steam_appid(game)

            # 用户已补充PV
            if title in resume_pv_map and Path(resume_pv_map[title]).exists():
                pv_path = Path(resume_pv_map[title])
                logger.info("[%s] 使用用户提供PV: %s", task_id, title)
            else:
                pv_path, ok = _fetch_steam_pv_direct(app_id, work_dir)
                if not ok:
                    logger.warning("[%s] PV获取失败: %s (app_id=%s)", task_id, title, app_id)
                    missing_pv.append({"title": title, "app_id": app_id, "url": game.get("url", "")})
                    pv_path = None

            game_segments.append({
                "title":          title,
                "app_id":         app_id,
                "discount":       game.get("discount", ""),
                "price_current":  game.get("price_current", ""),
                "price_original": game.get("price_original", ""),
                "deal_end":       game.get("deal_end", ""),
                "deal_start":     game.get("deal_start", ""),
                "content":        game.get("content", ""),
                "pv_path":        pv_path,
            })

        _update_task(task_id, progress=30)

        # Step 3: 有缺失PV → 更新为 waiting_pv 状态，暂停
        if missing_pv:
            logger.info("[%s] 有 %d 款游戏缺少PV，暂停等待用户补充", task_id, len(missing_pv))
            _update_task(
                task_id,
                status="waiting_pv",
                stage="waiting_pv",
                progress=30,
                missing_pv=missing_pv,
                _segments_snapshot=[
                    {k: v for k, v in seg.items() if k != "pv_path"}
                    for seg in game_segments
                ],
                _deals_snapshot=selected,
            )
            return

        # Step 4: 为每款游戏生成口播文案
        _update_task(task_id, stage="gen_scripts", progress=35)
        for seg in game_segments:
            seg["script"] = _generate_deal_segment_script(seg)
            seg["subtitle"] = seg["script"]
            logger.debug("[%s] 文案: %s → %s", task_id, seg["title"], seg["script"])
        _update_task(task_id, progress=45)

        # Step 5: 生成开场钩子
        _update_task(task_id, stage="gen_hook", progress=46)
        hook_text = _generate_deals_hook_script(game_segments)
        logger.info("[%s] 开场钩子: %s", task_id, hook_text)

        # 将开场钩子作为第一个段落插入
        hook_seg = {
            "title": "",
            "app_id": "",
            "discount": "",
            "price_current": "",
            "price_original": "",
            "content": "",
            "script": hook_text,
            "subtitle": hook_text,
            "pv_path": game_segments[0].get("pv_path") if game_segments else None,
            "is_hook": True,
        }
        all_segments = [hook_seg] + game_segments
        _update_task(task_id, progress=48)

        # Step 6: TTS 生成
        _update_task(task_id, stage="generate_tts", progress=50)
        tts_segs = [{"text": s["script"], "subtitle": s["subtitle"]} for s in all_segments]
        audio_paths = _step_generate_tts(task_id, tts_segs, work_dir, voice=voice, rate="+25%")

        # 把 TTS 实际时长、subtitle_timeline 回填到 all_segments
        for i, seg in enumerate(all_segments):
            seg["duration"] = tts_segs[i].get("duration", 12.0)
            seg["subtitle_timeline"] = tts_segs[i].get("subtitle_timeline")
        _update_task(task_id, progress=60)

        # 持久化 segments 快照到工作目录，方便重渲染时复用
        import json as _json
        try:
            snap = []
            for i, seg in enumerate(all_segments):
                snap.append({k: v for k, v in seg.items()})
            (work_dir / "segments_snapshot.json").write_text(
                _json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (work_dir / "audio_paths.json").write_text(
                _json.dumps(audio_paths, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as _e:
            logger.warning("[%s] segments 快照保存失败: %s", task_id, _e)

        # Step 7: 对有PV的游戏做AI画面匹配（逐段单独匹配，跳过开场钩子）
        _update_task(task_id, stage="match_pv_scenes", progress=62)
        for i, seg in enumerate(all_segments):
            if seg.get("is_hook") or not seg.get("pv_path"):
                continue
            pv_path_seg = seg["pv_path"]
            if pv_path_seg and Path(str(pv_path_seg)).exists():
                mini_segs = [{"text": seg["script"], "subtitle": seg["subtitle"],
                               "duration": seg["duration"]}]
                try:
                    matched = _step_match_pv_scenes(task_id, Path(str(pv_path_seg)), mini_segs)
                    if matched:
                        seg["pv_offset"] = matched[0].get("pv_offset", 0)
                        seg["pv_end_offset"] = matched[0].get("pv_end_offset", seg["duration"])
                except Exception as e:
                    logger.warning("[%s] seg %d PV画面匹配失败: %s", task_id, i, e)
        _update_task(task_id, progress=68)

        # Step 8: 合成视频
        video_path = _step_edit_deals_video(
            task_id, all_segments, audio_paths, work_dir,
            bgm_volume=bgm_volume,
        )
        if not video_path:
            return

        _update_task(
            task_id,
            status="completed",
            stage="done",
            progress=100,
            output_path=str(video_path),
        )
        logger.info("[%s] 折扣盘点视频完成: %s", task_id, video_path)

    except Exception as e:
        logger.exception("[%s] 折扣流水线异常: %s", task_id, e)
        _update_task(task_id, status="failed", error=str(e))


def run_deals_video_pipeline(
    deals: list,
    voice: str = "zh-CN-YunxiNeural",
    bgm_volume: float = 0.12,
) -> str:
    """
    启动折扣盘点视频流水线（后台线程）。

    deals: 折扣游戏列表，每项需含 title/url/discount/price_current/price_original/content
    Returns: task_id（用于 /api/video_status/<task_id> 轮询进度）
    """
    task_id = uuid.uuid4().hex[:12]
    with _task_lock:
        _task_store[task_id] = {
            "task_id":    task_id,
            "game_name":  f"折扣盘点（{len(deals)}款）",
            "status":     "pending",
            "stage":      "queued",
            "progress":   0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "error":      None,
            "output_path": None,
            "task_type":  "deals",
        }
    t = threading.Thread(
        target=_run_deals_video_pipeline,
        args=(task_id, deals, voice, bgm_volume),
        daemon=True,
    )
    t.start()
    logger.info("折扣盘点视频已启动，task_id=%s，游戏数=%d", task_id, len(deals))
    return task_id


def resume_deals_video_pipeline(task_id: str, pv_map: dict) -> bool:
    """
    用户补充PV后，继续折扣盘点流水线。
    pv_map: {game_title: local_pv_path}
    Returns: True 表示成功续跑，False 表示任务不存在或状态不对
    """
    with _task_lock:
        info = _task_store.get(task_id)
    if not info or info.get("status") != "waiting_pv":
        return False

    deals_snapshot = info.get("_deals_snapshot") or []
    if not deals_snapshot:
        return False

    _update_task(task_id, status="running", stage="resuming", progress=30)
    t = threading.Thread(
        target=_run_deals_video_pipeline,
        args=(task_id, deals_snapshot, info.get("voice", "zh-CN-YunxiNeural"),
              info.get("bgm_volume", 0.12), pv_map),
        daemon=True,
    )
    t.start()
    logger.info("折扣流水线续跑，task_id=%s", task_id)
    return True
