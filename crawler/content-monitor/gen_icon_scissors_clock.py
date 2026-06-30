"""生成剪刀和钟表 icon，参照截图的简洁扁平风格（单色描边+填充，青色调）"""
from PIL import Image, ImageDraw
import math, os

OUT = r"C:\Users\demiliang\Desktop\ppt_icons"
os.makedirs(OUT, exist_ok=True)

SZ = 160
TEAL = (46, 132, 160)        # 主色 teal
TEAL_L = (70, 165, 190)      # 浅一点
BG = (0, 0, 0, 0)            # 透明背景

# ──────────────────────────────────────────────
# 1. 剪刀 icon
# ──────────────────────────────────────────────
img = Image.new("RGBA", (SZ, SZ), BG)
d = ImageDraw.Draw(img)

# 两个圆形手柄环（左上 / 左下）
ring_w = 5
d.ellipse([16, 30, 60, 74], outline=TEAL, width=ring_w)   # 上柄
d.ellipse([16, 86, 60, 130], outline=TEAL, width=ring_w)  # 下柄

# 手柄内圆（实心小圆，视觉上区分内外）
d.ellipse([28, 42, 48, 62], fill=TEAL)
d.ellipse([28, 98, 48, 118], fill=TEAL)

# 两条刀刃线，从手柄出发向右汇聚成交叉
# 刀刃1：从上柄(60,52) → 交叉点(100,80) → 延伸到(144,62)
# 刀刃2：从下柄(60,108) → 交叉点(100,80) → 延伸到(144,98)
cross_x, cross_y = 100, 80

# 用多边形画有宽度的刀刃（细长梯形）
def blade(draw, x0, y0, x1, y1, w_start=7, w_end=2, color=TEAL):
    """从 (x0,y0) 到 (x1,y1) 画一条渐细的刀刃"""
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    nx, ny = -dy/length, dx/length  # 法向量
    pts = [
        (x0 + nx*w_start/2, y0 + ny*w_start/2),
        (x0 - nx*w_start/2, y0 - ny*w_start/2),
        (x1 - nx*w_end/2,   y1 - ny*w_end/2),
        (x1 + nx*w_end/2,   y1 + ny*w_end/2),
    ]
    draw.polygon([(int(p[0]), int(p[1])) for p in pts], fill=color)

# 上刀刃（手柄出口 → 交叉前）
blade(d, 60, 52, cross_x-2, cross_y-2, w_start=8, w_end=4)
# 上刀刃延伸（交叉后 → 右端）
blade(d, cross_x+2, cross_y+2, 144, 100, w_start=4, w_end=1, color=TEAL_L)

# 下刀刃（手柄出口 → 交叉前）
blade(d, 60, 108, cross_x-2, cross_y+2, w_start=8, w_end=4)
# 下刀刃延伸（交叉后 → 右端）
blade(d, cross_x+2, cross_y-2, 144, 60, w_start=4, w_end=1, color=TEAL_L)

# 交叉点小圆（铆钉）
d.ellipse([cross_x-6, cross_y-6, cross_x+6, cross_y+6], fill=TEAL)

img.save(os.path.join(OUT, "icon_scissors.png"))
print("icon_scissors.png saved")


# ──────────────────────────────────────────────
# 2. 钟表 icon
# ──────────────────────────────────────────────
img = Image.new("RGBA", (SZ, SZ), BG)
d = ImageDraw.Draw(img)

cx, cy = 80, 82   # 表盘中心
R = 60            # 外圆半径
ring_w = 6

# 外圆（表盘）
d.ellipse([cx-R, cy-R, cx+R, cy+R], outline=TEAL, width=ring_w)

# 12 个小时刻度
for i in range(12):
    angle = math.radians(i * 30 - 90)
    if i % 3 == 0:
        r_out, r_in, w = R-5, R-16, 4   # 3/6/9/12 点大刻度
    else:
        r_out, r_in, w = R-7, R-14, 2   # 普通小刻度
    x1 = cx + r_in  * math.cos(angle)
    y1 = cy + r_in  * math.sin(angle)
    x2 = cx + r_out * math.cos(angle)
    y2 = cy + r_out * math.sin(angle)
    d.line([int(x1), int(y1), int(x2), int(y2)], fill=TEAL, width=w)

# 时针（指向 10 点）
hour_angle = math.radians(-60)   # 10:00 方向
hx = cx + int(32 * math.cos(hour_angle))
hy = cy + int(32 * math.sin(hour_angle))
d.line([cx, cy, hx, hy], fill=TEAL, width=6)

# 分针（指向 12 点，稍长）
min_angle = math.radians(-90)    # 12:00
mx = cx + int(44 * math.cos(min_angle))
my = cy + int(44 * math.sin(min_angle))
d.line([cx, cy, mx, my], fill=TEAL, width=4)

# 秒针（红色细针，指向 4 点，增加动感）
sec_angle = math.radians(30)     # 4:00
sx = cx + int(48 * math.cos(sec_angle))
sy = cy + int(48 * math.sin(sec_angle))
d.line([cx, cy, sx, sy], fill=(220, 80, 80), width=2)
# 秒针反向短尾
sx2 = cx + int(12 * math.cos(sec_angle + math.pi))
sy2 = cy + int(12 * math.sin(sec_angle + math.pi))
d.line([cx, cy, sx2, sy2], fill=(220, 80, 80), width=2)

# 中心圆点
d.ellipse([cx-5, cy-5, cx+5, cy+5], fill=TEAL)
d.ellipse([cx-3, cy-3, cx+3, cy+3], fill=(255,255,255,240))

# 表冠（上方小矩形）
d.rectangle([cx-7, cy-R-10, cx+7, cy-R+2], fill=TEAL)
d.rectangle([cx-10, cy-R-14, cx+10, cy-R-8], fill=TEAL)

img.save(os.path.join(OUT, "icon_clock.png"))
print("icon_clock.png saved")
