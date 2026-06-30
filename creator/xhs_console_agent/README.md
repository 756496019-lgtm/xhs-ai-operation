# 游戏短视频生产工具

把游戏短视频的生产流程拆成 5 个独立能力——**素材采集、文案、配音、剪辑、封面**——每个都能独立用，也能串成完整流水线。

## 它的能力

- **题材无关**：折扣盘点、新游评测、怀旧回顾、品类盘点（魂游/JRPG/独立游戏）、系列回顾、主机选购指南……都用同一套工具
- **多源素材采集**：Steam/PS/Switch 商店爬虫、按游戏名精确查询、跨平台对标采集（基于 [Agent Reach](https://github.com/Panniantong/Agent-Reach)）三种方式自由组合
- **两种文案模式**：4 种 preset 模板（折扣/新游/即将发售）即装即用，或 prompt 模式接受任意主题让 Code Buddy 写
- **配音免费**：基于 Edge TTS（开源），8 种以上中文音色，剪映同款,无 API key 无 GPU
- **画面跟着配音走**:每段画面长度自动等于配音时长,画面+念词严格对齐
- **封面双模式**:简单模式(纯代码红顶白字+拼图) 或 模板模式(作图 AI 生成底板 + 代码贴游戏图和文字, 质感接近爆款封面)
- **图文笔记三模式**: 全自动 (复用视频文案) / 仅给文案排版 / lightai 出底图 + 工具打字
- **小红书规格**:视频 1080×1920 竖屏 + 封面 1080×1440 竖版 + 图文 1080×1440 竖版 + SRT 字幕

## 快速开始

**推荐方式（对话主导）**：在 Code Buddy 里, 进入项目目录, 直接对话:

> "帮我出一条本周折扣视频，标题叫'本周5款骨折必买'。"

Code Buddy 会自己读 `skills/` 里的说明书、自己跑命令、自己处理错误。运营全程不用敲命令。

**手动方式**（本地 agent 不可用时, 仅供参考）:

```bash
pip install -r requirements.txt
python code/make_video.py --section deals --limit 5 --title "本周5款骨折必买"
```

10 分钟左右去 `run/<时间戳>/output/` 拿成品。

## 文档

- **运营操作手册（对话主导）**: [`docs/操作手册.html`](docs/操作手册.html) — 教运营怎么和 Code Buddy 说话 (浏览器直接打开, 含示例图)
- **各能力 skill 文档**: [`skills/`](skills/) — agent 自动读, 运营无需关心
- **README**（你正在看的）: 整体架构和命令行 reference

## 架构

```
xhs_console_agent/
├── README.md
├── requirements.txt
├── docs/
│   ├── 操作手册.html             ← 给运营看的主手册 (浏览器打开)
│   ├── 操作手册.md               ← 同内容的 md 源文件 (Code Buddy 改起来方便)
│   └── images/                   ← 手册里引用的示例图
├── skills/                       ← 6 个能力模块的 skill 文档
│   ├── 01-material-collector/    ← 素材采集 (商店爬虫+按名查询+对标)
│   ├── 02-script-writer/         ← 文案 (任意题材, prompt/preset 双模)
│   ├── 03-tts-voiceover/         ← 配音 (edge-tts, 免费)
│   ├── 04-video-editor/          ← 视频剪辑 (按配音时长对齐)
│   ├── 05-cover-generator/       ← 封面 (拼图+标题, 支持模板)
│   └── 06-imagepost-generator/   ← 图文笔记 (5-10 张卡片, 三种模式)
├── code/
│   ├── make_video.py             ← 一键全流程
│   ├── scrapers/
│   │   ├── steam_scraper.py
│   │   ├── ps_scraper.py
│   │   ├── switch_scraper.py
│   │   ├── scrape_all.py         ← 三平台合一 (按板块)
│   │   ├── scrape_by_names.py    ← 按游戏名查询
│   │   └── pv_downloader.py
│   ├── video/
│   │   ├── script_generator.py
│   │   ├── tts_generator.py
│   │   └── video_editor.py
│   ├── cover/
│   │   └── cover_generator.py
│   └── imagepost/
│       └── imagepost_generator.py   ← 图文笔记生成 (三种模式)
└── assets/
    ├── fonts/                    ← 中文字体放这里
    └── templates/                ← 封面底板 PNG + 布局文件 .txt (lightai 生成)
```

## 整体流程

```
[商店爬虫]                 ┐
[按游戏名查询]              ├→ 素材数据 (.json)  →  下载预告片  →  pv_library/
[Agent Reach 跨平台采集]   ┘                                          │
                                                                       │
                              对标素材 ──→ 文案生成 ─┬─→ script.txt ─┤
                                          (prompt    │                 │
                                           或 preset)│                 │
                                                     ▼                 │
                                              配音 (edge-tts)          │
                                                     │                 │
                                                     ▼                 ▼
                                            ┌────视频剪辑────┐    封面生成
                                            ▼                ▼        │
                                        video.mp4        字幕.srt   cover.jpg
```

## 在 agent 里使用

skill 文档符合 Anthropic skill 协议, 任何能读 SKILL.md 并执行命令的 agent 都能用 (Claude Code、Cursor、Cline 等)。

把 `skills/` 目录给 Code Buddy，然后用自然语言描述需求：

> "用 Agent Reach 在小红书搜'魂游盘点'前 5 条对标，再做一条 5 款经典魂游推荐的视频，标题叫'魂游必玩TOP5'，男声解说"

agent 会按需依次触发：
1. `game-material-collector` 的 D 子能力（对标采集）→ 抓 5 条对标
2. `game-material-collector` 的 B 子能力（按名查询）→ 抓 5 款魂游数据
3. `game-material-collector` 的 C 子能力（PV 下载）
4. `game-script-writer`（prompt 模式 + 主题 + 对标）→ 生成原创文案
5. `tts-voiceover`（云健解说员声）→ 配音
6. `video-editor` → 剪视频
7. `xhs-cover-generator` → 出封面

## 限制

- 不会自动发布到小红书（涉及登录态/风控）
- 不绕付费墙、不爬登录态私人内容
- 平台改 API 会需要更新爬虫（让 Code Buddy 帮你改）
- 不替代有审美的设计；输出是"快速可发"水平
- 不做高级转场（建议导出无声+SRT 后用剪映加工）

## 致谢

- 视频剪辑：ffmpeg
- 封面拼图：Pillow
- TTS：[edge-tts](https://github.com/rany2/edge-tts)（MIT，可商用）
- 跨平台采集：[Agent Reach](https://github.com/Panniantong/Agent-Reach)（MIT）
- 商店数据来自各平台公开网页前端调用

全部免费可商用。
