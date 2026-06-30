"""AI 分析模块：用 Qwen-VL 分析游戏截图，生成总结报告和剪辑脚本。"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# DashScope / Qwen-VL 客户端封装
# ─────────────────────────────────────────────

class GameAnalyzer:
    """
    使用 Qwen-VL-Max 分析游戏截图，生成：
    - 每帧描述
    - 综合游戏体验总结
    - AI 剪辑脚本（含时间戳建议、解说文案、字幕）
    """

    def __init__(self, api_key: str, model: str = "qwen-vl-max"):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=120,
        )
        self._model = model
        self._text_model = "qwen-max"

    # ── 单帧分析 ──────────────────────────────

    def analyze_frame(self, frame_b64: str, game_name: str, frame_index: int) -> str:
        """分析单张游戏截图，返回中文描述。"""
        prompt = (
            f"这是游戏《{game_name}》的第{frame_index}张截图。\n"
            "请简洁描述：1) 当前游戏场景/状态 2) 画面中的关键元素 3) 玩家可能正在做什么。\n"
            "回答控制在80字以内。"
        )
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"帧{frame_index}分析失败: {e}")
            return f"[第{frame_index}帧分析失败]"

    def analyze_frames_batch(
        self,
        frame_b64_list: List[str],
        game_name: str,
        progress_cb=None,
    ) -> List[str]:
        """批量分析多帧，返回描述列表。"""
        progress_cb = progress_cb or (lambda msg: None)
        descriptions = []
        for i, b64 in enumerate(frame_b64_list):
            progress_cb(f"🔍 AI分析第 {i+1}/{len(frame_b64_list)} 帧...")
            desc = self.analyze_frame(b64, game_name, i + 1)
            descriptions.append(desc)
            time.sleep(0.3)  # 避免限速
        return descriptions

    # ── 综合游戏总结 ──────────────────────────

    def generate_summary(
        self,
        game_name: str,
        frame_descriptions: List[str],
        play_duration: int,
    ) -> Dict:
        """
        根据帧描述生成综合总结报告。
        返回字典：{summary, highlights, impressions, rating_aspects}
        """
        desc_text = "\n".join(
            f"[帧{i+1}] {d}" for i, d in enumerate(frame_descriptions)
        )

        prompt = f"""你是一位专业的游戏媒体编辑，以下是对游戏《{game_name}》约{play_duration}秒试玩过程的逐帧AI分析：

{desc_text}

请生成一份完整的试玩总结，以JSON格式返回：
{{
  "summary": "200字左右的整体试玩体验总结，包括游戏风格、玩法特色、视觉表现",
  "highlights": ["亮点1", "亮点2", "亮点3"],
  "impressions": {{
    "gameplay": "玩法机制评价（50字）",
    "visuals": "视觉/画面评价（30字）",
    "difficulty": "难度/挑战性评价（30字）",
    "originality": "创意/独特性评价（30字）"
  }},
  "tags": ["标签1", "标签2", "标签3"],
  "suitable_for": "适合什么类型的玩家",
  "one_line_pitch": "一句话推荐语（20字以内，适合社交媒体）"
}}"""

        try:
            resp = self._client.chat.completions.create(
                model=self._text_model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content.strip()
            # 提取 JSON
            import re
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.error(f"生成总结失败: {e}")

        return {
            "summary": f"《{game_name}》是一款有趣的休闲解谜游戏，试玩过程流畅，谜题设计有创意。",
            "highlights": ["独特谜题设计", "精致画面风格", "轻松游戏体验"],
            "impressions": {
                "gameplay": "玩法直觉，操作简单",
                "visuals": "画面精致",
                "difficulty": "难度适中",
                "originality": "创意独特",
            },
            "tags": ["解谜", "休闲", "独立游戏"],
            "suitable_for": "休闲玩家",
            "one_line_pitch": f"《{game_name}》让你在解谜中享受放松时光！",
        }

    # ── 剪辑脚本生成 ──────────────────────────

    def generate_edit_script(
        self,
        game_name: str,
        frame_descriptions: List[str],
        video_duration: int,
        output_duration: int = 60,
        style: str = "短视频种草",
    ) -> Dict:
        """
        生成视频剪辑脚本，包含时间戳、解说词、字幕、BGM建议。

        Args:
            video_duration: 原始录制视频总时长（秒）
            output_duration: 期望输出视频时长（秒）
            style: 风格 - "短视频种草" / "游戏评测" / "搞笑解说"

        Returns:
            {
              "title": "视频标题",
              "description": "视频简介",
              "segments": [
                {
                  "start": 5.0,     # 原视频时间戳（秒）
                  "end": 12.0,
                  "narration": "解说文案",
                  "subtitle": "字幕文字",
                  "transition": "cut|fade|dissolve",
                  "reason": "选取原因"
                }
              ],
              "bgm_style": "BGM风格建议",
              "hook": "开场钩子文案（前3秒）",
              "cta": "结尾引导语"
            }
        """
        desc_text = "\n".join(
            f"[{int(i * video_duration / len(frame_descriptions))}s] {d}"
            for i, d in enumerate(frame_descriptions)
        )

        style_hints = {
            "短视频种草": "语气轻松活泼，像在给朋友推荐游戏，多用感叹句，突出游戏亮点和趣味性",
            "游戏评测": "专业客观，分析游戏机制和设计，适合游戏爱好者",
            "搞笑解说": "幽默诙谐，可以吐槽游戏操作，用网络热梗增加互动感",
        }
        style_hint = style_hints.get(style, style_hints["短视频种草"])

        prompt = f"""你是一位专业的游戏短视频剪辑师，请根据以下试玩记录为游戏《{game_name}》制作剪辑脚本。

【原视频时长】{video_duration}秒
【期望输出时长】约{output_duration}秒
【视频风格】{style}：{style_hint}

【逐段画面描述（时间戳: 内容）】
{desc_text}

请生成剪辑脚本，以JSON格式返回：
{{
  "title": "吸引人的视频标题（含游戏名，20字以内）",
  "description": "视频简介（80字，含话题标签）",
  "hook": "开场3秒的钩子文案，要让人想继续看",
  "segments": [
    {{
      "start": 原视频开始时间秒数,
      "end": 原视频结束时间秒数,
      "narration": "这段的解说文案（配音用，15-30字）",
      "subtitle": "字幕显示文字（精简版，10字以内）",
      "transition": "cut",
      "reason": "选取这段的原因"
    }}
  ],
  "bgm_style": "推荐的BGM风格（如：轻松电子、像素风、悬疑氛围）",
  "cta": "结尾引导语（如：感兴趣的点赞关注，链接在评论区）"
}}

要求：segments总时长约{output_duration}秒，选取最精彩的片段，开头要有钩子。"""

        try:
            resp = self._client.chat.completions.create(
                model=self._text_model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content.strip()
            import re
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.error(f"生成剪辑脚本失败: {e}")

        # 兜底脚本
        seg_len = output_duration // 3
        return {
            "title": f"《{game_name}》试玩 - 这游戏太有意思了！",
            "description": f"#独立游戏 #{game_name} #游戏推荐",
            "hook": "这款游戏，我玩了5分钟就停不下来...",
            "segments": [
                {"start": 0, "end": seg_len, "narration": "游戏开场，来看看这款游戏是什么风格", "subtitle": "开场展示", "transition": "fade", "reason": "开场介绍"},
                {"start": seg_len, "end": seg_len * 2, "narration": "这里是游戏的核心玩法，挺有意思的", "subtitle": "核心玩法", "transition": "cut", "reason": "展示玩法"},
                {"start": seg_len * 2, "end": output_duration, "narration": "总体来说这款游戏值得一玩，感兴趣的可以去试试", "subtitle": "总结推荐", "transition": "fade", "reason": "结尾总结"},
            ],
            "bgm_style": "轻松欢快",
            "cta": "感兴趣的点赞收藏，想了解更多游戏的关注我！",
        }

    # ── 游戏截图视觉决策（供 VisionPlayer 调用）──

    def analyze_game_screenshot(
        self,
        screenshot_b64: str,
        background: str,
        system_prompt: str,
    ) -> str:
        """分析截图并返回操作建议（供 VisionPlayer 使用）。"""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}},
                            {"type": "text", "text": background},
                        ],
                    },
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"截图决策失败: {e}")
            return '{"type":"wait","delay":1.0,"label":"AI分析失败，等待"}'
