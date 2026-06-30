---
name: game-material-collector
description: Collect game material from multiple sources for short-video creation — store data (Steam new releases / discounts / specific game lookup), trailer videos (PV download), and reference content from social platforms (Xiaohongshu / Bilibili / YouTube via Agent Reach). Use this skill whenever the user wants to gather raw input before writing a script — phrases like "找素材" / "搜一下XX游戏" / "爬一下折扣" / "把这个B站视频字幕扒下来" / "我要做魂系游戏盘点先帮我找几个" / "给我对标视频". The skill auto-routes: store data → built-in scrapers; user-named games → name-based lookup; cross-platform reference content → Agent Reach. Outputs structured JSON / Markdown that downstream skills (script-writer, video-editor) consume.
---

# 素材采集 Skill (统一入口)

这个 skill 是**所有视频项目的起点**。它统一管理几种素材源：

| 子能力 | 用途 | 实现 |
|--------|------|------|
| **A. 主机商店爬虫** | 抓 Steam/PS/Switch 的折扣页、新品页、即将发售页 | 内置 Python 脚本 |
| **B. 按游戏名查询** | 自己想做的游戏列表 (魂系盘点 / JRPG 盘点 / 怀旧回顾) | 内置脚本 (Steam 搜索) |
| **C. 预告片下载** | 把游戏的 PV 下载到本地, 给视频剪辑用 | 内置脚本 |
| **D. 跨平台对标采集** | 小红书/B站/YouTube 上同行的字幕、文案、热帖 | [Agent Reach](https://github.com/Panniantong/Agent-Reach) |

**使用顺序通常是 A 或 B → C → (可选) D**。

## 怎么决定用哪个

**根据用户意图选**:

- 用户说"折扣"/"特价"/"新游"/"即将发售"等 → 用 **A** (商店爬虫)
- 用户说出具体游戏名 / 列出几个游戏 / "魂系盘点"/"塞尔达全系列回顾"等主题 → 用 **B** (按名查询)
- 用户说要做视频, 但不关心商店数据(比如纯剧情盘点、玩家社区话题) → **跳过 A/B**, 只用 D 找对标
- 任何主题, 想做"先看同行怎么做的" → 加 **D** (对标)

## A. 主机商店爬虫

### 命令

```bash
cd <项目根目录>/code/scrapers

# Steam + Switch 一起
python scrape_all.py --section deals --limit 8 --out data/

# 三种 section: deals / new / coming_soon

# 加 PS 平台 (需要 PS Store 分类页 URL)
python scrape_all.py --section deals --limit 8 --ps-url "https://store.playstation.com/zh-hans-hk/category/..." --out data/
```

### 注意

- PS Store 的 concept ID 经常变, 让用户从浏览器复制具体分类页 URL 进来; 不传 `--ps-url` 就跳过 PS
- Switch 用港服 Algolia, 偶尔任天堂会换 API key, 那就让用户更新 `switch_scraper.py` 顶部的 key (出错时报告即可)

## B. 按游戏名精确查询

### 命令

```bash
cd <项目根目录>/code/scrapers

# 直接列游戏名
python scrape_by_names.py --names "塞尔达传说 王国之泪" "艾尔登法环" "黑神话悟空" --tag souls

# 或从 txt 文件 (一行一个)
python scrape_by_names.py --names-file games.txt --tag souls
```

输出 `data/all_<tag>_<日期>.json`, 格式和 A 完全一致。

### 注意

- 这个能力**只用 Steam 搜索**(因为 Steam 的搜索 API 公开稳定)。其他平台目前不支持按名查询。
- 如果用户做的游戏在 Steam 上没有 (比如纯主机独占), 就只能让用户**自己手写一份 JSON** (schema 见下方"自定义素材")。

## C. 预告片下载

A 或 B 出 JSON 后, 跑这个把每个游戏的 PV 下到本地:

```bash
cd <项目根目录>/code/scrapers
python pv_downloader.py --input data/all_xxx.json --out pv_library/ --max-per-game 1
```

输出 `pv_library/<游戏slug>/trailer_01.mp4` + `pv_library/index.json` 总索引。

如果某些游戏没有预告片字段, 会被跳过——后续视频剪辑会用静态文字卡片代替, 不会让流程崩。

## D. 跨平台对标采集 (Agent Reach)

适合**所有题材**的"先看同行怎么做的"环节。

### 是否已安装

```bash
agent-reach --version
```

未安装时, 让用户跑:

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

### 各平台开通情况 (装好后跑 `agent-reach doctor`)

| 平台 | 开通要求 |
|------|---------|
| 任意网页 | ✅ 装好就用 |
| YouTube 字幕 + 搜索 | ✅ 装好就用 |
| B站字幕 + 搜索 | ✅ 装好就用 (服务器需代理) |
| Twitter 单条 | ✅ 装好就用 |
| Reddit 搜索 | ✅ |
| **小红书 (阅读 + 搜索)** | ❌ 必须配 Cookie |
| GitHub 公开仓库 | ✅ |

**小红书配 Cookie**: 让用户对自己的 agent 说"帮我配置 Agent Reach 的小红书 Cookie", agent 会引导(用 Cookie-Editor 浏览器插件导出 → 填进配置)。

### 调用方式 (对话式, 不用记命令)

直接告诉运营的 agent:

> "用 Agent Reach 在小红书搜'魂系游戏盘点'前 5 条最热的, 提取标题和正文, 保存到 references.md"

> "用 Agent Reach 把这条 B站视频字幕扒下来: https://..."

输出建议保存为 `references.md`, 这样下一步 `game-script-writer` 可以直接用 `--references` 参数引用。

### 合规

- ✅ **学语气、学结构、学切入角度** OK
- ❌ 不要照搬整句、特殊词组 (会被判洗稿)
- ❌ 不要把对标视频画面剪进自己视频 (侵权)
- 🔒 Cookie 不要传给任何人

## 自定义素材 (没有商店数据时)

如果用户做的题材是**剧情/玩法分析/社区话题**这种和商店数据无关的, 让 ta 直接手写一份 JSON:

```json
[
  {
    "name": "游戏名",
    "platform": "PS5/Switch/PC/...",
    "slug": "game_name_slug",
    "header_image": "本地路径或URL",
    "short_description": "用户自己写的一段介绍",
    "trailers": []
  }
]
```

`slug` 必须和 `pv_library/<slug>/` 目录对应 (用户自己手动建目录、放 mp4)。

## 报告结果时

不论用了哪些子能力, 最终至少应该让用户拿到:
- `data/all_*.json` 或自定义的 JSON (素材数据)
- `pv_library/index.json` (本地 PV 库索引)
- (可选) `references.md` (对标参考)

把这三类文件路径告诉用户, 并提示下一步用 `game-script-writer` skill。
