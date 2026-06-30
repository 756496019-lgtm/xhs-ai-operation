---
name: video-editor
description: Edit a Xiaohongshu vertical short video (1080x1920) by combining game trailer (PV) clips according to a script.txt file, optionally synced with TTS voiceover audio. Use this skill whenever the user asks to "剪视频" / "把PV剪一起" / "做视频" / "拼一条短视频" / "video editing" — topic-agnostic, works for any game video theme (discounts / reviews / retro / genre roundups / etc). Each script segment maps to one game's trailer; when a trailer is missing, the segment falls back to a text card so the workflow never crashes. If a `voice/` directory (from tts-voiceover) is provided, picture timing automatically follows voiceover duration so frames and narration stay aligned. Outputs a 1080x1920 MP4 plus an SRT subtitle file.
---

# 视频剪辑 Skill (题材无关)

把 `script.txt` + `pv_library/` [+ `voice/`] 合成一条 1080x1920 竖屏 MP4。

**任何题材都用同一个工具**——折扣盘点、新游评测、怀旧回顾、品类盘点……剪辑流程完全相同。

## 工作原理

`script.txt` 每个 segment 指定 `game_slug` 和 `duration_sec`, 剪辑器去 `pv_library/<slug>/trailer_01.mp4` 截一段, 加字幕, 拼起来。前后加 intro/outro 卡片。

**带配音模式** (推荐): 画面时长**自动跟着配音的实际长度**走, 不再用 script.txt 里的 `duration_sec`。这样画面和念词严格对齐。

## 前置检查

1. `ffmpeg -version` 能跑通 (Mac: `brew install ffmpeg`; Win: 去 https://www.gyan.dev/ffmpeg/builds/; Linux: `sudo apt install ffmpeg`)
2. `script.txt` 存在且 segments 不为空
3. `pv_library/` 存在 (允许部分游戏缺 PV, 会自动用文字卡片补)

## 调用

```bash
cd <项目根目录>/code/video

# 带配音 (推荐)
python video_editor.py --script script.txt \
    --pv-lib ../scrapers/pv_library \
    --voice-dir ../../voice \
    --out output/

# 无声 + 字幕版
python video_editor.py --script script.txt \
    --pv-lib ../scrapers/pv_library \
    --out output/

# 调整 PV 原声音量 (默认 0.1, 0=完全静音, 1=原始)
python video_editor.py --script ... --voice-dir ... --bgm-volume 0
```

## 输出

```
output/
├── video_<时间戳>.mp4   # 主视频, 1080x1920, 30fps
├── video_<时间戳>.srt   # 字幕文件 (剪映/小红书发布器可导入)
└── _clips_tmp/          # 中间产物, 可删
```

## 中文字幕字体

代码自动尝试以下路径:
- `<项目根>/assets/fonts/SourceHanSansSC-Bold.otf` (推荐)
- 系统字体 (PingFang.ttc / msyhbd.ttc / NotoSansCJK)

如果字幕是 □□□ 方块, 让用户:
1. 下思源黑体 https://github.com/adobe-fonts/source-han-sans/releases/latest
2. 解压, 找 `OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf`
3. 放到 `<项目根>/assets/fonts/`

## 常见问题

- 某些游戏画面是黑底文字 → `pv_library/<slug>/` 下没找到 mp4。检查 slug 拼写; 接受现状或手动下 mp4 补
- 字幕乱码方块 → 见上"中文字幕字体"
- 视频卡顿 → 源 PV 编码问题, 让用户用 ffmpeg 转码: `ffmpeg -i 原.mp4 -c:v libx264 -c:a aac 转码后.mp4`
- 总时长不对 → 检查 script.txt 里 `duration_sec` 总和 (无配音模式下决定时长); 带配音时长跟着配音走

## 不要做什么

- 不要把每段 `duration_sec` 设到 < 4 秒 (碎)
- 不要堆到 > 3 分钟 (小红书短视频一般 ≤90s)
- 不要重命名 `pv_library/` 子目录 (会让 slug 对不上)
