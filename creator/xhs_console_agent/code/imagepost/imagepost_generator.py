"""
图文笔记生成器 (小红书 5-10 张图文)
====================================

输出: 一组 1080x1440 PNG, 第 1 张是封面, 后面是内容卡片。

三种入口模式 (CLI --mode):

1. full       从素材数据 + 文案一键生成 (复用 script.json schema)
2. text-only  仅给文案文件, 不需要游戏数据 (用户自己有写好的笔记内容)
3. on-image   用户提供底图 (来自 lightai 或其他作图工具), 工具只在底图上打文字

模式 A: --mode full
    --script script.txt 文案
    --pv-lib pv_library/ 用来取游戏封面图 (可选)
    --out images/

模式 B: --mode text-only
    --text content.txt 文案文本文件 (一段一段, 每段一张卡片)
    --out images/

模式 C: --mode on-image
    --backgrounds bg1.png bg2.png ... 底图列表 (顺序对应卡片顺序)
    --text content.txt 文案 (每段对应一张底图)
    --layout layout.txt 文字位置布局 (可选, 没传就居中)
    --out images/

text/script 文件格式:
    第一行: 标题 (封面用)
    然后每段一行 (空行分割), 每段对应一张卡片

通用参数:
    --style default | playful | retro    样式
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


W, H = 1080, 1440


# ============== 工具函数 ==============

def find_font(custom: str | None = None, regular: bool = False) -> str | None:
    candidates = [custom] if custom else []
    root = Path(__file__).parent.parent.parent / "assets" / "fonts"
    candidates.extend([
        root / "SourceHanSansSC-Bold.otf",
        root / "NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ])
    for p in candidates:
        if p and Path(p).exists():
            return str(p)
    return None


def load_image(src) -> Image.Image:
    src = str(src)
    if src.startswith("http"):
        r = requests.get(src, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    return Image.open(src).convert("RGBA")


def fit_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    sr = img.width / img.height
    dr = w / h
    if sr > dr:
        nh, nw = h, int(h * sr)
    else:
        nw, nh = w, int(w / sr)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def wrap_chinese(text: str, max_chars: int) -> list[str]:
    """中文按字数硬换行 (兼容英文单词不切断)"""
    lines = []
    cur = ""
    for ch in text:
        if ch == "\n":
            if cur:
                lines.append(cur)
                cur = ""
            continue
        cur += ch
        if len(cur) >= max_chars and ch in "，。！？、,.!? ":
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def draw_text_box(canvas, draw, x, y, w, h, text, font_path,
                  size=48, color="#1a1a1a", line_height=1.4,
                  max_chars_per_line=18, anchor="ma", stroke=None):
    """在指定 box 内绘制文字, 自动换行 + 缩字号"""
    cur_size = size
    while cur_size > 24:
        font = ImageFont.truetype(font_path, cur_size)
        # 估算每行字数
        sample_w = draw.textbbox((0, 0), "测", font=font)[2]
        max_chars = max(1, int(w / sample_w))
        max_chars = min(max_chars, max_chars_per_line)
        lines = wrap_chinese(text, max_chars)
        total_h = int(cur_size * line_height * len(lines))
        if total_h <= h:
            break
        cur_size -= 4

    line_h = int(cur_size * line_height)
    if anchor == "ma":
        # 中上对齐: x 是中心, y 是顶端
        start_y = y
    elif anchor == "mm":
        start_y = y - len(lines) * line_h // 2
    else:
        start_y = y

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        line_x = x - lw // 2
        line_y = start_y + i * line_h
        if stroke:
            for dx in (-2, 0, 2):
                for dy in (-2, 0, 2):
                    if dx or dy:
                        draw.text((line_x + dx, line_y + dy),
                                  line, font=font, fill=stroke)
        draw.text((line_x, line_y), line, font=font, fill=color)
    return cur_size


# ============== 卡片模板 (Pillow 程序化) ==============

def make_cover_card(title: str, subtitle: str = "", font_path: str = None,
                    bg_image: Image.Image = None,
                    style: str = "default",
                    cards_preview: list[str] = None) -> Image.Image:
    """封面卡片
    cards_preview: 可选, 如 ['塞尔达 王国之泪', '艾尔登法环', ...], 中间会渲染索引
    """
    canvas = Image.new("RGBA", (W, H), "white")

    if bg_image:
        # 用底图 + 暗色蒙版
        bg = fit_crop(bg_image, W, H)
        canvas.paste(bg, (0, 0))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 100))
        canvas.alpha_composite(overlay, (0, 0))
    elif style == "playful":
        # 渐变背景
        for y in range(H):
            r = int(255 - y / H * 50)
            g = int(240 - y / H * 30)
            b = int(220 - y / H * 20)
            ImageDraw.Draw(canvas).line([(0, y), (W, y)], fill=(r, g, b))
    elif style == "retro":
        canvas = Image.new("RGBA", (W, H), "#f4ecd8")
    else:
        # default: 顶部彩色色块 (标题区) + 底部副标题区
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, 0, W, 480], fill="#FFE9C2")
        d.rectangle([40, 40, W - 40, 440], fill="white",
                     outline="#FFA947", width=8)
        # 底部副标题胶囊条
        d.rounded_rectangle([60, 1340, W - 60, 1420], radius=40,
                             fill="#FFE9C2", outline="#FFA947", width=4)

    draw = ImageDraw.Draw(canvas)

    if font_path:
        if bg_image:
            # 底图模式: 标题居中靠上
            title_box_y, title_box_h = 320, 480
            title_max_chars = 10
            title_size = 96
            title_color = "white"
            title_stroke = "#000000"
        else:
            # default 模式: 标题在顶部色块内
            title_box_y, title_box_h = 80, 320
            title_max_chars = 9
            title_size = 100
            title_color = "#1a1a1a"
            title_stroke = None

        draw_text_box(canvas, draw,
                      x=W // 2, y=title_box_y,
                      w=W - 160, h=title_box_h,
                      text=title, font_path=font_path,
                      size=title_size,
                      color=title_color,
                      line_height=1.2,
                      max_chars_per_line=title_max_chars,
                      stroke=title_stroke)

        if subtitle:
            if bg_image:
                sub_y = 900
                sub_color, sub_stroke = "white", "#000000"
            else:
                sub_y = 1360
                sub_color, sub_stroke = "#1a1a1a", None
            draw_text_box(canvas, draw,
                          x=W // 2, y=sub_y, w=W - 200, h=120,
                          text=subtitle, font_path=font_path,
                          size=56,
                          color=sub_color,
                          line_height=1.4,
                          max_chars_per_line=16,
                          stroke=sub_stroke)

        # 中部内容索引 (default 风格, 无底图时)
        if cards_preview and not bg_image:
            try:
                idx_font = ImageFont.truetype(font_path, 48)
                num_font = ImageFont.truetype(font_path, 56)
            except Exception:
                idx_font = ImageFont.load_default()
                num_font = ImageFont.load_default()
            # 最多 6 行
            items = cards_preview[:6]
            line_h = 100
            block_h = len(items) * line_h
            start_y = 580 + (660 - block_h) // 2  # 居中于中部 580-1240 区域
            for i, name in enumerate(items):
                y = start_y + i * line_h
                # 圆形序号
                cx = 130
                draw.ellipse([cx - 30, y - 30, cx + 30, y + 30], fill="#FF2442")
                num = str(i + 1)
                bbox = draw.textbbox((0, 0), num, font=num_font)
                nw = bbox[2] - bbox[0]
                draw.text((cx - nw // 2, y - 30), num, font=num_font, fill="white")
                # 游戏名
                name_display = name if len(name) <= 12 else name[:11] + "…"
                draw.text((cx + 60, y - 22), name_display, font=idx_font,
                          fill="#1a1a1a")

    return canvas


def make_content_card(idx: int, total: int, heading: str, body: str,
                       font_path: str = None,
                       bg_image: Image.Image = None,
                       style: str = "default") -> Image.Image:
    """内容卡片 (第 idx 张 / 共 total 张)"""
    if bg_image:
        canvas = fit_crop(bg_image, W, H).copy()
        # 加暗色底, 文字才看得清
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 120))
        canvas.alpha_composite(overlay, (0, 0))
    elif style == "playful":
        canvas = Image.new("RGBA", (W, H), "#fff5e6")
    elif style == "retro":
        canvas = Image.new("RGBA", (W, H), "#f4ecd8")
    else:
        canvas = Image.new("RGBA", (W, H), "white")

    draw = ImageDraw.Draw(canvas)

    # 顶部页码徽章
    if font_path and not bg_image:
        badge_font = ImageFont.truetype(font_path, 36)
        badge_text = f"{idx} / {total}"
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # 圆角矩形徽章
        bx, by = 60, 60
        draw.rounded_rectangle([bx, by, bx + bw + 40, by + bh + 24],
                                radius=20, fill="#FF2442")
        draw.text((bx + 20, by + 12), badge_text, font=badge_font, fill="white")

    if font_path:
        # 标题 (heading)
        text_color = "white" if bg_image else "#1a1a1a"
        body_color = "#f8f8f8" if bg_image else "#333333"
        stroke = "#000000" if bg_image else None

        heading_y = 200 if not bg_image else 250
        draw_text_box(canvas, draw,
                      x=W // 2, y=heading_y, w=W - 160, h=200,
                      text=heading, font_path=font_path,
                      size=72,
                      color=text_color,
                      line_height=1.3,
                      max_chars_per_line=14,
                      stroke=stroke)

        # 正文 (body)
        body_y = heading_y + 280 if not bg_image else heading_y + 320
        draw_text_box(canvas, draw,
                      x=W // 2, y=body_y, w=W - 200, h=H - body_y - 200,
                      text=body, font_path=font_path,
                      size=52,
                      color=body_color,
                      line_height=1.6,
                      max_chars_per_line=18,
                      stroke=stroke)

    return canvas


# ============== 入口: 三种模式 ==============

def parse_text_file(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """
    解析文案文件:
    - 第一行: 标题
    - 后面每段 (空行分割) 一张卡片: 第一行=heading, 其余=body
    返回 (title, [(heading, body), ...])
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        raise ValueError("文案文件为空")
    title = blocks[0].strip().split("\n")[0]
    cards = []
    for b in blocks[1:]:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lines) == 1:
            cards.append(("", lines[0]))
        else:
            cards.append((lines[0], "\n".join(lines[1:])))
    return title, cards


def parse_script_json(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """从 script.txt/json 解析 (复用视频文案 schema)"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    title = data["title"]
    cards = []
    for seg in data.get("segments", []):
        heading = seg.get("game_name", "")
        body = seg.get("text", "")
        cards.append((heading, body))
    return title, cards


def run_text_only(text_path, out_dir, style="default", subtitle=""):
    title, cards = parse_text_file(text_path)
    font = find_font()
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(cards) + 1

    print(f"[图文] 标题: {title}, 共 {n} 张")
    # 提取每段的 heading 作为封面索引 (若 heading 为空就用 body 前 12 字)
    previews = []
    for h, b in cards:
        if h:
            previews.append(h)
        else:
            previews.append(b[:12])

    cover = make_cover_card(title, subtitle=subtitle, font_path=font, style=style,
                             cards_preview=previews)
    cover.convert("RGB").save(out_dir / "01_cover.jpg", quality=92)
    print(f"  ✓ 01_cover.jpg")

    for i, (h, b) in enumerate(cards, 1):
        card = make_content_card(i, len(cards), h, b, font_path=font, style=style)
        out = out_dir / f"{i+1:02d}_card.jpg"
        card.convert("RGB").save(out, quality=92)
        print(f"  ✓ {out.name}")


def run_full(script_path, pv_lib, out_dir, style="default"):
    """模式 A: 用 script.txt + pv_library 一条龙生成 (复用视频文案 schema)"""
    title, cards = parse_script_json(script_path)
    font = find_font()
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(cards) + 1

    print(f"[图文] full 模式: {title}, 共 {n} 张")

    # 封面: 用第一个游戏的封面图当背景
    cover_bg = None
    if pv_lib:
        with open(script_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data["segments"]:
            slug = data["segments"][0]["game_slug"]
            meta_path = Path(pv_lib) / slug / "meta.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("header_image"):
                    try:
                        cover_bg = load_image(meta["header_image"])
                    except Exception:
                        pass

    cover = make_cover_card(title, subtitle="", font_path=font,
                             bg_image=cover_bg, style=style)
    cover.convert("RGB").save(out_dir / "01_cover.jpg", quality=92)
    print(f"  ✓ 01_cover.jpg")

    # 每张内容卡片用对应游戏的封面图作背景
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for i, seg in enumerate(data["segments"], 1):
        slug = seg["game_slug"]
        bg = None
        meta_path = Path(pv_lib) / slug / "meta.json" if pv_lib else None
        if meta_path and meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("header_image"):
                try:
                    bg = load_image(meta["header_image"])
                except Exception:
                    pass
        heading = seg["game_name"]
        body = seg["text"]
        card = make_content_card(i, len(data["segments"]),
                                  heading, body,
                                  font_path=font, bg_image=bg, style=style)
        out = out_dir / f"{i+1:02d}_card.jpg"
        card.convert("RGB").save(out, quality=92)
        print(f"  ✓ {out.name}")


def run_on_image(backgrounds, text_path, out_dir, style="default"):
    """模式 C: 用户提供底图 + 文案, 工具只打字"""
    title, cards = parse_text_file(text_path)
    font = find_font()
    out_dir.mkdir(parents=True, exist_ok=True)

    bgs = [load_image(b) for b in backgrounds]
    if len(bgs) < 1:
        raise ValueError("至少要提供 1 张底图 (封面用)")

    print(f"[图文] on-image 模式: {title}, 底图 {len(bgs)} 张, 内容卡片 {len(cards)} 段")

    # 封面用第 1 张底图
    cover = make_cover_card(title, font_path=font, bg_image=bgs[0], style=style)
    cover.convert("RGB").save(out_dir / "01_cover.jpg", quality=92)
    print(f"  ✓ 01_cover.jpg")

    # 内容卡片用后面的底图; 不够时循环用最后一张
    for i, (h, b) in enumerate(cards, 1):
        bg_idx = min(i, len(bgs) - 1)
        bg = bgs[bg_idx] if bg_idx < len(bgs) else bgs[-1]
        card = make_content_card(i, len(cards), h, b,
                                  font_path=font, bg_image=bg, style=style)
        out = out_dir / f"{i+1:02d}_card.jpg"
        card.convert("RGB").save(out, quality=92)
        print(f"  ✓ {out.name}")


def main():
    ap = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--mode", choices=["full", "text-only", "on-image"],
                    default="text-only")
    ap.add_argument("--script", default=None,
                    help="(mode=full) script.txt 文案文件 (复用视频 schema)")
    ap.add_argument("--pv-lib", default=None,
                    help="(mode=full) pv_library/ 目录, 提供游戏封面背景")
    ap.add_argument("--text", default=None,
                    help="(mode=text-only / on-image) 纯文案文件 .txt")
    ap.add_argument("--backgrounds", nargs="*", default=[],
                    help="(mode=on-image) 底图列表, 顺序对应封面+各卡片")
    ap.add_argument("--style", choices=["default", "playful", "retro"],
                    default="default")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out", default="imagepost_out")
    args = ap.parse_args()

    out_dir = Path(args.out)

    if args.mode == "full":
        if not args.script:
            ap.error("--mode full 必须提供 --script")
        run_full(Path(args.script), args.pv_lib, out_dir, style=args.style)
    elif args.mode == "text-only":
        if not args.text:
            ap.error("--mode text-only 必须提供 --text")
        run_text_only(Path(args.text), out_dir, style=args.style,
                       subtitle=args.subtitle)
    else:  # on-image
        if not args.backgrounds:
            ap.error("--mode on-image 必须提供 --backgrounds")
        if not args.text:
            ap.error("--mode on-image 必须提供 --text")
        run_on_image(args.backgrounds, Path(args.text), out_dir, style=args.style)

    print(f"\n[done] 全部完成, 文件在: {out_dir}/")


if __name__ == "__main__":
    main()
