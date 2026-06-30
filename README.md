# 小红书运营｜个人创作者的 AI 内容生产闭环

> 基于 WorkBuddy 搭建的内容创作与发布分析系统

---

## 一句话定位

把"素材采集 → 选题生成 → 内容生产 → 内容改写 → 发布计划 → 数据回收复盘"6 个环节，用 WorkBuddy 串成一个**人机协作**的闭环，让一个人能像团队一样持续产出小红书精品内容。

## 真实战绩

- 4 个月时间，小红书账号 0 → 2978 粉
- AI 辅助下，每周稳定 2-3 条内容，单条最高阅读 2 万+
- 完整工作流已沉淀给团队新成员使用：见 `docs/操作手册.html`

> 增长曲线截图：见 `demo/0to2978_growth.png`（PPT 第一页素材）

---

## ⚠ 一个必须先说清楚的事

> ### 这个账号不是 AI 做出来的。AI 只负责**跑腿**。
>
> 判断、温度、节奏、视觉、口吻——**全部由人定**。
> AI 帮我节省了 60% 的素材搬运、初稿撰写、调度时间，但
> 「这条选题要不要做」、「标题怎么改才有钩子」、「封面留哪一帧」——
> 这些**决定 80% 点击率**的事，AI 一个字都不出。

### 人工参与比例 ∝ 账号精品程度

| 环节 | 人工 : AI | 说明 |
|---|---|---|
| 素材采集 | 30 : 70 | 重复劳动，AI 跑就行 |
| 选题判断 | **75 : 25** | AI 出候选，人定取舍 |
| 内容初稿 | 40 : 60 | AI 起草，人改方向 |
| 文案精修 | **90 : 10** | 温度、节奏必须人手过 |
| **标题 / 封面** | **95 : 5** | 决定 80% 点击率，人手专属 |
| 发布调度 | 25 : 75 | 调度劳动，自动化 |
| 数据复盘 | 65 : 35 | AI 出建议，人定方向 |

4 个月真实运营拆出来的占比，不是估算。整套系统的核心定位是**给人省力**，不是替人做判断。

---

## 6 环节闭环

```
                    ┌──────────────────────────────────┐
                    │  环节 6: 数据回收 → 反哺选题       │
                    │  analytics/                       │
                    └──────────┬───────────────────────┘
                               │
   ┌────────────┐    ┌────────▼────────┐    ┌────────────┐
   │ 环节 1     │    │ 环节 2          │    │ 环节 3     │
   │ 素材库构建 │───▶│ 选题生成        │───▶│ 内容生产   │
   │ crawler/   │    │ benchmark/ +    │    │ creator/   │
   │            │    │ analytics 反哺  │    │            │
   └────────────┘    └─────────────────┘    └─────┬──────┘
                                                  │
   ┌────────────┐    ┌─────────────────┐    ┌────▼───────┐
   │ 环节 6 起  │◀───│ 环节 5 发布计划  │◀───│ 环节 4 改写│
   │ CSV 导入   │    │ crawler/...     │    │ + 事实核查 │
   └────────────┘    └─────────────────┘    └────────────┘
```

每个环节对应仓里一个子目录：

| 环节 | 子目录 | 角色 |
|---|---|---|
| 1. 素材库构建 | `crawler/content-monitor/` | 14 个 scrapers 多源素材采集（Reddit/微博超话/B站/TapTap/触乐/17173/游民/Epic/Steam/eShop） |
| 1+ 对标补充 | `benchmark/` | 用 Agent-Reach OpenCLI 监控对标账号（如小红书 taptap） |
| 2. 选题生成 | `crawler/...` 热度评分 + `analytics/` 反哺 | 0-100 规则评分 + AI 精排 + 历史复盘建议 |
| 3. 内容生产 | `creator/xhs_console_agent/` | 6 个 skill 模块（素材/文案/配音/剪辑/封面/图文笔记） |
| 3+ 动效视频 | `creator/motion-remotion/` | React + Remotion 代码驱动的动效视频（增长动画 / 周复盘动画） |
| 4. 内容改写 | `crawler/content-monitor/` | 双路径改写（文字/视频）+ `fact_check_content` 事实核查 |
| 5. 发布计划 | `crawler/content-monitor/` | 草稿箱 + 定时发布 + 多平台导出（小红书/B站/公众号） |
| 6. 数据回收 | `analytics/` | CSV 导入 → SQLite → AI 复盘 → 选题反哺到 02-script-writer |

## 项目结构

```
xhs-yunying/
├── README.md                    ← 你正在看
├── index.html                   ← 单页项目展示（浏览器直接打开）
├── docs/
│   ├── 操作手册.html             ← 给团队新成员的入门手册（直接浏览器打开）
│   ├── 6环节闭环.md              ← 系统架构图（mermaid）
│   └── demo_storyboard.md       ← 7 分钟 Demo 录屏分镜
├── crawler/                     ← 环节 1 + 4 + 5: snapshot 复制自 D:/project/content-monitor/
│   └── content-monitor/         ← Flask 全栈监控/改写/发布平台
├── creator/                     ← 环节 3: 解压自 xhs_console_agent.tar.gz
│   ├── xhs_console_agent/       ← WorkBuddy 对话式 6 skill 生产流水线
│   └── motion-remotion/         ← 新写: React + Remotion 动效视频（数据可视化 / 字卡动画）
├── benchmark/                   ← 环节 1+ 对标账号监控（新建）
│   ├── README.md
│   ├── install.md               ← Agent-Reach Windows 安装步骤
│   ├── monitor_taptap.py        ← 对标小红书 taptap 账号
│   └── data/
├── analytics/                   ← 环节 6: 数据回收闭环（新建）
│   ├── README.md
│   ├── cli.py
│   ├── csv_importer.py
│   ├── schema.py                ← SQLite (notes / snapshots / followers)
│   ├── analyzer.py
│   ├── topic_recommender.py     ← 输出对接 xhs_console_agent
│   ├── report_renderer.py       ← 复用 xhs-weeklyreport 的 render_xhs_cards
│   ├── qwen_bridge.py
│   └── examples/sample_export.csv
└── demo/
    ├── 0to2978_growth.png
    └── recording_script.md
```

## 快速开始

### 0. 直接看作品展示页（无需跑代码）

浏览器打开 `index.html`（项目根目录）—— 单页 HTML 展示，包含项目介绍、6 环节闭环图、各模块、亮点、实跑演示、源代码索引。

### 1. 看产品（无需跑代码）

打开 `docs/操作手册.html`，这是给运营同学看的"对话主导"入门手册。整套系统的最终用户体验是：在 WorkBuddy 里说一句话，它自己读 skill 文档、自己跑命令、自己处理错误。

### 2. 跑数据回收闭环（5 分钟）

```bash
cd analytics
pip install -r requirements.txt
python cli.py --import examples/sample_export.csv --analyze --suggest --render
```

输出：
- 终端：本周复盘文本
- `data/reports/W{N}_dashboard.html`：双风格卡片报告（暗黑 + 奶油），浏览器打开后点下载按钮导 JPG
- `data/reports/next_week_prompt_W{N}.md`：下期选题建议 + WorkBuddy 触发话术（复制末段进 `creator/xhs_console_agent/` 对话即可起一轮新生产）

### 3. 跑对标账号监控（10 分钟）

```bash
cd benchmark
python monitor.py --user-url "<目标用户主页 URL>"
```

不需要登录、不需要 cookie，靠浏览器自动建立的游客 session 就能拉首屏笔记。

输出：`benchmark/data/{昵称}_YYYYMMDD.json` —— 对标账号近期笔记列表 + 互动数据。

输出：`benchmark/data/taptap_YYYYMMDD.json` — 对标账号近期笔记列表。

### 4. 看完整生产流水线

```bash
cd creator/xhs_console_agent
# 在 WorkBuddy 里：
# > 帮我做一条本周折扣盘点的小红书图文，标题方向是「Steam 夏促值得买的5款新游」
```

WorkBuddy 自动读 `skills/01-material-collector/SKILL.md` → 跑 Steam 爬虫 → 生成文案 → 出图。

### 5. 渲染动效视频（5-7 分钟）

```bash
cd creator/motion-remotion
npm install         # 首次约 18 秒
npm run dev         # 实时预览（http://localhost:3000）
npm run build:all   # 一键 render 两个示例视频
```

输出：`out/growth.mp4`（4 个月增长动画）+ `out/weekly.mp4`（W27 周复盘动画）。1080×1920 竖屏，小红书直接发布规格。改 `src/data/sample.ts` 即可换数据 re-render。

## 设计哲学：AI 用越少越好

> 这是用户从 4 个月真实运营踩出来的判断，与"全自动"的产品叙事相反。

精品账号的"精品感"来自人手把控的选题判断、文案温度、视觉细节。AI 用太多内容会"AI 味太浓"，反伤账号洗标签和长尾搜索表现（参见 `D:/project/xhs-weeklyreport/` 的 W17 / W21 踩坑红线）。

本系统的 AI 介入边界：

| 环节 | AI 用得多吗 | 为什么 |
|---|---|---|
| 素材采集 | 多 | 重复劳动，AI 节省 80% 时间 |
| 选题生成 | 中 | AI 出候选，人手做最终判断 |
| 内容生产（一稿） | 多 | AI 起草是效率核心 |
| 内容改写（精修） | **少** | 温度、节奏、口吻必须人手过 |
| 标题 / 封面 | **少** | 决定 80% 点击率，人手专属 |
| 发布计划 | 多 | 草稿箱 + 定时调度 |
| 数据复盘 | 中 | AI 出建议，人手定方向 |

`index.html` 第 8 段专门讲这个边界判断——这是这套系统不同于"全自动 AI 出片"工具的核心。

## 复用与新写

| 来源 | 复用方式 |
|---|---|
| `crawler/content-monitor/qwen_client.py` 19 个 AI 函数 | snapshot 后由 `analytics/qwen_bridge.py` import |
| `D:/project/xhs-weeklyreport/render_xhs_cards.py` | analytics 的报告渲染直接调用 `render_dual_html()` |
| 视觉规范（375×500 / 暗黑 #0C1520 / 奶油 #FFFDF9 / PingFang SC） | 沿用 `D:/project/xhs-weeklyreport/小红书周报发布规范.md` |
| 操作手册.html | 本仓 `docs/` 拷一份 |
| `trending_scorer.py` 启发式 | 不复用，新写笔记表现打分（互动率三件套：likes/views, saves/views, comments/views） |
| CSV 解析 / SQLite schema / 选题反哺 | 全部新写 |

## 关于本项目

- 真实战绩、真实代码、真实运营 4 个月——不是为了演示搭的样板间
- `crawler/content-monitor/` 的 v6.1 是日常使用的工具，本仓是它的快照
- `creator/xhs_console_agent/` 的运营操作手册（`docs/操作手册.html`）已经在团队里跑过验证
- 真正的差异点不在"用了多少 AI"，在"该不用 AI 的环节让 AI 退场"

完整作品展示见 `index.html`，5-7 分钟实跑演示分镜见 `demo/recording_script.md`。
