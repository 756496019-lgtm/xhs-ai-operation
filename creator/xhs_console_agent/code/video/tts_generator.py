"""
免费配音生成器 (基于微软 Edge TTS)
=====================================
把 script.json 里每一段文字转成 mp3 配音, 完全免费, 不需要 API key,
不需要 GPU, 不需要梯子。

依赖:
    pip install edge-tts --break-system-packages

工作原理:
    edge-tts 复用了 Edge 浏览器调用的微软在线 TTS 接口, 速度快, 音质好。
    生成的 mp3 是 24khz 单声道, 适合短视频。

输入:
    script.json (script_generator 生成的, 或运营自己写的)

输出:
    voice/
      intro.mp3
      seg_001_<slug>.mp3
      seg_002_<slug>.mp3
      ...
      outro.mp3
      voice_index.json   <- 每个 mp3 的实际时长, 视频剪辑要用

中文音色推荐 (按性别/调性挑):
    zh-CN-XiaoxiaoNeural  晓晓 - 女声, 标准/亲和, 万能选项 ✅ 默认
    zh-CN-XiaoyiNeural    晓伊 - 女声, 年轻/活泼, 适合美妆/穿搭/游戏
    zh-CN-YunxiNeural     云希 - 男声, 阳光/活泼, 适合年轻向
    zh-CN-YunxiaNeural    云夏 - 男声, 温暖, 适合知识科普
    zh-CN-YunyangNeural   云扬 - 男声, 沉稳/专业, 适合财经/数码
    zh-CN-YunjianNeural   云健 - 男声, 解说员/磁性
    zh-HK-HiuMaanNeural   曉曼 - 粤语女声
    zh-TW-HsiaoChenNeural 曉臻 - 台湾国语女声

完整列表用命令: edge-tts --list-voices

用法:
    python tts_generator.py --script script.json --out voice/
    python tts_generator.py --script ... --voice zh-CN-XiaoyiNeural --rate -10%
    python tts_generator.py --script ... --voice zh-CN-YunxiNeural   # 男声
"""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    print("错误: 没装 edge-tts。请运行: pip install edge-tts --break-system-packages",
          file=sys.stderr)
    sys.exit(1)


DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def slugify(s: str) -> str:
    return (re.sub(r"[^\w\u4e00-\u9fa5]+", "_", s).strip("_") or "x")[:40]


def probe_duration(path: Path) -> float:
    """ffprobe 拿 mp3 时长。没装 ffmpeg 也不会崩, 只是返回 0。"""
    if not shutil.which("ffprobe"):
        return 0.0
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


async def synthesize(text: str, voice: str, rate: str, volume: str,
                     out_path: Path):
    """单段文字 -> mp3。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        text=text, voice=voice, rate=rate, volume=volume,
    )
    await communicate.save(str(out_path))


async def synthesize_all(script: dict, voice: str, rate: str, volume: str,
                         out_dir: Path) -> dict:
    """把整个 script.json 转完整的配音库。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {"voice": voice, "rate": rate, "volume": volume, "items": []}

    # intro
    if script.get("intro"):
        intro_path = out_dir / "intro.mp3"
        print(f"  [intro] {script['intro'][:30]}...")
        await synthesize(script["intro"], voice, rate, volume, intro_path)
        dur = probe_duration(intro_path)
        index["items"].append({
            "role": "intro", "text": script["intro"],
            "file": intro_path.name, "duration_sec": dur,
        })

    # segments
    for i, seg in enumerate(script.get("segments", []), 1):
        slug = slugify(seg.get("game_slug") or seg.get("game_name", "x"))
        seg_path = out_dir / f"seg_{i:03d}_{slug}.mp3"
        print(f"  [seg {i}] {seg['game_name']}: {seg['text'][:30]}...")
        await synthesize(seg["text"], voice, rate, volume, seg_path)
        dur = probe_duration(seg_path)
        index["items"].append({
            "role": "segment",
            "index": i,
            "game_slug": seg["game_slug"],
            "game_name": seg["game_name"],
            "text": seg["text"],
            "file": seg_path.name,
            "duration_sec": dur,
        })

    # outro
    if script.get("outro"):
        outro_path = out_dir / "outro.mp3"
        print(f"  [outro] {script['outro'][:30]}...")
        await synthesize(script["outro"], voice, rate, volume, outro_path)
        dur = probe_duration(outro_path)
        index["items"].append({
            "role": "outro", "text": script["outro"],
            "file": outro_path.name, "duration_sec": dur,
        })

    # 写索引
    idx_path = out_dir / "voice_index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n[done] 配音索引: {idx_path}")

    total = sum(it["duration_sec"] for it in index["items"])
    print(f"[done] 共 {len(index['items'])} 段, 总时长 {total:.1f} 秒")
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="script.json 路径")
    ap.add_argument("--voice", default=DEFAULT_VOICE,
                    help="音色, 见脚本顶部注释")
    ap.add_argument("--rate", default="+0%",
                    help="语速, 如 -10% 慢一点, +20% 快一点 (默认 +0%)")
    ap.add_argument("--volume", default="+0%",
                    help="音量, 同 rate 格式 (默认 +0%)")
    ap.add_argument("--out", default="voice", help="输出目录")
    ap.add_argument("--list-voices", action="store_true",
                    help="只列出所有可用音色, 不生成")
    args = ap.parse_args()

    if args.list_voices:
        async def _list():
            voices = await edge_tts.list_voices()
            zh_voices = [v for v in voices if v["Locale"].startswith("zh")]
            for v in zh_voices:
                print(f"  {v['ShortName']:35s}  {v.get('Gender','?'):6s}  "
                      f"{v.get('FriendlyName','')}")
        asyncio.run(_list())
        return

    with open(args.script, "r", encoding="utf-8") as f:
        script = json.load(f)

    asyncio.run(synthesize_all(
        script, args.voice, args.rate, args.volume, Path(args.out),
    ))


if __name__ == "__main__":
    main()
