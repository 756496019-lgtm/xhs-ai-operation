"""
小红书封面生成器 (v2)
======================
两种模式:

1. **模板模式 (推荐, 视觉效果好)**:
   读取一张"封面模板图"(背景 + 标题底 + 副标题底 已经设计好的, 由作图 AI 生成),
   然后在指定位置拼上游戏封面 + 写上标题文字。

2. **简单模式 (默认, 无模板时)**:
   纯程序化生成 — 红底白字标题 + 游戏拼图。

模板素材怎么来:
- 让 Midjourney / Stable Diffusion / 即梦 / 其他作图 AI 一次性生成
- 提示词例子: "小红书游戏封面模板, 1080x1440 竖版, 顶部留出标题区(红色质感色块,
  带胶带感), 中间留出 4-6 个游戏封面位置(深色暗调背景), 底部留出副标题标签位"
- 生成后保存到 assets/templates/<风格名>.png + 配套 layout.json (定义各区域坐标)

模板风格做一次复用很久, 不需要每次出片重新生成。
"""

import argparse
import json
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 默认尺寸 (小红书竖版 3:4)
COVER_W, COVER_H = 1080, 1440


def load_image(src) -> Image.Image:
    src = str(src)
    if src.startswith("http"):
        r = requests.get(src, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    return Image.open(src).convert("RGBA")


def fit_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = int(h * src_ratio)
    else:
        new_w = w
        new_h = int(w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def round_corners(img: Image.Image, radius: int) -> Image.Image:
    """给 RGBA 图加圆角"""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def find_font(custom: str | None = None) -> str | None:
    candidates = [
        custom,
        # 项目内
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "SourceHanSansSC-Bold.otf",
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "NotoSansCJK-Bold.ttc",
        # 系统
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return str(p)
    return None


# ============== 默认布局 (无模板时使用) ==============

DEFAULT_LAYOUT = {
    "size": [COVER_W, COVER_H],
    "title_box": {"x": 0, "y": 0, "w": COVER_W, "h": 320, "bg": "#FF2442"},
    "title_text": {"x": 540, "y": 160, "size": 96, "color": "#FFFFFF",
                   "stroke_color": "#000000", "stroke_width": 3, "anchor": "mm"},
    "subtitle_text": {"x": 540, "y": 1380, "size": 44, "color": "#FFFFFF",
                      "stroke_color": "#000000", "stroke_width": 2, "anchor": "mm"},
    "subtitle_bg": {"x": 0, "y": 1340, "w": COVER_W, "h": 100, "color": "#222222"},
    "grid": {"x": 24, "y": 344, "w": 1032, "h": 980, "padding": 16, "corner_radius": 18},
    "label_overlay": True,
}

# 网格布局 (n -> 每个 cell 的 [rx, ry, rw, rh] 0..1 比例)
def grid_layout(n: int):
    if n <= 1: return [(0, 0, 1, 1)]
    if n == 2: return [(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)]
    if n == 3: return [(0, 0, 1, 0.5), (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)]
    if n == 4: return [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5),
                       (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)]
    if n == 5: return [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5),
                       (0, 0.5, 1/3, 0.5), (1/3, 0.5, 1/3, 0.5), (2/3, 0.5, 1/3, 0.5)]
    if n == 6: return [(c/3, r/2, 1/3, 1/2) for r in range(2) for c in range(3)]
    if n in (7, 8, 9):
        cells = [(c/3, r/3, 1/3, 1/3) for r in range(3) for c in range(3)]
        return cells[:n]
    return grid_layout(9)


def draw_text_with_stroke(canvas, draw, x, y, text, font, fill, stroke_color, stroke_width, anchor="mm"):
    """画带描边的文字, anchor='mm' 表示 (x,y) 是文字中心"""
    bbox = draw.textbbox((0, 0), text, font=font, anchor=anchor)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if anchor == "mm":
        # PIL 的 textbbox 已根据 anchor 算好了, 描边也要按同 anchor
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx*dx + dy*dy <= stroke_width*stroke_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke_color, anchor=anchor)
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)
    else:
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx*dx + dy*dy <= stroke_width*stroke_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
        draw.text((x, y), text, font=font, fill=fill)


def auto_fit_font_size(draw, text, font_path, max_width, target_size, min_size=48):
    """如果文字太宽就缩字号"""
    cur = target_size
    while cur > min_size:
        try:
            font = ImageFont.truetype(font_path, cur)
        except Exception:
            return ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        cur -= 6
    return ImageFont.truetype(font_path, min_size)


# ============== 主流程 ==============

def build_cover(games: list[dict],
                title: str,
                subtitle: str = "",
                template_path: str | None = None,
                layout_path: str | None = None,
                font_path: str | None = None,
                out_path: Path | None = None) -> Path:
    """
    生成封面:
    - 有 template_path -> 模板模式: 加载模板图作背景, 按 layout 把游戏图拼上去
    - 无 template_path -> 简单模式: 纯程序化(默认布局)
    """
    if not games:
        raise ValueError("games 列表为空")

    # 解析 layout
    if template_path:
        # 模板模式: layout_path 必须提供 (描述游戏区/标题区在模板图的哪里)
        if not layout_path:
            # 同名文件: 优先找 .txt (用户友好), 兼容 .json
            for ext in (".txt", ".json"):
                guess = Path(template_path).with_suffix(ext)
                if guess.exists():
                    layout_path = guess
                    break
            else:
                raise ValueError(
                    f"模板模式必须提供布局文件 (内容是 JSON 格式)。"
                    f"放在 {Path(template_path).with_suffix('.txt')} 或用 --layout 指定"
                )
        with open(layout_path, "r", encoding="utf-8") as f:
            layout = json.load(f)
    else:
        layout = DEFAULT_LAYOUT

    cover_w, cover_h = layout.get("size", [COVER_W, COVER_H])

    # 1. 底图
    if template_path:
        canvas = load_image(template_path).convert("RGBA")
        if canvas.size != (cover_w, cover_h):
            canvas = canvas.resize((cover_w, cover_h), Image.LANCZOS)
        print(f"[cover] 模板模式: {template_path} ({cover_w}x{cover_h})")
    else:
        canvas = Image.new("RGBA", (cover_w, cover_h), "white")
        # 顶部标题色块
        tb = layout.get("title_box")
        if tb:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([tb["x"], tb["y"],
                           tb["x"] + tb["w"], tb["y"] + tb["h"]],
                           fill=tb.get("bg", "#FF2442"))
        # 底部副标题色块
        sb = layout.get("subtitle_bg")
        if sb:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([sb["x"], sb["y"],
                           sb["x"] + sb["w"], sb["y"] + sb["h"]],
                           fill=sb.get("color", "#222222"))
        print(f"[cover] 简单模式 ({cover_w}x{cover_h})")

    draw = ImageDraw.Draw(canvas)
    fp = find_font(font_path)
    if not fp:
        print("[!] 找不到字体, 中文会显示为方块", file=sys.stderr)

    # 2. 拼游戏封面
    grid = layout["grid"]
    grid_layouts = grid_layout(len(games))
    pad = grid.get("padding", 16)
    radius = grid.get("corner_radius", 18)

    for (rx, ry, rw, rh), game in zip(grid_layouts, games):
        cell_w = int(grid["w"] * rw) - pad
        cell_h = int(grid["h"] * rh) - pad
        cell_x = grid["x"] + int(grid["w"] * rx) + pad // 2
        cell_y = grid["y"] + int(grid["h"] * ry) + pad // 2

        img_src = game.get("header_image") or game.get("cover")
        try:
            tile = load_image(img_src) if img_src else None
        except Exception as e:
            print(f"  [warn] 加载封面失败 {game.get('name')}: {e}", file=sys.stderr)
            tile = None
        if tile is None:
            tile = Image.new("RGBA", (cell_w, cell_h), (60, 60, 60, 255))

        tile = fit_crop(tile, cell_w, cell_h)
        if radius > 0:
            tile = round_corners(tile, radius)
        canvas.alpha_composite(tile, (cell_x, cell_y))

        # 游戏名标签 (可选)
        if layout.get("label_overlay") and fp:
            label_h = 60
            overlay = Image.new("RGBA", (cell_w, label_h), (0, 0, 0, 160))
            if radius > 0:
                # 只圆下边角
                mask = Image.new("L", (cell_w, label_h), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    (0, 0, cell_w, label_h), radius=radius, fill=255)
                # 上半部分变方角
                ImageDraw.Draw(mask).rectangle((0, 0, cell_w, label_h - radius), fill=255)
                overlay.putalpha(mask)
            canvas.alpha_composite(overlay, (cell_x, cell_y + cell_h - label_h))

            try:
                lfont = ImageFont.truetype(fp, 28)
            except Exception:
                lfont = ImageFont.load_default()
            name = game.get("name", "")
            label = name if len(name) <= 16 else name[:15] + "…"
            d = ImageDraw.Draw(canvas)
            bbox = d.textbbox((0, 0), label, font=lfont)
            lw = bbox[2] - bbox[0]
            d.text((cell_x + (cell_w - lw) // 2, cell_y + cell_h - 48),
                   label, font=lfont, fill="white")

    # 3. 标题
    draw = ImageDraw.Draw(canvas)
    if fp:
        tt = layout.get("title_text", {})
        target_size = tt.get("size", 96)
        max_w = tt.get("max_width", cover_w - 80)
        font = auto_fit_font_size(draw, title, fp, max_w, target_size)
        x = tt.get("x", cover_w // 2)
        y = tt.get("y", 160)
        draw_text_with_stroke(
            canvas, draw, x, y, title, font,
            fill=tt.get("color", "#FFFFFF"),
            stroke_color=tt.get("stroke_color", "#000000"),
            stroke_width=tt.get("stroke_width", 3),
            anchor=tt.get("anchor", "mm"),
        )

    # 4. 副标题
    if subtitle and fp:
        st = layout.get("subtitle_text") or {
            "x": cover_w // 2, "y": cover_h - 80, "size": 44,
            "color": "#FFFFFF", "stroke_color": "#000000",
            "stroke_width": 2, "anchor": "mm",
        }
        try:
            sfont = ImageFont.truetype(fp, st.get("size", 44))
        except Exception:
            sfont = ImageFont.load_default()
        draw_text_with_stroke(
            canvas, draw, st.get("x", cover_w // 2), st.get("y", cover_h - 80),
            subtitle, sfont,
            fill=st.get("color", "#FFFFFF"),
            stroke_color=st.get("stroke_color", "#000000"),
            stroke_width=st.get("stroke_width", 2),
            anchor=st.get("anchor", "mm"),
        )

    # 5. 输出
    out_path = out_path or Path("output") / f"cover_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)
    print(f"[done] 封面: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="游戏列表 JSON (含 name, header_image)")
    ap.add_argument("--title", required=True, help="标题")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--max-games", type=int, default=6)
    ap.add_argument("--font", default=None)
    ap.add_argument("--out", default=None)

    # 模板相关
    ap.add_argument("--template", default=None,
                    help="封面模板图路径 (PNG, 1080x1440); 不传走默认布局")
    ap.add_argument("--layout", default=None,
                    help="模板对应的 layout JSON; 不传则自动找同名 .json")

    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        items = json.load(f)
    games = items[: args.max_games]
    out = Path(args.out) if args.out else None
    build_cover(games, args.title, args.subtitle,
                template_path=args.template,
                layout_path=args.layout,
                font_path=args.font,
                out_path=out)


if __name__ == "__main__":
    main()
