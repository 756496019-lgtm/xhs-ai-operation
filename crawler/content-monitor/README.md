# 内容监控面板 / 游戏雷达局

一个基于 Flask 的小红书自动化运营工具，监控游戏相关内容并生成适合发布到小红书的图文/视频内容。

## 主要功能

### 数据监控
- **Reddit**：r/gaming、r/artificial，以及二次元/女性向板块（r/otomegames、r/gachagaming、r/HonkaiStarRail、r/Genshin_Impact 等）
- **微博超话**：原神、崩铁、鸣潮、碧蓝档案、乙女游戏、手游抽卡超话监控
- **B站动态**：游戏官方账号动态监控（原神/崩铁/鸣潮/碧蓝档案），文章 + 投稿视频双通道
- **TapTap**：游戏官方动态 + 平台综合热门资讯
- **国内资讯**：触乐 / 17173 / 手游那些事多源聚合
- **游民星空**：国内游戏新闻
- **游戏折扣**：Epic / Steam / Nintendo eShop
- **搞笑游戏**：B站整活/搞笑视频 + Reddit 游戏梗帖

### AI 内容生成
- **双路径改写**：勾选新闻后选择「文字改写」或「视频脚本」，两条路径均支持多来源融合
  - 文字改写：游戏雷达局长人设，结构化小红书图文
  - 视频脚本：AI 自由发挥口头禅开场 + 「游戏雷达局，情报已送达——」结尾
- **二次元文案**：4 种人设风格（攻略组 / 酋长 / 独立游戏雷达 / 二次元局长）
- **游戏评测**：标准版（600-900字）+ 深度版（2500-4000字，Steam 评论 Map-Reduce 分析）
- **Reddit 摘要**：海外热帖 + 高赞评论自动改写为小红书文案
- **热门推荐评分**：规则打分（0-100）+ 可选 AI 精排 Top5

### 全自动视频流水线
1. Qwen 生成视频脚本（按行分段，每段独立配音/字幕/画面）
2. yt-dlp 自动搜索并下载游戏官方 PV（B站优先 → YouTube 备选 → 纯色背景兜底）
3. edge-tts 生成中文配音，支持 **9 种声音**自由选择（女声 5 种 / 男声 4 种），可调语速
4. **两步 AI 画面匹配**：qwen-vl-max 逐帧视觉理解 PV → qwen-max 文本语义匹配脚本，分配不重叠区间，充分覆盖整段 PV
5. MoviePy 剪辑合成（保持 PV 原始分辨率），字幕按 TTS `SentenceBoundary` 事件精准同步配音，黑底字幕条逐句轮转
6. 每个脚本段落支持**自定义背景图**（分段配图页上传，优先于 PV）
7. 自动上传小红书视频笔记

### 游戏行业周报生成（v6.0 新增）
- 上传本地 `.docx` 周报文档，一键生成两种格式输出：
  - **微信公众号 HTML**：深海军蓝 × 琥珀橙配色，纯 `<table>` 布局 + `bgcolor` 双写，粘贴到公众号编辑器后颜色完整保留，支持手机端自适应
  - **小红书图文卡片**：7 张 375px 卡片，深色背景 + 橙色装饰，浏览器直接预览 / 一键下载全部 JPG（3× 像素比，高清导出）
- 覆盖率抓取：奇麦 iOS 免费榜（中国大陆 / 港台 / 美国 / 日本 / 韩国）7 日连续数据，自动聚合为周榜单
- 支持独立运行脚本 `gen_xhs.py` / `gen_html.py` 快速重新生成静态文件

### 小红书发布
- 简版编辑器：截图 + 文案一键发布
- 全功能编辑器：Markdown 排版、多页卡片导出、图片宽度/对齐控制、**「📰 公众号风」深色主题**
- 定时发布 + 草稿箱管理
- 视频笔记上传

### 定时自动化
| 任务 | 时间 |
|------|------|
| 二次元 Reddit 抓取 | 09:00 |
| 微博超话抓取 | 09:30 |
| B站动态抓取 | 10:00 |
| 国内手游资讯抓取 | 10:30 |
| 每日自动生成视频 | 14:00 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> `imageio-ffmpeg` 内置了 ffmpeg，视频流水线无需额外配置。

### 2. 配置环境变量

复制 `.env` 并填写必要配置：

```env
# Reddit API（用于抓取帖子评论，可选）
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret

# 通义千问 API Key（已内置，可覆盖）
# DASHSCOPE_API_KEY=sk-xxxxxxxx

# 微博 Cookie（可选，用于访问超话内容）
# WEIBO_COOKIE=SUB=xxxx; SUBP=xxxx

# 定时任务（默认关闭）
ENABLE_SCHEDULER=false
VIDEO_DAILY_COUNT=1
VIDEO_DEFAULT_GAME=原神
```

### 3. 启动

```bash
python app.py
```

浏览器自动打开 `http://localhost:5050`

## 页面导航

| 图标 | 路径 | 功能 |
|------|------|------|
| 监控 | `/` | 数据抓取面板（全部数据源） |
| 改写 | `/rewrite` | AI 改写 + 多来源融合（文字/视频双模式） |
| 脚本预览 | `/script_preview` | 视频脚本分段配图页 |
| 编辑 | `/reddit_edit` | Reddit 截图翻译卡片 |
| 评测 | `/review` | 游戏评测聚合生成 |
| 生成 | `/xhs_full` | 全功能小红书编辑器（含公众号风主题） |
| 速写 | `/freewrite` | 自由写作 |
| 草稿箱 | `/xhs_drafts` | 定时发布草稿管理 |
| **二次元** | `/anime` | 女性向/二次元内容监控 + 文案生成 |
| **视频** | `/video` | 全自动视频流水线 + 定时任务控制台 |
| **周报** | `/weekly_report` | 游戏行业周报生成（公众号 + 小红书双输出） |
| **周报预览** | `/output/wechat` | 周报微信公众号 HTML 预览 |
| **小红书预览** | `/output/xhs` | 周报小红书卡片预览 + 一键下载 JPG |

## 典型工作流

```
抓取新闻列表
    │
    ├─ 勾选条目 → [文字改写] → AI 改写（小红书图文风格）→ [事实核查] → 确认通过 → [图文生成] → xhs_full 编辑器
    │
    └─ 勾选条目 → [视频脚本] → AI 改写（口播脚本风格）→ [事实核查] → 确认通过 → [生成视频脚本]
                                                                                          │
                                                                                          ▼
                                                                                脚本预览页（分段配图）
                                                                                          │
                                                                                          ▼
                                                                                视频生成页（选声音/PV/时长）
                                                                                          │
                                                                                          ▼
                                                                                全自动生成 → 小红书上传
```

## 更新日志

### v6.1 — 文案事实核查

**新增功能**
- 所有改写流程（文字改写 / 视频脚本）在进入「图文生成」或「视频生成」前，自动触发 **事实核查**
- 「下一步」操作栏新增独立「🛡 事实核查」按钮，可单独调用
- 核查由 qwen-max 驱动，重点检查：
  - 未经证实的数据（销量、营收、下载量数字）
  - 夸大表述（"史上最强"、"业界第一"等）
  - 传闻/爆料被误写成官方确认
  - 错误事实引用（版本号、发售日期、开发商归属）
  - 情绪化表述被当作客观事实
- 核查结果弹窗：
  - **通过**：绿色徽章，一键确认继续原流程
  - **有疑问**：逐条展示「原文片段 / 疑问原因 / 建议核实来源」，支持"返回修改"或"忽略风险继续"

**修改文件**
```
qwen_client.py         新增 fact_check_content() 函数
app.py                 新增 POST /api/fact_check 路由
static/js/rewrite.js   runFactCheck() / renderFactCheckResult() / closeFactCheck()
templates/rewrite.html 事实核查按钮 + Modal 弹窗 UI
```

---

### v6.0 — 游戏行业周报生成系统

**新增功能**
- 上传 `.docx` 文档，自动解析标题 / 正文 / 表格，生成双格式输出
- **微信公众号 HTML**（`/output/wechat`）：
  - 深海军蓝 `#0F1824` 背景 + 琥珀橙 `#E8820C` 装饰，纯 `<table>` 布局
  - `bgcolor` + `style` 双写确保公众号编辑器颜色不丢失
  - 排行榜表格 `table-layout:fixed`，手机端不截断
  - 橙色顶部 Banner（含报告标题）+ 橙色底部版权条
- **小红书图文卡片**（`/output/xhs`）：
  - 7 张 375px 卡片，封面合并入第一卡
  - html-to-image 一键导出全部 7 张 JPG（3× 像素比）
- **全功能编辑器新增「📰 公众号风」主题**（`/xhs_full`）：深色背景 + 橙色标题/分割线/引用块
- 周报系统 API `POST /api/weekly_report_to_xhs` 默认使用 `pro` 主题

**新增文件**
```
templates/weekly_report.html   周报上传 + 生成控制台
static/output_wechat.html      微信公众号 HTML 静态产物
static/output_xhs.html         小红书卡片 HTML 静态产物（含下载按钮）
gen_xhs.py                     独立脚本：重新生成 output_xhs.html
gen_html.py                    独立脚本：重新生成 output_wechat.html
scrapers/qimai_rank.py         奇麦 iOS 免费榜爬虫（多区域 7 日数据）
scrapers/weekly_news.py        周报新闻段落解析
```

**修改文件**
```
app.py                app.py  /weekly_report、/output/wechat、/output/xhs 路由 + API
static/js/xhs_full.js          pro 主题样式 + 封面渲染
templates/xhs_full.html        pro 主题 CSS
templates/weekly_report.html   copyWechatHtml() 公众号风格输出
```

---

### v5.0 — 视频流水线大幅优化

**字幕系统重写**
- 字幕改为**黑底字幕条**样式（半透明黑底 + 微软雅黑白字），宽度随文字自适应
- 使用 edge-tts `SentenceBoundary` 事件获取精确配音时间轴，字幕与配音**逐句精准同步**
- 超过 15 字的长句自动按标点（`，。！？、；：`）细分，每段更短更易读
- 脚本括号内容（`（模仿音效）`等）不再出现在字幕上
- 字幕渲染改用 `fl(get_frame, t)` numpy 像素替换，彻底解决 ffmpeg alpha 合成内存死锁问题

**AI 画面匹配升级**
- **两步匹配**：Step 1 用 qwen-vl-max 分批视觉理解每帧内容；Step 2 用 qwen-max 纯文本匹配脚本语义与帧描述
- 强制输出 `[start_frame, end_frame]` 区间，各段不重叠，充分利用整段 PV
- PV 片段用 `speedx` 拉伸/压缩精确匹配脚本段时长

**执行顺序修正**
- TTS 配音先于 AI 画面匹配执行，确保匹配时使用真实 TTS 时长而非字数估算，画面与配音节奏真正对齐

**TTS 配音优化**
- 默认语速 `+15%`（减少 AI 停顿感，接近真人播客节奏）
- 所有 break 停顿时长减半，情绪标签（笑/叹气）去掉前置 break

---

### v4.0 — 双路径改写 + 视频脚本分段配图 + AI 配音选择

**新增功能**
- 监控列表顶栏拆为「文字改写」和「视频脚本」两个入口，模式独立
- 视频脚本默认提示词：AI 自由发挥口头禅开场 + 「游戏雷达局，情报已送达——」固定结尾
- 新增脚本预览页（`/script_preview`）：脚本按行分段，每段可上传自定义背景图
- 视频生成支持 **9 种 edge-tts 声音**（女声 5 / 男声 4），下拉选择
- 视频段落背景优先级：自定义图 > PV 片段 > 纯色背景
- 游民星空来源的行不再显示独立操作按钮，统一通过顶栏处理

**新增文件**
```
templates/script_preview.html   视频脚本分段配图页
```

**修改文件**
```
templates/index.html     顶栏双按钮（文字改写 / 视频脚本）
templates/rewrite.html   模式徽章 + 分拆出口按钮
templates/video.html     声音选择器 + 分段配图接收 + _is_script_preview 预填
static/js/index.js       双路径跳转 + gamersky 行无按钮
static/js/rewrite.js     rewriteMode 感知 + VIDEO_SCRIPT_PROMPT + goToVideo 分叉
app.py                   /script_preview 路由 + segment_images/voice 参数接收
video_pipeline.py        segment_images 配图注入 + voice 传递到 TTS
```

---

### v3.1 — Scraper 修复 + 热门推荐评分

**修复**
- Bilibili：切换为 `x/space/article` + `x/space/arc/search`（不需要 WBI 签名）
- TapTap：切换为 `/webapiv2/feed/v7/for-app-detail`，修复 X-UA 头
- 微博：无 Cookie 时提前返回并给出明确提示
- 搞笑游戏：替换失效搜索 API，改为已知 UP 主视频列表

**新增**
- 规则热度打分（0-100），🔥 ≥70 / ⭐ ≥40，高分行背景高亮
- AI 精排 Top5 按钮（仅在有高分内容时出现）
- 每行统一显示「图文」+「视频」双按钮（deals/reddit/其他来源）

---

### v3.0 — 二次元/视频/自动化扩展

**新增数据源**
- 微博超话监控（原神/崩铁/鸣潮/碧蓝档案/乙女游戏/手游抽卡）
- B站动态监控（游戏官方账号，动态 API + RSS 双保险）
- TapTap 游戏官方动态 + 平台综合热门
- 国内手游资讯：触乐 / 17173 / 手游那些事 并行聚合
- Reddit 扩展 6 个二次元板块

**新增功能**
- 全自动视频流水线（5步：脚本→PV→配音→剪辑→上传）
- 二次元专属文案 4 种人设风格
- APScheduler 定时任务（每日自动抓取 + 生成视频）
- 视频页面实时进度条 + 定时任务控制台

**新增文件**
```
scrapers/weibo.py          微博超话 scraper
scrapers/bilibili.py       B站动态 scraper
scrapers/taptap.py         TapTap scraper
scrapers/domestic_games.py 国内资讯聚合
scrapers/pv_downloader.py  yt-dlp PV 下载封装
video_pipeline.py          视频流水线
scheduler.py               APScheduler 定时任务
templates/anime.html       二次元内容页
templates/video.html       视频流水线页
requirements.txt           依赖清单
```

---

### v2.x — 小红书发布 & 评测系统

- 一键发布支持定时 & 快速测试（+1min / +2min）
- 小红书定时发布草稿箱
- Steam 折扣信息增强（简介/评分/上线时间）
- 图文编辑器图片宽度 + 对齐控制
- 游戏折扣多选按点击顺序排布
- Steam 深度评测（700条评论 Map-Reduce + 2500-4000字长评）

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端 | Python 3.11 / Flask |
| AI | 通义千问（qwen-turbo / qwen-max / qwen-vl-max） |
| 爬虫 | requests / BeautifulSoup / feedparser / Playwright |
| 视频 | yt-dlp / edge-tts / MoviePy / imageio-ffmpeg |
| 调度 | APScheduler |
| 发布 | xhs 库 |
| 前端 | Vanilla JS / Tailwind CSS |
