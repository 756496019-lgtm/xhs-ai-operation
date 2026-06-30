"""内容监控面板：Flask 应用入口。"""

import base64
import json
import logging
import os
import shutil
import time
import threading
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path

import requests
from flask import Flask, request, jsonify, render_template, send_file

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

from config import APP_HOST, APP_PORT, APP_DEBUG, setup_logging
from scrapers import run_reddit_monitor, run_gamersky_monitor, run_news_monitor, run_deals_monitor
from scrapers import run_weibo_monitor, run_bilibili_monitor, run_taptap_monitor, run_domestic_games_monitor, run_twitter_monitor
from scrapers import fetch_weekly_news, fetch_rank, fetch_multi_region_ranks
from scrapers.qimai_rank import fetch_weekly_rank_excel
from qwen_client import (
    rewrite_content,
    translate_title_to_zh,
    batch_translate_to_zh,
    generate_game_review,
    generate_reddit_summary,
    analyze_reddit_screenshot,
    generate_video_script,
    generate_weekly_report_article,
    analyze_rank_anomalies_batch,
    rewrite_news_item,
)
from scrapers.reddit_comments import fetch_post_and_comments
from scrapers.review_finder import search_game_reviews
from scrapers.fan_tagger import run_fan_tag_task, get_task_state, OUTPUT_DIR as FAN_TAG_OUTPUT_DIR, CACHE_FILE as FAN_TAG_CACHE_FILE
from xhs_publisher import publish_to_xhs
from ttl_store import TTLStore
from draft_store import DraftStore
from game_ai import GameDemoRunner, get_demo_task, list_demo_tasks

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
app.config["TEMPLATES_AUTO_RELOAD"] = True   # 模板文件修改后无需重启
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # 静态文件不缓存（开发环境）

# 截图 / 会话数据存储（按 token 隔离，10 分钟自动过期）
_xhs_store = TTLStore(default_ttl=600)

# 小红书定时发布草稿箱（本地 JSON）
_draft_store = DraftStore(Path(__file__).parent / "xhs_drafts.json")

# GameAI Demo 全局 runner（延迟初始化，首次调用时按 API Key 创建）
_game_demo_runner: "GameDemoRunner | None" = None
_DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()

def _get_game_runner() -> GameDemoRunner:
    global _game_demo_runner
    if _game_demo_runner is None:
        _game_demo_runner = GameDemoRunner(api_key=_DASHSCOPE_API_KEY)
    return _game_demo_runner

# 图片上传临时目录
UPLOAD_DIR = Path(__file__).parent / "xhs_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ==================== 页面路由 ====================


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/rewrite")
def rewrite_page():
    """AI 改写页面"""
    return render_template("rewrite.html")


@app.route("/script_preview")
def script_preview_page():
    """视频脚本分段配图预览页面"""
    return render_template("script_preview.html")


@app.route("/api/tts_preview", methods=["POST"])
def tts_preview_api():
    """生成 TTS 试听音频，返回 base64 MP3。"""
    import asyncio, base64, tempfile
    from pathlib import Path
    data = request.get_json(force=True) or {}
    text  = (data.get("text") or "游戏雷达局，情报已送达！").strip()[:100]
    voice = (data.get("voice") or "zh-CN-XiaoxiaoNeural").strip()
    try:
        import edge_tts
        from video_pipeline import _parse_tts_text
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = Path(f.name)
        import re as _re_app
        # edge-tts 7.x 不支持 ssml=True，直接剥除所有 XML 标签用纯文本
        clean_text = _parse_tts_text(text)
        clean_text = _re_app.sub(r'<[^>]+>', '', clean_text).strip() or text.strip()
        async def _gen():
            communicate = edge_tts.Communicate(clean_text, voice)
            await communicate.save(str(tmp_path))
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_gen())
        finally:
            loop.close()
        audio_b64 = base64.b64encode(tmp_path.read_bytes()).decode()
        tmp_path.unlink(missing_ok=True)
        return jsonify({"status": "ok", "audio_b64": audio_b64})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/reddit_edit")
def reddit_edit_page():
    """Reddit 截图翻译编辑页面"""
    return render_template("reddit_edit.html")


@app.route("/xhs")
def xhs_page():
    """小红书编辑页面：展示截图 + 默认文案（中文标题 + 原帖链接）"""
    token = request.args.get("token", "")
    ctx = _xhs_store.pop(token, {}) if token else {}
    image_data = ctx.get("image_b64", "")
    title_zh = ctx.get("title_zh") or ctx.get("title") or ""
    url = ctx.get("url") or ""
    if title_zh or url:
        default_text = f"{title_zh}\n\n原帖链接：{url}"
    else:
        default_text = ""
    # 文案标题默认使用翻译后的中文标题（最多20字）
    default_title = (title_zh or "").strip()[:20]
    return render_template(
        "xhs.html",
        image_data=image_data,
        default_text=default_text,
        default_title=default_title,
    )


@app.route("/xhs_full")
def xhs_full_page():
    """完整小红书生成器页面，兼容 title / content URL 参数，支持 token 预填。"""
    token = request.args.get("token", "")
    prefill = _xhs_store.pop(token, {}) if token else {}
    return render_template("xhs_full.html", prefill=prefill)


@app.route("/output/wechat")
def output_wechat():
    """周报微信公众号版预览（可全选复制粘贴）"""
    from flask import send_from_directory
    return send_from_directory("static", "output_wechat.html")


@app.route("/output/xhs")
def output_xhs():
    """周报小红书图文版预览（3张卡片，可编辑文字后截图）"""
    from flask import send_from_directory
    return send_from_directory("static", "output_xhs.html")


# ==================== API 路由 ====================


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(force=True) or {}
    source = data.get("source")

    # 前端传入的 cookie，临时覆盖环境变量（仅当前请求线程）
    _cookies = data.get("cookies") or {}
    _old_env = {}
    for env_key, val in {
        "WEIBO_COOKIE":    _cookies.get("weibo", ""),
        "BILIBILI_COOKIE": _cookies.get("bilibili", ""),
        "TWITTER_COOKIE":  _cookies.get("twitter", ""),
    }.items():
        if val:
            _old_env[env_key] = os.environ.get(env_key, "")
            os.environ[env_key] = val

    try:
        if source == "reddit":
            labels = data.get("labels") or []
            per_label = int(data.get("per_label") or 20)
            items = run_reddit_monitor(labels, per_label)
        elif source in ("news", "gamersky"):
            news_sources = data.get("news_sources") or []
            target_date = data.get("date") or ""
            max_pages = int(data.get("max_pages") or 5)
            sounova_limit = int(data.get("sounova_limit") or 20)
            if not target_date:
                target_date = date.today().strftime("%Y-%m-%d")
            items = run_news_monitor(news_sources, target_date, max_pages, sounova_limit)
        elif source == "deals":
            platforms = data.get("platforms") or ["epic", "steam", "nintendo"]
            limit = int(data.get("limit") or 20)
            items = run_deals_monitor(platforms, limit)
        elif source == "weibo":
            topics = data.get("topics") or []
            per_topic = int(data.get("per_topic") or 20)
            items = run_weibo_monitor(topics, per_topic)
        elif source == "bilibili":
            uid_keys = data.get("uid_keys") or []
            per_uid = int(data.get("per_uid") or 20)
            items = run_bilibili_monitor(uid_keys, per_uid)
        elif source == "taptap":
            game_keys = data.get("game_keys") or []
            per_game = int(data.get("per_game") or 20)
            items = run_taptap_monitor(game_keys, per_game)
        elif source == "domestic_games":
            sources_list = data.get("sources") or []
            per_source = int(data.get("per_source") or 20)
            items = run_domestic_games_monitor(sources_list, per_source)
        elif source == "twitter":
            topic_keys = data.get("topics") or []
            per_topic = int(data.get("per_topic") or 15)
            items = run_twitter_monitor(topic_keys, per_topic)
        else:
            return jsonify({"status": "error", "message": "未知 source"}), 400
        return jsonify({"status": "ok", "items": items})
    except Exception as e:
        logger.error("抓取失败 (source=%s): %s", source, e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # 恢复环境变量
        for env_key, old_val in _old_env.items():
            if old_val:
                os.environ[env_key] = old_val
            else:
                os.environ.pop(env_key, None)


@app.route("/api/paste_screenshot", methods=["POST"])
def paste_screenshot():
    """接收用户粘贴的截图（base64），存储并返回 token，用于跳转编辑器。"""
    data = request.get_json(force=True) or {}
    image_data = data.get("image") or data.get("image_base64") or ""
    url = (data.get("url") or "").strip()
    title = data.get("title") or ""
    title_zh = data.get("title_zh") or ""

    if not image_data:
        return jsonify({"status": "error", "message": "未提供图片数据"}), 400

    try:
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        raw = base64.b64decode(image_data)
        b64 = base64.b64encode(raw).decode("utf-8")
        token = uuid.uuid4().hex
        _xhs_store.set(token, {
            "image_b64": f"data:image/png;base64,{b64}",
            "title": title,
            "title_zh": title_zh,
            "url": url,
        })
        logger.info("粘贴截图已存储: token=%s", token)
        return jsonify({"status": "ok", "token": token})
    except Exception as e:
        logger.error("粘贴截图处理失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/rewrite", methods=["POST"])
def api_rewrite():
    """调用通义千问，对单条原文进行改写（支持多来源融合）。"""
    data = request.get_json(force=True) or {}
    prompt        = (data.get("prompt")   or "").strip()
    tone          = data.get("tone")      or "professional"
    original      = (data.get("original") or "").strip()
    extra_sources = data.get("extra_sources") or []  # [{title, url, content}]
    mode          = data.get("mode") or "text"  # 'text' 或 'video'

    if not original:
        return jsonify({"status": "error", "message": "原文不能为空"}), 400

    try:
        text = rewrite_content(prompt, tone, original, extra_sources=extra_sources, mode=mode)
        return jsonify({"status": "ok", "text": text})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/fact_check", methods=["POST"])
def api_fact_check():
    """对改写后的文案进行事实核查，返回疑问列表和核实建议。"""
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"status": "error", "message": "文案内容不能为空"}), 400
    try:
        from qwen_client import fact_check_content
        result = fact_check_content(text)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/fetch_sources", methods=["POST"])
def fetch_sources():
    """Bing 搜索相关来源并返回正文摘要列表。接受 query 或 title 参数。"""
    data  = request.get_json(force=True) or {}
    query = (data.get("query") or data.get("title") or "").strip()
    num   = min(int(data.get("num") or 5), 8)

    if not query:
        return jsonify({"status": "error", "message": "搜索关键词不能为空"}), 400

    try:
        from scrapers.source_finder import find_related_sources
        sources = find_related_sources(query, num)
        return jsonify({"status": "ok", "sources": sources})
    except Exception as e:
        logger.error("查找来源失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/fetch_urls", methods=["POST"])
def fetch_urls():
    """抓取用户提供的多个 URL，返回正文内容列表。"""
    data = request.get_json(force=True) or {}
    urls = data.get("urls") or []
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip().startswith("http")][:6]

    if not urls:
        return jsonify({"status": "error", "message": "请提供有效的 URL"}), 400

    try:
        from scrapers.source_finder import fetch_url_content
        results = [fetch_url_content(u) for u in urls]
        results = [r for r in results if len(r.get("content", "")) > 50]
        return jsonify({"status": "ok", "sources": results})
    except Exception as e:
        logger.error("URL 抓取失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/proxy_image")
def proxy_image():
    """代理外部图片，带正确的 Referer 头绕过防盗链。"""
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        return "", 400
    try:
        from urllib.parse import urlparse
        parsed  = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        headers = {**_HEADERS, "Referer": referer}
        resp = requests.get(url, headers=headers, timeout=10)
        if not resp.ok:
            return "", resp.status_code
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        return resp.content, 200, {
            "Content-Type":  content_type,
            "Cache-Control": "public, max-age=3600",
        }
    except Exception as e:
        logger.warning("图片代理失败 (%s): %s", url, e)
        return "", 502


@app.route("/api/fetch_images", methods=["POST"])
def fetch_images():
    """从多个文章页面提取游戏截图列表。"""
    data = request.get_json(force=True) or {}
    urls = data.get("urls") or []
    if not urls:
        return jsonify({"status": "error", "message": "未提供页面 URL"}), 400
    try:
        from scrapers.source_finder import fetch_images_from_pages
        images = fetch_images_from_pages(urls[:5], max_per_page=10)
        return jsonify({"status": "ok", "images": images})
    except Exception as e:
        logger.error("图片提取失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/images_to_xhs", methods=["POST"])
def images_to_xhs():
    """下载选中图片 + 正文 → TTL store → 返回 token 跳转小红书生成器。"""
    data     = request.get_json(force=True) or {}
    img_urls = data.get("image_urls") or []
    title    = (data.get("title")   or "").strip()
    content  = (data.get("content") or "").strip()
    tag      = (data.get("tag")     or "游戏雷达局").strip()
    desc     = (data.get("desc")    or "").strip()

    body_images = {}
    new_content = content
    for i, url in enumerate(img_urls[:9]):
        try:
            from urllib.parse import urlparse as _urlparse
            _parsed = _urlparse(url)
            _referer = f"{_parsed.scheme}://{_parsed.netloc}/"
            dl_headers = {**_HEADERS, "Referer": _referer}
            resp = requests.get(url, headers=dl_headers, timeout=10)
            if not resp.ok or not resp.content:
                continue
            ext  = url.split("?")[0].rsplit(".", 1)[-1].lower()
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
            img_id = f"img{i+1}_{int(time.time() * 1000)}"
            body_images[img_id] = f"data:{mime};base64,{base64.b64encode(resp.content).decode()}"
            new_content += f"\n\n![游戏截图 {i + 1}](img:{img_id})"
        except Exception as e:
            logger.warning("图片下载失败 (%s): %s", url, e)

    token = uuid.uuid4().hex
    _xhs_store.set(token, {
        "title":       title,
        "content":     new_content,
        "body_images": body_images,
        "tag":         tag,
        "desc":        desc,
    })
    return jsonify({"status": "ok", "token": token})


_PLATFORM_LABEL = {"epic": "Epic", "steam": "Steam", "nintendo": "Nintendo"}

def _platform_title(raw_title: str, label: str) -> str:
    """给标题加上平台前缀，超 20 字自动截断。
    若标题已带 【...】 前缀（如 【任天堂】、【Steam】）则直接截断，不重复添加。"""
    if raw_title.startswith("【"):
        return raw_title[:20]
    tag = _PLATFORM_LABEL.get((label or "").lower(), "")
    prefix = f"【{tag}】" if tag else ""
    return (prefix + raw_title)[:20]


def _deal_item_to_markdown(item: dict) -> str:
    """将单条折扣数据组装为情报局风格的 Markdown 正文。"""
    title         = (item.get("title")         or "").strip()
    raw_content   = (item.get("content")       or "").strip()
    price_current = (item.get("price_current") or "").strip()
    price_original= (item.get("price_original")or "").strip()
    discount      = (item.get("discount")      or "").strip()
    url           = (item.get("url")           or "").strip()
    label         = (item.get("label")         or "").strip().lower()

    lines: list[str] = []
    lines.append(f"# 【情报速报】{title}\n")

    # 关键情报
    lines.append("## 关键情报\n")
    if label == "epic":
        lines.append(f"- **平台：** Epic Games Store")
    elif label == "steam":
        lines.append(f"- **平台：** Steam")
    elif label == "nintendo":
        lines.append(f"- **平台：** Nintendo eShop")
    if price_current:
        lines.append(f"- **💰 当前价格：** {price_current}")
    if price_original and price_original != price_current:
        lines.append(f"- **🏷 原价：** ~~{price_original}~~")
    if discount:
        lines.append(f"- **🔥 折扣：** {discount}")

    # 游戏简介（清理掉原始文本里已有的 key-value 重复行）
    if raw_content:
        # 原始 content 里首行通常是状态文字（免费领取中 / 折扣信息），跳过重复内容
        desc_lines = [l for l in raw_content.splitlines()
                      if l.strip() and not any(l.startswith(k) for k in ("免费领取中", "即将免费", "折扣：", "原价：", "折后价：", "免费时间：", "类型：", "发售日期：", "Metacritic 评分："))]
        desc = "\n".join(desc_lines).strip()
        if desc:
            lines.append("\n## 游戏简介\n")
            lines.append(desc)

    lines.append("\n*—— 游戏雷达局，今日情报已送达*")
    return "\n".join(lines)


def _extract_game_name_zh(title: str, label: str) -> str:
    """从折扣条目标题中提取游戏名（去掉平台前缀和状态后缀），并翻译非中文名。"""
    import re as _re
    from qwen_client import batch_translate_to_zh

    # 去掉常见前缀：【Epic 喜加一】、【Steam】、【任天堂】等
    name = _re.sub(r"^【[^】]+】\s*", "", title).strip()
    # 去掉后缀：— 免费领取中、— 25% OFF 等
    name = _re.sub(r"\s*[—–-]+\s*.+$", "", name).strip()

    # 判断是否需要翻译（中文字符占比 < 15% 视为非中文）
    if name:
        chinese = sum(1 for c in name if "\u4e00" <= c <= "\u9fff")
        if len(name) > 0 and chinese / len(name) < 0.15:
            try:
                translated = batch_translate_to_zh([name])
                if translated and translated[0] != name:
                    return translated[0]
            except Exception:
                pass
    return name


def _multi_deal_to_markdown(items: list, body_images: dict) -> str:
    """将多条折扣数据合并为情报局风格的汇总 Markdown。
    封面图的 base64 data URI 写入 body_images（key=img:<id>），
    Markdown 正文只存轻量的 img:key 占位符，避免巨型 URL 塞入文本。
    """
    from qwen_client import generate_game_pitch

    n = len(items)
    # 收集平台信息用于标题
    platforms = list(dict.fromkeys(
        _PLATFORM_LABEL[l] for it in items if (l := (it.get("label") or "").lower()) in _PLATFORM_LABEL
    ))
    platform_str = "/".join(platforms) if platforms else "游戏"

    lines: list[str] = []
    lines.append(f"# 【{platform_str} 喜加{n}】本周折扣情报\n")
    lines.append("## 📡 局长说\n")
    lines.append(f"本周局长精选 **{n} 款**游戏特惠，按需领取！\n")
    lines.append("---\n")

    for i, item in enumerate(items):
        title         = (item.get("title")         or "").strip()
        raw_content   = (item.get("content")       or "").strip()
        cover_url     = (item.get("cover_image")   or "").strip()
        url           = (item.get("url")           or "").strip()
        price_current = (item.get("price_current") or "").strip()
        price_original= (item.get("price_original")or "").strip()
        discount      = (item.get("discount")      or "").strip()
        label         = (item.get("label")         or "").strip().lower()

        # 提取并翻译游戏名
        game_name_zh = _extract_game_name_zh(title, label)
        display_title = game_name_zh if game_name_zh else title

        lines.append(f"## {i + 1}. {display_title}\n")

        # 封面图：base64 存入 body_images，Markdown 只写 img:key 占位符
        cover_b64 = (item.get("cover_b64") or "").strip()
        if cover_b64:
            img_key = f"cover_{i}"
            body_images[img_key] = cover_b64
            lines.append(f"![封面图](img:{img_key})\n")
        elif cover_url:
            lines.append(f"![封面图]({cover_url})\n")

        # 价格行
        price_parts = []
        if price_current:
            price_parts.append(f"💰 **{price_current}**")
        if price_original and price_original != price_current:
            price_parts.append(f"~~{price_original}~~")
        if discount:
            price_parts.append(f"🔥 `{discount}`")
        if price_parts:
            lines.append(" · ".join(price_parts) + "\n")

        # 折扣时间
        deal_start = (item.get("deal_start") or "").strip()
        deal_end   = (item.get("deal_end")   or "").strip()
        if deal_start and deal_end:
            lines.append(f"🗓 **活动时间：** {deal_start} ~ {deal_end}\n")
        elif deal_end:
            lines.append(f"🗓 **截止时间：** {deal_end}\n")

        # AI 推荐语：从原始简介中提取纯描述部分
        raw_desc = ""
        if raw_content:
            raw_desc_lines = [l for l in raw_content.splitlines()
                              if l.strip() and not any(l.startswith(k) for k in
                              ("免费领取中", "即将免费", "折扣：", "原价：", "折后价：", "免费时间：", "Metacritic 评分：", "类型："))]
            raw_desc = " ".join(raw_desc_lines).strip()

        pitch = generate_game_pitch(display_title, raw_desc)
        if pitch:
            lines.append(f"{pitch}\n")

        lines.append("---\n")

    lines.append("\n*—— 游戏雷达局，今日情报已送达*")
    return "\n".join(lines)


def _download_cover(cover_url: str) -> str:
    """下载封面图并返回 base64 data URI，失败返回空字符串。"""
    if not cover_url:
        return ""
    try:
        resp = requests.get(cover_url, headers=_HEADERS, timeout=10)
        if resp.ok and resp.content:
            ext  = cover_url.split("?")[0].rsplit(".", 1)[-1].lower()
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
            return f"data:{mime};base64,{base64.b64encode(resp.content).decode()}"
    except Exception as e:
        logger.warning("封面图下载失败 (%s): %s", cover_url, e)
    return ""


@app.route("/api/deals_to_xhs", methods=["POST"])
def deals_to_xhs():
    """折扣条目一键跳转小红书生成器：格式化内容 + 下载封面 + 存入 TTL store 返回 token。
    支持单条目（title/content/cover_image/…）和多条目（items 数组）两种模式。
    """
    data = request.get_json(force=True) or {}
    tag  = (data.get("tag") or "游戏雷达局").strip()

    items = data.get("items") or []
    if items:
        # ── 多条目合并模式 ──
        # 预下载所有封面图为 base64 data URI，避免 html-to-image 导出时的 CORS 问题
        for it in items:
            it["cover_b64"] = _download_cover(it.get("cover_image") or "")
        body_images: dict = {}
        content_md = _multi_deal_to_markdown(items, body_images)
        # 收集所有平台，去重后拼接前缀
        platforms = list(dict.fromkeys(
            _PLATFORM_LABEL[l] for i in items if (l := (i.get("label") or "").lower()) in _PLATFORM_LABEL
        ))
        platform_str = "/".join(platforms) if platforms else "游戏"
        title_main = f"【{platform_str} 喜加{len(items)}】本周折扣情报"
        cover_url_0 = (items[0].get("cover_image") or "").strip() if items else ""
        image_b64 = _download_cover(cover_url_0)
        # 生成简介：每条游戏附链接，方便用户在帖子文字中点击
        desc_lines = []
        for idx, it in enumerate(items):
            t = (it.get("title") or "").strip()
            u = (it.get("url")   or "").strip()
            if t:
                desc_lines.append(f"{idx + 1}、{t}" + (f"\n链接：{u}" if u else ""))
        desc = "\n".join(desc_lines) + "\n\n#游戏推荐# #每日一推# #主机游戏# #过期羊毛犹如砒霜# #游戏折扣#"
        token = uuid.uuid4().hex
        _xhs_store.set(token, {
            "title":       title_main,
            "content":     content_md,
            "image_b64":   image_b64,
            "body_images": body_images,
            "tag":         tag,
            "desc":        desc,
        })
        return jsonify({"status": "ok", "token": token})

    # ── 单条目模式 ──
    item = {
        "title":          (data.get("title")          or "").strip(),
        "content":        (data.get("content")        or "").strip(),
        "price_current":  (data.get("price_current")  or "").strip(),
        "price_original": (data.get("price_original") or "").strip(),
        "discount":       (data.get("discount")       or "").strip(),
        "url":            (data.get("url")            or "").strip(),
        "label":          (data.get("label")          or "").strip(),
        "cover_image":    (data.get("cover_image")    or "").strip(),
    }
    content_md = _deal_item_to_markdown(item)
    image_b64  = _download_cover(item["cover_image"])
    # 生成简介：标题 + 链接
    desc = item["title"]
    if item["url"]:
        desc += f"\n链接：{item['url']}"
    desc += "\n\n#游戏推荐# #每日一推# #主机游戏# #过期羊毛犹如砒霜# #游戏折扣#"
    token = uuid.uuid4().hex
    _xhs_store.set(token, {
        "title":     _platform_title(item["title"], item["label"]),
        "content":   content_md,
        "image_b64": image_b64,
        "tag":       tag,
        "desc":      desc,
    })
    return jsonify({"status": "ok", "token": token})


@app.route("/api/upload_images", methods=["POST"])
def upload_images():
    """接收前端 base64 图片数组，保存到临时目录，返回 token。"""
    data = request.get_json(force=True) or {}
    images = data.get("images") or []

    if not images:
        return jsonify({"status": "error", "message": "未提供图片"}), 400
    if len(images) > 9:
        images = images[:9]

    token = uuid.uuid4().hex
    session_dir = UPLOAD_DIR / token
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        for i, img_data in enumerate(images):
            # 移除 data:image/...;base64, 前缀
            if "," in img_data:
                img_data = img_data.split(",", 1)[1]
            img_bytes = base64.b64decode(img_data)
            (session_dir / f"{i + 1}.jpg").write_bytes(img_bytes)

        # 保存 token → 目录路径的映射，10 分钟后自动过期
        _xhs_store.set(f"upload_{token}", str(session_dir))
        logger.info("图片上传完成: token=%s, count=%d", token, len(images))
        return jsonify({"status": "ok", "token": token, "count": len(images)})
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.error("图片上传失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/reddit_comments", methods=["POST"])
def reddit_comments_api():
    """抓取 Reddit 帖子评论并批量翻译为中文。"""
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    limit = min(int(data.get("limit", 10)), 20)

    if not url:
        return jsonify({"status": "error", "message": "URL 不能为空"}), 400

    try:
        result = fetch_post_and_comments(url, limit)
        post = result["post"]
        comments = result["comments"]

        post["title_zh"] = translate_title_to_zh(post["title"]) or post["title"]

        bodies = [c["body"] for c in comments]
        translations = batch_translate_to_zh(bodies)
        for c, zh in zip(comments, translations):
            c["body_zh"] = zh

        return jsonify({"status": "ok", "post": post, "comments": comments})
    except Exception as e:
        logger.error("Reddit 评论抓取失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/analyze_screenshot", methods=["POST"])
def analyze_screenshot_api():
    """接收 Reddit 截图（base64 data URL），调用 Qwen-VL 提取并翻译评论。"""
    data   = request.get_json(force=True) or {}
    images = data.get("images") or []
    if not images:
        return jsonify({"status": "error", "message": "未提供截图"}), 400

    results = []
    for img_data in images[:5]:
        try:
            comments = analyze_reddit_screenshot(img_data)
            results.append({"status": "ok", "comments": comments})
        except Exception as e:
            logger.error("截图分析失败: %s", e)
            results.append({"status": "error", "message": str(e)})

    return jsonify({"status": "ok", "results": results})


@app.route("/api/translate_batch", methods=["POST"])
def translate_batch_api():
    """批量翻译文本为中文（供手动输入评论翻译使用）。"""
    data  = request.get_json(force=True) or {}
    texts = data.get("texts") or []
    if not texts:
        return jsonify({"status": "ok", "translated": []})
    try:
        result = batch_translate_to_zh(texts)
        return jsonify({"status": "ok", "translated": result})
    except Exception as e:
        logger.error("批量翻译失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/cards_to_xhs", methods=["POST"])
def cards_to_xhs():
    """接收前端生成的 base64 卡片图片，存入 TTL store，返回 token 跳转生成器。"""
    data = request.get_json(force=True) or {}
    image_b64s = data.get("image_b64s") or []
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    tag  = (data.get("tag")  or "游戏雷达局").strip()
    desc = (data.get("desc") or "").strip()

    body_images = {}
    new_content = content
    for i, b64_data in enumerate(image_b64s[:9]):
        if not isinstance(b64_data, str) or not b64_data.startswith("data:"):
            continue
        img_id = f"card{i+1}_{int(time.time() * 1000)}"
        body_images[img_id] = b64_data
        new_content += f"\n\n![Reddit评论卡片 {i + 1}](img:{img_id})"

    token = uuid.uuid4().hex
    _xhs_store.set(token, {
        "title":       title,
        "content":     new_content,
        "body_images": body_images,
        "tag":         tag,
        "desc":        desc,
    })
    return jsonify({"status": "ok", "token": token})


@app.route("/api/reddit_summary", methods=["POST"])
def reddit_summary_api():
    """根据 Reddit 帖子 + 评论，生成小红书发布文案（标题 + 正文）。"""
    data     = request.get_json(force=True) or {}
    post     = data.get("post")     or {}
    comments = data.get("comments") or []
    if not post:
        return jsonify({"status": "error", "message": "缺少帖子信息"}), 400
    try:
        title, content = generate_reddit_summary(post, comments)
        return jsonify({"status": "ok", "title": title, "content": content})
    except Exception as e:
        logger.error("Reddit 文案生成失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/publish_reddit_direct", methods=["POST"])
def publish_reddit_direct():
    """直接将 base64 长图发布到小红书（跳过编辑器）。"""
    import tempfile
    data       = request.get_json(force=True) or {}
    image_b64s = data.get("image_b64s") or []
    title      = (data.get("title")   or "").strip()[:20]
    content    = (data.get("content") or "").strip()
    cookie     = (data.get("cookie")  or "").strip()
    post_time  = (data.get("post_time") or "").strip() or None
    source_tag = (data.get("source") or "reddit_screenshot").strip() or "reddit_screenshot"
    is_draft   = bool(data.get("is_draft", False))

    if not cookie:
        return jsonify({"status": "error", "message": "Cookie 不能为空"}), 400
    if not image_b64s:
        return jsonify({"status": "error", "message": "请先生成图片"}), 400
    if not title or not content:
        return jsonify({"status": "error", "message": "标题和文案不能为空"}), 400

    temp_dir = Path(tempfile.mkdtemp())
    try:
        for i, b64_data in enumerate(image_b64s[:9]):
            if not isinstance(b64_data, str) or "," not in b64_data:
                continue
            _, encoded = b64_data.split(",", 1)
            (temp_dir / f"{i + 1}.jpg").write_bytes(base64.b64decode(encoded))

        result  = publish_to_xhs(cookie, title, content, temp_dir, max_images=9,
                                 post_time=post_time, is_draft=is_draft)
        note_id = ""
        if isinstance(result, dict):
            note_id = result.get("note_id") or result.get("id") or ""
        url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
        # 草稿箱 / 定时发布均记录到本地
        if is_draft or post_time:
            try:
                _draft_store.add({
                    "id":         note_id or uuid.uuid4().hex,
                    "title":      title,
                    "source":     source_tag,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "post_time":  post_time,
                    "note_id":    note_id,
                    "url":        url,
                    "status":     "draft" if is_draft else "scheduled",
                })
            except Exception as e:
                logger.warning("保存 Reddit 草稿失败: %s", e)
        return jsonify({"status": "ok", "note_id": note_id, "url": url, "is_draft": is_draft})
    except Exception as e:
        logger.error("Reddit 直发失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/xhs_api_publish", methods=["POST"])
def xhs_api_publish():
    """一键发布到小红书：使用 xhs 库 + 实时粘贴的 Cookie。

    支持两种图片来源：
    1. image_token：前端通过 /api/upload_images 上传的图片
    2. 兜底：从项目根目录扫描最近的 PNG/JPG
    """
    data = request.get_json(force=True) or {}
    cookie = (data.get("cookie") or "").strip()
    title = (data.get("title") or "").strip()
    desc = (data.get("desc") or "").strip()
    image_token = (data.get("image_token") or "").strip()
    post_time = (data.get("post_time") or "").strip() or None
    is_draft = bool(data.get("is_draft", False))
    source_tag = (data.get("source") or "xhs").strip() or "xhs"

    if not title or not desc:
        return jsonify({"status": "error", "message": "标题或文案不能为空"}), 400

    # 确定图片来源目录
    session_dir = None
    if image_token:
        dir_path = _xhs_store.pop(f"upload_{image_token}", None)
        if dir_path and Path(dir_path).is_dir():
            session_dir = Path(dir_path)
        else:
            return jsonify({"status": "error", "message": "图片已过期，请重新上传"}), 400

    base_dir = session_dir or Path(__file__).parent

    try:
        logger.info("开始发布: title=%s, is_draft=%s, post_time=%s, image_count in dir=%s",
                    title, is_draft, post_time, len(list(base_dir.glob("*.jpg"))) if base_dir else 0)
        result = publish_to_xhs(cookie, title, desc, base_dir, max_images=9, post_time=post_time, is_draft=is_draft)
        logger.info("发布结果: %s", result)
        note_id = ""
        if isinstance(result, dict):
            note_id = (result.get("note_id") or result.get("id") or
                       result.get("noteId") or result.get("data", {}).get("note_id") or "")
        url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
        # 草稿箱或定时发布，均记录到本地草稿
        if is_draft or post_time:
            try:
                _draft_store.add({
                    "id":        note_id or uuid.uuid4().hex,
                    "title":     title,
                    "source":    source_tag,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "post_time": post_time or "草稿（待手动设置）",
                    "note_id":   note_id,
                    "url":       url,
                    "status":    "draft" if is_draft else "scheduled",
                })
            except Exception as e:
                logger.warning("保存草稿记录失败: %s", e)
        return jsonify({"status": "ok", "note_id": note_id, "url": url, "is_draft": is_draft})
    except Exception as e:
        logger.error("发布失败: is_draft=%s, post_time=%s, error=%s", is_draft, post_time, e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # 发布后清理临时目录
        if session_dir:
            shutil.rmtree(session_dir, ignore_errors=True)


# ==================== 游戏行业周报 ====================

# 周报新闻缓存（供异动分析时匹配相关新闻）
_weekly_news_cache: list = []


@app.route("/weekly_report")
def weekly_report_page():
    """游戏行业周报编辑页面"""
    preload_token = request.args.get("preload")
    preload_data = None
    if preload_token:
        preload_data = _xhs_store.get(preload_token)
    return render_template("weekly_report.html", preload=preload_data)


@app.route("/api/preload_weekly", methods=["POST"])
def preload_weekly_api():
    """存储预填充数据，返回 token 供 /weekly_report?preload=<token> 使用。"""
    data = request.get_json(force=True) or {}
    token = uuid.uuid4().hex
    _xhs_store.set(token, data, ttl=3600)
    return jsonify({"status": "ok", "token": token})


@app.route("/unity_report_2026")
def unity_report_2026_page():
    """Unity 2026 游戏开发报告深度解读（微信长文）"""
    return render_template("unity_report_2026.html")

@app.route("/unity_report_xhs")
def unity_report_xhs_page():
    """Unity 2026 游戏开发报告小红书图文（6张卡片）"""
    return render_template("unity_report_xhs.html")

@app.route("/gaming_2026_wechat")
def gaming_2026_wechat_page():
    """Epyllion 2026全球游戏市场报告深度解读（微信长文）"""
    return render_template("gaming_2026_wechat.html")

@app.route("/gaming_2026_xhs")
def gaming_2026_xhs_page():
    """Epyllion 2026全球游戏市场报告小红书图文（8张卡片）"""
    return render_template("gaming_2026_xhs.html")

@app.route("/mhstories3_xhs")
def mhstories3_xhs_page():
    """怪猎物语3首发危机小红书图文（6张卡片）"""
    return render_template("mhstories3_xhs.html")


@app.route("/chenbaijinqu_xhs")
def chenbaijinqu_xhs_page():
    """尘白禁区停服事件小红书图文（6张卡片，可编辑）"""
    return render_template("chenbaijinqu_xhs.html")


@app.route("/luoke_xhs")
def luoke_xhs_page():
    """洛克王国亚文化现象观察小红书图文（6张卡片，可编辑）"""
    return render_template("luoke_xhs.html")


@app.route("/mhstories3")
def mhstories3_intel_page():
    """怪猎物语3首发危机 · 情报局风格小红书图片生成器（预填充版）"""
    import uuid as _uuid
    content = r"""## 局长说

今天是怪物猎人物语3的发售日。

媒体均分 **MC 86 / IGN 9分**，系列最成熟一作。
但发售日一到，Steam国区好评率跌破 **50%**。

---

## 📊 数据割裂

媒体评测的是**游戏质量**，玩家差评的是**购买体验**——这两件事，本来就不是同一个维度。

> 媒体评测窗口在发售前，评的是战斗系统、剧情完成度、画面表现。
> 玩家发售日评的是：承诺是否兑现、首发定价是否合理、技术是否就绪。

今天，这三项全部出了问题。

---

## 🔴 问题一：存档继承，官方食言

官方多渠道明确宣传：**试玩版存档可完整导入正式版**。

今天上线之后，这个功能不存在。
没有公告，没有补偿，没有任何解释。

这不是技术Bug，是**承诺落空**。

---

## 🔴 问题二：首发16个付费DLC

18项DLC，**16项付费**，部分服装拆开单独定价。

发售第一天集中上线，传递的信号非常清晰：后续还会更多。

> 我现在买的，是完整的游戏吗？

---

## 🔴 问题三：PC版技术不达标

- 随机崩溃/闪退，**RTX 5090也未幸免**
- DLSS开启后帧率不稳
- Denuvo每日激活**限5台设备**，家庭共享受阻
- Capcom至今**零回应**

---

## 局长结论

**游戏质量过关，但建议等一个月。**

等补丁稳定，等DLC轮廓清晰，等官方给出回应。
首发溢价从来不只是价格——卡普空的促销一定会来。

*— 游戏雷达局，今日情报已送达*"""

    token = _uuid.uuid4().hex
    _xhs_store.set(token, {
        "title": "媒体9分、玩家差评过半——怪猎物语3首发发生了什么",
        "content": content,
        "tag": "游戏雷达局",
        "style": "intel",
    })
    from flask import redirect, url_for
    return redirect(url_for("xhs_full_page", token=token))

@app.route("/api/weekly_news", methods=["POST"])
def weekly_news_api():
    """抓取游戏行业周报新闻（36kr / gamelook / 游戏茶馆）。"""
    global _weekly_news_cache
    data = request.get_json(force=True) or {}
    sources = data.get("sources") or ["36kr", "gamelook", "youxichaguan"]
    days = int(data.get("days") or 7)
    per_source = int(data.get("per_source") or 30)
    try:
        items = fetch_weekly_news(sources=sources, days=days, per_source=per_source)
        _weekly_news_cache = items  # 缓存，供异动分析匹配用
        return jsonify({"status": "ok", "items": items, "total": len(items)})
    except Exception as e:
        logger.error("周报新闻抓取失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/qimai_rank", methods=["POST"])
def qimai_rank_api():
    """抓取七麦数据游戏榜单。"""
    data = request.get_json(force=True) or {}
    countries = data.get("countries") or ["cn", "hk", "tw", "us", "jp", "kr"]
    chart_types = data.get("chart_types") or ["free", "grossing"]
    top = int(data.get("top") or 10)
    try:
        result = fetch_multi_region_ranks(countries=countries, chart_types=chart_types, top=top)
        # 检查是否所有榜单数据全为空（IP 被封或 API 异常）
        total_items = sum(
            len(result.get(c, {}).get(ct, {}).get("items", []))
            for c in countries for ct in chart_types
        )
        if total_items == 0:
            return jsonify({"status": "error", "message": "七麦数据返回为空，当前 IP 可能被封禁，请稍后重试或切换网络"}), 502
        return jsonify({"status": "ok", "data": result})
    except Exception as e:
        logger.error("七麦榜单抓取失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/qimai_rank_excel", methods=["POST"])
def qimai_rank_excel_api():
    """抓取过去7天每日榜单并生成 Excel 文件下载，同时返回异动数据。"""
    import io
    from datetime import date
    data = request.get_json(force=True) or {}
    countries = data.get("countries") or ["cn"]
    chart_types = data.get("chart_types") or ["free", "grossing"]
    top = int(data.get("top") or 30)
    try:
        excel_bytes, anomalies, rank_tables = fetch_weekly_rank_excel(countries=countries, chart_types=chart_types, top=top)
        filename = f"游戏榜单周报_{date.today().strftime('%Y%m%d')}.xlsx"
        excel_b64 = base64.b64encode(excel_bytes).decode("utf-8")
        return jsonify({
            "status": "ok",
            "filename": filename,
            "excel_b64": excel_b64,
            "anomalies": anomalies,
            "rank_tables": rank_tables,
        })
    except Exception as e:
        logger.error("Excel 生成失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/translate_names", methods=["POST"])
def translate_names_api():
    """将日韩游戏名批量翻译为中文。"""
    from qwen_client import get_qwen_client
    data = request.get_json(force=True) or {}
    names = data.get("names") or []
    if not names:
        return jsonify({"status": "ok", "translations": {}})
    try:
        client = get_qwen_client()
        prompt = (
            "请将以下游戏名称翻译为中文（如有官方中文名优先使用官方名，否则意译）。"
            "直接返回 JSON 对象，格式：{\"原名\": \"中文名\", ...}，不要其他内容。\n\n"
            + "\n".join(f"- {n}" for n in names[:30])
        )
        completion = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
            extra_body={"enable_thinking": False},
            max_tokens=800,
        )
        raw = (completion.choices[0].message.content or "").strip()
        # 提取 JSON
        import re
        m = re.search(r'\{[\s\S]*\}', raw)
        translations = json.loads(m.group()) if m else {}
        return jsonify({"status": "ok", "translations": translations})
    except Exception as e:
        logger.error("游戏名翻译失败: %s", e)
        return jsonify({"status": "ok", "translations": {}})


@app.route("/api/analyze_rank_anomalies", methods=["POST"])
def analyze_rank_anomalies_api():
    """
    AI 分析榜单异动原因。
    策略：先在本次抓取的新闻里匹配游戏名 → 若有相关新闻则用 AI 总结；
         若无相关新闻则用 Qwen 联网搜索（enable_search=True）。
    """
    data = request.get_json(force=True) or {}
    anomalies = data.get("anomalies") or []
    # 前端可传已选新闻；否则用服务端缓存的全量新闻
    news_from_client = data.get("news_items") or []
    all_news = news_from_client or _weekly_news_cache
    if not anomalies:
        return jsonify({"status": "ok", "analyses": []})
    try:
        results = analyze_rank_anomalies_batch(anomalies, all_news=all_news)
        return jsonify({"status": "ok", "analyses": results})
    except Exception as e:
        logger.error("异动分析失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/generate_weekly_report", methods=["POST"])
def generate_weekly_report_api():
    """AI 生成游戏行业周报长文。"""
    data = request.get_json(force=True) or {}
    news_items = data.get("news_items") or []
    rank_data = data.get("rank_data") or {}
    week_label = (data.get("week_label") or "").strip()
    excel_anomalies = data.get("excel_anomalies") or []

    if not news_items:
        return jsonify({"status": "error", "message": "请至少选择一条新闻"}), 400

    if not week_label:
        from datetime import date
        today = date.today()
        week_label = today.strftime("%Y年第%V周")

    try:
        article = generate_weekly_report_article(
            news_items=news_items,
            rank_data=rank_data,
            week_label=week_label,
            excel_anomalies=excel_anomalies,
        )
        return jsonify({"status": "ok", "article": article, "week_label": week_label})
    except Exception as e:
        logger.error("周报生成失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/weekly_report_to_xhs", methods=["POST"])
def weekly_report_to_xhs():
    """将周报 Markdown 存入 token，供小红书编辑器预填充。"""
    data = request.get_json(force=True) or {}
    markdown = (data.get("markdown") or "").strip()
    title = (data.get("title") or "").strip()
    if not markdown:
        return jsonify({"status": "error", "message": "内容为空"}), 400
    token = uuid.uuid4().hex
    _xhs_store.set(token, {
        "content": markdown,
        "title": title,
        "style": "pro",  # 默认专业风
    })
    return jsonify({"status": "ok", "token": token})


@app.route("/api/generate_output_html", methods=["POST"])
def generate_output_html_api():
    """
    根据周报 Markdown + Excel 榜单，生成微信公众号 HTML 和小红书卡片 HTML，
    写入 static/output_wechat.html 和 static/output_xhs.html。

    请求体 (JSON):
      markdown    str   完整周报 Markdown（含 --- 分隔符后的榜单表格）
      excel_path  str   七麦榜单 Excel 文件绝对路径（用于小红书卡片）
      week_label  str   如 "2026年3月9日-15日"
      week_short  str   如 "2026年3月第二周"
      date_range  str   如 "03月09日 – 03月15日"
      issue       str   如 "2026-11"
      week_tag    str   如 "2026 · W11"（卡片右上角）

    返回:
      { status, wechat_url, xhs_url, wechat_chars, xhs_chars }
    """
    import os as _os
    try:
        import openpyxl as _openpyxl
    except ImportError:
        return jsonify({"status": "error", "message": "缺少 openpyxl，请 pip install openpyxl"}), 500

    from weekly_output_builder import (
        build_wechat_html, build_xhs_html,
        read_sheet_rows,
        xhs_card, xhs_h2, xhs_h3, xhs_para, xhs_quote,
        rank_table, section_label,
    )

    data = request.get_json(force=True) or {}
    full_md     = (data.get("markdown")    or "").strip()
    excel_path  = (data.get("excel_path")  or "").strip()
    week_label  = (data.get("week_label")  or "本周").strip()
    week_short  = (data.get("week_short")  or week_label).strip()
    date_range  = (data.get("date_range")  or "").strip()
    issue       = (data.get("issue")       or "").strip()
    week_tag    = (data.get("week_tag")    or week_short).strip()

    if not full_md:
        return jsonify({"status": "error", "message": "markdown 不能为空"}), 400

    # ── 1. 微信版 ──────────────────────────────────────────────────────────
    wechat_html = build_wechat_html(full_md, week_label, week_short, date_range, issue)
    wechat_out = _os.path.join(_os.path.dirname(__file__), "static", "output_wechat.html")
    with open(wechat_out, "w", encoding="utf-8") as f:
        f.write(wechat_html)
    logger.info("微信版已生成: %d chars -> %s", len(wechat_html), wechat_out)

    # ── 2. 小红书版（需要 Excel） ──────────────────────────────────────────
    cards_html_list = []
    xhs_error = None

    if excel_path and _os.path.isfile(excel_path):
        try:
            wb = _openpyxl.load_workbook(excel_path, read_only=True)
            rows_cn_free     = read_sheet_rows(wb, '中国大陆_免费榜')
            rows_cn_grossing = read_sheet_rows(wb, '中国大陆_畅销榜')
            rows_hk_free     = read_sheet_rows(wb, '中国香港_免费榜')
            rows_us_free     = read_sheet_rows(wb, '美国_免费榜')
            rows_jp_free     = read_sheet_rows(wb, '日本_免费榜')
            rows_kr_free     = read_sheet_rows(wb, '韩国_免费榜')
            wb.close()

            # 从 markdown 中提取文章正文（--- 前面的部分）
            SEP = "\n\n---\n\n"
            article_body = full_md.split(SEP, 1)[0] if SEP in full_md else full_md

            # 封面块
            cover_block = (
                '<div style="background-color:#0A1524;margin:-14px -14px 12px;padding:12px 14px 10px;'
                'border-bottom:1px solid #1E2D40;text-align:center;">'
                '<div style="font-size:9px;color:#E8820C;letter-spacing:3px;font-weight:700;margin-bottom:4px;">' + week_tag + '</div>'
                '<div style="font-size:26px;font-weight:900;color:#EAF0F8;letter-spacing:2px;line-height:1.1;">游戏行业周报</div>'
                '<div style="width:32px;height:2px;background-color:#E8820C;margin:6px auto;"></div>'
                '<div style="font-size:9px;color:#6A8090;letter-spacing:1px;">手游榜单 · 行业大事 · 新游速递</div>'
                '</div>'
            )

            # 从 Markdown 提取各小节内容（H2/H3 结构）用于简化卡片
            import re as _re

            def _extract_section(md, h2_keyword):
                """提取指定 H2 段落下的所有文本（到下一个 H2 为止）"""
                lines = md.split('\n')
                in_section = False
                result = []
                for ln in lines:
                    if _re.match(r'^## ', ln):
                        if h2_keyword in ln:
                            in_section = True
                            continue
                        elif in_section:
                            break
                    if in_section:
                        result.append(ln)
                return '\n'.join(result).strip()

            def _md_to_xhs_paras(md_block, max_chars=200):
                """将 MD 段落转成 xhs_para，总字数控制"""
                paras = []
                total = 0
                for ln in md_block.split('\n'):
                    ln = ln.strip()
                    if not ln or _re.match(r'^#{1,3} ', ln) or _re.match(r'^[-*] \*\*', ln):
                        continue
                    # 去掉 bold/italic markdown 标记
                    ln = _re.sub(r'\*\*(.+?)\*\*', r'\1', ln)
                    ln = _re.sub(r'\*(.+?)\*', r'\1', ln)
                    if total + len(ln) > max_chars:
                        break
                    paras.append(xhs_para(ln))
                    total += len(ln)
                return ''.join(paras)

            # 卡片1：封面 + 平台降佣
            sec1 = _extract_section(article_body, '平台')
            c1 = (
                cover_block
                + xhs_h2('01', '平台大让利')
                + (_md_to_xhs_paras(sec1, 300) or xhs_para('苹果/谷歌同步降佣，移动游戏分发生态近年最大变革。'))
            )

            # 卡片2：沙特资本
            sec2 = _extract_section(article_body, '沙特')
            c2 = (
                xhs_h2('02', '沙特资本买下全球游戏业')
                + (_md_to_xhs_paras(sec2, 350) or xhs_para('EA收购、Moonton出售、腾讯入股育碧，沙特+腾讯双线布局。'))
            )

            # 卡片3：开发者动态
            sec3 = _extract_section(article_body, '开发者')
            if not sec3:
                sec3 = _extract_section(article_body, 'AI')
            c3 = (
                xhs_h2('03', '开发者注意这几件事')
                + (_md_to_xhs_paras(sec3, 350) or xhs_para('AI替代QA、Unity断商店、欧盟抽卡新规，开发者需关注。'))
            )

            # 卡片4：新游速递
            sec4 = _extract_section(article_body, '新游')
            if not sec4:
                sec4 = _extract_section(article_body, '游戏')
            c4 = (
                xhs_h2('04', '本周新游速递')
                + (_md_to_xhs_paras(sec4, 350) or xhs_para('本周多款新游上线，详见正文。'))
            )

            # 卡片5-7：榜单数据
            date_label = date_range or week_label
            c5 = (
                xhs_h2('05', '本周榜单数据')
                + section_label(f'中国大陆 免费榜 TOP10 · {date_label}（每行为一周内出现最多的游戏）')
                + rank_table(rows_cn_free)
                + section_label(f'中国大陆 畅销榜 TOP10 · {date_label}')
                + rank_table(rows_cn_grossing)
            )

            c6 = (
                xhs_h2('05', '本周榜单数据')
                + section_label(f'美国 免费榜 TOP10 · {date_label}')
                + rank_table(rows_us_free)
                + section_label(f'日本 免费榜 TOP10 · {date_label}')
                + rank_table(rows_jp_free)
            )

            c7 = (
                xhs_h2('05', '本周榜单数据')
                + section_label(f'韩国 免费榜 TOP10 · {date_label}')
                + rank_table(rows_kr_free)
                + section_label(f'中国香港 免费榜 TOP10 · {date_label}')
                + rank_table(rows_hk_free)
                + '<div style="margin-top:10px;padding:8px;background-color:#0A1220;border-radius:4px;">'
                + '<div style="font-size:9px;color:#E8820C;font-weight:700;margin-bottom:3px;letter-spacing:1px;">数据说明</div>'
                + '<div style="font-size:10px;color:#7090A0;line-height:1.6;">· 数据来源：七麦数据 App Store<br>'
                + f'· 时间：{date_label}<br>'
                + '· 每行显示该名次一周内出现最多的游戏</div>'
                + '</div>'
            )

            cards_html_list = [
                xhs_card(1, week_tag,    c1),
                xhs_card(2, '大事件②',   c2),
                xhs_card(3, '开发者动态', c3),
                xhs_card(4, '新游速递',   c4),
                xhs_card(5, '大陆榜单',   c5),
                xhs_card(6, '美日榜单',   c6),
                xhs_card(7, '港韩榜单',   c7),
            ]
        except Exception as e:
            logger.error("小红书卡片生成失败: %s", e, exc_info=True)
            xhs_error = str(e)
    else:
        xhs_error = "未提供 Excel 路径或文件不存在，小红书榜单卡片无法生成"
        logger.warning(xhs_error)

    # 无论 XHS 是否有榜单数据，都写文件（可能只有文字卡片）
    if not cards_html_list:
        # 最低限度：生成纯文字卡片
        cards_html_list = [
            xhs_card(1, week_tag, xhs_h2('01', '游戏行业周报') + xhs_para('Excel 文件未提供，请在主程序中上传榜单数据后重新生成。'))
        ]

    xhs_html = build_xhs_html(cards_html_list)
    xhs_out = _os.path.join(_os.path.dirname(__file__), "static", "output_xhs.html")
    with open(xhs_out, "w", encoding="utf-8") as f:
        f.write(xhs_html)
    logger.info("小红书版已生成: %d chars -> %s", len(xhs_html), xhs_out)

    result = {
        "status": "ok",
        "wechat_url": "/output/wechat",
        "xhs_url": "/output/xhs",
        "wechat_chars": len(wechat_html),
        "xhs_chars": len(xhs_html),
    }
    if xhs_error:
        result["xhs_warning"] = xhs_error
    return jsonify(result)


@app.route("/api/rewrite_single_news", methods=["POST"])
def rewrite_single_news_api():
    """改写单条新闻，支持手动来源（URL 或纯文本）。
    请求体: {
        title: str, content: str, url: str,
        fetch_sources: bool,           # 是否自动搜索
        manual_sources: [              # 手动添加来源（最多3条）
            {type: "url"|"text", value: str},
            ...
        ]
    }
    """
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    original = (data.get("content") or title)
    item_url = data.get("url") or ""
    do_fetch = bool(data.get("fetch_sources", True))
    manual_sources_raw = data.get("manual_sources") or []

    if not title and not original:
        return jsonify({"status": "error", "message": "内容不能为空"}), 400

    extra = []

    # 1. 处理手动来源（URL 抓取 或 直接文本）
    from scrapers.source_finder import fetch_url_content
    for ms in manual_sources_raw[:3]:
        ms_type = ms.get("type", "text")
        ms_val = (ms.get("value") or "").strip()
        if not ms_val:
            continue
        if ms_type == "url" and ms_val.startswith("http"):
            fetched = fetch_url_content(ms_val)
            if fetched.get("content"):
                extra.append(fetched)
        elif ms_type == "text" and len(ms_val) > 20:
            extra.append({"title": "用户提供文本", "url": "", "domain": "", "content": ms_val})

    # 2. 自动搜索补充（如果手动来源不足3条且开启了自动搜索）
    if do_fetch and len(extra) < 3 and title:
        try:
            from scrapers.source_finder import find_related_sources
            auto = find_related_sources(title, num=3 - len(extra))
            extra.extend(auto)
        except Exception as e:
            logger.warning("自动搜索来源失败 [%s]: %s", title, e)

    try:
        rewritten = rewrite_news_item(title, original, extra_sources=extra if extra else None)
        return jsonify({
            "status": "ok",
            "url": item_url,
            "title": title,
            "rewritten": rewritten,
            "sources_used": len(extra),
            "sources_found": [{"title": s.get("title",""), "url": s.get("url","")} for s in extra],
        })
    except Exception as e:
        logger.error("单条改写失败 [%s]: %s", title, e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/rewrite_weekly_news", methods=["POST"])
def rewrite_weekly_news_api():
    """批量改写周报新闻条目为专业资讯（搜索额外来源融合降重）。
    请求体: { items: [{title, url, content, channel}, ...], fetch_sources: bool }
    返回: { results: [{url, rewritten}, ...] }
    """
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    do_fetch = bool(data.get("fetch_sources", True))

    if not items:
        return jsonify({"status": "error", "message": "没有待改写的新闻"}), 400

    results = []

    def _process_one(item):
        title = (item.get("title") or "").strip()
        original = (item.get("content") or title)
        url = item.get("url") or ""
        extra = []
        if do_fetch and title:
            try:
                from scrapers.source_finder import find_related_sources
                extra = find_related_sources(title, num=3)
            except Exception as e:
                logger.warning("搜索额外来源失败 [%s]: %s", title, e)
        try:
            rewritten = rewrite_news_item(title, original, extra_sources=extra)
        except Exception as e:
            logger.error("改写失败 [%s]: %s", title, e)
            rewritten = f"## {title}\n\n{original}"
        return {"url": url, "title": title, "rewritten": rewritten}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_process_one, it) for it in items[:20]]
        results = [f.result() for f in futures]

    return jsonify({"status": "ok", "results": results})


# ==================== 微信公众号发布 ====================


# ==================== 自由撰写 ====================


@app.route("/freewrite")
def freewrite_page():
    return render_template("freewrite.html")


# ==================== 游戏评测聚合 ====================


@app.route("/review")
def review_page():
    return render_template("review.html")


@app.route("/api/search_reviews", methods=["POST"])
def search_reviews_api():
    """搜索多来源游戏评测文章。"""
    data = request.get_json(force=True) or {}
    game_name = (data.get("game_name") or "").strip()
    if not game_name:
        return jsonify({"status": "error", "message": "请输入游戏名称"}), 400
    try:
        results = search_game_reviews(game_name, per_source=2)
        return jsonify({"status": "ok", "results": results, "total": len(results)})
    except Exception as e:
        logger.error("评测搜索失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/steam_search", methods=["POST"])
def steam_search_api():
    """在 Steam 搜索游戏，返回 [{appid, name, image}]。"""
    data = request.get_json(force=True) or {}
    name = (data.get("game_name") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "游戏名不能为空"}), 400
    try:
        from scrapers.steam_reviews import search_steam_game
        games = search_steam_game(name)
        return jsonify({"status": "ok", "games": games})
    except Exception as e:
        logger.error("Steam 搜索失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/steam_reviews", methods=["POST"])
def steam_reviews_route():
    """抓取 Steam 指定游戏的玩家评论，返回 {summary, reviews, formatted}。"""
    data  = request.get_json(force=True) or {}
    appid = (data.get("appid") or "").strip()
    name  = (data.get("name")  or "").strip()
    if not appid:
        return jsonify({"status": "error", "message": "appid 不能为空"}), 400
    try:
        from scrapers.steam_reviews import fetch_steam_reviews, format_for_ai
        from qwen_client import analyze_steam_reviews
        result    = fetch_steam_reviews(appid, max_pages=3)
        formatted = format_for_ai(name, appid, result["summary"], result["reviews"])
        analysis  = analyze_steam_reviews(name, formatted)
        return jsonify({"status": "ok", "summary": result["summary"],
                        "reviews": result["reviews"], "formatted": formatted,
                        "analysis": analysis})
    except Exception as e:
        logger.error("Steam 评论抓取失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/generate_review", methods=["POST"])
def generate_review_api():
    """融合多来源评测 + 用户观点，生成新的评测文章，存入 TTL store 返回 token。"""
    data = request.get_json(force=True) or {}
    game_name   = (data.get("game_name")    or "").strip()
    sources     = data.get("sources")       or []
    user_opinion = (data.get("user_opinion") or "").strip()

    if not game_name or not sources:
        return jsonify({"status": "error", "message": "缺少游戏名或来源内容"}), 400

    try:
        article = generate_game_review(game_name, sources, user_opinion)

        title_field = f"【游戏评测】{game_name}"[:20]

        token = uuid.uuid4().hex
        _xhs_store.set(token, {
            "title":       title_field,
            "content":     article,
            "body_images": {},
            "tag":         "游戏雷达局",
        })
        return jsonify({"status": "ok", "article": article, "token": token})
    except Exception as e:
        logger.error("评测生成失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/store_article", methods=["POST"])
def store_article_api():
    """直接存入已生成的文章内容，返回 token 供跳转 xhs_full 页面。"""
    data    = request.get_json(force=True) or {}
    title   = (data.get("title")   or "").strip()
    content = (data.get("content") or "").strip()
    tag     = (data.get("tag")     or "游戏雷达局").strip()
    if not content:
        return jsonify({"status": "error", "message": "content 不能为空"}), 400
    body_images = data.get("body_images") or {}
    image_b64   = (data.get("image_b64") or "").strip()
    style       = (data.get("style")     or "").strip()
    token = uuid.uuid4().hex
    payload = {"title": title, "content": content, "body_images": body_images, "tag": tag}
    if image_b64:
        payload["image_b64"] = image_b64
    if style:
        payload["style"] = style
    _xhs_store.set(token, payload)
    return jsonify({"status": "ok", "token": token})


@app.route("/api/generate_deep_review", methods=["POST"])
def generate_deep_review_api():
    """深度评测长文：批量抓取 Steam 评论 + 媒体来源 → 2500-4000 字长文。"""
    data         = request.get_json(force=True) or {}
    appid        = (data.get("appid")        or "").strip()
    game_name    = (data.get("game_name")    or "").strip()
    sources      = data.get("sources")       or []
    user_opinion = (data.get("user_opinion") or "").strip()

    if not game_name:
        return jsonify({"status": "error", "message": "缺少游戏名"}), 400

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from scrapers.steam_reviews import fetch_steam_reviews_bulk, build_stats_block, chunk_reviews
        from qwen_client import generate_deep_review, summarize_review_batch

        steam_stats  = ""
        sample_count = 0
        batch_summaries = []

        if appid:
            logger.info("深度评测：批量抓取 Steam 评论 appid=%s（最大 50+10 页）", appid)
            result       = fetch_steam_reviews_bulk(appid)   # 默认 helpful_pages=50, recent_pages=10
            sample_count = result["sample_count"]
            steam_stats  = build_stats_block(game_name, result["summary"], result["reviews"])
            logger.info("深度评测：抓取完成，样本 %d 条，开始并发批次摘要…", sample_count)

            # Map 阶段：每 100 条一批，最多 5 个并发
            chunks = chunk_reviews(result["reviews"], size=100)
            batch_summaries = [None] * len(chunks)
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {
                    pool.submit(summarize_review_batch, game_name, chunk, i): i
                    for i, chunk in enumerate(chunks)
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        batch_summaries[idx] = future.result()
                    except Exception as be:
                        logger.warning("批次 %d 摘要失败: %s", idx, be)
                        batch_summaries[idx] = ""
            logger.info("深度评测：批次摘要完成（%d 批），开始生成长文…", len(chunks))

        # Reduce 阶段：合并摘要 + 媒体来源 → 长文
        article = generate_deep_review(game_name, steam_stats, batch_summaries, sources, user_opinion)

        token = uuid.uuid4().hex
        _xhs_store.set(token, {
            "title":       f"【深度评测】{game_name}"[:20],
            "content":     article,
            "body_images": {},
            "tag":         "游戏雷达局",
            "desc":        f"#游戏评测# #深度评测# #游戏推荐# #游戏雷达局# #{game_name}#",
        })
        return jsonify({"status": "ok", "article": article, "token": token,
                        "sample_count": sample_count, "batch_count": len(batch_summaries)})
    except Exception as e:
        logger.error("深度评测生成失败: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== 启动 ====================


@app.route("/video")
def video_page():
    return render_template("video.html")


@app.route("/deals_video")
def deals_video_page():
    """Steam 折扣盘点视频生成页面"""
    return render_template("deals_video.html")


@app.route("/api/video_pipeline", methods=["POST"])
def video_pipeline_api():
    """触发视频生成流水线，返回 task_id。"""
    from video_pipeline import run_video_pipeline
    data = request.get_json(force=True) or {}
    game_name   = (data.get("game_name") or "").strip() or "原神"
    content     = (data.get("content") or "").strip()
    pv_url      = (data.get("pv_url") or "").strip()
    duration    = int(data.get("duration_secs") or 60)
    xhs_cookie  = (data.get("xhs_cookie") or "").strip()
    segment_images = data.get("segment_images") or []
    voice = (data.get("voice") or "zh-CN-XiaoxiaoNeural").strip()
    bgm_b64 = (data.get("bgm_b64") or "").strip()
    bgm_volume = float(data.get("bgm_volume") or 0.15)
    bgm_volume = max(0.0, min(1.0, bgm_volume))
    tts_volume = float(data.get("tts_volume") or 1.0)
    tts_volume = max(0.1, min(2.0, tts_volume))
    pv_local_path = (data.get("pv_local_path") or "").strip()
    yt_cookies = (data.get("yt_cookies") or "").strip()
    if not content:
        return jsonify({"status": "error", "message": "请提供内容文案"}), 400
    task_id = run_video_pipeline(
        game_name=game_name,
        content=content,
        pv_url=pv_url,
        duration_secs=duration,
        xhs_cookie=xhs_cookie,
        segment_images=segment_images,
        voice=voice,
        bgm_b64=bgm_b64,
        bgm_volume=bgm_volume,
        pv_local_path=pv_local_path,
        yt_cookies=yt_cookies,
        tts_volume=tts_volume,
    )
    return jsonify({"status": "ok", "task_id": task_id})



@app.route("/api/game_promo_script", methods=["POST"])
def game_promo_script_api():
    """
    只生成游戏推荐文案（不生成视频），供用户预览/编辑后再决定是否生成视频。
    返回: {status, script, steam_info}
    """
    from video_pipeline import _fetch_steam_info, _search_game_reviews, _generate_promo_script
    data = request.get_json(force=True) or {}
    steam_url = (data.get("steam_url") or "").strip()
    if not steam_url:
        return jsonify({"status": "error", "message": "请提供 steam_url"}), 400
    game_name_hint = (data.get("game_name") or "").strip()
    try:
        steam_info = _fetch_steam_info(steam_url)
        game_name = steam_info.get("game_name") or game_name_hint or "未知游戏"
        review_summary = _search_game_reviews(game_name, steam_url)
        script_text = _generate_promo_script(steam_info, review_summary)
        if not script_text:
            return jsonify({"status": "error", "message": "AI 未能生成文案，请重试"}), 500
        return jsonify({
            "status": "ok",
            "script": script_text,
            "game_name": game_name,
            "steam_info": {
                "game_name": game_name,
                "description": steam_info.get("description", ""),
                "release_date": steam_info.get("release_date", ""),
                "is_free": steam_info.get("is_free", False),
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/game_promo", methods=["POST"])
def game_promo_api():
    """
    一键游戏推荐视频接口。
    只需提供 steam_url，自动完成全套工作流（爬取→搜索→脚本→PV→合成→水印）。
    可选：game_name（提示名），voice，bgm_volume，tts_volume，tts_rate，script_override（用户确认后的文案）
    """
    from video_pipeline import run_game_promo_pipeline
    data = request.get_json(force=True) or {}
    steam_url = (data.get("steam_url") or "").strip()
    if not steam_url:
        return jsonify({"status": "error", "message": "请提供 steam_url"}), 400
    game_name_hint  = (data.get("game_name") or "").strip()
    voice           = (data.get("voice") or "zh-CN-YunxiNeural").strip()
    bgm_volume      = float(data.get("bgm_volume") or 0.12)
    tts_volume      = float(data.get("tts_volume") or 1.0)
    tts_rate        = (data.get("tts_rate") or "+30%").strip()
    script_override = (data.get("script_override") or "").strip()
    task_id = run_game_promo_pipeline(
        steam_url=steam_url,
        game_name_hint=game_name_hint,
        voice=voice,
        bgm_volume=bgm_volume,
        tts_volume=tts_volume,
        tts_rate=tts_rate,
        script_override=script_override,
    )
    return jsonify({"status": "ok", "task_id": task_id})


@app.route("/api/video_status/<task_id>", methods=["GET"])
def video_status_api(task_id: str):
    """查询视频流水线任务状态。"""
    from video_pipeline import get_task_status
    info = get_task_status(task_id)
    if not info:
        return jsonify({"status": "error", "message": "task_id 不存在"}), 404
    return jsonify({"status": "ok", "task": info})


@app.route("/video_outputs/<task_id>/final_output.mp4", methods=["GET"])
def serve_video_output(task_id: str):
    """下载生成完成的视频文件。"""
    from video_pipeline import VIDEO_OUTPUT_DIR
    path = VIDEO_OUTPUT_DIR / task_id / "final_output.mp4"
    if not path.exists():
        return jsonify({"status": "error", "message": "文件不存在"}), 404
    return send_file(str(path), mimetype="video/mp4", as_attachment=True,
                     download_name=f"video_{task_id[:8]}.mp4")


@app.route("/api/trending_score", methods=["POST"])
def trending_score_api():
    """对内容列表进行规则打分（不消耗 API），返回附有 trending_score/reason 的列表。"""
    from trending_scorer import score_items
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"status": "ok", "items": []})
    scored = score_items(items)
    return jsonify({"status": "ok", "items": scored})


@app.route("/api/trending_rank", methods=["POST"])
def trending_rank_api():
    """AI 精排：对规则分 >=40 的内容进行 Qwen 传播潜力排序，返回 Top5 附推荐理由。"""
    from qwen_client import rank_trending_items
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    # 仅取规则分较高的条目
    candidates = [it for it in items if (it.get("trending_score") or 0) >= 40]
    if not candidates:
        candidates = items[:20]
    try:
        ranked = rank_trending_items(candidates)
        return jsonify({"status": "ok", "items": ranked[:5]})
    except Exception as e:
        logger.error("trending_rank 失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/search_pv", methods=["POST"])
def search_pv_api():
    """搜索游戏官方 PV：B 站优先 → YouTube 备选。"""
    from scrapers.pv_downloader import search_game_pv_auto
    data = request.get_json(force=True) or {}
    game_name = (data.get("game_name") or "").strip()
    if not game_name:
        return jsonify({"status": "error", "message": "请提供游戏名称"}), 400
    try:
        url, source = search_game_pv_auto(game_name)
        return jsonify({"status": "ok", "url": url or "", "source": source})
    except Exception as e:
        logger.error("search_pv 失败: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/verify_pv", methods=["POST"])
def verify_pv_api():
    """用 yt-dlp 验证 PV 链接是否可访问，返回视频标题和时长。"""
    import subprocess
    from scrapers.pv_downloader import _base_ytdlp_cmd
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    yt_cookies = (data.get("yt_cookies") or "").strip()
    if not url:
        return jsonify({"status": "error", "message": "请提供 URL"}), 400
    # 用 -f all --no-download 获取元数据（不触发格式选择失败）
    cmd = _base_ytdlp_cmd([
        "--no-playlist", "--quiet",
        "-f", "all",
        "--no-download",
        "--print", "%(title)s|||%(duration)s",
        url,
    ], cookies_content=yt_cookies or None)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if result.returncode != 0:
            err = (result.stderr or "").strip()[:300] or "链接无法访问或视频不存在"
            if "Sign in" in err or "bot" in err:
                err = "YouTube 需要登录验证（bot检测）。请在左侧「YouTube Cookie」栏粘贴 Cookie 后重新验证。"
            elif "No supported JavaScript" in err:
                err = "yt-dlp 需要 Node.js 支持，已检测到 Node 但仍失败，请检查 cookies 配置。"
            elif "unavailable" in err.lower() or "not available" in err.lower():
                err = "该视频不可用（可能受地区限制或已下线）。"
            return jsonify({"status": "error", "message": err})
        # 取第一行（-f all 时每个格式输出一行，内容相同）
        line = (result.stdout or "").strip().splitlines()[0] if result.stdout.strip() else ""
        if "|||" in line:
            title, dur_str = line.split("|||", 1)
            try:
                secs = int(float(dur_str))
                duration_str = f"{secs // 60}:{secs % 60:02d}"
            except Exception:
                duration_str = dur_str
            return jsonify({"status": "ok", "title": title.strip(), "duration": duration_str})
        return jsonify({"status": "ok", "title": url, "duration": ""})
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "验证超时（35s），请检查网络或尝试其他链接"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/upload_pv", methods=["POST"])
def upload_pv_api():
    """接收本地视频文件上传，保存到 video_outputs/uploads/，返回服务器路径。"""
    from pathlib import Path
    f = request.files.get("file")
    if not f:
        return jsonify({"status": "error", "message": "未收到文件"}), 400
    upload_dir = Path(__file__).parent / "video_outputs" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    import uuid
    ext = Path(f.filename).suffix.lower() or ".mp4"
    save_path = upload_dir / f"{uuid.uuid4().hex[:8]}{ext}"
    f.save(str(save_path))
    return jsonify({"status": "ok", "path": str(save_path)})


@app.route("/api/deals_video", methods=["POST"])
def deals_video_api():
    """启动 Steam 折扣盘点视频流水线，返回 task_id。"""
    from video_pipeline import run_deals_video_pipeline
    data = request.get_json(force=True) or {}
    deals = data.get("deals") or []
    voice = (data.get("voice") or "zh-CN-YunxiNeural").strip()
    bgm_volume = float(data.get("bgm_volume") or 0.12)
    bgm_volume = max(0.0, min(1.0, bgm_volume))
    if not deals:
        return jsonify({"status": "error", "message": "请至少提供一款折扣游戏"}), 400
    task_id = run_deals_video_pipeline(deals=deals, voice=voice, bgm_volume=bgm_volume)
    return jsonify({"status": "ok", "task_id": task_id})


@app.route("/api/deals_video_resume", methods=["POST"])
def deals_video_resume_api():
    """用户补充缺失PV后继续折扣盘点流水线。"""
    from video_pipeline import resume_deals_video_pipeline
    data = request.get_json(force=True) or {}
    task_id = (data.get("task_id") or "").strip()
    pv_map  = data.get("pv_map") or {}   # {game_title: server_file_path}
    if not task_id:
        return jsonify({"status": "error", "message": "缺少 task_id"}), 400
    ok = resume_deals_video_pipeline(task_id, pv_map)
    if not ok:
        return jsonify({"status": "error", "message": "任务不存在或不处于 waiting_pv 状态"}), 400
    return jsonify({"status": "ok", "task_id": task_id})



# ==================== 🎮 Game AI Demo 路由 ====================


@app.route("/game_demo")
def game_demo_page():
    """AI 游戏试玩 Demo 页面"""
    return render_template("game_demo.html")


@app.route("/api/game_demo/start", methods=["POST"])
def api_game_demo_start():
    """启动 AI 试玩流水线任务。"""
    data = request.get_json(force=True) or {}
    game_config = data.get("game_config")
    options = data.get("options", {})
    if not game_config:
        return jsonify({"error": "缺少 game_config"}), 400
    if not game_config.get("name"):
        return jsonify({"error": "game_config.name 不能为空"}), 400
    try:
        runner = _get_game_runner()
        task_id = runner.start(game_config, options)
        return jsonify({"task_id": task_id, "status": "started"})
    except Exception as e:
        logger.exception("game_demo start error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/game_demo/status/<task_id>")
def api_game_demo_status(task_id: str):
    """轮询任务进度。"""
    task = get_demo_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


@app.route("/api/game_demo/list")
def api_game_demo_list():
    """列出所有任务。"""
    return jsonify(list_demo_tasks())


@app.route("/api/game_demo/stop/<task_id>", methods=["POST"])
def api_game_demo_stop(task_id: str):
    """发送停止信号（标记任务错误，后台线程会在下一个安全点退出）。"""
    from game_ai.runner import _update
    _update(task_id, status="error", error="用户手动停止")
    return jsonify({"ok": True})


@app.route("/api/game_demo/frame/<task_id>/<int:frame_idx>")
def api_game_demo_frame(task_id: str, frame_idx: int):
    """获取指定任务的关键帧图片。"""
    task = get_demo_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    frames = task.get("keyframes", [])
    if frame_idx >= len(frames):
        return jsonify({"error": "帧索引越界"}), 404
    frame_path = Path(frames[frame_idx])
    if not frame_path.exists():
        return jsonify({"error": "帧文件不存在"}), 404
    return send_file(str(frame_path), mimetype="image/jpeg")


@app.route("/api/game_demo/video/<task_id>")
def api_game_demo_video(task_id: str):
    """流式提供最终视频（用于前端 video 标签预览）。"""
    task = get_demo_task(task_id)
    if not task or not task.get("final_video"):
        return jsonify({"error": "视频未就绪"}), 404
    video_path = Path(task["final_video"])
    if not video_path.exists():
        return jsonify({"error": "视频文件不存在"}), 404
    return send_file(str(video_path), mimetype="video/mp4", conditional=True)


@app.route("/api/game_demo/download/<task_id>")
def api_game_demo_download(task_id: str):
    """下载最终剪辑视频。"""
    task = get_demo_task(task_id)
    if not task or not task.get("final_video"):
        return jsonify({"error": "视频未就绪"}), 404
    video_path = Path(task["final_video"])
    if not video_path.exists():
        return jsonify({"error": "视频文件不存在"}), 404
    game_name = task.get("game_name", "game").replace(" ", "_")[:30]
    return send_file(
        str(video_path),
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"{game_name}_demo.mp4",
    )


@app.route("/api/game_demo/analysis/<task_id>")
def api_game_demo_analysis(task_id: str):
    """下载 AI 分析 JSON 文件。"""
    from game_ai.runner import DEMO_OUTPUT_DIR
    result_file = DEMO_OUTPUT_DIR / task_id / "analysis_result.json"
    if not result_file.exists():
        # 尝试从内存任务中构建
        task = get_demo_task(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404
        payload = {
            "summary": task.get("summary"),
            "edit_script": task.get("edit_script"),
        }
        return jsonify(payload)
    return send_file(
        str(result_file),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"game_analysis_{task_id[:8]}.json",
    )


@app.route("/api/game_demo/recut", methods=["POST"])
def api_game_demo_recut():
    """使用修改后的剪辑脚本重新执行剪辑步骤。"""
    data = request.get_json(force=True) or {}
    task_id = data.get("task_id", "").strip()
    edit_script = data.get("edit_script")
    if not task_id or not edit_script:
        return jsonify({"error": "缺少 task_id 或 edit_script"}), 400

    task = get_demo_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    raw_video = task.get("raw_video")
    if not raw_video or not Path(raw_video).exists():
        return jsonify({"error": "原始视频不存在，无法重新剪辑"}), 400

    def _recut():
        from game_ai.runner import _update, _log, DEMO_OUTPUT_DIR
        from game_ai.editor import GameVideoEditor
        _update(task_id, status="editing", stage="editing", progress=80, edit_script=edit_script)
        _log(task_id, "🔄 开始重新剪辑（使用修改后的脚本）...")
        work_dir = DEMO_OUTPUT_DIR / task_id / "recut_workspace"
        editor = GameVideoEditor(
            work_dir=work_dir,
            project_root=Path(__file__).parent,
        )
        voice = "zh-CN-XiaoxiaoNeural"
        final = editor.run_full_pipeline(
            source_video=Path(raw_video),
            edit_script=edit_script,
            output_filename="final_demo_recut.mp4",
            voice=voice,
            progress_cb=lambda msg: _log(task_id, msg),
        )
        if final and final.exists():
            _update(task_id, status="done", stage="done", progress=100, final_video=str(final))
            _log(task_id, f"✅ 重新剪辑完成: {final}")
        else:
            _update(task_id, status="error", error="重新剪辑失败")

    import threading
    threading.Thread(target=_recut, daemon=True).start()
    return jsonify({"ok": True})


# ==================== 粉丝打标路由 ====================

@app.route("/fan_tagger")
def fan_tagger_page():
    """小红书粉丝打标页面"""
    return render_template("fan_tagger.html")


@app.route("/api/start_fan_tag", methods=["POST"])
def api_start_fan_tag():
    """启动粉丝爬取打标任务（后台线程）。"""
    data = request.get_json(force=True) or {}
    cookie = (data.get("cookie") or "").strip()
    target_user_id = (data.get("target_user_id") or "59721a7182ec3947669d07be").strip()

    task_id = str(uuid.uuid4())[:8]
    t = threading.Thread(
        target=run_fan_tag_task,
        args=(task_id, cookie, target_user_id),
        daemon=True,
    )
    t.start()
    return jsonify({"ok": True, "task_id": task_id})


@app.route("/api/fan_tag_progress")
def api_fan_tag_progress():
    """轮询粉丝打标任务进度。"""
    task_id = request.args.get("task_id", "").strip()
    if not task_id:
        return jsonify({"error": "缺少 task_id"}), 400
    state = get_task_state(task_id)
    if not state:
        return jsonify({"error": "任务不存在或已过期"}), 404
    return jsonify(state)


@app.route("/api/download_fan_excel")
def api_download_fan_excel():
    """下载最新生成的粉丝打标 Excel 文件。"""
    task_id = request.args.get("task_id", "").strip()
    excel_path = None

    if task_id:
        state = get_task_state(task_id)
        ep = state.get("excel_path")
        if ep:
            excel_path = Path(ep)

    # 如果没有从状态获取，则找最新的 Excel
    if not excel_path or not excel_path.exists():
        files = sorted(FAN_TAG_OUTPUT_DIR.glob("粉丝打标_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return jsonify({"error": "Excel 文件不存在，请先完成打标任务"}), 404
        excel_path = files[0]

    return send_file(
        str(excel_path),
        as_attachment=True,
        download_name=excel_path.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/fan_tag_manual_done", methods=["POST"])
def api_fan_tag_manual_done():
    """用户确认已完成手动滚动操作。"""
    data = request.get_json(force=True) or {}
    task_id = data.get("task_id", "").strip()
    if not task_id:
        return jsonify({"error": "缺少 task_id"}), 400
    from scrapers.fan_tagger import _set_state
    _set_state(task_id, manual_done=True)
    return jsonify({"ok": True})


@app.route("/api/fan_tag_probe", methods=["POST"])
def api_fan_tag_probe():
    """调试接口：在当前已登录的 Chrome 里探测 API 路径，直接返回结果。"""
    from scrapers.fan_tagger import _task_state
    # 找一个已有 session 的 task（最近运行过的）
    import asyncio, json as _json
    result = {}
    try:
        # 找最近的 running/done 任务的 task_id（有 Chrome 窗口的）
        for tid, state in _task_state.items():
            if state.get("stage") in ("fetch_detail", "ai_tag", "export", "done"):
                result["found_task"] = tid
                result["stage"] = state.get("stage")
                break
        result["message"] = "请重新启动任务来探测，或直接查看日志"
    except Exception as e:
        result["error"] = str(e)
    return jsonify(result)


@app.route("/api/fan_tag_clear_cache", methods=["POST"])
def api_fan_tag_clear_cache():
    """清除断点缓存文件。"""
    try:
        if FAN_TAG_CACHE_FILE.exists():
            FAN_TAG_CACHE_FILE.unlink()
            return jsonify({"ok": True, "message": "断点缓存已清除，下次将从头开始爬取"})
        return jsonify({"ok": True, "message": "缓存文件不存在，无需清除"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def open_browser():
    url = f"http://localhost:{APP_PORT}"
    logger.info("Opening browser: %s", url)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info(" 内容监控面板启动中: http://localhost:%s", APP_PORT)
    logger.info("=" * 60)
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
