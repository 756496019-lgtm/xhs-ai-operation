# benchmark｜对标账号监控（playwright 直驱，零登录）

> 赛题"对标账号监控"能力。不依赖 Agent-Reach / OpenCLI / 任何外部 CLI，自己用 playwright 写。
>
> **不需要登录、不会暴露你的小红书账号。** 用游客（guest）session 就够了。

---

## 已实测跑通

```
[monitor] 提取到笔记 11 条
  样例（前 3 条）:
  - TapTap游戏发布会，50+款游戏即将登场！  (59 赞)
  - 核聚变通关结算！回顾在深圳的精彩瞬间！  (13 赞)
  - 历年评分最高且有手游移植的Top10游戏    (15 赞)
```

监控小红书 TapTap 官方账号（user_id `5b6919dff7e8b96b50ec46bd`），首屏 11 条笔记全部拉到，含标题/点赞/封面/置顶标识。

## 它怎么做到不登录就拉数据的

小红书 web 给未登录访问的用户分配一个**游客 session**：浏览器首次访问 `xiaohongshu.com` 会自动调 `v1/login/qrcode/create` + `v1/login/activate` + `v2/user/me`，拿到 `guest: True` 的临时身份。这个游客 session 能访问 `v1/user_posted` 拉用户笔记列表（首页 30 条范围内）。

我们做的：
1. **playwright 启动 fresh chromium**（不复用任何 profile，避免污染）
2. 访问目标用户主页 `https://www.xiaohongshu.com/user/profile/{user_id}?xsec_token=...`
3. **被动监听 `page.on('response')`**——浏览器自己跑完 guest session 初始化和 user_posted 调用，我们只在响应回来时拷贝 JSON
4. 主动 polling 直到看到一个 `code:0` 的 user_posted 响应，立即停止滚动
5. 解析 JSON 拿笔记列表

**不逆向 sign**、**不带任何 cookie**、**不模拟登录请求**——浏览器做所有脏活，我们只观察。

## 跑

```powershell
cd D:\project\xhs-yunying\benchmark
python monitor.py --user-url "<完整 user 主页 URL>" --limit 20
```

URL 来源：
- 在小红书网页版 / App 搜目标账号
- 点进主页
- 复制地址栏 URL（**带 xsec_token 完整 URL**最稳）

```powershell
# 示例
python monitor.py --user-url "https://www.xiaohongshu.com/user/profile/5b6919dff7e8b96b50ec46bd?xsec_token=AB5j..." --limit 20
```

输出：

```
data/{user_nickname}_{YYYYMMDD}.json   # 笔记列表
data/last_page.png                     # 最后一帧页面截图（调试）
data/xhr_debug.json                    # 所有 XHR 响应（首次跑或失败时）
```

## 命令行参数

```
--user-url URL          # 完整用户主页 URL（推荐，带 xsec_token）
--user-id ID            # 仅 user_id（自动拼 URL）
--limit N               # 笔记上限，默认 20
--scroll-rounds N       # 下滚多少轮触发懒加载，默认 3
--scroll-pause SEC      # 每轮间隔秒数，默认 2.0
--headless              # 无头模式（调试好后可开，平时不开方便看进度）
--profile DIR           # 自定义 chrome profile（默认走 fresh context，不需要）
--browse                # 仅打开浏览器手动浏览（不抓数据，找 URL 用）
```

## 笔记 schema

```python
{
  "note_id":         str,    # 真实 note_id（小红书反爬不返回）+ fallback 'cover:{图像ID}' 或 'xsec:{头16字符}'
  "xsec_token":      str,    # 笔记访问凭证（会话级，不能跨会话用）
  "title":           str,    # display_title
  "desc":            str,    # 正文摘要（user_posted 列表里通常空，详情页才有）
  "note_type":       str,    # normal / video
  "liked_count":     int,    # 点赞数
  "collected_count": int,    # 收藏数（列表 API 通常返回 0，详情页才有）
  "comment_count":   int,    # 评论数（同上）
  "shared_count":    int,    # 分享数（同上）
  "sticky":          bool,   # 是否置顶
  "cover_url":       str,    # 封面 CDN URL
  "publish_time":    str,    # 发布时间（列表 API 通常空）
  "user_id":         str,    # 作者 user_id
  "user_nickname":   str,    # 作者昵称
  "note_url":        str,    # 笔记详情页 URL（含 xsec_token）
}
```

## 已知限制

| 限制 | 原因 | 影响 |
|---|---|---|
| 收藏 / 评论 / 分享数 = 0 | 小红书反爬：列表 API 不返回 | 可点进详情页用同样 XHR 监听拿到（后续可加 `monitor.py --detail`） |
| note_id 是伪 ID | 列表 API 故意不返回真实 note_id | 跨周对比同一笔记时用 `cover:{图像ID}` 当 key（cover URL 末段是稳定的） |
| publish_time 是空 | 列表 API 不返回 | 只能用 sticky 标识 + 列表顺序近似排序 |
| 翻页失败（cursor 调用 -101） | 游客 session 只许首屏 | 当前只拉首屏 11 条，再多需要登录或用更慢的"打开每条详情页"路径 |

## 与 analytics 的联动

```python
# 在你自己的 wrapper 脚本里
from analytics.analyzer import analyze
from analytics.topic_recommender import recommend_topics, save
from analytics.schema import get_conn
import json

conn = get_conn('analytics/data/analytics.db')
analysis = analyze(conn)

with open('benchmark/data/TapTap_20260629.json', encoding='utf-8') as f:
    benchmark = json.load(f)

result = recommend_topics(analysis, benchmark_notes=benchmark['notes'])
save(result, 'analytics/data/reports')
```

qwen-max 会综合自己账号的复盘 + 对标账号的选题动态，给出"对方在打但我没打"的方向。

## 文件清单

| 文件 | 角色 |
|---|---|
| `monitor.py` | CLI 入口（包括 `--browse` 找 URL 工具模式） |
| `xhs_scraper.py` | 核心：playwright + XHR 监听 + 字段标准化 |
| `data/` | 输出目录 |
| `data/{user}_{date}.json` | 笔记列表 |
| `data/last_page.png` | 最后一帧调试截图 |
| `data/xhr_debug.json` | 所有 XHR 响应 dump（用于调试新账号、字段适配） |

## 设计选择

**为什么不用 Agent-Reach / OpenCLI**：
- Agent-Reach 是个调度器，自己不写小红书代码，委托给 OpenCLI / xiaohongshu-mcp 等外部工具
- 复现要 venv + pip + Chrome 扩展 + qrcode 登录，链路太长
- 我们直接用 playwright（content-monitor 已装）跳过中间层，3 个文件、零外部 CLI

**为什么用 fresh context 而不是 persistent profile**：
- persistent profile 上次跑留下的 cookie 可能被风控标记，下次跑就拿不到 user_posted 数据
- fresh context 每次都是全新游客，反爬识别概率最低
- 缺点是每次浏览器启动稍慢（~3 秒）

**为什么不抓收藏数 / 评论数**：
- 列表 API 不返回，要点详情页才有
- 详情页要 navigate 11 次，速度慢 + 风控触发概率高
- 监控的核心信号是"对方发了什么"+"哪些选题点赞高"，已经足够做对标分析

## 不要做的事

- 不要把这个脚本设成定时任务（每天 / 每小时跑）。游客 session 短期内多次创建会被风控。建议节奏：每周一次手动跑。
- 不要在 `--user-url` 里去掉 xsec_token。token 是搜索/分享颁发的访问凭证，去掉后页面可能直接跳登录。
- 不要传你自己账号的 cookie。游客模式够用，登录态只增加被封风险。
