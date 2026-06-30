"""通义千问（DashScope）AI 客户端：翻译 & 改写。"""

import logging
import os
import re
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_qwen_client: OpenAI | None = None


def get_qwen_client() -> OpenAI:
    """懒加载通义千问客户端，使用 OpenAI 兼容接口。"""
    global _qwen_client
    if _qwen_client is not None:
        return _qwen_client

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "缺少环境变量 DASHSCOPE_API_KEY。\n"
            "请按 .env.example 配置：\n"
            "  Linux/macOS:  export DASHSCOPE_API_KEY=sk-xxxxxx\n"
            "  Windows PS :  $env:DASHSCOPE_API_KEY=\"sk-xxxxxx\"\n"
            "  或在项目根目录创建 .env 并装 python-dotenv 自动加载。"
        )

    _qwen_client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=120.0,
    )
    return _qwen_client


def translate_title_to_zh(title: str) -> Optional[str]:
    """使用通义千问将英文标题翻译为简体中文。"""
    if not title:
        return None
    try:
        client = get_qwen_client()
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的中英翻译助手。"
                        "请将用户提供的帖子标题翻译成自然流畅的简体中文，保持含义准确。"
                        "只输出翻译后的中文标题，不要添加任何解释或前后引号。"
                    ),
                },
                {"role": "user", "content": title},
            ],
            extra_body={"enable_thinking": False},
        )
        if not completion.choices or not completion.choices[0].message.content:
            return None
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("通义千问翻译标题失败: %s", e)
        return None


def generate_game_review(game_name: str, sources: list, user_opinion: str = "") -> str:
    """融合多来源游戏评测，生成专业评测文章。

    Args:
        game_name: 游戏名称
        sources: [{"source_name", "title", "url", "content"}]
        user_opinion: 用户自己的核心观点（可为空）
    """
    client = get_qwen_client()

    sources_text = ""
    for i, src in enumerate(sources, 1):
        name = src.get("source_name", "")
        title = src.get("title", "")
        content = (src.get("content") or "")[:1500]
        sources_text += f"\n【参考来源 {i}·{name}】{title}\n{content}\n"

    # 核心观点作为强约束写入 system，而非仅放在 user_text 末尾
    opinion_instruction = ""
    if user_opinion and user_opinion.strip():
        opinion_instruction = (
            f"\n【强制约束：作者核心观点】\n"
            f"{user_opinion.strip()}\n"
            "以上是作者本人的判断，必须作为文章的核心立场贯穿全文，"
            "尤其体现在「核心玩法」「局长结论」两节。"
            "不得与此观点矛盾，不得将其弱化为一句话带过。\n"
        )

    system_text = (
        f"你是「游戏雷达局」的游戏评测员，面向从未接触过「{game_name}」的游戏爱好者写评测。\n"
        "根据以下多个来源的评测内容，综合提炼并独立创作一篇游戏评测文章。\n"
        f"{opinion_instruction}\n"
        "写作要求：\n"
        "1. 内容必须重新创作，不能照抄原文\n"
        "2. 语言专业、简练、有观点，不废话，不套话，不用「总的来说」「不得不说」之类的过渡句\n"
        "3. 受众是没玩过这款游戏的玩家，需要先说清楚游戏是什么，再评价好坏\n"
        "4. 引用玩家或媒体评价时直接引用内容，不要出现「第X批评论」「据来源X」等内部标注\n"
        "5. 使用 Markdown 格式，结构如下：\n"
        "   # 【游戏评测】游戏名 — 一句核心评语（20字内，有观点，不是废话）\n"
        "   ## 🎮 这是一款什么游戏（50字内，类型+核心卖点+定位）\n"
        "   ## ⚔️ 核心玩法（重点机制、体验节奏、与同类游戏的差异）\n"
        "   ## 🌟 值得称道的地方（3-5条，说清楚为什么好，不只是列举）\n"
        "   ## 💢 不能回避的问题（2-3条，区分硬伤和遗憾，诚实评价）\n"
        "   ## 🎯 局长结论（明确给出「买」「等打折」「不买」+ 适合/不适合什么人，不模棱两可）\n"
        "   *—— 游戏雷达局，今日情报已送达*\n"
        "6. 全文约600-900字，各节精炼，不注水\n"
    )

    user_text = f"游戏名：{game_name}\n\n以下是参考的多篇评测内容：\n{sources_text}"

    completion = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user",   "content": user_text},
        ],
        extra_body={"enable_thinking": False},
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("AI 未返回有效内容")
    return completion.choices[0].message.content.strip()


def generate_reddit_summary(post: dict, comments: list) -> tuple:
    """根据 Reddit 帖子和高赞评论，生成小红书发布文案。

    Returns:
        (title, content)  title ≤ 20字
    """
    client = get_qwen_client()

    subreddit    = post.get("subreddit", "")
    post_title   = post.get("title", "")
    post_title_zh = post.get("title_zh") or post_title

    comments_text = ""
    for i, c in enumerate(comments[:10], 1):
        score = c.get("score", 0)
        score_str = f"{score/1000:.1f}k" if score >= 1000 else str(score)
        body_zh = c.get("body_zh") or c.get("body") or ""
        comments_text += f"{i}. u/{c.get('author', '')}（⬆{score_str}）：{body_zh}\n"

    system_text = (
        "你是「游戏雷达局」的运营者，擅长将海外玩家热议内容改写为小红书爆款文案。\n"
        "根据 Reddit 热帖信息和高赞评论，生成一篇小红书帖子文案，要求：\n"
        "1. 第一行是标题：不超过20字，格式「【reddit热帖】...」，吸引眼球\n"
        "2. 空一行后是正文：介绍讨论背景（1-2句）→ 精选3-5条最有趣/有代表性的中文评论引用 → 结尾署名\n"
        "3. 语气：接地气、有梗、适合小红书，引用评论时加引号\n"
        "4. 结尾固定为：*—— 游戏雷达局，今日资讯已送达*\n"
        "只输出标题和正文，不要任何额外说明。"
    )
    user_text = (
        f"帖子来自 r/{subreddit}\n"
        f"原标题：{post_title}\n"
        f"中文标题：{post_title_zh}\n\n"
        f"高赞评论（中文翻译）：\n{comments_text}"
    )

    completion = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user",   "content": user_text},
        ],
        extra_body={"enable_thinking": False},
    )
    raw = (completion.choices[0].message.content or "").strip()

    lines = raw.split("\n", 1)
    title   = lines[0].strip().lstrip("# ").strip()[:20]
    content = lines[1].strip() if len(lines) > 1 else ""
    return title, content


def analyze_reddit_screenshot(image_data: str) -> list:
    """使用 Qwen-VL 分析 Reddit 截图，提取并翻译所有评论文字，同时返回垂直位置（百分比）。

    Args:
        image_data: base64 data URL (data:image/...;base64,...)

    Returns:
        [{"english": "原文", "chinese": "译文", "y_start": 10, "y_end": 25}]
        y_start/y_end 为文字块在图片中从上到下的百分比位置（0~100）。
    """
    client = get_qwen_client()
    completion = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data}},
                    {
                        "type": "text",
                        "text": (
                            "这是一张 Reddit 截图，可能包含帖子标题、帖子正文、多条评论。\n"
                            "请按从上到下的顺序，将图中所有可见文字（帖子标题、帖子正文、每一条评论）"
                            "全部提取并翻译成简体中文。"
                            "每一条评论都必须单独输出，不得遗漏、合并或跳过任何一条，"
                            "输出的评论数量必须与截图中实际显示的评论数量完全一致。\n\n"
                            "每块文字严格按如下格式输出，块之间用 --- 分隔：\n"
                            "类型：[post_title / post_body / comment]\n"
                            "原文：[该文字块完整原文]\n"
                            "译文：[流畅自然的简体中文翻译]\n"
                            "位置：[开始%]-[结束%]\n"
                            "---\n\n"
                            "规则：\n"
                            "1. 跳过用户名、点赞数、时间戳、按钮、子版块名等界面装饰元素\n"
                            "2. 每条评论单独一个块，绝对不能与其他评论合并\n"
                            "3. 位置填写该文字块在图片总高度中的垂直范围（百分比），如 '5-18'\n"
                            "4. 如图中完全没有可识别文字，只输出：无内容"
                        ),
                    },
                ],
            }
        ],
        extra_body={"enable_thinking": False},
    )
    raw = (completion.choices[0].message.content or "").strip()
    if not raw or raw in ("无内容", "无评论"):
        return []

    blocks = []
    for block in raw.split("---"):
        block = block.strip()
        if not block or block in ("无内容", "无评论"):
            continue
        block_type, english, chinese = "comment", "", ""
        y_start, y_end = None, None          # None = AI 未返回位置，前端均分
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("类型："):
                block_type = line[3:].strip()
            elif line.startswith("原文："):
                english = line[3:].strip()
            elif line.startswith("译文："):
                chinese = line[3:].strip()
            elif line.startswith("位置："):
                pos = line[3:].strip().rstrip('%')
                if '-' in pos:
                    parts = pos.split('-')
                    try:
                        y_start = float(parts[0].strip().rstrip('%'))
                        y_end   = float(parts[1].strip().rstrip('%'))
                    except ValueError:
                        pass
        if english or chinese:
            blocks.append({
                "type":    block_type,          # post_title / post_body / comment
                "english": english or chinese,
                "chinese": chinese or english,
                "y_start": y_start,             # None 表示未知
                "y_end":   y_end,
            })
    return blocks


def batch_translate_to_zh(texts: list) -> list:
    """批量将英文文本翻译为简体中文，单次 API 调用，按序返回。失败时返回原文列表。"""
    if not texts:
        return []
    try:
        client = get_qwen_client()
        # 换行符替换为空格，避免破坏编号格式
        numbered = "\n".join(f"{i+1}. {t.replace(chr(10), ' ')}" for i, t in enumerate(texts))
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是专业中英翻译助手。用户给你一组带编号的英文文本，"
                        "请将每条翻译成自然流畅的简体中文。"
                        "输出格式：每条翻译一行，以相同序号开头，例如：\n"
                        "1. 翻译内容\n2. 翻译内容\n"
                        "不要添加任何额外说明。"
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            extra_body={"enable_thinking": False},
        )
        raw = (completion.choices[0].message.content or "").strip()
        result = []
        for line in raw.splitlines():
            m = re.match(r"^\d+\.\s*(.+)", line.strip())
            if m:
                result.append(m.group(1).strip())
        if len(result) == len(texts):
            return result
        # 解析数量对不上时逐条兜底
        return [translate_title_to_zh(t) or t for t in texts]
    except Exception as e:
        logger.warning("批量翻译失败: %s", e)
        return texts


def summarize_review_batch(game_name: str, reviews: list, batch_idx: int = 0) -> str:
    """对一批（~100 条）Steam 评论提炼好评/差评主题，输出极度紧凑的摘要文本。"""
    client = get_qwen_client()

    pos = [r for r in reviews if r.get("voted_up")]
    neg = [r for r in reviews if not r.get("voted_up")]

    lines = []
    for r in pos[:60]:
        lines.append(f"[好|{r.get('playtime_h', 0)}h] {r.get('text', '')[:120]}")
    for r in neg[:40]:
        lines.append(f"[差|{r.get('playtime_h', 0)}h] {r.get('text', '')[:120]}")

    system = (
        f"你在分析游戏「{game_name}」的一批 Steam 玩家评论（批次 {batch_idx + 1}）。\n"
        "请极度简洁地提炼本批次的核心信息，总输出不超过 350 字，格式：\n"
        "好评主题：[主题1] / [主题2] / [主题3]（每个主题15字内）\n"
        "差评主题：[槽点1] / [槽点2]（每个15字内，无差评则写'无'）\n"
        "好评代表原话：[一句最典型的好评，50字内]\n"
        "差评代表原话：[一句最典型的差评，50字内，无则写'无']\n"
        "玩时分布特点：[轻度/深度玩家的明显差异，如有的话，否则写'无明显差异']"
    )
    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": "\n".join(lines)},
            ],
            extra_body={"enable_thinking": False},
            max_tokens=500,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("评论批次 %d 摘要失败: %s", batch_idx, e)
        return ""


def generate_deep_review(
    game_name: str,
    steam_stats: str,
    batch_summaries: list,
    media_sources: list,
    user_opinion: str = "",
) -> str:
    """融合 Steam 全量批次摘要 + 统计数据 + 媒体来源，生成 2500-4000 字深度长文评测。

    Args:
        steam_stats:     纯统计数据块（好评率、玩时分布等）
        batch_summaries: 每批 100 条评论的 AI 摘要列表（全量评论分批处理后汇总）
        media_sources:   游戏媒体评测来源列表
    """
    client = get_qwen_client()

    media_text = ""
    for i, src in enumerate(media_sources[:8], 1):
        name    = src.get("source_name", "")
        title   = src.get("title", "")
        content = (src.get("content") or "")[:1200]
        media_text += f"\n【媒体来源 {i}·{name}】{title}\n{content}\n"

    opinion_block = ""
    if user_opinion and user_opinion.strip():
        opinion_block = f"\n【作者核心观点】\n{user_opinion.strip()}\n请务必将此观点融入文章，作为重要视角。\n"

    # 合并所有批次摘要（去掉"第X批"标注，避免泄露到输出）
    valid_summaries = [s for s in batch_summaries if s]
    summaries_text  = "\n---\n".join(
        f"[评论摘要 {i+1}/{len(batch_summaries)}]\n{s}" for i, s in enumerate(batch_summaries) if s
    )

    # 核心观点强约束
    opinion_instruction = ""
    if user_opinion and user_opinion.strip():
        opinion_instruction = (
            f"\n【强制约束：作者核心观点】\n"
            f"{user_opinion.strip()}\n"
            "以上是作者本人的判断，必须作为文章的核心立场贯穿全文，"
            "尤其体现在「核心玩法」「局长最终判决」两节，不得弱化或与之矛盾。\n"
        )

    system_text = (
        f"你是「游戏雷达局」的首席评测员，面向从未接触过「{game_name}」的游戏爱好者写深度评测。\n"
        "你的任务是创作一篇**独创观点**的深度长评，而不是汇总玩家意见的摘要文章。\n"
        f"{opinion_instruction}\n"
        "你将获得：\n"
        "① Steam 统计数据（好评率、玩时分布等）\n"
        "② Steam 全量评论的 AI 摘要（多批次玩家反馈提炼）\n"
        "③ 游戏媒体评测参考\n\n"
        "【写作原则（极重要）】\n"
        "- 受众是没玩过这款游戏的玩家，先说清楚游戏是什么，再深入评价\n"
        "- 每个论点先给出你的判断，再用数据或评论佐证，不要反过来\n"
        "- 引用玩家评论时直接引用内容，不要出现「第X批」「某批次」等内部词汇\n"
        "- 允许提出争议性判断，不做墙头草，不模棱两可\n"
        "- 多用第一人称「我」或「局长」，体现个人立场\n"
        "- 不用「总的来说」「不得不说」「值得一提的是」等套话过渡句\n\n"
        "输出格式（Markdown，严格按各节参考字数）：\n\n"
        f"# 【深度评测】{game_name} — [你自己的核心评语，20字内，有观点]\n\n"
        "## 📊 数据一览（约100字）\n"
        "评价等级、好评率、总评论数、分析样本量，直接引用数字\n\n"
        f"## 🎮 {game_name}是什么（约150字）\n"
        "类型、核心卖点、在同类游戏中的定位，给没玩过的人讲清楚\n\n"
        "## ⚔️ 核心玩法——我的判断（约600字）\n"
        "对核心机制的评价：哪里设计精妙、哪里妥协、哪里是行业通病；用玩家反馈佐证判断\n\n"
        "## 🌟 真正值得称道的地方（约500字）\n"
        "3-4个亮点，说清楚为什么好、这设计为什么成立，不只是列举「玩家好评」\n\n"
        "## 💢 不能回避的问题（约400字）\n"
        "2-3个槽点，区分「设计失误」vs「取舍带来的遗憾」，给出你自己的判断\n\n"
        "## 📰 媒体 vs 玩家：谁说得更准（约300字）\n"
        "比较媒体评测与玩家口碑的异同，指出哪方更接近真实体验\n\n"
        "## 👥 谁应该玩，谁应该跳过（约200字）\n"
        "基于玩时分布和受众画像给出精准判断，点名具体受众，不笼统\n\n"
        "## 🎯 局长最终判决（约200字）\n"
        "明确给出「买」「等打折」「不买」+ 具体理由，不含糊\n\n"
        "*—— 游戏雷达局，今日情报已送达*\n\n"
        "额外要求：\n"
        "- 全文目标 2500-4000 字，各节按参考字数，不注水\n"
        "- 数据必须引用（直接写好评率数字、样本量）\n"
        "- 语言生动有力，避免套话"
    )

    user_text = (
        f"游戏名：{game_name}\n"
        f"=== Steam 统计数据 ===\n{steam_stats}\n\n"
        f"=== Steam 全量评论摘要（共 {len(valid_summaries)} 批） ===\n{summaries_text}\n\n"
        f"=== 游戏媒体评测 ===\n{media_text if media_text else '（暂无媒体来源，请仅基于 Steam 数据生成）'}"
    )

    completion = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user",   "content": user_text},
        ],
        extra_body={"enable_thinking": False},
        max_tokens=4096,
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("AI 未返回有效内容")
    return completion.choices[0].message.content.strip()


def analyze_steam_reviews(game_name: str, review_block: str) -> str:
    """对 Steam 评论样本进行深度 AI 分析，生成结构化玩家口碑报告。"""
    client = get_qwen_client()
    system_text = (
        "你是「游戏雷达局」的数据分析师，专门分析 Steam 玩家口碑。\n"
        "根据提供的 Steam 评论数据（含好评率、玩时分布、代表性好评/差评），"
        "生成一份权威、客观的玩家口碑分析报告。\n\n"
        "输出格式（Markdown）：\n"
        "### 🗳️ 玩家口碑总结\n"
        "（1-2句概括整体口碑，含好评率数据和评价级别）\n\n"
        "### ✅ 玩家一致好评的点\n"
        "（3-5条，提炼多条好评的共同主题，用 - 列举；如有深度玩家认可请注明）\n\n"
        "### ❌ 玩家集中吐槽的点\n"
        "（2-4条，提炼差评的共同主题，用 - 列举；区分严重问题与轻微缺点）\n\n"
        "### 👥 受众画像\n"
        "（根据玩时分布和评论内容，描述：什么类型玩家最买单、什么人容易失望）\n\n"
        "### 📊 局长口碑结论\n"
        "（1句话，直接给出是否值得买的结论，不模棱两可）\n\n"
        "要求：客观准确，基于数据说话，不捏造内容，语气参考游戏雷达局风格。"
    )
    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user",   "content": f"游戏名：{game_name}\n\n{review_block}"},
            ],
            extra_body={"enable_thinking": False},
        )
        if not completion.choices or not completion.choices[0].message.content:
            return review_block
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Steam 评论 AI 分析失败: %s", e)
        return review_block


def rank_trending_items(items: list) -> list:
    """对内容列表进行 AI 传播潜力精排，返回排序后的列表（每条附 ai_reason 字段）。

    只应在用户主动点击"AI 精排"时调用，会消耗 API。
    输入：最多 20 条已有 trending_score 的 item
    输出：按传播潜力排序，每条新增 ai_reason 字段
    """
    import json as _json

    if not items:
        return items

    # 只取前 20 条，构造简洁摘要
    candidates = items[:20]
    summaries = []
    for i, it in enumerate(candidates):
        summaries.append({
            "idx": i,
            "title": (it.get("title") or "")[:80],
            "source": it.get("source") or "",
            "label": it.get("label") or "",
            "score": it.get("trending_score") or 0,
            "reason": it.get("trending_reason") or "",
            "snippet": (it.get("content") or it.get("summary") or "")[:120],
        })

    system_text = (
        "你是小红书游戏账号「游戏雷达局」的内容策划，精通游戏圈热点。\n"
        "你的任务：从以下游戏内容列表中，选出最有可能在小红书获得高流量的 5 条，\n"
        "按传播潜力从高到低排列，并给每条写一句简短的推荐理由（15字以内）。\n\n"
        "评判维度：\n"
        "1. 小红书用户兴趣（二次元、手游、折扣、新奇事件优先）\n"
        "2. 话题热度（是否正在破圈、是否有讨论度）\n"
        "3. 内容稀缺性（独家/首发/限定优先）\n"
        "4. 情感共鸣（让人有「转发冲动」的内容）\n\n"
        "以 JSON 格式输出，严格遵守 schema：\n"
        '[{"idx": 原始序号, "ai_reason": "推荐理由"}, ...]'
        "\n只输出 JSON 数组，不要其他内容。"
    )

    user_text = "内容列表：\n" + _json.dumps(summaries, ensure_ascii=False, indent=2)

    client = get_qwen_client()
    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            extra_body={"enable_thinking": False},
        )
        raw = (completion.choices[0].message.content or "").strip()
        import re as _re
        fence = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if fence:
            raw = fence.group(1).strip()
        ranked = _json.loads(raw)
    except Exception as e:
        logger.error("rank_trending_items AI 精排失败: %s", e)
        # 降级：原顺序返回，没有 ai_reason
        for it in candidates:
            it.setdefault("ai_reason", "")
        return candidates

    # 按 AI 返回顺序重排，附 ai_reason
    idx_to_reason = {r["idx"]: r.get("ai_reason", "") for r in ranked if "idx" in r}
    result = []
    for r in ranked:
        idx = r.get("idx")
        if idx is not None and 0 <= idx < len(candidates):
            it = candidates[idx]
            it["ai_reason"] = idx_to_reason.get(idx, "")
            result.append(it)

    return result


def generate_anime_xhs_post(item: dict, style: str = "general_anime") -> tuple:
    """根据二次元/女性向内容，生成小红书风格文案。

    Args:
        item: 内容条目，含 title/content/source 等字段
        style: 人设风格，可选 otome / gacha / indie / general_anime

    Returns:
        (title, body)  title <= 20字
    """
    STYLES = {
        "otome": {
            "persona": (
                "你是「攻略组」的核心成员，一个深爱乙女游戏和女性向手游的玩家，温柔有观点、有态度。"
                "自称'攻略组'，把粉丝称为'小伙伴们'。"
                "开头必须是：攻略组来啦~\n结尾必须是：—— 攻略组已送达，期待与你同行 🌸"
            ),
            "tone": "语气温柔亲切，带一点少女心，可以加 🌸💕🎀 等女性向 emoji，但不过度堆砌。",
        },
        "gacha": {
            "persona": (
                "你是「氪金局」的酋长，一个在手游界打滚多年、见识广泛的老玩家，接地气有梗。"
                "自称'酋长'，把粉丝称为'打工人们'。"
                "开头必须是：今日爆料🎰\n结尾必须是：—— 酋长今天也没出金，继续打工 💀"
            ),
            "tone": "语气接地气，充满自嘲和梗，可以加 😭🎰💸 等 emoji，风格幽默不严肃。",
        },
        "indie": {
            "persona": (
                "你是「独立游戏雷达」的编辑，真诚热爱小众和国产独立游戏，有温度有深度。"
                "自称'雷达君'，把粉丝称为'游戏爱好者'。"
                "开头必须是：发现一款宝藏游戏🔍\n结尾必须是：—— 宝藏游戏，已安利给你 ✨"
            ),
            "tone": "语气真诚有温度，像朋友推荐好东西，不夸张，信息准确。",
        },
        "general_anime": {
            "persona": (
                "你是「游戏雷达局」的二次元情报官，活泼开朗，对动漫游戏充满热情。"
                "自称'情报官'，把粉丝称为'二次元的同学们'。"
                "开头必须是：二次元情报来了！\n结尾必须是：—— 游戏雷达局，今日情报已送达 🎮"
            ),
            "tone": "语气活泼有感情，可以加动漫相关 emoji，充满热情但信息准确。",
        },
    }

    style_cfg = STYLES.get(style, STYLES["general_anime"])

    source_title = item.get("title") or ""
    source_content = item.get("content") or ""
    source_game = item.get("game") or item.get("topic") or item.get("label") or ""
    source_url = item.get("url") or ""

    system_text = (
        f"{style_cfg['persona']}\n\n"
        f"语气要求：{style_cfg['tone']}\n\n"
        "根据以下游戏资讯，生成一篇小红书帖子。要求：\n"
        "1. 第一行是标题：不超过20字，吸引眼球，与人设风格匹配\n"
        "2. 空一行后是正文：150-300字\n"
        "   - 引入背景（1-2句）\n"
        "   - 核心内容介绍（2-4句，用自己的语言，不直接复制）\n"
        "   - 结合人设的个人观点或推荐理由（1-2句）\n"
        "   - 结尾固定语（使用上面要求的结尾）\n"
        "3. 正文末尾换行，附 3-5 个话题标签，格式：#话题名\n"
        "只输出标题和正文，不要任何额外说明。"
    )

    user_text = (
        f"游戏/话题：{source_game}\n"
        f"标题：{source_title}\n"
        f"内容：{source_content[:600]}\n"
    )
    if source_url:
        user_text += f"来源：{source_url}\n"

    client = get_qwen_client()
    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            extra_body={"enable_thinking": False},
        )
        text = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("generate_anime_xhs_post 失败: %s", e)
        raise

    lines = text.split("\n")
    title = lines[0].lstrip("#").strip() if lines else source_title[:20]
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
    return title[:20], body


def generate_video_script(game_name: str, content: str, duration_secs: int = 60) -> dict:
    """根据游戏名和内容文案，生成视频脚本（JSON格式）。

    Returns:
        {
          "title": "...",
          "segments": [{"text": "旁白", "duration": 15, "subtitle": "字幕", "scene": "画面建议"}],
          "tags": ["#话题1#", "#话题2#"]
        }
    """
    import json

    system_text = (
        "你是「游戏雷达局」的视频策划，擅长将游戏资讯改写为适合小红书/抖音竖屏短视频的脚本。\n"
        "请根据提供的游戏资讯，生成一个短视频脚本，以 JSON 格式输出，严格遵守以下 schema：\n"
        "{\n"
        '  "title": "视频标题（20字以内，吸引人）",\n'
        '  "segments": [\n'
        '    {"text": "旁白文案（播音员读出的内容，自然流畅）", "duration": 数字（秒）, '
        '"subtitle": "屏幕底部字幕（与旁白相同或精简版）", "scene": "画面内容建议"}\n'
        "  ],\n"
        '  "tags": ["#话题标签1#", "#话题标签2#", "#话题标签3#"]\n'
        "}\n"
        "要求：\n"
        f"1. 视频总时长约 {duration_secs} 秒，segments 数量 3-6 段，每段 duration 加总等于总时长\n"
        "2. 旁白自然流畅，像真人播报资讯，不生硬\n"
        "3. 字幕是旁白的精简版，不超过20字\n"
        "4. 只输出 JSON，不要任何额外说明或 markdown 代码块"
    )

    user_text = f"游戏名：{game_name}\n\n资讯内容：\n{content[:800]}"

    client = get_qwen_client()
    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            extra_body={"enable_thinking": False},
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Strip markdown code fences like ```json ... ``` or ``` ... ```
        import re as _re
        _fence = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if _fence:
            raw = _fence.group(1).strip()
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("视频脚本 JSON 解析失败: %s，返回默认结构", e)
        result = {
            "title": f"{game_name}资讯速报",
            "segments": [
                {"text": content[:100], "duration": duration_secs, "subtitle": f"{game_name}资讯", "scene": "游戏画面"},
            ],
            "tags": [f"#{game_name}#", "#手游资讯#", "#游戏雷达局#"],
        }
    except Exception as e:
        logger.error("generate_video_script 失败: %s", e)
        raise

    return result


def analyze_rank_anomaly(app_name: str, region: str, chart: str, change: str, rank: int,
                          related_news: list = None) -> str:
    """
    分析单个榜单异动游戏的原因。

    优先从 related_news 中找答案；若无相关新闻，则使用联网搜索。

    Args:
        app_name:     游戏名
        region:       地区，如 "中国大陆"
        chart:        榜单类型，如 "免费榜"
        change:       变化，如 "↑22"
        rank:         当前排名
        related_news: 本次已抓取的新闻中与该游戏相关的条目

    Returns:
        原因分析字符串（50-100字）
    """
    client = get_qwen_client()

    # 构建上下文
    news_context = ""
    if related_news:
        for item in related_news[:3]:
            news_context += f"- {item.get('title','')}: {(item.get('content','') or '')[:200]}\n"

    if news_context:
        prompt = (
            f"《{app_name}》本周在{region}{chart}排名{change}，现排第{rank}名。\n"
            f"以下是本周相关新闻：\n{news_context}\n"
            f"请根据以上新闻，用50字以内解释排名变化的原因。直接给出分析，不要套话。"
        )
        enable_search = False
    else:
        prompt = (
            f"《{app_name}》本周在{region}{chart}排名{change}，现排第{rank}名。"
            f"请搜索分析最近该游戏排名大幅变化的原因，用50字以内简洁说明。直接给出分析结论。"
        )
        enable_search = True

    try:
        completion = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system", "content": "你是游戏行业数据分析师，分析榜单异动原因，言简意赅。"},
                {"role": "user", "content": prompt},
            ],
            extra_body={"enable_thinking": False, "enable_search": enable_search},
            max_tokens=200,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("异动分析失败 %s: %s", app_name, e)
        return ""


def analyze_rank_anomalies_batch(anomalies: list, all_news: list = None) -> list:
    """
    批量分析榜单异动原因。

    Args:
        anomalies:  [{"app", "region", "chart", "change", "rank"}, ...]
        all_news:   所有已抓取的新闻条目（用于匹配相关新闻）

    Returns:
        [{"app": ..., "reason": ...}, ...]
    """
    import concurrent.futures

    all_news = all_news or []

    def _analyze_one(a):
        app_name = a.get("app", "")
        # 从新闻中找相关内容（按游戏名匹配标题）
        related = [n for n in all_news if app_name in n.get("title", "")]
        reason = analyze_rank_anomaly(
            app_name=app_name,
            region=a.get("region", ""),
            chart=a.get("chart", ""),
            change=a.get("change", ""),
            rank=a.get("rank", 0),
            related_news=related,
        )
        return {"app": app_name, "reason": reason}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_analyze_one, a) for a in anomalies[:8]]
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                logger.error("异动批量分析子任务失败: %s", e)

    return results


def generate_weekly_report_article(
    news_items: list,
    rank_data: dict,
    week_label: str = "",
    excel_anomalies: list = None,
) -> str:
    """
    根据筛选出的新闻条目 + 榜单数据，生成游戏行业周报长文（公众号风格）。

    Args:
        news_items: 已人工挑选的新闻列表，每条 {title, content, url, channel}
        rank_data:  fetch_multi_region_ranks() 返回的榜单数据
        week_label: 周报标识，如 "2026-W10"
        excel_anomalies: fetch_weekly_rank_excel() 返回的七天异动列表
                         [{"app", "region", "chart", "change", "rank"}, ...]

    Returns:
        Markdown 格式的周报全文
    """
    client = get_qwen_client()

    # 构建新闻部分
    news_block = ""
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        content = (item.get("content") or "")[:600]
        channel = item.get("channel", "")
        news_block += f"\n【新闻{i}】来源：{channel}\n标题：{title}\n内容：{content}\n"

    # 构建榜单摘要
    rank_block = ""
    region_names = {"cn": "中国大陆", "hk": "中国香港", "tw": "中国台湾",
                    "us": "美国", "jp": "日本", "kr": "韩国"}
    for country, cname in region_names.items():
        if country not in rank_data:
            continue
        region_data = rank_data[country]
        for chart_type, chart_name in [("free", "免费榜"), ("grossing", "畅销榜")]:
            if chart_type not in region_data:
                continue
            chart = region_data[chart_type]
            items = chart.get("items", [])[:10]
            if not items:
                continue
            tops = ", ".join(f"#{it['rank']}{it['app_name']}" for it in items[:5])
            rank_block += f"{cname}{chart_name}TOP5：{tops}\n"

    # 异动摘要（合并今日榜单异动 + 七天Excel异动）
    anomalies = rank_data.get("anomalies", [])
    anomaly_block = ""
    if anomalies:
        for a in anomalies[:10]:
            anomaly_block += f"- {a['region']} {a['chart']}：《{a['app']}》{a['change']}，现排名#{a['rank']}\n"

    # 七天涨幅异动（来自 Excel 抓取，更准确的7天对比）
    excel_anomaly_block = ""
    if excel_anomalies:
        # 按 change 排序：★新上榜 > ↑N（降序）
        def _sort_key(a):
            c = a.get("change", "")
            if c == "★新上榜":
                return 9999
            if c.startswith("↑"):
                try: return int(c[1:])
                except: return 0
            return 0
        sorted_ea = sorted(excel_anomalies, key=_sort_key, reverse=True)
        for a in sorted_ea[:15]:
            excel_anomaly_block += f"- {a['region']} {a['chart']}：《{a['app']}》{a['change']}（当前排名第{a['rank']}）\n"

    system_text = (
        "你是一个在小红书上运营游戏行业观察账号的博主，账号名「游戏雷达局」。\n"
        "你的定位：稍专业但不晦涩——懂行的人觉得有料，不懂行的人也能读懂、感兴趣。\n"
        "语气像一个真正懂游戏的朋友在给你讲这周发生了什么，有观点、有态度，不只是播报。\n\n"
        "请根据本周游戏新闻和榜单数据，撰写一篇小红书风格的游戏行业周报。\n\n"
        "━━━ 结构要求 ━━━\n\n"
        f"# 🎮 游戏周报｜{week_label}\n\n"
        "开头写 1-2 句吸引人的导语（可用 emoji，点出本周最有看头的 1-2 件事，让人想继续读）。\n\n"
        "## 📰 本周大事件\n"
        "将提供的新闻整理为 6-8 条大事件，每条格式：\n"
        "### [emoji] 标题（20字以内，点出核心，可带情绪色彩）\n"
        "正文 150-250 字：先说清楚发生了什么（1-2句），然后给出你的观点或分析，\n"
        "关键数据必须保留，用**加粗**强调核心信息。\n"
        "每条结尾可选加一句「> 划重点：xxx」或「> 💡 xxx」作为金句提炼（不强制每条都加）。\n\n"
        "## 📊 本周榜单看点\n"
        "基于提供的七天榜单数据，分析 2-3 个有趣现象或值得关注的异动，\n"
        "不要逐条罗列所有榜单，而是挑重点讲：\n"
        "- 哪些游戏异军突起？可能原因是什么？\n"
        "- 哪些地区有特别的榜单现象？\n"
        "- 国产游戏表现如何？\n"
        "150-250 字，有自己的判断。\n\n"
        "结尾写 1-2 句本周总结或对下周的展望，轻松收尾。\n\n"
        "━━━ 写作规范 ━━━\n"
        "1. emoji 自然穿插，不要每句话都加，每个标题一个就够\n"
        "2. 口语化但不低俗，像朋友聊天，不像论文也不像公关稿\n"
        "3. 有观点敢说话，遇到争议话题可以明确表态\n"
        "4. 关键数据必须保留（如具体金额、排名、百分比）\n"
        "5. 不要写来源链接或网址\n"
        "6. 全文 1500-2200 字，Markdown 格式\n"
    )

    user_text = (
        f"本周新闻（共{len(news_items)}条，请全部纳入分析）：\n{news_block}\n\n"
        f"本周各地区榜单 TOP5（3月15日快照）：\n{rank_block}\n\n"
        f"今日榜单异动（当日对比上周变化）：\n{anomaly_block if anomaly_block else '暂无'}\n\n"
        f"七天榜单异动（3月9日→3月15日，上升≥3名或新上榜，请在「本周榜单看点」板块中重点分析）：\n"
        f"{excel_anomaly_block if excel_anomaly_block else '暂无七天涨幅数据'}\n"
    )

    completion = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        extra_body={"enable_thinking": False},
        max_tokens=4096,
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("AI 未返回有效内容")
    article = completion.choices[0].message.content.strip()

    # 在文章末尾追加真实榜单表格
    table_block = _build_rank_tables(rank_data)
    if table_block:
        article += "\n\n" + table_block

    return article


def _build_rank_tables(rank_data: dict) -> str:
    """将榜单数据转换为 Markdown 表格，追加到周报末尾。"""
    if not rank_data:
        return ""
    region_names = {
        "cn": "🇨🇳 中国大陆", "hk": "🇭🇰 中国香港", "tw": "🇹🇼 中国台湾",
        "us": "🇺🇸 美国",     "jp": "🇯🇵 日本",     "kr": "🇰🇷 韩国",
        "gb": "🇬🇧 英国",     "de": "🇩🇪 德国",     "fr": "🇫🇷 法国",
        "sg": "🇸🇬 新加坡",   "th": "🇹🇭 泰国",     "sa": "🇸🇦 沙特",
        "tr": "🇹🇷 土耳其",   "br": "🇧🇷 巴西",     "in": "🇮🇳 印度",
    }
    chart_names = {"free": "免费榜", "grossing": "畅销榜"}
    lines = ["## 📋 附：本周各地区榜单数据\n"]
    for country, cname in region_names.items():
        if country not in rank_data:
            continue
        region_data = rank_data[country]
        for chart_type, chart_name in chart_names.items():
            chart = region_data.get(chart_type, {})
            items = chart.get("items", [])
            if not items:
                continue
            lines.append(f"### {cname} · {chart_name} TOP10\n")
            lines.append("| 排名 | 游戏名称 | 涨跌 | 上周排名 |")
            lines.append("|:---:|:---|:---:|:---:|")
            for it in items:
                change = it.get("change", "-")
                last = it.get("last_rank", "-")
                lines.append(f"| {it['rank']} | {it['app_name']} | {change} | {last} |")
            lines.append("")
    return "\n".join(lines)


def generate_game_pitch(game_name: str, desc: str = "") -> str:
    """为折扣游戏生成 200 字以内的玩法推荐语（不提打折，纯从玩法角度推荐）。

    Args:
        game_name: 游戏名称（中文）
        desc: 游戏原始简介（可为空）
    Returns:
        200 字以内的推荐语字符串
    """
    client = get_qwen_client()
    system_text = (
        "你是一位资深游戏玩家，擅长用简短生动的文字推荐游戏。\n"
        "请根据游戏名称和简介，写一段 200 字以内的游戏推荐语，要求：\n"
        "1. 从玩法、类型、乐趣点、适合人群等角度推荐，不要提打折、价格、免费等促销信息\n"
        "2. 语气像朋友安利游戏，生动有感染力，让人想立刻去玩\n"
        "3. 只输出推荐语正文，不加任何标题或前缀"
    )
    user_text = f"游戏名：{game_name}\n"
    if desc:
        user_text += f"游戏简介：{desc[:400]}\n"

    try:
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user",   "content": user_text},
            ],
            extra_body={"enable_thinking": False},
            max_tokens=300,
        )
        result = (completion.choices[0].message.content or "").strip()
        # 超出 200 字时截断到最近的句号
        if len(result) > 200:
            cut = result[:200].rfind("。")
            result = result[:cut + 1] if cut > 100 else result[:200]
        return result
    except Exception as e:
        logger.warning("游戏推荐语生成失败 (%s): %s", game_name, e)
        return desc[:200] if desc else ""


def rewrite_content(
    prompt: str,
    tone: str,
    original: str,
    extra_sources: Optional[list] = None,
    mode: str = "text",
) -> str:
    """调用通义千问，对原文进行改写。返回改写后的文本，失败则抛异常。

    Args:
        extra_sources: 额外参考来源列表，格式 [{"title", "url", "content"}]。
                       提供时 AI 会融合多来源视角，降低与原文重合率。
        mode: 'text'（小红书图文，Markdown 格式）或 'video'（口播脚本，纯文本）。
    """

    if mode == "video":
        # 视频脚本模式：直接用前端传来的 prompt 作为 system 指令，不叠加任何 Markdown 格式要求
        system_text = prompt if prompt else (
            "你是「游戏雷达局」的视频脚本撰写官。"
            "请将以下游戏资讯改写为适合短视频口播的脚本，"
            "开头用一句引人注目的口头禅切入，"
            "中间完整覆盖原文所有信息点（包括信息来源、具体数据、未经证实的内容也要如实交代），用口语化表达每句不超过25字，"
            "结尾固定以「游戏雷达局，情报已送达——」收尾。"
            "只输出脚本正文，不要标题，不要任何 Markdown 符号（#、**、- 等），不要额外说明。"
        )
    else:
        persona = """你是「游戏雷达局」的局长，一个对游戏有品味、有观点的游戏资讯自媒体运营者。
你的人设特点：
- 自称"局长"，把粉丝称为"情报局的同学们"
- 懂美学、懂剧情、懂玩家真正在意什么，不只是搬运资讯
- 口吻：有观点、不装、偶尔有梗，但信息永远准确
- 口头禅：开头常用"今天的情报，局长亲自带来"，结尾用"—— 游戏雷达局，今日情报已送达"
"""

        if not prompt:
            prompt = persona
        else:
            prompt = persona + "\n" + prompt

        if tone == "humor":
            tone_hint = (
                "语气偏活泼有梗，像局长在向线人通报情报，可以加入自己的吐槽和观点，"
                "但核心信息要准确，不要低俗。"
            )
        else:
            tone_hint = (
                "语气偏专业简报风，像发布一份精炼的情报文件，条理清晰，有自己的判断，"
                "不要太生硬，保留一点人情味。"
            )

        system_text = (
            f"{prompt}\n"
            f"语气风格要求：{tone_hint}\n"
            "请将非中文内容翻译成自然流畅的简体中文。\n"
            "输出格式要求（使用 Markdown）：\n"
            "1. 第一行写一个吸引人的封面标题，格式：# 【情报速报】XXX 或 # 【独家】XXX\n"
            "2. ## 局长说  —— 1-2句引入，用局长口吻点出这条情报的核心价值\n"
            "3. ## 关键情报  —— 用加粗 + 列表整理核心事实（时间/数据/官方说法等）\n"
            "4. ## 局长点评  —— 局长的主观判断：值不值得关注、玩家该怎么行动\n"
            "5. 最后一行固定为：*—— 游戏雷达局，今日情报已送达*\n"
            "不要输出任何多余解释，直接给出改写后的完整 Markdown 内容。"
        )

    # 构建用户消息：原文 + 可选多来源参考
    user_content = (
        "下面是需要改写的原文（包含标题和正文文本），"
        "请先整体理解其含义，再按上述要求进行改写：\n\n"
        f"{original}"
    )
    if extra_sources:
        user_content += (
            "\n\n---\n"
            "以下是从其他渠道找到的同一事件相关报道，供你参考融合，"
            "目的是提供更多细节与不同视角，请勿直接摘抄，要用自己的语言综合表达：\n"
        )
        for i, src in enumerate(extra_sources, 1):
            src_title = src.get("title") or ""
            src_url   = src.get("url")   or ""
            src_text  = (src.get("content") or "")[:800]
            user_content += f"\n【参考来源 {i}】{src_title}\n来源：{src_url}\n{src_text}\n"

    client = get_qwen_client()
    completion = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ],
        extra_body={"enable_thinking": False},
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("AI 未返回有效内容")
    return completion.choices[0].message.content.strip()


def fact_check_content(text: str) -> dict:
    """对改写后的文案进行事实核查。

    Returns:
        {
            "passed": bool,          # True = 无明显疑问，False = 存在待核实内容
            "issues": [              # 仅当 passed=False 时非空
                {
                    "claim": str,    # 有疑问的具体说法
                    "reason": str,   # 疑问原因
                    "suggestion": str,  # 建议核实方式或来源
                }
            ],
            "summary": str           # 一句话总结
        }
    """
    system_text = (
        "你是一位专业的游戏媒体事实核查编辑。\n"
        "你的任务是审查游戏自媒体文案中是否存在可能引发粉丝质疑的内容，包括但不限于：\n"
        "1. 未经证实的数据、销量、下载量、营收数字\n"
        "2. 模糊或夸大的比较（如「最强」「业界第一」「史无前例」）\n"
        "3. 未来事件被描述为已确定发生（如将「传闻」写成「已官宣」）\n"
        "4. 错误引用已知事实（版本号、发售日期、开发商归属等）\n"
        "5. 情绪化表述可能被误认为客观事实\n\n"
        "请以 JSON 格式返回结果，结构严格如下（不要输出 Markdown 代码块，直接输出纯 JSON）：\n"
        "{\n"
        '  "passed": true 或 false,\n'
        '  "issues": [\n'
        '    {"claim": "有疑问的原文片段", "reason": "疑问原因", "suggestion": "建议核实来源或方式"}\n'
        "  ],\n"
        '  "summary": "一句话总结核查结论"\n'
        "}\n"
        "如果文案内容基本可信、无明显事实风险，returned passed=true，issues=[]。\n"
        "只关注客观事实类问题，不评价文风或创意表达。"
    )

    client = get_qwen_client()
    completion = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": f"请核查以下文案：\n\n{text}"},
        ],
        extra_body={"enable_thinking": False},
    )
    raw = (completion.choices[0].message.content or "").strip()

    # 尝试解析 JSON，允许 AI 偶尔带 markdown 代码块
    import json as _json
    clean = raw.strip("` \n")
    if clean.startswith("json"):
        clean = clean[4:].strip()
    try:
        result = _json.loads(clean)
        # 规范化字段
        result.setdefault("passed", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        return result
    except Exception:
        # 解析失败时返回通过（保守降级）
        return {"passed": True, "issues": [], "summary": raw[:200] if raw else "核查完成，未发现明显问题。"}


def rewrite_news_item(
    title: str,
    original: str,
    extra_sources: Optional[list] = None,
) -> str:
    """将单条游戏资讯改写为专业简洁的资讯文章（无媒体人设，纯干货）。

    Args:
        title: 原始标题
        original: 原文正文或摘要
        extra_sources: 额外相关来源列表 [{"title", "url", "content"}]
    Returns:
        改写后的 Markdown 字符串（含 ## 标题行）
    """
    system_text = (
        "你是一名资深游戏行业记者，擅长将碎片化资讯改写为专业、简洁的中文资讯报道。\n"
        "改写要求：\n"
        "1. 输出格式：纯 Markdown，第一行为 ## 资讯标题（不要加来源名），正文段落清晰\n"
        "2. 【严格禁止】篡改任何事实性内容，包括：\n"
        "   - 年份、日期、时间不得修改（原文说2026年就是2026年，不能改成其他年份）\n"
        "   - 事件的确认状态不得改变（原文说'尚未确认'/'疑似'/'据悉'，改写后必须保持同样的不确定性，不能写成已确认的事实）\n"
        "   - 数字、百分比、金额、人名、游戏名、公司名不得修改\n"
        "   - 官方声明的措辞不得强化或弱化\n"
        "3. 语气：专业、客观、简洁，不带任何媒体人设或口头禅\n"
        "4. 字数：200~350字，不需要总结评论，事实优先\n"
        "5. 如有多个来源，请综合提炼，不能直接复制原文句子（降重）\n"
        "6. 不要出现任何媒体名称（如'据36kr报道'等），也不要出现改写者身份\n"
        "7. 只输出改写后的 Markdown，不加任何前后说明\n"
    )

    user_parts = [f"标题：{title}\n\n原文：\n{original[:1500]}"]
    if extra_sources:
        user_parts.append("\n\n---\n以下是同一事件的其他来源，请综合参考：")
        for i, src in enumerate(extra_sources, 1):
            src_title = src.get("title") or ""
            src_text = (src.get("content") or "")[:800]
            user_parts.append(f"\n【参考{i}】{src_title}\n{src_text}")

    client = get_qwen_client()
    completion = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": "".join(user_parts)},
        ],
        extra_body={"enable_thinking": False},
        max_tokens=600,
    )
    if not completion.choices or not completion.choices[0].message.content:
        raise RuntimeError("AI 未返回内容")
    return completion.choices[0].message.content.strip()
