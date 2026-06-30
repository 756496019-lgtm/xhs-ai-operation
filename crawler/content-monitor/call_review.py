import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json

payload = {
    "game_name": "零：红蝶 重制版",
    "sources": [
        {
            "source_name": "IGN中国",
            "title": "零：红蝶 重制版 评测 8/10",
            "url": "https://news.qq.com/rain/a/20260311A02WUI00",
            "content": "评分8/10。优点：以本世代游戏标准进行的完全重制，操作模式更为流畅顺滑，同时更能增加心理压力；增加了相当多的新场景；大量新增的文档和对话可以让玩家更近一步了解角色故事。缺点：主机版锁定30帧；新建模表情略显呆滞，缺乏PS2版那般灵动的气韵。总结：不论是零系列的老粉丝，还是喜爱日式恐怖的新玩家，都欢迎来热情好客的皆神村逛逛。"
        },
        {
            "source_name": "Gamer Guides",
            "title": "Fatal Frame II: Crimson Butterfly Remake Review — 86/100",
            "url": "https://www.gamerguides.com/fatal-frame-ii-crimson-butterfly-remake/review",
            "content": "综合评分86/100。画面S级、音效A+、游戏性A、剧情A、值得度A。优点：令人难以置信的恐怖氛围与音景；过场动画画面精致度在同类游戏中无与伦比；支线故事充实了世界观；独特的相机战斗玩法让本作与市面上任何游戏都不同；深度的升级系统体验感实在。缺点：战斗系统不适合所有人；战斗节奏偏慢有时令人沮丧。结论：保持了20年前老游戏的风格，以近乎完美的形式呈现升级后的视觉效果，是入坑日式恐怖的绝佳起点。"
        },
        {
            "source_name": "Steam玩家 & 官方资料",
            "title": "零红蝶重制版 Steam 综合评测与新增内容汇总",
            "url": "https://store.steampowered.com/app/2936840/",
            "content": "Steam首发好评率81%（特别好评）。新增内容：全新原创结局（独立于原版）、两个新探索区域（幽影冢、荣门寺烛光大厅）、支线故事扩展角色背景、意志力系统、护身符系统、射影机升级（实时对焦/光学变焦/灵视滤镜）、越肩第三人称视角替代原固定镜头。与《寂静岭f》联动免费服装DLC。Steam国区标准版298元，豪华版423元（含原声音乐集、美术画集、特别服装）。主机版PS5/XSX锁30帧，PC版无帧率限制。试玩版存档可继承正式版。"
        }
    ],
    "user_opinion": "文章结构要求：第一节是资讯速报，列出今日正式发售、平台、国区定价（标准版298元/豪华版423元）、豪华版包含内容、寂静岭联动DLC免费等关键信息，让读者第一时间掌握购买决策所需数据；之后再进入游戏介绍、玩法分析和推荐结论。语气专业克制，像游戏媒体编辑写的评测，不要过于口语化，不要用感叹号，不要用'真的''确实'等口语词，引用媒体评分时要有据可查，结论清晰但有分析支撑。"
}

resp = requests.post("http://localhost:5050/api/generate_review", json=payload, timeout=120)
print("Status:", resp.status_code)
data = resp.json()
print("Token:", data.get("token"))
print("\n--- 生成文章 ---\n")
print(data.get("article", data.get("message", "")))
