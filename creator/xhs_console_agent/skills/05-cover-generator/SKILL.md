---
name: xhs-cover-generator
description: Generate a Xiaohongshu (Little Red Book) vertical cover image (1080x1440, 3:4) by combining game header images into a grid with title text. Two modes available — simple mode (pure code, red title bar + grid) and template mode (loads a designer-made or AI-generated background template PNG, code overlays game thumbnails and title text on top). Use this skill whenever the user wants to create a cover / 封面 / 首图 / poster — topic-agnostic. For production-grade visual quality (textured backgrounds, hand-drawn title bars, sticker effects), use template mode with assets the user generated via Midjourney / Stable Diffusion / 即梦 / etc. Independent of the video editing step.
---

# 封面生成 Skill (题材无关)

把多个游戏 header 图拼成一张小红书竖版封面 (1080x1440)。

**两种模式**:

| 模式 | 输出质感 | 使用场景 |
|------|---------|---------|
| **简单模式** (默认) | 红顶白字 + 标准拼图 | 快速出片、统一调性 |
| **模板模式** ⭐ | 由作图 AI 生成的背景 + 代码拼游戏图和文字 | 想要参考图那种"质感封面" |

## 简单模式

直接跑命令, 无需任何额外素材:

```bash
cd <项目根目录>/code/cover
python cover_generator.py \
    --input ../scrapers/pv_library/index.json \
    --title "本周5款骨折必买" \
    --subtitle "三主机折扣盘点" \
    --max-games 5 \
    --out ../../output/cover.jpg
```

输出: 红色顶部标题区 + 中间游戏拼图 + 底部副标题黑条。

## 模板模式 (推荐, 视觉效果接近参考图)

### 工作原理

让作图 AI 一次性做一张**只含背景和装饰**的"封面模板"PNG (1080x1440), 留出标题区、游戏区、副标题区的空白。然后:

```bash
python cover_generator.py \
    --input ... \
    --title "..." \
    --subtitle "..." \
    --template ../../assets/templates/dark_steam.png \
    --layout ../../assets/templates/dark_steam.json \
    --out ../../output/cover.jpg
```

代码会把模板作为底图, 在 layout 指定的坐标位置贴游戏封面 + 写标题文字。

### 给作图 AI 的提示词模板

让用户用 Midjourney / SD / 即梦 / 豆包出图等任意作图 AI, 提示词例子:

> 小红书游戏封面模板, 1080x1440 竖版, 顶部 320 像素留出红色质感色块带胶带感(放标题用),
> 中间从 380 到 1300 像素是 6 个深色游戏封面位置(目前只画背景, 暗色游戏氛围, 有Steam风格的元素),
> 底部 100 像素深色标签条(放副标题用), 整体调性: Steam 春促, 桌面游戏, 像素元素点缀。
> 重要: 顶部色块和底部标签条要留空, 不要写任何文字; 中间游戏位置只画背景不画游戏图。

### 配套 layout JSON

模板 PNG 要配一份同名的 `.json`, 描述各区域坐标。完整范例: `assets/templates/example_layout.json`。

关键字段:

```json
{
  "size": [1080, 1440],
  "title_text":    {"x": 540, "y": 200, "size": 110, "anchor": "mm",
                    "color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 4},
  "subtitle_text": {"x": 540, "y": 1380, "size": 48, "anchor": "mm",
                    "color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 2},
  "grid":          {"x": 60, "y": 380, "w": 960, "h": 880,
                    "padding": 24, "corner_radius": 24},
  "label_overlay": true
}
```

- `title_text.x/y` 是**文字中心点**位置 (因 `anchor: "mm"` 即 middle-middle)
- `grid` 是游戏拼图区域, 图块数量自动适配 (2 上下 / 4 田字 / 6 二三宫格 等)
- `label_overlay: true` 在每张游戏图底部叠半透明黑条 + 游戏名

### 风格做一次复用很久

每次出新视频不需要重新让 AI 作图——同一个 `<风格>.png + .json` 可以一直复用, 只换游戏封面和标题文字。建议运营准备 2-3 套常用风格 (如 `dark_steam`, `light_kawaii`, `retro`)。

## 步骤 1: 让用户输入标题

封面成败 80% 在标题。**让用户自己输入**, 不要替他想。

好标题特征:
- ≤15 字
- 数字 + 强词: "5款骨折""TOP10""周末必囤"
- 痛点/情绪: "姐妹快冲""我哭了"

## 步骤 2: 决定拼几个游戏

| 数量 | 布局 | 推荐 |
|------|------|------|
| 4 | 田字 | ✅ 通用首选 |
| 6 | 2x3 | ✅ 内容多时 |
| 5 | 上2下3 | |
| 9 | 3x3 | 不推荐 (字看不清) |

最佳 4-6 个。

## 中文字体

代码自动尝试常见字体路径。中文方块时:
- 下思源黑体 (见 video-editor skill 字体说明)
- 用 `--font /path/to/SourceHanSansSC-Bold.otf` 传入

## 不要做什么

- 不要用 < 400px 宽的 header 图 (放大会糊)
- 标题不要超过 15 字 (缩略图看不清)
- 模板模式下 layout 坐标错了会出现"标题写到游戏图上"——让用户对照 PNG 调 layout

