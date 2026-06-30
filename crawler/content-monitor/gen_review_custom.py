import sys, os
sys.path.insert(0, r'D:\project\content-monitor')
sys.stdout.reconfigure(encoding='utf-8')
import requests
from qwen_client import get_qwen_client

client = get_qwen_client()

system_text = """你是「游戏雷达局」的游戏编辑，为游戏爱好者撰写专业评测文章。

写作规范：
- 语言专业、克制，不口语化
- 不使用感叹号、"真的""确实""不得不说""总的来说"等口语/套话
- 引用媒体评分时标明来源
- 结论明确，有分析依据

文章结构（严格按以下顺序，不得调换）：

# 标题（游戏名 + 一句有观点的核心评语，20字内）

## 📋 发售资讯
以条目形式列出：发售日期、平台、国区标准版定价、豪华版定价及包含内容、免费DLC说明。

## 🎮 游戏简介
游戏类型、核心玩法定位、故事背景简述，约60字，让从未接触本作的玩家快速建立认知。

## ⚔️ 核心玩法
射影机战斗系统的运作方式、重制版新增的操作系统、体验节奏特点、与同类恐怖游戏的差异。

## 🌟 值得肯定的地方
3-4条，每条需说清楚为什么好，不只列举形容词，结合媒体评测数据。

## 💢 需要提前知道的问题
2-3条，区分硬伤（主机锁帧）和设计遗憾，诚实评价。

## 🎯 编辑结论
分两段：
1. 明确给出「推荐购买」「建议等打折」或「不推荐」，说明分析依据
2. 分别对新玩家、老玩家、PC玩家、主机玩家给出具体建议

*—— 游戏雷达局*

全文约700-900字。"""

user_text = """游戏名：零：红蝶 重制版（FATAL FRAME II: Crimson Butterfly REMAKE）

发售信息：
- 发售日期：2026年3月12日
- 平台：PS5、Xbox Series X|S、Nintendo Switch 2、Steam（PC）
- Steam国区标准版：298元
- Steam国区豪华版：423元，包含：和风哥特连衣裙、蕾丝手套、护身符·特、数字美术画集、原声音乐集
- 免费DLC：与《寂静岭f》联动服装，发售日起可免费获取
- 试玩版存档可继承至正式版

媒体评分与评测内容：

【IGN中国 8/10】
以本世代游戏标准进行的完全重制，操作模式更为流畅顺滑，同时更能增加心理压力。增加了相当多的新场景，大量新增的文档和对话可以让玩家更近一步了解角色故事。
缺点：主机版锁定30帧；新建模表情略显呆滞，缺乏PS2版那般灵动的气韵。
评测结语：不论是零系列的老粉丝，还是喜爱日式恐怖的新玩家，都欢迎来热情好客的皆神村逛逛。

【Gamer Guides 86/100】
各项评分：画面S级、音效A+级、游戏性A级、剧情A级、值得度A级。
优点：令人难以置信的恐怖氛围与音景；过场动画精致度在同类游戏中无与伦比；支线故事充实了世界观；相机战斗机制独特，与市面上任何游戏都不同；升级系统体验感实在。
缺点：战斗系统不适合所有人；战斗节奏偏慢有时令人沮丧。
结论：保持了20年前老游戏的风格，以近乎完美的形式呈现升级后的视觉效果，是入坑日式恐怖的绝佳起点。

【Steam玩家口碑】
首发好评率81%，评级为「特别好评」。

重制版新增内容（相比原版）：
- 全新原创结局（独立于原版剧情）
- 两个新探索区域：幽影冢、荣门寺烛台大厅
- 支线故事扩展双胞胎角色背景
- 意志力系统（消耗意志力释放高伤害技能）、护身符系统
- 射影机升级：实时对焦、光学变焦、灵视滤镜（可显现残留思念）
- 操作视角从固定镜头改为越肩第三人称
- 主机版PS5/Xbox Series X|S锁30帧；PC版无帧率限制"""

completion = client.chat.completions.create(
    model="qwen-max",
    messages=[
        {"role": "system", "content": system_text},
        {"role": "user",   "content": user_text},
    ],
    extra_body={"enable_thinking": False},
)

article = completion.choices[0].message.content
print(article)
print("\n" + "="*60)

# 存入 Flask 进程的 TTL store
resp = requests.post("http://localhost:5050/api/store_article", json={
    "title": "零：红蝶 重制版首发评测",
    "content": article,
    "tag": "游戏雷达局",
}, timeout=10)

data = resp.json()
if data.get("status") == "ok":
    token = data["token"]
    print(f"\n编辑页面已就绪：http://localhost:5050/xhs_full?token={token}")
else:
    print("存储失败：", data)
