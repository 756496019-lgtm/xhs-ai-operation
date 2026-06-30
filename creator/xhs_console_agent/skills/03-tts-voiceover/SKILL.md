---
name: tts-voiceover
description: Generate free Chinese voiceover audio (MP3) for any video script using Microsoft Edge TTS. Use this skill whenever the user wants to "加配音" / "生成旁白" / "做语音" / "voice over" / "TTS" for short-video content (game-related or otherwise — this skill is topic-agnostic), or whenever the workflow has produced a script.txt and the next step is making audio narration. Outputs one MP3 per script segment plus a voice_index.json with real durations, which the video editor uses to perfectly time picture-to-voice alignment. Free, no API key, no GPU, no account — uses edge-tts (the same engine Edge browser uses for read-aloud).
---

# 配音生成 Skill (免费 TTS, 题材无关)

输入 `script.txt`, 输出 `voice/` 目录(每段一个 mp3 + `voice_index.json`)。

**完全免费**, 无需 API key / GPU / 账号。底层用 `edge-tts` (开源 Python 包, 复用 Edge 浏览器调用的微软在线 TTS 引擎)。

**这个 skill 不挑题材**——只要有 script.txt, 任何主题都能配音。

## 前置

```bash
pip install edge-tts --break-system-packages
edge-tts --list-voices | head      # 验证安装
```

## 执行

```bash
cd <项目根目录>/code/video

python tts_generator.py --script script.txt --out voice/
python tts_generator.py --script script.txt --voice zh-CN-YunxiNeural --out voice/
python tts_generator.py --script script.txt --rate=-10% --out voice/
python tts_generator.py --list-voices   # 看完整音色列表
```

## 选音色

| 音色 | 性别 | 调性 | 适合 |
|------|------|------|------|
| `zh-CN-XiaoxiaoNeural` ⭐ | 女 | 标准、亲和 | **默认万能**, 各种题材 |
| `zh-CN-XiaoyiNeural` | 女 | 年轻、活泼 | 美妆、年轻向、休闲游戏 |
| `zh-CN-YunxiNeural` | 男 | 阳光、活泼 | 年轻向, 大众游戏推荐 |
| `zh-CN-YunxiaNeural` | 男 | 温暖 | 怀旧回顾、知识科普 |
| `zh-CN-YunyangNeural` | 男 | 沉稳、专业 | 财经、数码评测、深度内容 |
| `zh-CN-YunjianNeural` | 男 | 解说员、磁性 | 游戏解说、剧情向、硬核题材 |
| `zh-HK-HiuMaanNeural` | 女 | 粤语 | 港服内容专题 |

题材→音色对应建议:
- 折扣/新游/常规推荐 → 晓晓/晓伊
- 怀旧回顾 → 云夏 (温暖)
- 硬核/魂系/剧情向 → 云健 (磁性解说员)
- 数码评测/主机选购 → 云扬 (专业)

## 输出结构

```
voice/
├── intro.mp3
├── seg_001_<slug>.mp3
├── seg_002_<slug>.mp3
├── ...
├── outro.mp3
└── voice_index.json   # 含每段实际时长, 视频剪辑用
```

## 报告结果

告知用户:
- 共生成多少段
- 总时长 (即视频成品时长, 因画面会跟着念词走)
- 输出目录
- 下一步: 视频剪辑器加 `--voice-dir voice/`

## 常见问题

- `edge-tts: command not found` → `pip install edge-tts --break-system-packages`
- 网络超时 → edge-tts 是在线服务, 极个别地区受限
- `Invalid voice` → 音色名拼错, 必须含 `Neural` 后缀, 区分大小写
- 多音字念错 → 在 script.txt 改写那个字 (用同音字或换说法)

## 离线替代方案 (如有需要)

`edge-tts` 是在线的。若用户必须离线, 推荐:
- **Kokoro-82M** (Apache 2.0, 可商用, CPU 即可, 4.5 秒生成 2 分钟语音)
- **CosyVoice** (阿里开源, 质量更高但需 GPU)
- **PaddleSpeech** (百度老牌)

默认仍推 edge-tts (装一个 pip 包搞定, 质量足够)。

## 不要做什么

- 不要在文案塞 emoji (会被读成"哭笑表情符号")
- 单段不要超 200 字 (偶尔漏字)
- 不要把英文单词直接拼进中文音色 ("PS5"会念成"P S 五", 应改成"PS 五"或"PlayStation 5")
