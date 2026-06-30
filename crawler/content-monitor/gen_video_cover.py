"""
生成新游推荐视频封面图
尺寸：1080×1920（竖屏，适配抖音/小红书/视频号）
从 PV 抽帧做背景，叠加标题、标签、品牌水印
用法：python gen_video_cover.py <pv_path> <output_path> [--title 标题] [--subtitle 副标题] [--tags 标签1 标签2]
"""

import sys, os, math, argparse
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── 参数解析 ──
parser = argparse.ArgumentParser()
parser.add_argument("pv_path",    help="PV 视频路径")
parser.add_argument("output_path", help="封面图输出路径（.png/.jpg）")
parser.add_argument("--title",    default="拾光旅人", help="主标题")
parser.add_argument("--subtitle", default="Outbound", help="英文副标题")
parser.add_argument("--tags",     nargs="*", default=["开放世界", "建造", "治愈", "联机"], help="标签列表")
parser.add_argument("--frame-sec", type=float, default=None, help="指定抽帧时间点（秒），默认自动选最佳帧")
parser.add_argument("--brand",    default="游戏雷达局", help="品牌名")
args = parser.parse_args()

W, H = 1080, 1920

# ── 字体 ──
FONT_PATHS = [
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]
def load_font(size):
    for fp in FONT_PATHS:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ── Step 1: 从 PV 抽取背景帧 ──
def extract_best_frame(pv_path, frame_sec=None):
    cap = cv2.VideoCapture(pv_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    duration = total_frames / fps

    if frame_sec is not None:
        cap.set(cv2.CAP_PROP_POS_MSEC, frame_sec * 1000)
        ret, frame = cap.read()
        cap.release()
        if ret:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 自动选最佳帧：在 20%-60% 时段每隔 3s 采样，选色彩最丰富的帧
    candidates = []
    sample_times = [duration * t for t in [0.2, 0.28, 0.36, 0.44, 0.52, 0.60]]
    for t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # 色彩丰富度：HSV 饱和度均值
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1].mean()
        brightness = hsv[:, :, 2].mean()
        # 选饱和度高且亮度适中的帧
        score = sat * (1 - abs(brightness - 140) / 140)
        candidates.append((score, rgb))

    cap.release()
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

print("抽取 PV 背景帧...")
frame_rgb = extract_best_frame(args.pv_path, args.frame_sec)
if frame_rgb is None:
    print("PV 读取失败，使用纯色背景")
    bg_img = Image.new("RGB", (W, H), (12, 20, 35))
else:
    # 将帧缩放并居中裁剪到 1080×1920
    fh, fw = frame_rgb.shape[:2]
    scale = max(W / fw, H / fh)
    nw, nh = int(fw * scale), int(fh * scale)
    resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    x0 = (nw - W) // 2
    y0 = (nh - H) // 2
    cropped = resized[y0:y0+H, x0:x0+W]
    bg_img = Image.fromarray(cropped)

bg_img = bg_img.convert("RGBA")

# ── Step 2: 叠加渐变蒙版（上浅下深，突出底部文字区） ──
mask_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
mask_draw = ImageDraw.Draw(mask_layer)

# 顶部轻蒙版（品牌区）
for y in range(0, 220):
    alpha = int(160 * (1 - y / 220))
    mask_draw.line([(0, y), (W, y)], fill=(10, 15, 25, alpha))

# 底部重蒙版（文字区，从 y=900 到底部）
for y in range(900, H):
    t = (y - 900) / (H - 900)
    alpha = int(210 * (t ** 0.6))
    mask_draw.line([(0, y), (W, y)], fill=(8, 12, 22, alpha))

# 中部装饰色块（橙色斜切光晕）
glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
glow_draw = ImageDraw.Draw(glow_layer)
for r in range(320, 0, -1):
    alpha = int(55 * (r / 320) ** 2)
    glow_draw.ellipse([W//2 - r, H//2 - r*2//3, W//2 + r, H//2 + r*2//3],
                      fill=(230, 140, 20, alpha))
glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=60))

bg_img = Image.alpha_composite(bg_img, glow_layer)
bg_img = Image.alpha_composite(bg_img, mask_layer)
bg_img = bg_img.convert("RGB")
draw = ImageDraw.Draw(bg_img)

# ── Step 3: 品牌区（顶部）──
font_brand = load_font(32)
brand_text = f"🎮 {args.brand}"
# 橙色品牌标识左上角
draw.text((48, 62), args.brand, fill=(245, 180, 30), font=font_brand)
# 右侧"新游推荐"胶囊标签
badge_font = load_font(26)
badge_text = "新游推荐"
bw = draw.textlength(badge_text, font=badge_font) + 32
bx = W - bw - 48
by = 54
badge_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
badge_draw = ImageDraw.Draw(badge_img)
badge_draw.rounded_rectangle([bx, by, bx + bw, by + 44], radius=22, fill=(230, 80, 30, 230))
badge_draw.text((bx + 16, by + 8), badge_text, fill=(255, 255, 255), font=badge_font)
bg_img = bg_img.convert("RGBA")
bg_img = Image.alpha_composite(bg_img, badge_img)
bg_img = bg_img.convert("RGB")
draw = ImageDraw.Draw(bg_img)

# ── Step 4: 主标题区（底部） ──
# 英文副标题
font_en = load_font(52)
en_text = args.subtitle.upper()
en_w = draw.textlength(en_text, font=font_en)
en_y = H - 420
draw.text((W//2 - en_w//2 + 2, en_y + 2), en_text, fill=(0, 0, 0, 120), font=font_en)
draw.text((W//2 - en_w//2, en_y), en_text, fill=(200, 215, 235), font=font_en)

# 橙色分隔线
line_y = en_y + 68
draw.rectangle([W//2 - 40, line_y, W//2 + 40, line_y + 3], fill=(245, 180, 30))

# 中文主标题（大字）
font_title = load_font(128)
title_text = args.title
title_w = draw.textlength(title_text, font=font_title)
title_y = line_y + 24

# 文字描边（黑色轮廓）
for dx, dy in [(-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)]:
    draw.text((W//2 - title_w//2 + dx, title_y + dy), title_text,
              fill=(0, 0, 0), font=font_title)
draw.text((W//2 - title_w//2, title_y), title_text, fill=(232, 240, 252), font=font_title)

# ── Step 5: 标签行 ──
font_tag = load_font(30)
tag_y = title_y + 148
tag_x = 0
tag_imgs = []
total_tag_w = 0
for tag in args.tags:
    tw = draw.textlength(f"# {tag}", font=font_tag) + 28
    total_tag_w += tw + 16
total_tag_w -= 16
cur_x = W//2 - total_tag_w//2

tag_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
tag_d = ImageDraw.Draw(tag_layer)
for tag in args.tags:
    tw = tag_d.textlength(f"# {tag}", font=font_tag) + 28
    tag_d.rounded_rectangle(
        [cur_x, tag_y, cur_x + tw, tag_y + 48],
        radius=24,
        fill=(255, 255, 255, 35),
        outline=(255, 255, 255, 80),
        width=1,
    )
    tag_d.text((cur_x + 14, tag_y + 8), f"# {tag}", fill=(220, 235, 255, 230), font=font_tag)
    cur_x += tw + 16

bg_img = bg_img.convert("RGBA")
bg_img = Image.alpha_composite(bg_img, tag_layer)
bg_img = bg_img.convert("RGB")
draw = ImageDraw.Draw(bg_img)

# ── Step 6: 底部发售信息 ──
font_info = load_font(34)
info_text = "2026.04.23 正式发售  |  支持中文  |  1-4人联机"
info_w = draw.textlength(info_text, font=font_info)
draw.text((W//2 - info_w//2, H - 130), info_text,
          fill=(170, 190, 215), font=font_info)

# ── 保存 ──
bg_img.save(args.output_path, quality=95)
print(f"封面已生成: {args.output_path} ({W}×{H})")
