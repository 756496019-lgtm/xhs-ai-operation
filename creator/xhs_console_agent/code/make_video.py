"""
一键全流程: 素材采集 -> 文案 -> 配音 -> 剪视频 -> 出封面
==========================================================

支持两种入口:

A. 商店折扣/新品/即将发售 (内置爬虫):
    python make_video.py --section deals --limit 5 --title "本周骨折5款必买"
    python make_video.py --section new --limit 5 --title "本周新游"

B. 自定义游戏列表 (任意题材):
    python make_video.py --names "塞尔达 王国之泪" "艾尔登法环" "黑神话悟空" \
        --topic "本周值得入手的3款魂系游戏" \
        --title "魂游必玩TOP3"

通用参数:
    --voice zh-CN-YunjianNeural       # 换音色 (默认晓晓)
    --voice-rate=-10%                  # 调语速
    --no-voice                         # 不要配音
    --references references.md         # 加对标素材 (仅 prompt 模式)
    --script-mode prompt|preset-deals|preset-new|preset-coming
                                       # 文案模式 (默认 prompt)
    --ps-url "..."                     # 加 PS Store 数据 (section 模式)
    --script run/.../script.txt        # 用已有文案, 跳过爬取/写文案 (.txt 或 .json 都行)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "code" / "scrapers"))
sys.path.insert(0, str(ROOT / "code" / "video"))
sys.path.insert(0, str(ROOT / "code" / "cover"))

import scrape_all
import scrape_by_names
import pv_downloader
import script_generator
import video_editor
import cover_generator


def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # 入口 A: 商店爬取
    ap.add_argument("--section", choices=["deals", "new", "coming_soon"],
                    default=None, help="商店板块 (与 --names 互斥)")
    # 入口 B: 自定义游戏列表
    ap.add_argument("--names", nargs="*", default=[],
                    help="游戏名列表 (与 --section 互斥)")
    ap.add_argument("--names-file", default=None, help="一行一个游戏名的 txt")
    ap.add_argument("--tag", default="custom", help="自定义模式下的输出 tag")

    # 通用
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--ps-url", default=None, help="(仅 section 模式) PS Store 分类页 URL")

    # 文案
    ap.add_argument("--topic", default=None,
                    help="本期主题 (仅 prompt 模式), 例如:'本周值得入手的5款魂系'")
    ap.add_argument("--script-mode",
                    choices=["prompt", "preset-deals", "preset-new", "preset-coming"],
                    default="prompt",
                    help="文案模式 (默认 prompt)")
    ap.add_argument("--references", default=None, help="对标素材 md/txt")
    ap.add_argument("--script", default=None,
                    help="已有文案文件 (script.txt 或 script.json, 跳过素材采集和文案生成)")

    # 输出
    ap.add_argument("--title", required=True, help="封面标题")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--workdir", default="run")

    # 配音
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    ap.add_argument("--voice-rate", default="+0%")

    # 封面 (高级: 模板模式)
    ap.add_argument("--cover-template", default=None,
                    help="封面底板 PNG 路径 (作图 AI 生成); 不传走简单模式")
    ap.add_argument("--cover-layout", default=None,
                    help="封面底板对应的布局 JSON; 不传则自动找同名 .json")
    args = ap.parse_args()

    # 互斥校验
    if args.section and (args.names or args.names_file):
        ap.error("--section 和 --names/--names-file 互斥, 二选一")
    if not args.script and not args.section and not args.names and not args.names_file:
        ap.error("必须指定 --section 或 --names/--names-file 之一 (或用 --script 跳过)")

    work = Path(args.workdir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    work.mkdir(parents=True, exist_ok=True)
    print(f"=== 工作目录: {work} ===\n")

    # ---- 跳过模式 ----
    if args.script:
        script_json = Path(args.script)
        guess = [script_json.parent / "pv_library",
                 script_json.parent.parent / "pv_library"]
        pv_lib = next((p for p in guess if p.exists()), None)
        if not pv_lib:
            print(f"[!] 找不到 pv_library, 请放在 {guess[0]}")
            sys.exit(1)
        index_json = pv_lib / "index.json"
        print(f"使用已有 script: {script_json}")
    else:
        # ---- 1. 素材采集 ----
        print("【步骤 1/5】素材采集")
        if args.section:
            sys.argv = ["scrape_all", "--section", args.section,
                        "--limit", str(args.limit), "--out", str(work / "data")]
            sys.argv += ["--ps-url", args.ps_url] if args.ps_url else ["--skip", "ps"]
            try:
                scrape_all.main()
            except SystemExit:
                pass
            data_files = sorted((work / "data").glob(f"all_{args.section}_*.json"))
        else:
            print(f"  按游戏名采集: {args.names or '(从文件读取)'}")
            sys.argv = ["scrape_by_names",
                        "--tag", args.tag, "--out", str(work / "data")]
            if args.names:
                sys.argv += ["--names", *args.names]
            if args.names_file:
                sys.argv += ["--names-file", args.names_file]
            try:
                scrape_by_names.main()
            except SystemExit:
                pass
            data_files = sorted((work / "data").glob(f"all_{args.tag}_*.json"))

        if not data_files:
            print("[!] 素材采集失败"); sys.exit(1)
        data_json = data_files[-1]

        # ---- 2. 下 PV ----
        print(f"\n【步骤 2/5】下载预告片")
        sys.argv = ["pv_downloader", "--input", str(data_json),
                    "--out", str(work / "pv_library"), "--max-per-game", "1"]
        pv_downloader.main()
        pv_lib = work / "pv_library"
        index_json = pv_lib / "index.json"

        # ---- 3. 文案 ----
        print(f"\n【步骤 3/5】文案 (mode={args.script_mode})")
        if args.script_mode == "prompt":
            out_path = work / "prompt.txt"
            sys.argv = ["script_generator", "--input", str(index_json),
                        "--mode", "prompt", "--out", str(out_path)]
            if args.topic:
                sys.argv += ["--topic", args.topic]
            if args.references:
                sys.argv += ["--references", args.references]
            script_generator.main()

            print(f"\n[!] Prompt 模式: 生成了 {out_path}")
            print(f"    Code Buddy 应该读取 {out_path} 并写出文案保存为 {work}/script.txt")
            print(f"    然后重跑: python code/make_video.py --title '{args.title}' "
                  f"--script {work}/script.txt")
            return
        else:
            out_path = work / "script.txt"
            sys.argv = ["script_generator", "--input", str(index_json),
                        "--mode", args.script_mode, "--out", str(out_path)]
            script_generator.main()
            script_json = out_path

    # ---- 4. 配音 ----
    voice_dir = work / "voice"
    if not args.no_voice:
        print(f"\n【步骤 4/5】配音 (voice={args.voice})")
        try:
            import tts_generator
            with open(script_json, "r", encoding="utf-8") as f:
                _script = json.load(f)
            asyncio.run(tts_generator.synthesize_all(
                _script, args.voice, args.voice_rate, "+0%", voice_dir))
        except ImportError:
            print("[!] edge-tts 未装, 出无声版本; pip install edge-tts 后再来")
            voice_dir = None
        except Exception as e:
            print(f"[!] 配音失败 ({e}), 出无声版本"); voice_dir = None
    else:
        print(f"\n【步骤 4/5】跳过配音"); voice_dir = None

    # ---- 5. 剪视频 + 封面 ----
    print(f"\n【步骤 5/5】剪视频 + 封面")
    video_editor.check_ffmpeg()
    video_path = video_editor.assemble(
        script_json, pv_lib, work / "output", voice_dir=voice_dir)

    games = json.load(open(index_json, "r", encoding="utf-8"))[: max(4, args.limit)]
    cover_path = cover_generator.build_cover(
        games, args.title, args.subtitle,
        template_path=args.cover_template,
        layout_path=args.cover_layout,
        out_path=work / "output" / "cover.jpg")

    print("\n" + "=" * 50)
    print("全部完成!")
    print(f"  视频: {video_path}")
    print(f"  封面: {cover_path}")
    print(f"  字幕: {video_path.with_suffix('.srt')}")
    print(f"  文案: {script_json}")
    if voice_dir:
        print(f"  配音: {voice_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
