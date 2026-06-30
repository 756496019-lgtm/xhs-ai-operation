"""PV/宣传片下载封装：使用 yt-dlp 下载游戏官方视频。"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BILIBILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json",
}

# cookies.txt 默认路径（Netscape 格式，可通过环境变量覆盖）
_DEFAULT_COOKIES_FILE = Path(__file__).parent.parent / "youtube_cookies.txt"


def _write_cookies_tempfile(cookies_content: str) -> Optional[Path]:
    """
    将 cookie 字符串写入 Netscape 格式临时文件。
    支持两种输入：
      - 已是 Netscape 格式（以 # Netscape HTTP Cookie File 开头）：直接写入
      - HTTP header 格式（name=value; name2=value2 ...）：自动转换为 Netscape 格式

    YouTube cookie 注意事项：
      - __Secure- 前缀的 cookie 只属于 .youtube.com，不写到 .google.com
      - SAPISID / APISID / HSID / SSID / SID 系列同时写给 .youtube.com 和 .google.com
      - __Secure-1PSIDTS 是 YouTube bot 验证的关键 cookie，必须正确写入
    """
    import tempfile, time
    try:
        content = cookies_content.strip()
        if not content:
            return None

        if content.startswith("# Netscape HTTP Cookie File"):
            netscape = content
        else:
            lines = [
                "# Netscape HTTP Cookie File",
                "# https://curl.haxx.se/rfc/cookie_spec.html",
                "# This is a generated file! Do not edit.",
                "",
            ]
            expire = int(time.time()) + 86400 * 365

            # 哪些 cookie 需要同时写给 .google.com
            GOOGLE_ALSO = {"HSID", "SSID", "APISID", "SAPISID", "SID",
                           "LSID", "NID", "PREF", "1P_JAR"}

            for pair in content.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                name, _, value = pair.partition("=")
                name = name.strip()
                value = value.strip()
                if not name:
                    continue

                # __Secure- 前缀 cookie 只写 .youtube.com
                lines.append(f".youtube.com\tTRUE\t/\tTRUE\t{expire}\t{name}\t{value}")

                # 部分 cookie 同时写给 google.com（登录态共享）
                base_name = name.lstrip("_").replace("Secure-", "").replace("3P", "").replace("1P", "")
                if base_name in GOOGLE_ALSO or name in GOOGLE_ALSO:
                    lines.append(f".google.com\tTRUE\t/\tTRUE\t{expire}\t{name}\t{value}")

            netscape = "\n".join(lines) + "\n"

        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
        os.write(fd, netscape.encode("utf-8"))
        os.close(fd)
        return Path(tmp_path)
    except Exception as e:
        logger.warning("写入临时 cookies 文件失败: %s", e)
        return None


_BGUTIL_SCRIPT = Path.home() / "bgutil-ytdlp-pot-provider" / "server" / "build" / "generate_once.js"


def _get_pot_extractor_args() -> Optional[str]:
    """
    尝试通过 bgutil generate_once.js 获取 YouTube PO Token。
    需要已安装 bgutil-ytdlp-pot-provider 并编译好 server/build/generate_once.js。
    返回 --extractor-args 的值字符串，或 None（若 bgutil 不可用）。
    """
    import shutil, json, subprocess as _sp
    node_path = shutil.which("node")
    if not node_path or not _BGUTIL_SCRIPT.exists():
        return None
    try:
        r = _sp.run([node_path, str(_BGUTIL_SCRIPT)], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout.strip())
        potoken = data.get("poToken", "")
        visitor_data = data.get("contentBinding", "")
        if potoken:
            logger.debug("bgutil PO Token 获取成功")
            return f"youtube:player_client=web;po_token=web+{potoken};visitor_data={visitor_data}"
    except Exception as e:
        logger.debug("bgutil PO Token 获取失败: %s", e)
    return None


def _base_ytdlp_cmd(extra_args: list = None, cookies_content: str = None) -> list:
    """
    构造基础 yt-dlp 命令，自动加入：
    - --extractor-args youtube:player_client=tv_embedded,web （绕过 bot 检测）
    - --cookies（优先级：传入的 cookies_content > 环境变量 YTDLP_COOKIES_FILE > 默认路径）
    - YTDLP_COOKIES_BROWSER 环境变量：指定浏览器名称（chrome/firefox/edge），用 --cookies-from-browser
    - --extractor-args with PO Token（若 bgutil 可用，覆盖为 web client + token）
    """
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings"]

    # 默认使用 tv_embedded client，不需要 PO Token，绕过 bot 检测
    # 若 bgutil 可用则覆盖为 web + potoken（画质更好）
    pot_args = _get_pot_extractor_args()
    if pot_args:
        cmd += ["--extractor-args", pot_args]
    else:
        cmd += ["--extractor-args", "youtube:player_client=tv_embedded,web"]

    # cookies：优先使用调用方传入的内容（写临时文件）
    if cookies_content and cookies_content.strip():
        tmp = _write_cookies_tempfile(cookies_content)
        if tmp:
            cmd += ["--cookies", str(tmp)]
            logger.debug("使用传入 cookies 临时文件: %s", tmp)
            if extra_args:
                cmd += extra_args
            return cmd

    # 退回1：环境变量指定 cookies 文件
    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "") or str(_DEFAULT_COOKIES_FILE)
    if cookies_file and Path(cookies_file).exists():
        cmd += ["--cookies", cookies_file]
        logger.debug("使用 cookies 文件: %s", cookies_file)
    else:
        # 退回2：环境变量指定浏览器（需要浏览器未运行）
        browser = os.getenv("YTDLP_COOKIES_BROWSER", "")
        if browser:
            cmd += ["--cookies-from-browser", browser]
            logger.debug("使用浏览器 cookies: %s", browser)
        else:
            logger.debug("未找到 cookies，YouTube 可能被 bot 验证拦截")

    if extra_args:
        cmd += extra_args
    return cmd


def download_pv(
    url: str,
    output_dir: str | Path,
    filename_stem: str = "pv",
    max_duration_secs: int = 120,
    preferred_quality: str = "720",
    cookies_content: str = None,
) -> Optional[Path]:
    """
    使用 yt-dlp 下载 YouTube/Bilibili 视频。

    cookies_content: 可选，YouTube cookie 文本（Netscape 格式或 header 格式），
                     优先于本地 cookies 文件。

    Returns:
        下载完成的 mp4 文件 Path，失败返回 None。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_tmpl = str(output_dir / f"{filename_stem}.%(ext)s")

    cmd = _base_ytdlp_cmd([
        "--no-playlist",
        "--quiet",
        "-f", f"bestvideo[height<={preferred_quality}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={preferred_quality}]+bestaudio/bestvideo+bestaudio/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--match-filter", f"duration <= {max_duration_secs}",
        "-o", output_tmpl,
        url,
    ], cookies_content=cookies_content)

    logger.info("yt-dlp 下载: %s", url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning("yt-dlp 下载失败 (code=%d): %s", result.returncode, result.stderr[:300])
            return None
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp 下载超时")
        return None
    except Exception as e:
        logger.error("yt-dlp 执行异常: %s", e)
        return None

    for ext in ["mp4", "mkv", "webm"]:
        candidate = output_dir / f"{filename_stem}.{ext}"
        if candidate.exists():
            logger.info("下载完成: %s", candidate)
            return candidate

    for f in sorted(output_dir.glob(f"{filename_stem}.*")):
        if f.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            return f

    logger.warning("yt-dlp 完成但未找到输出文件 (stem=%s)", filename_stem)
    return None


def search_game_pv_bilibili(game_name: str) -> Optional[str]:
    """
    在 Bilibili 搜索游戏宣传片，返回第一条结果的 URL。

    Returns:
        Bilibili 视频 URL 或 None。
    """
    query = f"{game_name} 官方PV 宣传片"
    params = {
        "search_type": "video",
        "keyword": query,
        "page": 1,
        "pagesize": 5,
        "order": "totalrank",
        "duration": 2,  # 时长 1-10 分钟
    }
    try:
        resp = requests.get(
            _BILIBILI_SEARCH_API, params=params, headers=_HEADERS, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        videos = data.get("data", {}).get("result") or []
        for v in videos:
            bvid = v.get("bvid") or ""
            if bvid:
                return f"https://www.bilibili.com/video/{bvid}"
    except Exception as e:
        logger.warning("Bilibili 搜索 PV 失败 (%s): %s", game_name, e)
    return None


def search_game_pv_youtube(game_name: str) -> Optional[str]:
    """
    用 yt-dlp ytsearch1: 语法在 YouTube 搜索官方 PV，无需 API Key。
    """
    query = f"{game_name} official trailer PV"
    cmd = _base_ytdlp_cmd([
        "--no-download",
        "--print", "webpage_url",
        "--quiet",
        f"ytsearch1:{query}",
    ])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        url = result.stdout.strip()
        if url.startswith("http"):
            logger.info("YouTube PV 搜索结果 (%s): %s", game_name, url)
            return url
    except subprocess.TimeoutExpired:
        logger.warning("YouTube PV 搜索超时: %s", game_name)
    except Exception as e:
        logger.warning("YouTube PV 搜索失败 (%s): %s", game_name, e)
    return None


def search_game_pv_auto(game_name: str) -> tuple:
    """
    B站优先 → YouTube 备选，自动搜索游戏官方 PV。

    Returns:
        (url: Optional[str], source: str)
        source 为 'bilibili' / 'youtube' / ''
    """
    logger.info("自动搜索 PV: %s，先尝试 B站...", game_name)
    url = search_game_pv_bilibili(game_name)
    if url:
        return url, "bilibili"

    logger.info("B站未找到，尝试 YouTube: %s", game_name)
    url = search_game_pv_youtube(game_name)
    if url:
        return url, "youtube"

    logger.info("B站和 YouTube 均未找到 PV: %s", game_name)
    return None, ""

