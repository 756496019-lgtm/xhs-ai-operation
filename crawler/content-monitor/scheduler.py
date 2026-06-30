"""APScheduler 定时任务管理器：每日自动抓取内容 + 生成视频。"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler = None


def _job_scrape_anime_reddit():
    """每日 09:00：抓取二次元/女性向 Reddit 内容。"""
    try:
        from scrapers.reddit import run_reddit_monitor
        labels = ["otome", "gacha", "hsr", "genshin", "wuwa", "ba"]
        items = run_reddit_monitor(labels, per_label=15)
        logger.info("[定时任务] anime_reddit 抓取完成，共 %d 条", len(items))
    except Exception as e:
        logger.error("[定时任务] anime_reddit 失败: %s", e)


def _job_scrape_weibo():
    """每日 09:30：抓取微博超话内容。"""
    try:
        from scrapers.weibo import run_weibo_monitor
        items = run_weibo_monitor([], per_topic=10)
        logger.info("[定时任务] weibo 抓取完成，共 %d 条", len(items))
    except Exception as e:
        logger.error("[定时任务] weibo 失败: %s", e)


def _job_scrape_bilibili():
    """每日 10:00：抓取 B 站官号动态。"""
    try:
        from scrapers.bilibili import run_bilibili_monitor
        items = run_bilibili_monitor([], per_uid=10)
        logger.info("[定时任务] bilibili 抓取完成，共 %d 条", len(items))
    except Exception as e:
        logger.error("[定时任务] bilibili 失败: %s", e)


def _job_scrape_domestic():
    """每日 10:30：抓取国内手游资讯。"""
    try:
        from scrapers.domestic_games import run_domestic_games_monitor
        items = run_domestic_games_monitor([], per_source=15)
        logger.info("[定时任务] domestic_games 抓取完成，共 %d 条", len(items))
    except Exception as e:
        logger.error("[定时任务] domestic_games 失败: %s", e)


def _job_daily_video():
    """每日 14:00：自动生成视频并上传小红书。"""
    try:
        count = int(os.getenv("VIDEO_DAILY_COUNT", "1"))
        game_name = os.getenv("VIDEO_DEFAULT_GAME", "原神")
        xhs_cookie = os.getenv("VIDEO_XHS_COOKIE", "")

        from scrapers.taptap import fetch_taptap_game_news, TAPTAP_GAMES
        from video_pipeline import run_video_pipeline

        # 找到对应游戏 app_id
        game_key = None
        for k, v in TAPTAP_GAMES.items():
            if v["name"] == game_name:
                game_key = k
                break

        contents = []
        if game_key:
            news = fetch_taptap_game_news(game_key, TAPTAP_GAMES[game_key]["app_id"], game_name, limit=5)
            contents = [n.get("content") or n.get("title") for n in news if n.get("title")]

        if not contents:
            contents = [f"{game_name}最新游戏资讯，精彩不容错过！"]

        for i in range(min(count, len(contents))):
            task_id = run_video_pipeline(
                game_name=game_name,
                content=contents[i],
                pv_url="",
                duration_secs=60,
                xhs_cookie=xhs_cookie,
            )
            logger.info("[定时任务] daily_video 启动任务 %d: task_id=%s", i + 1, task_id)

    except Exception as e:
        logger.error("[定时任务] daily_video 失败: %s", e)


def _job_evening_video():
    """每日 21:00：傍晚高峰期自动生成第二条视频（晚间流量峰值）。"""
    try:
        game_name = os.getenv("VIDEO_DEFAULT_GAME", "原神")
        xhs_cookie = os.getenv("VIDEO_XHS_COOKIE", "")
        if not xhs_cookie:
            logger.info("[定时任务] evening_video 未配置 XHS Cookie，跳过上传")

        from scrapers.weibo import run_weibo_monitor
        from video_pipeline import run_video_pipeline

        # 用微博超话内容作为晚间视频素材
        news = run_weibo_monitor(["genshin", "honkai_star"], per_topic=3)
        content = (news[0].get("content") or news[0].get("title")) if news else f"{game_name}今日资讯"

        task_id = run_video_pipeline(
            game_name=game_name,
            content=content,
            pv_url="",
            duration_secs=60,
            xhs_cookie=xhs_cookie,
        )
        logger.info("[定时任务] evening_video 启动: task_id=%s", task_id)
    except Exception as e:
        logger.error("[定时任务] evening_video 失败: %s", e)


# 任务注册表（供 API 查询）
JOBS = [
    {
        "id": "scrape_anime_reddit",
        "name": "二次元Reddit抓取",
        "func": _job_scrape_anime_reddit,
        "trigger": "cron",
        "hour": 9, "minute": 0,
    },
    {
        "id": "scrape_weibo",
        "name": "微博超话抓取",
        "func": _job_scrape_weibo,
        "trigger": "cron",
        "hour": 9, "minute": 30,
    },
    {
        "id": "scrape_bilibili",
        "name": "B站动态抓取",
        "func": _job_scrape_bilibili,
        "trigger": "cron",
        "hour": 10, "minute": 0,
    },
    {
        "id": "scrape_domestic",
        "name": "国内手游资讯抓取",
        "func": _job_scrape_domestic,
        "trigger": "cron",
        "hour": 10, "minute": 30,
    },
    {
        "id": "daily_video",
        "name": "每日自动生成视频",
        "func": _job_daily_video,
        "trigger": "cron",
        "hour": 14, "minute": 0,
    },
    {
        "id": "evening_video",
        "name": "晚间自动生成视频",
        "func": _job_evening_video,
        "trigger": "cron",
        "hour": 21, "minute": 0,
    },
]


def start_scheduler():
    """启动 APScheduler 后台调度器。"""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except ImportError:
        logger.error("APScheduler 未安装，请执行 pip install APScheduler")
        return

    tz = pytz.timezone("Asia/Shanghai")
    _scheduler = BackgroundScheduler(timezone=tz)

    for job in JOBS:
        _scheduler.add_job(
            job["func"],
            trigger=CronTrigger(
                hour=job["hour"],
                minute=job["minute"],
                timezone=tz,
            ),
            id=job["id"],
            name=job["name"],
            replace_existing=True,
            misfire_grace_time=300,
        )

    _scheduler.start()
    logger.info("定时任务调度器已启动，共 %d 个任务", len(JOBS))


def get_scheduler_status() -> list:
    """返回所有定时任务的状态信息。"""
    result = []
    for job_def in JOBS:
        info = {
            "id": job_def["id"],
            "name": job_def["name"],
            "hour": job_def["hour"],
            "minute": job_def["minute"],
            "next_run": None,
            "running": _scheduler is not None and _scheduler.running,
        }
        if _scheduler:
            try:
                apsjob = _scheduler.get_job(job_def["id"])
                if apsjob and apsjob.next_run_time:
                    info["next_run"] = apsjob.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        result.append(info)
    return result


def trigger_job(job_id: str) -> bool:
    """手动立即触发指定任务。"""
    for job in JOBS:
        if job["id"] == job_id:
            try:
                import threading
                t = threading.Thread(target=job["func"], daemon=True)
                t.start()
                logger.info("手动触发任务: %s", job_id)
                return True
            except Exception as e:
                logger.error("触发任务 %s 失败: %s", job_id, e)
                return False
    logger.warning("未知任务 ID: %s", job_id)
    return False
