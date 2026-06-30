"""
视频剪辑器 v2 — 根据文案剪 PV, 支持配音
==========================================
读 script.json (文案) + pv_library/ (预告片库) [+ voice/ (配音, 可选)],
按文案 segments 顺序拼成 1080x1920 竖屏 MP4。

新增配音支持:
- 如果传了 --voice-dir, 视频会用配音的实际时长决定每段画面的长度
  (这样画面和念词严格对齐, 不会出现"画面播完了还在念"或"画面剩一半就没声了")
- 没传 --voice-dir 就退化为 v1 行为: 用 script.json 里写的 duration_sec
- PV 自带的原声会被压低或静音, 由 --bgm-volume 控制 (默认 0.1, 几乎静音)

依赖: ffmpeg
用法:
    # 不带配音 (静音视频, 加字幕)
    python video_editor.py --script script.json --pv-lib pv_library

    # 带配音
    python video_editor.py --script script.json --pv-lib pv_library --voice-dir voice/

输出:
    output/video_<ts>.mp4
    output/video_<ts>.srt
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VIDEO_W, VIDEO_H = 1080, 1920
FPS = 30


def run(cmd, quiet=False):
    if not quiet:
        print("  $", " ".join(str(c) for c in cmd[:6]) +
              (" ..." if len(cmd) > 6 else ""))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise RuntimeError(f"ffmpeg 失败: {' '.join(cmd[:3])}")
    return res


def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        print("错误: 找不到 ffmpeg。请安装:", file=sys.stderr)
        print("  Mac:    brew install ffmpeg", file=sys.stderr)
        print("  Win:    https://www.gyan.dev/ffmpeg/builds/", file=sys.stderr)
        print("  Linux:  sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)


def probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def find_pv(pv_lib: Path, slug: str, name: str):
    candidate = pv_lib / slug
    if candidate.exists():
        for ext in ("trailer_01.mp4", "trailer_01.webm", "trailer_01.mov"):
            p = candidate / ext
            if p.exists():
                return p
        mp4s = list(candidate.glob("*.mp4"))
        if mp4s:
            return mp4s[0]
    for d in pv_lib.iterdir():
        if d.is_dir() and (slug in d.name or d.name in slug):
            mp4s = list(d.glob("*.mp4"))
            if mp4s:
                return mp4s[0]
    return None


def find_font():
    """找一个能渲染中文的字体, 找不到就退到默认 (中文方块)。"""
    candidates = [
        # 项目内自带的优先
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "SourceHanSansSC-Bold.otf",
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "NotoSansCJK-Bold.ttc",
        # 系统字体
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ""


FONT_PATH = None


def _font():
    global FONT_PATH
    if FONT_PATH is None:
        FONT_PATH = find_font()
        if FONT_PATH:
            print(f"  [字体] 使用 {FONT_PATH}")
        else:
            print(f"  [字体] 警告: 没找到字体, 中文将显示为方块", file=sys.stderr)
    return FONT_PATH


def _wrap(text: str, per_line: int = 16) -> str:
    out, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= per_line and ch in "，。！？、 ,.!?":
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return "\n".join(out)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def make_clip_from_video(src: Path, duration: float, caption: str,
                         work_dir: Path, idx: int,
                         voice_path=None, bgm_volume: float = 0.1) -> Path:
    src_dur = probe_duration(src)
    start = max(0.5, min(src_dur * 0.15, src_dur - duration - 0.5))
    if start < 0:
        start = 0

    out = work_dir / f"clip_{idx:03d}.mp4"
    font_path = _font()
    safe = _esc(caption)
    drawtext = ""
    if font_path:
        drawtext = (
            f"drawtext=fontfile='{font_path}':"
            f"text='{safe}':fontcolor=white:fontsize=42:"
            f"box=1:boxcolor=black@0.6:boxborderw=20:"
            f"x=(w-text_w)/2:y=h-300"
        )

    vf_parts = [
        f"scale={VIDEO_W}:-2",
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=black",
    ]
    if drawtext:
        vf_parts.append(drawtext)
    vf = ",".join(vf_parts)

    if voice_path and Path(voice_path).exists():
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.2f}", "-t", f"{duration:.2f}",
            "-i", str(src),
            "-i", str(voice_path),
            "-filter_complex",
            f"[0:v]{vf}[v];"
            f"[0:a]volume={bgm_volume},apad[a0];"
            f"[1:a]volume=1.6,apad[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "[v]", "-map", "[a]",
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(out),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.2f}", "-t", f"{duration:.2f}",
            "-i", str(src),
            "-vf", vf,
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
    run(cmd, quiet=True)
    return out


def make_card_clip(text: str, duration: float, work_dir: Path, idx: int,
                   voice_path=None, bg_color: str = "0xff2442") -> Path:
    out = work_dir / f"card_{idx:03d}.mp4"
    font_path = _font()
    safe = _esc(text)
    drawtext = ""
    if font_path:
        drawtext = (
            f"drawtext=fontfile='{font_path}':"
            f"text='{safe}':fontcolor=white:fontsize=72:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )

    if voice_path and Path(voice_path).exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"color=c={bg_color}:s={VIDEO_W}x{VIDEO_H}:d={duration}:r={FPS}",
            "-i", str(voice_path),
        ]
        if drawtext:
            cmd += ["-vf", drawtext]
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(out),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"color=c={bg_color}:s={VIDEO_W}x{VIDEO_H}:d={duration}:r={FPS}",
            "-f", "lavfi", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest",
        ]
        if drawtext:
            cmd += ["-vf", drawtext]
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
    run(cmd, quiet=True)
    return out


def concat_clips(clips, out_path: Path):
    list_file = out_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{c.absolute()}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out_path),
    ]
    try:
        run(cmd)
    except RuntimeError:
        print("  [concat] copy 失败, 改用重编码...")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        run(cmd)


def make_srt(timeline, out_path: Path):
    def fmt(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s - h*3600 - m*60
        return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")
    lines = []
    for i, item in enumerate(timeline, 1):
        lines.append(f"{i}\n{fmt(item['t_start'])} --> {fmt(item['t_end'])}\n{item['text']}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def load_voice_index(voice_dir):
    if not voice_dir:
        return None
    idx_path = Path(voice_dir) / "voice_index.json"
    if not idx_path.exists():
        print(f"  [voice] 警告: {idx_path} 不存在, 不使用配音", file=sys.stderr)
        return None
    with open(idx_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_voice_for(voice_index, role, segment_idx=None, voice_dir=None):
    if not voice_index:
        return None, None
    for it in voice_index["items"]:
        if it["role"] == role and (
            role != "segment" or it.get("index") == segment_idx
        ):
            return Path(voice_dir) / it["file"], it["duration_sec"]
    return None, None


def assemble(script_path: Path, pv_lib: Path, out_dir: Path,
             voice_dir=None, bgm_volume: float = 0.1) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    voice_index = load_voice_index(voice_dir)
    if voice_index:
        print(f"[voice] 启用配音: {voice_dir} (共 {len(voice_index['items'])} 段)")

    work_dir = out_dir / "_clips_tmp"
    work_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    timeline = []
    t_cur = 0.0

    if script.get("intro"):
        v_path, v_dur = get_voice_for(voice_index, "intro", voice_dir=voice_dir)
        dur = (v_dur + 0.3) if v_dur else max(4, len(script["intro"]) / 4)
        print(f"[intro] {dur:.1f}s")
        clips.append(make_card_clip(_wrap(script["intro"], 14), dur, work_dir, 0,
                                    voice_path=v_path))
        timeline.append({"text": script["intro"], "t_start": t_cur, "t_end": t_cur + dur})
        t_cur += dur

    for i, seg in enumerate(script.get("segments", []), 1):
        slug, name = seg["game_slug"], seg["game_name"]
        text = seg["text"]
        v_path, v_dur = get_voice_for(voice_index, "segment", segment_idx=i,
                                      voice_dir=voice_dir)
        if v_dur:
            dur = v_dur + 0.3
        else:
            dur = seg.get("duration_sec", 8)
        print(f"[seg {i}] {name}  {dur:.1f}s")

        pv = find_pv(pv_lib, slug, name)
        if pv:
            print(f"    PV: {pv.name}")
            clip = make_clip_from_video(pv, dur, _wrap(text, 18), work_dir, i,
                                        voice_path=v_path, bgm_volume=bgm_volume)
        else:
            print(f"    [!] 没找到 PV, 用文字卡片代替")
            clip = make_card_clip(_wrap(f"{name}\n\n{text}", 14), dur,
                                  work_dir, i, voice_path=v_path,
                                  bg_color="0x222222")
        clips.append(clip)
        timeline.append({"text": text, "t_start": t_cur, "t_end": t_cur + dur})
        t_cur += dur

    if script.get("outro"):
        v_path, v_dur = get_voice_for(voice_index, "outro", voice_dir=voice_dir)
        dur = (v_dur + 0.3) if v_dur else max(5, len(script["outro"]) / 4)
        print(f"[outro] {dur:.1f}s")
        clips.append(make_card_clip(_wrap(script["outro"], 14), dur,
                                    work_dir, 999, voice_path=v_path))
        timeline.append({"text": script["outro"], "t_start": t_cur, "t_end": t_cur + dur})
        t_cur += dur

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_video = out_dir / f"video_{ts}.mp4"
    print(f"\n[concat] 拼接 {len(clips)} 个片段")
    concat_clips(clips, out_video)

    srt = out_dir / f"video_{ts}.srt"
    make_srt(timeline, srt)
    print(f"\n[done] 视频: {out_video}  (总时长 {t_cur:.1f}s)")
    print(f"[done] 字幕: {srt}")
    return out_video


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--pv-lib", required=True)
    ap.add_argument("--voice-dir", default=None,
                    help="tts_generator.py 的输出目录 (含 voice_index.json)")
    ap.add_argument("--bgm-volume", type=float, default=0.1,
                    help="原 PV 声音音量 (0=静音, 1=原始); 默认 0.1")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    check_ffmpeg()
    assemble(Path(args.script), Path(args.pv_lib), Path(args.out),
             voice_dir=args.voice_dir, bgm_volume=args.bgm_volume)


if __name__ == "__main__":
    main()
