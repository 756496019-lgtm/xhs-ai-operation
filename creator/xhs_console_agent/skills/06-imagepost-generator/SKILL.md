---
name: xhs-imagepost-generator
description: Generate Xiaohongshu (Little Red Book) photo-text notes — a set of 5-10 vertical 1080x1440 images consisting of a cover + content cards. Use this skill whenever the user wants to "做图文" / "做图文笔记" / "出小红书图片" / "生成卡片" / "做图文版" — any time the output should be image cards rather than a video. Three flexible input modes: full (script + game data, end-to-end), text-only (just a text file with content), on-image (user provides background images from lightai or other art-AI, this skill only writes text on top). Topic-agnostic, works for any game theme. Outputs JPGs to a directory.
---

# 图文笔记生成 Skill

输出小红书图文笔记 (5-10 张 1080×1440 JPG): 第 1 张是封面, 后面是内容卡片。

**和视频生产共享文案格式**——如果用户先做视频再做图文 (或反之), 同一份 `script.txt` 文案可以无缝复用。

## 三种输入模式

### 模式 A: full (一条龙生成)

输入: `script.txt` (复用视频文案 schema) + `pv_library/` (提供游戏封面背景)。

```bash
cd <项目根目录>/code/imagepost
python imagepost_generator.py \
    --mode full \
    --script ../../run/.../script.txt \
    --pv-lib ../../run/.../pv_library \
    --out ../../output/imagepost/
```

封面用第一个游戏的官方封面图作背景, 每张内容卡片用对应游戏的封面图作背景。

**适合**: 已经在做视频流水线、希望同时出一份图文版。

### 模式 B: text-only (仅给文案)

输入: 纯文本 `.txt` 文件, 格式如下:

```
第一行：标题

塞尔达传说 王国之泪
Switch平台年度神作，开放世界冒险天花板。原价519港币，现在折扣到349港币，相当于7折。

艾尔登法环
PC平台魂系巅峰之作，宫崎英高携手乔治马丁。
```

规则:
- 第一行 = 标题 (封面用)
- 每段之间用**空行**分割
- 每段第一行 = 卡片小标题, 后面几行 = 卡片正文

```bash
python imagepost_generator.py \
    --mode text-only \
    --text content.txt \
    --subtitle "可选副标题" \
    --out ../../output/imagepost/
```

输出: 默认风格 (浅黄色色块 + 红圆序号索引), 封面会自动从每段标题提取作为目录。

**适合**: 用户已有完整文案 (自己写的或用其他工具写好), 不需要素材采集。

### 模式 C: on-image (底图 + 文字)

输入: 多张底图 PNG (用户用 lightai 等作图 AI 生成) + 文案 txt。

```bash
python imagepost_generator.py \
    --mode on-image \
    --backgrounds bg1.png bg2.png bg3.png bg4.png \
    --text content.txt \
    --out ../../output/imagepost/
```

- 第 1 张底图用作封面背景
- 后面的底图依次用作内容卡片背景
- 底图数量不足时, 最后一张会重复使用
- 工具会自动加黑色半透明蒙版 + 白字描边, 保证文字在任何底图上都可读

**给 lightai 的提示词建议**:
> "生成一张 1080x1440 竖版图片, 中央留出大块空白用于放文字, 风格 [描述你想要的]。"

如果用户希望文字精确定位, 让他们用 lightai 生成时**预留空白文字区**, 工具默认把标题放在画面上中部, 兼容大多数底图布局。

## 通用参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--style` | `default` | 风格: `default` / `playful` / `retro` (仅 text-only 模式有效, 底图模式跟着底图走) |
| `--subtitle` | (无) | 副标题, 显示在封面底部胶囊里 |
| `--out` | `imagepost_out` | 输出目录 |

## 输出结构

```
output/imagepost/
├── 01_cover.jpg     # 封面 (小红书首图)
├── 02_card.jpg      # 第 1 个内容卡片
├── 03_card.jpg      # 第 2 个内容卡片
└── ...
```

直接拖到小红书发布器, 按顺序选这些图就行。

## 选哪个模式的判断

- 用户说"做图文" + 已经在做视频 → **模式 A**
- 用户说"我已经写好稿子了, 帮我做成图文" → **模式 B**
- 用户说"我用 lightai 做了底图, 帮我把文字打上去" → **模式 C**

## 报告结果时

告诉用户:
- 总共生成几张 (封面 + 卡片数)
- 输出目录路径
- 提示发布顺序 (01_cover 是首图, 后面按编号顺序)

## 常见问题

- **中文是方块** → 没装中文字体。让用户装思源黑体到 `assets/fonts/`
- **某段文字超出卡片** → 自动会缩字号, 但可能很小。建议每段正文 ≤ 80 字
- **底图模式文字不在用户期望的位置** → 当前版本固定位置 (上中部标题、中下正文)。让用户在 lightai 提示词里要求"中央留白"

## 不要做什么

- 不要为底图模式自动改文字颜色 (用户传什么底图、文字保持白色 + 黑色描边, 一律可读)
- 不要在 text-only 模式下叠加游戏封面图 (那是 full 模式的事, 避免混淆)
- 不要把 `01_cover.jpg` 之外的图当封面 (小红书首图就是第一张)
