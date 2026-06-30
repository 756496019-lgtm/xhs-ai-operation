# Snapshot 说明

此目录是从 `C:/Users/demiliang/Desktop/xhs_console_agent.tar.gz` 在 2026-06-29 解压的代码快照，仅用于本项目展示和复现。

## 与原资产的关系

- 原资产：`C:/Users/demiliang/Desktop/xhs_console_agent.tar.gz`，2026-05-11 打包
- 本快照：完整解压，**不修改内容**
- 大小：约 2.1 MB

## 在本仓的角色

承担赛题 6 环节里的「环节 3：内容生产」：
- 6 个独立 skill 的对话式生产流水线：
  - `01-material-collector` — 多源素材采集（Steam/PS/Switch + 按游戏名 + 跨平台对标）
  - `02-script-writer` — 文案（4 种 preset + prompt 模式）
  - `03-tts-voiceover` — Edge TTS 配音（9 种中文音色，免费）
  - `04-video-editor` — 视频剪辑（按配音时长对齐）
  - `05-cover-generator` — 封面（拼图+标题，支持模板）
  - `06-imagepost-generator` — 图文笔记（5-10 张卡片，三种模式）
- 配套运营操作手册：`docs/操作手册.html`（也复制到了本仓的 `../../docs/操作手册.html`）

## 与 analytics 模块的接口

`analytics/topic_recommender.py` 的输出 `next_week_prompt_W{N}.md` 末尾的"WorkBuddy 触发话术"，就是用来复制粘贴给 WorkBuddy（在本目录下对话），让它读 `skills/02-script-writer/SKILL.md` 自动出片的提示语。
