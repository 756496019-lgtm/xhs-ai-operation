"""用 PIL 直接画各 icon PNG，供 PPT 插入用"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = r"C:\Users\demiliang\Desktop\ppt_icons"
os.makedirs(OUT, exist_ok=True)

SZ = 160  # 每个 icon 160×160 px

def new_img():
    img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)

def rounded_rect(draw, xy, r, fill, outline=None, width=3):
    x0,y0,x1,y1 = xy
    draw.rounded_rectangle([x0,y0,x1,y1], radius=r, fill=fill, outline=outline, width=width)

# ── 1. 新闻 icon ─────────────────────────────────────────────
img, d = new_img()
# 窗口
rounded_rect(d, [10,10,150,150], 14, (44,58,74))
# 三点
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)
# 内容区
rounded_rect(d, [18,42,142,142], 6, (255,255,255))
# 红色报头
rounded_rect(d, [18,42,142,62], 4, (220,80,80))
d.text((80,48), "NEWS", fill=(255,255,255), anchor="mm")
# 标题粗线
rounded_rect(d, [26,68,124,78], 3, (44,58,74))
# 图片占位
rounded_rect(d, [26,84,68,118], 3, (91,191,181,180))
# 文字线
for oy in [84,92,100,108]:
    rounded_rect(d, [74,oy,130,oy+5], 2, (200,195,185))
img.save(f"{OUT}/icon_news.png")

# ── 2. 纪录片 icon ───────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (44,58,74))
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)
# 暗色内容区
rounded_rect(d, [18,42,142,142], 6, (28,38,52))
# 胶片条纹上
rounded_rect(d, [18,42,142,58], 0, (20,28,42))
for i in range(7):
    rounded_rect(d, [24+i*18,45,34+i*18,55], 2, (44,58,74))
# 胶片条纹下
rounded_rect(d, [18,126,142,142], 0, (20,28,42))
for i in range(7):
    rounded_rect(d, [24+i*18,129,34+i*18,139], 2, (44,58,74))
# 播放按钮
d.ellipse([48,64,112,120], fill=(91,191,181,220))
d.polygon([(68,78),(68,106),(102,92)], fill=(255,255,255))
img.save(f"{OUT}/icon_doc.png")

# ── 3. 榜单 icon ─────────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (44,58,74))
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)
rounded_rect(d, [18,42,142,142], 6, (240,237,232))
# 领奖台
rounded_rect(d, [26,100,62,138], 3, (155,155,155))   # 2
rounded_rect(d, [64,84,104,138], 3, (246,201,78))    # 1
rounded_rect(d, [106,112,138,138], 3, (200,149,108)) # 3
# 数字
d.text((44,119), "2", fill=(255,255,255), anchor="mm")
d.text((84,111), "1", fill=(255,255,255), anchor="mm")
d.text((122,125), "3", fill=(255,255,255), anchor="mm")
# 奖杯
rounded_rect(d, [68,50,100,72], 4, (246,201,78))
d.ellipse([62,54,74,68], fill=(0,0,0,0), outline=(246,201,78), width=4)
d.ellipse([90,54,102,68], fill=(0,0,0,0), outline=(246,201,78), width=4)
rounded_rect(d, [78,72,86,80], 2, (246,201,78))
rounded_rect(d, [72,78,92,82], 3, (246,201,78))
d.text((84,61), "★", fill=(255,255,255), anchor="mm")
img.save(f"{OUT}/icon_rank.png")

# ── 4. 行业报告 icon ─────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (44,58,74))
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)
# 文档
d.polygon([18,42, 118,42, 142,66, 142,142, 18,142], fill=(255,255,255))
d.polygon([118,42, 142,66, 118,66], fill=(210,205,200))
# 标题线
rounded_rect(d, [28,50,100,60], 3, (44,58,74))
rounded_rect(d, [28,64,80,70], 2, (197,192,184))
# 图表区
rounded_rect(d, [26,74,136,130], 4, (240,247,246))
# 坐标轴
d.line([36,126,36,78], fill=(197,210,208), width=2)
d.line([36,126,128,126], fill=(197,210,208), width=2)
# 柱
for i,(h,c) in enumerate([(24,(91,191,181,180)),(36,(91,191,181,210)),(46,(91,191,181)),(30,(91,191,181,180)),(40,(246,201,78))]):
    x = 46+i*18
    rounded_rect(d, [x,126-h,x+12,126], 2, c)
# 折线
pts = [(52,102),(70,93),(88,84),(106,94),(124,88)]
d.line(pts, fill=(220,80,80), width=3)
for p in pts:
    d.ellipse([p[0]-3,p[1]-3,p[0]+3,p[1]+3], fill=(220,80,80))
img.save(f"{OUT}/icon_report.png")

# ── 5. 社区 icon ─────────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (44,58,74))
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)
rounded_rect(d, [18,42,142,142], 6, (234,244,242))
# 气泡A（左）
d.ellipse([24,52,44,72], fill=(91,191,181))
d.text((34,62), "A", fill=(255,255,255), anchor="mm")
rounded_rect(d, [48,52,118,76], 10, (255,255,255))
d.polygon([(48,64),(40,68),(48,72)], fill=(255,255,255))
rounded_rect(d, [56,59,100,64], 3, (197,210,208))
rounded_rect(d, [56,67,88,72], 3, (197,210,208))
# 气泡B（右）
d.ellipse([114,82,134,102], fill=(246,201,78))
d.text((124,92), "B", fill=(255,255,255), anchor="mm")
rounded_rect(d, [30,80,110,104], 10, (91,191,181))
d.polygon([(110,92),(118,96),(110,100)], fill=(91,191,181))
rounded_rect(d, [38,87,82,92], 3, (255,255,255,160))
rounded_rect(d, [38,95,68,100], 3, (255,255,255,120))
# 气泡C（小）
d.ellipse([24,110,40,126], fill=(141,168,200,200))
d.text((32,118), "C", fill=(255,255,255), anchor="mm")
rounded_rect(d, [44,108,110,128], 8, (255,255,255,230))
d.polygon([(44,118),(38,121),(44,124)], fill=(255,255,255,230))
rounded_rect(d, [52,114,84,119], 3, (197,210,208))
rounded_rect(d, [52,121,72,126], 3, (197,210,208))
img.save(f"{OUT}/icon_community.png")

# ── 6. 爬虫 icon（数据获取）────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (30,58,95))
# 蜘蛛网
cx,cy = 80,90
for angle in range(0,360,45):
    import math
    ex = cx+int(60*math.cos(math.radians(angle)))
    ey = cy+int(60*math.sin(math.radians(angle)))
    d.line([cx,cy,ex,ey], fill=(91,191,181,120), width=1)
for r in [20,38,56]:
    d.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(91,191,181,100), width=1)
# 中心爬虫（简化）
d.ellipse([62,72,98,108], fill=(91,191,181))
# 腿
for angle in [30,60,120,150,210,240,300,330]:
    ex = cx+int(42*math.cos(math.radians(angle)))
    ey = cy+int(42*math.sin(math.radians(angle)))
    d.line([cx,cy,ex,ey], fill=(91,191,181), width=3)
d.ellipse([70,80,90,100], fill=(28,38,52))
d.ellipse([74,84,78,88], fill=(255,255,255))
d.ellipse([82,84,86,88], fill=(255,255,255))
img.save(f"{OUT}/icon_crawler.png")

# ── 7. 分析 icon ─────────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (26,58,42))
# 放大镜
d.ellipse([30,38,100,108], outline=(129,199,132), width=8, fill=(26,58,42))
d.line([92,100,128,136], fill=(129,199,132), width=10)
# 里面的折线
d.line([(46,86),(60,68),(74,78),(88,60)], fill=(129,199,132,180), width=3)
for p in [(46,86),(60,68),(74,78),(88,60)]:
    d.ellipse([p[0]-4,p[1]-4,p[0]+4,p[1]+4], fill=(129,199,132))
img.save(f"{OUT}/icon_analysis.png")

# ── 8. 产出 icon ─────────────────────────────────────────────
img, d = new_img()
rounded_rect(d, [10,10,150,150], 14, (58,42,26))
# 播放三角（视频）
d.polygon([(36,48),(36,112),(104,80)], fill=(246,201,78))
# 右侧图文
rounded_rect(d, [112,48,144,68], 4, (246,201,78,180))
rounded_rect(d, [112,74,144,80], 3, (246,201,78,120))
rounded_rect(d, [112,84,144,90], 3, (246,201,78,100))
rounded_rect(d, [112,94,144,100], 3, (246,201,78,80))
# 星星装饰
d.text((128,122), "★", fill=(246,201,78,180), anchor="mm")
img.save(f"{OUT}/icon_output.png")

# ── 9. Skill 中央 icon ───────────────────────────────────────
img, d = new_img()
# 外圈
d.ellipse([8,8,152,152], outline=(91,191,181,80), width=2)
d.ellipse([16,16,144,144], outline=(91,191,181,40), width=1)
# 文件夹形状
d.polygon([(24,55),(24,130),(136,130),(136,55),(80,55),(68,42),(24,42)], fill=(30,46,62))
d.polygon([(24,55),(136,55),(136,130),(24,130)], fill=(36,54,74))
# 文件
rounded_rect(d, [52,60,108,120], 4, (28,42,58))
rounded_rect(d, [60,70,100,76], 3, (91,191,181,200))
rounded_rect(d, [60,80,88,85], 2, (91,191,181,140))
rounded_rect(d, [60,89,95,94], 2, (91,191,181,120))
rounded_rect(d, [60,98,82,103], 2, (91,191,181,100))
d.text((80,135), "Skill", fill=(91,191,181), anchor="mm")
img.save(f"{OUT}/icon_skill.png")

print("OK - icons saved to", OUT)
