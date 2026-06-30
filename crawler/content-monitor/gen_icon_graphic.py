from PIL import Image, ImageDraw
import os

OUT = r"C:\Users\demiliang\Desktop\ppt_icons"
os.makedirs(OUT, exist_ok=True)
SZ = 160

img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

def rounded_rect(draw, xy, r, fill=None, outline=None, width=3):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

# 窗口外框
rounded_rect(d, [10,10,150,150], 14, fill=(58,42,26))
# 三点
for i,c in enumerate([(224,87,115),(255,183,77),(129,199,132)]):
    d.ellipse([22+i*16,22,34+i*16,34], fill=c)

# 内容区（白底卡片）
rounded_rect(d, [18,42,142,142], 6, fill=(255,255,255))

# 左侧大图占位（带山+太阳，模拟封面图）
rounded_rect(d, [24,50,80,108], 5, fill=(91,191,181))
# 太阳
d.ellipse([32,56,48,70], fill=(246,201,78))
# 山形
d.polygon([(24,108),(44,80),(58,95),(68,82),(80,108)], fill=(44,120,110))

# 右侧文字区
# 标题粗线
rounded_rect(d, [86,54,136,62], 3, fill=(44,58,74))
# 副标题线
rounded_rect(d, [86,66,126,72], 2, fill=(180,175,168))
# 正文小线 x4
for oy in [80,88,96,104]:
    rounded_rect(d, [86,oy,136,oy+5], 2, fill=(210,205,198))

# 底部标签区（模拟图文排版标签）
rounded_rect(d, [24,114,62,126], 6, fill=(246,201,78,220))
rounded_rect(d, [66,114,104,126], 6, fill=(91,191,181,220))
rounded_rect(d, [108,114,136,126], 6, fill=(167,139,250,220))

# 小标签文字用色块代替
rounded_rect(d, [28,118,58,122], 2, fill=(255,255,255,180))
rounded_rect(d, [70,118,100,122], 2, fill=(255,255,255,180))
rounded_rect(d, [112,118,132,122], 2, fill=(255,255,255,180))

# 底部笔/编辑 icon（右下角）
# 笔杆
d.polygon([(110,132),(120,122),(128,130),(118,140)], fill=(246,201,78))
# 笔尖
d.polygon([(118,140),(128,130),(132,138),(122,144)], fill=(200,160,60))
# 光点
d.ellipse([113,124,119,130], fill=(255,230,150))

img.save(os.path.join(OUT, "icon_graphic.png"))
print("icon_graphic.png saved")
