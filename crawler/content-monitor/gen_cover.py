"""生成游戏行业周报封面图（微信公众号首图尺寸 900×383）"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os

W, H = 900, 383
AVATAR_PATH = "static/avatar.jpg"
OUT_PATH = "static/cover_weekly.png"

# ── 底色：深海军蓝渐变 ──
bg = Image.new("RGB", (W, H), (10, 18, 30))
draw = ImageDraw.Draw(bg)

# 渐变从左深蓝到右稍亮
for x in range(W):
    t = x / W
    r = int(10 + t * 15)
    g = int(18 + t * 20)
    b = int(30 + t * 35)
    draw.line([(x, 0), (x, H)], fill=(r, g, b))

# ── 橙色光晕（仿头像背景）──
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
cx, cy, radius = W // 2, H // 2 + 20, 260
for r in range(radius, 0, -1):
    alpha = int(80 * (r / radius) ** 2)
    color = (220, 100, 20, alpha)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
glow = glow.filter(ImageFilter.GaussianBlur(radius=40))
bg = bg.convert("RGBA")
bg = Image.alpha_composite(bg, glow)
bg = bg.convert("RGB")
draw = ImageDraw.Draw(bg)

# ── 像素风装饰格子（仿头像四角）──
px_size = 12
px_color_dark  = (15, 28, 48)
px_color_med   = (20, 40, 65)
for row in range(0, H, px_size):
    for col in range(0, W, px_size):
        dist_x = min(col, W - col) / (W / 2)
        dist_y = min(row, H - row) / (H / 2)
        edge = 1 - min(dist_x, dist_y)
        if edge > 0.7 and (row // px_size + col // px_size) % 2 == 0:
            alpha = int((edge - 0.7) / 0.3 * 180)
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.rectangle([col, row, col + px_size - 1, row + px_size - 1],
                          fill=(*px_color_dark, alpha))
            bg = bg.convert("RGBA")
            bg = Image.alpha_composite(bg, overlay)
            bg = bg.convert("RGB")
            draw = ImageDraw.Draw(bg)

# ── 头像（左侧，圆形裁剪）──
avatar_orig = Image.open(AVATAR_PATH).convert("RGBA")
AV = 260
avatar = avatar_orig.resize((AV, AV), Image.LANCZOS)

# 圆形遮罩
mask = Image.new("L", (AV, AV), 0)
md = ImageDraw.Draw(mask)
md.ellipse([0, 0, AV - 1, AV - 1], fill=255)

# 橙色边框环
border_size = AV + 8
border_img = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
bd = ImageDraw.Draw(border_img)
bd.ellipse([0, 0, border_size - 1, border_size - 1], fill=(230, 130, 20, 255))
bd.ellipse([4, 4, border_size - 5, border_size - 5], fill=(0, 0, 0, 0))

av_x, av_y = 60, (H - AV) // 2
bg_rgba = bg.convert("RGBA")
bg_rgba.paste(border_img, (av_x - 4, av_y - 4), border_img)
av_img = Image.new("RGBA", (AV, AV), (0, 0, 0, 0))
av_img.paste(avatar, (0, 0), mask)
bg_rgba.paste(av_img, (av_x, av_y), av_img)
bg = bg_rgba.convert("RGB")
draw = ImageDraw.Draw(bg)

# ── 竖线分割 ──
sep_x = av_x + AV + 40
draw.line([(sep_x, H // 2 - 80), (sep_x, H // 2 + 80)], fill=(245, 184, 32), width=2)

# ── 文字 ──
# 尝试系统中文字体
font_paths = [
    "C:/Windows/Fonts/msyh.ttc",         # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",        # 黑体
    "C:/Windows/Fonts/NotoSansCJK-Bold.ttc",
]
font_title, font_sub, font_label = None, None, None
for fp in font_paths:
    if os.path.exists(fp):
        try:
            font_title = ImageFont.truetype(fp, 72)
            font_sub   = ImageFont.truetype(fp, 28)
            font_label = ImageFont.truetype(fp, 18)
            print(f"使用字体: {fp}")
            break
        except Exception:
            continue
if font_title is None:
    font_title = ImageFont.load_default()
    font_sub = font_label = font_title
    print("使用默认字体")

text_x = sep_x + 40
cx_text = text_x + (W - text_x) // 2

# 副标题：GAME RADAR
label = "GAME RADAR"
lw = draw.textlength(label, font=font_label) if hasattr(draw, 'textlength') else font_label.getlength(label)
draw.text((cx_text - lw / 2, H // 2 - 110),
          label, fill=(245, 184, 32), font=font_label)

# 主标题：游戏行业周报（分两行）
line1, line2 = "游戏行业", "周报"
for i, (line, y_off) in enumerate([(line1, -28), (line2, 48)]):
    lw = draw.textlength(line, font=font_title) if hasattr(draw, 'textlength') else font_title.getlength(line)
    # 文字阴影
    draw.text((cx_text - lw / 2 + 2, H // 2 + y_off + 2), line, fill=(0, 0, 0, 128), font=font_title)
    draw.text((cx_text - lw / 2, H // 2 + y_off), line, fill=(232, 238, 244), font=font_title)

# 橙色强调线（周报下方）
accent_y = H // 2 + 48 + 78
lw2 = draw.textlength(line2, font=font_title) if hasattr(draw, 'textlength') else font_title.getlength(line2)
draw.rectangle([cx_text - lw2 / 2, accent_y, cx_text + lw2 / 2, accent_y + 4],
               fill=(245, 184, 32))

# 底部：游戏雷达局
footer = "游戏雷达局 · 每周游戏行业动态精选"
fw = draw.textlength(footer, font=font_sub) if hasattr(draw, 'textlength') else font_sub.getlength(footer)
draw.text((cx_text - fw / 2, H - 55), footer, fill=(160, 185, 210), font=font_sub)

bg.save(OUT_PATH)
print(f"封面已保存至 {OUT_PATH}（{W}×{H}）")
