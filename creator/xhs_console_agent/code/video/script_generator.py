"""
游戏视频文案生成器 (通用版)
============================
不绑定特定题材, 适用于任意游戏内容: 折扣盘点 / 新游评测 / 怀旧回顾 /
品类盘点 (魂系/JRPG/独立游戏) / 系列回顾 / 主机选购……

输出统一格式 script.json, 视频剪辑模块只认这个格式:
{
  "title": "小红书标题, <=20字",
  "intro": "开头引导语",
  "segments": [
    {
      "game_slug": "<和素材库目录名一致>",
      "game_name": "...",
      "text": "对应这一段视频里要念的旁白",
      "duration_sec": 8
    }
  ],
  "outro": "结尾引导语"
}

四种生成模式 (--mode):
1. prompt        ← 通用首选: 产出提示词文件, 给任意 AI 写文案
2. preset-deals  ← 折扣盘点预设模板 (offline, 不需 AI)
3. preset-new    ← 新品速报预设模板 (offline)
4. preset-coming ← 即将发售预设模板 (offline)

如果你的题材不在三种 preset 里, 用 prompt 模式 + 自定义主题描述。
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ============== 预设模板 (折扣/新品/即将发售) ==============
# 这些模板锁定了语气, 适合特定题材。其他题材请用 prompt 模式。

INTRO_TEMPLATES = {
    "deals": "姐妹们！本周三大主机折扣盘点来了，最低{lowest}折！",
    "new": "本周新游一图流，{count}款值得关注的新作！",
    "coming": "下个月即将发售的好游戏，先码住！",
}

SEGMENT_TEMPLATES = {
    "deals": "第{idx}款 · 《{name}》——{platform}平台，原价{original}，现价{final}，相当于{discount}折！{desc_or_genre}",
    "new": "第{idx}款 · 《{name}》——{platform}独占/新作，{desc_or_genre}",
    "coming": "第{idx}款 · 《{name}》——{platform}，{desc_or_genre}，期待！",
}

OUTRO_DEFAULT = "想知道哪台主机最适合你？评论区留言，或者私信我，免费帮你选！"


def fmt_price(item: dict) -> tuple[str, str]:
    plat = item.get("platform")
    o = (item.get("price_original_cny") or item.get("price_original_hkd")
         or item.get("price_original") or item.get("price_original_display"))
    f = (item.get("price_final_cny") or item.get("price_final_hkd")
         or item.get("price_final") or item.get("price_final_display"))

    def _fmt(x, sym):
        if x is None:
            return "—"
        if isinstance(x, (int, float)):
            return f"{sym}{x:.0f}"
        return str(x)

    if plat == "Steam":
        return _fmt(o, "￥"), _fmt(f, "￥")
    elif plat == "Switch":
        return _fmt(o, "HK$"), _fmt(f, "HK$")
    else:
        return _fmt(o, ""), _fmt(f, "")


def _slugify(name: str) -> str:
    return (re.sub(r"[^\w\u4e00-\u9fa5]+", "_", name).strip("_") or "untitled")[:60]


def build_segment(idx: int, item: dict, preset: str) -> dict:
    name = item.get("name", "未命名")
    plat = item.get("platform", "")
    discount = item.get("discount_percent")
    discount_display = f"{int(round((100 - discount) / 10))}" if discount else "—"
    o, f = fmt_price(item)

    desc = (item.get("short_description") or "")[:60]
    genres = item.get("genres") or []
    genres_str = "/".join(str(g) for g in genres[:2]) if genres else ""
    desc_or_genre = (desc[:30] + "…") if len(desc) > 32 else (desc or genres_str or "口碑佳作")

    text = SEGMENT_TEMPLATES[preset].format(
        idx=idx, name=name, platform=plat,
        original=o, final=f, discount=discount_display,
        desc_or_genre=desc_or_genre,
    )
    duration = max(6, min(12, len(text) / 4 + 1))
    return {
        "game_slug": item.get("slug") or item.get("game_slug") or _slugify(name),
        "game_name": name,
        "text": text,
        "duration_sec": round(duration, 1),
    }


def build_preset(items: list[dict], preset: str) -> dict:
    discounts = [it.get("discount_percent") for it in items if it.get("discount_percent")]
    lowest = max(discounts) if discounts else 0
    lowest_display = f"{int(round((100 - lowest) / 10))}" if lowest else "骨折"

    intro = INTRO_TEMPLATES[preset].format(
        lowest=lowest_display, count=len(items),
    )
    segments = [build_segment(i + 1, it, preset) for i, it in enumerate(items)]
    title_word = {"deals": "折扣盘点", "new": "新游速报", "coming": "即将发售"}[preset]
    return {
        "title": f"三主机{title_word}｜{len(items)}款必看",
        "intro": intro,
        "segments": segments,
        "outro": OUTRO_DEFAULT,
    }


# ============== Prompt 模式 (通用, 适合任意题材) ==============

PROMPT_TEMPLATE = """\
你是一个小红书游戏内容创作者。请根据以下素材, 写一条 60-90 秒的短视频文案。

【本期主题】
{topic}

【风格要求】
- 小红书口语化, 有人味, 但不油腻
- 每个游戏 1-2 句话, 突出本期主题相关的卖点
  (例: 折扣题材就强调价格; 怀旧题材就强调情怀; 新游评测就强调玩点)
- 总字数控制在 250-350 字 (约 60-90 秒念完)
- 不要 emoji 滥用, 全文最多 3 个

【输出格式 (严格按此 JSON 格式, 不要加任何其他文字, 不要用 ```json 包裹)】
{
  "title": "标题, ≤20 字, 适合做封面大字",
  "intro": "开头一两句, 5-8 秒念完",
  "segments": [
    {
      "game_slug": "<必须照抄下方游戏数据中的 slug 字段>",
      "game_name": "...",
      "text": "这一段念的话",
      "duration_sec": 8
    }
  ],
  "outro": "结尾引导关注/咨询/评论的话"
}

【游戏/素材数据】
{games_json}
{references_block}"""


REFERENCES_BLOCK = """

【对标参考素材 (仅参考语气和结构, 严禁照抄文字)】
下面是同类账号的对标视频/帖子文案。**重要**:
- 学习它们的开头钩子、节奏、口语调性、读者痛点切入方式
- **绝对不要**照搬任何整句、关键词组合、独特表达
- 你的输出必须是基于上方素材的**全新原创文案**
- 如果对标里有"反话""反向思维"等创意结构, 可以借鉴框架, 但内容必须重写

{refs_text}
"""


DEFAULT_TOPIC = "三主机折扣盘点 (本周精选)"


def build_prompt(items: list[dict], topic: str = DEFAULT_TOPIC,
                 references_path: str | None = None) -> str:
    light = []
    for it in items:
        light.append({
            "slug": it.get("slug") or _slugify(it.get("name", "")),
            "name": it.get("name"),
            "platform": it.get("platform"),
            "price_original": it.get("price_original_cny")
                              or it.get("price_original_hkd")
                              or it.get("price_original"),
            "price_final": it.get("price_final_cny")
                           or it.get("price_final_hkd")
                           or it.get("price_final"),
            "discount_percent": it.get("discount_percent"),
            "short_description": (it.get("short_description") or "")[:120],
            "genres": it.get("genres", []),
            "release_date": it.get("release_date"),
        })

    refs_block = ""
    if references_path:
        try:
            with open(references_path, "r", encoding="utf-8") as f:
                refs_text = f.read()
            if len(refs_text) > 8000:
                refs_text = refs_text[:8000] + "\n... (已截断)"
            refs_block = REFERENCES_BLOCK.format(refs_text=refs_text)
        except Exception as e:
            print(f"[warn] 读取对标素材失败: {e}, 跳过", file=sys.stderr)

    return (PROMPT_TEMPLATE
            .replace("{topic}", topic)
            .replace("{games_json}", json.dumps(light, ensure_ascii=False, indent=2))
            .replace("{references_block}", refs_block))


# ============== 入口 ==============

def main():
    ap = argparse.ArgumentParser(
        description="游戏视频文案生成 - 支持任意题材",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument("--input", required=True,
                    help="素材 JSON (从素材采集步骤来), 或 pv_library/index.json")
    ap.add_argument("--mode",
                    choices=["prompt", "preset-deals", "preset-new", "preset-coming"],
                    default="prompt",
                    help="prompt = 给 AI 写 (通用); preset-* = 套预设模板")
    ap.add_argument("--topic", default=None,
                    help="本期主题 (仅 prompt 模式), 例: '本周值得入手的5款魂系游戏'。"
                         "不传就用默认 (折扣盘点)")
    ap.add_argument("--references", default=None,
                    help="对标素材文件 (markdown/txt), 仅 prompt 模式有效")
    ap.add_argument("--out", default=None,
                    help="输出路径; 默认 script.txt (preset) 或 prompt.txt (prompt)。"
                         "内容是 JSON 格式但用 .txt 扩展名, 方便记事本直接打开")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        items = json.load(f)

    if args.mode == "prompt":
        topic = args.topic or DEFAULT_TOPIC
        prompt = build_prompt(items, topic=topic, references_path=args.references)
        out = args.out or "prompt.txt"
        with open(out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[done] 提示词已生成: {out}")
        print(f"  本期主题: {topic}")
        if args.references:
            print(f"  含对标素材: {args.references}")
        print(f"  下一步: 让 Code Buddy / 其他 agent 读 {out}, 写出文案保存为 script.txt")
    else:
        if args.references or args.topic:
            print("[warn] preset 模式忽略 --references / --topic", file=sys.stderr)
        preset = args.mode.replace("preset-", "")
        script = build_preset(items, preset=preset)
        out = args.out or "script.txt"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        print(f"[done] 文案已生成: {out}")
        print(f"  预设: {preset}")
        print(f"  标题: {script['title']}")
        print(f"  共 {len(script['segments'])} 段")


if __name__ == "__main__":
    main()
