"""Reddit 帖子 + 评论抓取（通过 PRAW + Reddit OAuth，需配置 API 凭证）。

配置方式：在项目根目录创建 .env 文件，或设置系统环境变量：
    REDDIT_CLIENT_ID      = 你的 Reddit App client_id
    REDDIT_CLIENT_SECRET  = 你的 Reddit App client_secret
    REDDIT_USER_AGENT     = 随意，如 "content-monitor:v1 (by /u/你的用户名)"

获取凭证：
    1. 登录 Reddit，访问 https://www.reddit.com/prefs/apps
    2. 点击「create another app」→ 选 script → 随便填名称和 redirect_uri
    3. 创建后左上方 14 位字符串 = client_id，secret = client_secret
"""

import logging
import os

logger = logging.getLogger(__name__)

# 尝试从 .env 文件加载（python-dotenv 可选）
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass


def _get_reddit():
    """懒加载 PRAW Reddit 只读客户端。返回 None 表示未配置。"""
    try:
        import praw
        client_id     = os.getenv("REDDIT_CLIENT_ID",     "").strip()
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        user_agent    = os.getenv("REDDIT_USER_AGENT",    "content-monitor:v1 (personal)").strip()
        if not client_id or not client_secret:
            return None
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        logger.warning("PRAW 初始化失败: %s", e)
        return None


def fetch_post_and_comments(url: str, limit: int = 10) -> dict:
    """通过 PRAW 抓取帖子基本信息 + 高赞顶级评论（按分数降序）。

    Returns:
        {
            "post":     {title, score, num_comments, subreddit, author, url},
            "comments": [{author, score, body}]  最多 limit 条
        }

    Raises:
        RuntimeError: PRAW 未配置 或 请求失败
    """
    reddit = _get_reddit()
    if reddit is None:
        raise RuntimeError(
            "Reddit API 未配置，请按以下步骤操作：\n"
            "① 访问 https://www.reddit.com/prefs/apps\n"
            "② 点击「create another app」→ 选 script\n"
            "③ 创建后把 client_id 和 client_secret 填入项目根目录的 .env 文件：\n"
            "   REDDIT_CLIENT_ID=xxxxxx\n"
            "   REDDIT_CLIENT_SECRET=xxxxxx\n"
            "④ 重启服务"
        )

    try:
        submission = reddit.submission(url=url)

        post = {
            "title":        submission.title,
            "score":        submission.score,
            "num_comments": submission.num_comments,
            "subreddit":    submission.subreddit.display_name,
            "author":       str(submission.author) if submission.author else "[deleted]",
            "url":          url,
        }

        # 只取顶级评论，不展开 MoreComments
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)

        comments = []
        for c in submission.comments:
            body = (getattr(c, "body", "") or "").strip()
            if not body or body in ("[deleted]", "[removed]"):
                continue
            comments.append({
                "author": str(c.author) if c.author else "[deleted]",
                "score":  c.score,
                "body":   body,
            })

        comments.sort(key=lambda x: x.get("score", 0), reverse=True)
        return {"post": post, "comments": comments[:limit]}

    except Exception as e:
        logger.error("Reddit 帖子抓取失败 url=%s: %s", url, e)
        raise RuntimeError(str(e)) from e
