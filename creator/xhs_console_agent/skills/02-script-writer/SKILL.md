---
name: game-script-writer
description: Write short-video scripts for any game-related content topic — discount roundups, new release reviews, retro retrospectives, genre roundups (souls-likes / JRPGs / indie), series retrospectives, console buying guides, story analysis, etc. Use this skill whenever the user wants to "写文案" / "写口播稿" / "做文案" / "拼成一篇视频脚本" — regardless of theme. Two paths: prompt mode (universal, the calling agent reads the prompt and writes the script itself — recommended for non-discount themes) or three preset templates (discount / new / coming-soon — offline, no AI needed). Output is always a strict-schema script.txt that the video editor consumes.
---

# 通用文案 Skill

输入是 [game-material-collector](../01-material-collector/SKILL.md) 输出的 JSON (任意素材), 输出是结构化的 `script.txt`。

**这个 skill 不绑定题材**——折扣盘点、新游评测、怀旧回顾、魂游盘点、JRPG 推荐、塞尔达系列回顾、主机选购指南、独立游戏挖掘……都用同一个工具。

## 选哪种模式

### 1. Prompt 模式 ⭐ 通用首选

适合 **任意题材**。工作原理: 不直接写文案, 而是产出一份提示词文件 (含游戏数据 + 主题描述), 由当前 agent (Code Buddy) 读完后就地写出 JSON 文案。

**当 agent 是大模型时, 推荐流程是:**
1. 跑 `script_generator.py --mode prompt --topic "..."` 产出 `prompt.txt`
2. **agent 自己** view 一下 prompt.txt, 就地按提示词生成 JSON
3. 保存为 `script.txt`

不调外部 API, 不需要用户切换工具, 文案质量由当前 agent 的能力决定。

### 2. Preset 模板模式 (offline)

只针对三种特定题材, 不需要 LLM 调用:
- `preset-deals` 折扣盘点
- `preset-new` 新游速报
- `preset-coming` 即将发售

适合: 用户赶时间、希望每周稳定输出同一种格式、电脑离线。

**其他题材不要用 preset**——会出现"语气不对"。比如怀旧题材用 `preset-deals` 模板, 会把"原价 X 折扣 Y"硬塞进文案, 完全不合适。

### 3. 用户已有文案

用户写好了底稿, 让他们直接整理成 `script.txt` 格式 (见 schema 末尾), 跳过本 skill。

## 调用

```bash
cd <项目根目录>/code/video

# Prompt 模式 (通用, 任意题材)
python script_generator.py \
    --input ../scrapers/pv_library/index.json \
    --mode prompt \
    --topic "本周值得入手的5款魂系游戏" \
    --out prompt.txt

# 加上对标参考 (语气和结构借鉴, 不抄)
python script_generator.py \
    --input ../scrapers/pv_library/index.json \
    --mode prompt \
    --topic "怀旧主机回顾: PS3 时代的5个被遗忘的杰作" \
    --references references.md \
    --out prompt.txt

# Preset 模板 (仅折扣/新游/即将发售)
python script_generator.py --input ... --mode preset-deals --out script.txt
python script_generator.py --input ... --mode preset-new --out script.txt
python script_generator.py --input ... --mode preset-coming --out script.txt
```

`--topic` 是 prompt 模式的关键。**好主题描述的特征**:
- 包含**视角** (盘点 / 评测 / 回顾 / 推荐 / 教程)
- 包含**题材范围** (魂系 / JRPG / 独立 / PS5 独占)
- 包含**情绪基调** (必入 / 慎入 / 冷门佳作 / 怀旧)

例: `"本周值得回坑的5款魂系/类魂游戏"` 比 `"魂游推荐"` 好得多。

## script.txt 输出 schema

> **重要**: `script.txt` 文件内容是 **JSON 格式** (用 `.txt` 扩展名是因为对运营更友好, 但代码读取时按 JSON 解析)。下游 `video_editor` / `tts_generator` 既能读 `.txt` 也能读 `.json`, 只看文件内容。

```json
{
  "title": "标题 ≤20字 (封面用)",
  "intro": "开头引导语 (5-8秒念完)",
  "segments": [
    {
      "game_slug": "<必须和 pv_library/ 下的目录名一致>",
      "game_name": "塞尔达传说 王国之泪",
      "text": "这一段念什么。一两句, 8 秒内念完。",
      "duration_sec": 8
    }
  ],
  "outro": "结尾钩子"
}
```

`game_slug` **必须**和 `pv_library/` 下的目录名匹配, 否则视频剪辑找不到素材。最简单办法: 让用户从 `pv_library/index.json` 复制 slug。

## 写文案时的通用风格点

不论题材:
- 小红书口语, 但避免装亲热(不要每句都"姐妹们""家人们")
- 每段 1-2 句, 8 秒内念完
- 突出**与主题相关的卖点**: 折扣题材强调价格; 怀旧题材强调情怀; 评测题材强调玩点
- 不要 emoji 滥用 (≤3个/全文)
- 总时长 60-90 秒
- 结尾必须有钩子 (评论区留言、私信咨询、点赞收藏)

## 不要做什么

- 不要瞎编游戏信息 (价格、独占性、类型) — 只用素材数据中的信息
- 非折扣题材不要套折扣 preset
- `game_slug` 必须和素材库一致, 拼写错了视频会用文字卡片代替

## 与对标素材结合

`--references` 加一份 `references.md` (Markdown, 含同行视频/帖子文案), prompt 中会自动加入"借鉴语气/严禁照抄"指令。Prompt 模式专享, preset 模式忽略此参数。
