"""
按游戏名/列表抓取（通用模式）
==============================
不限于折扣/新品板块, 适合任意主题:
- 想做"魂系游戏盘点" → 自己列出 5 个游戏名
- 想做"塞尔达全系列回顾" → 列出系列各作
- 想做"独立游戏推荐" → 列一组独立游戏

输入: 游戏名列表 (CLI 参数 / txt 文件)
输出: 和 scrape_all 一致的 all_*.json, 后续流程通用

工作原理:
- 在 Steam 里搜索每个游戏名, 取最匹配的一条
- 自动拉取价格、封面、预告片
- 后续可与 pv_downloader / script_generator 衔接

用法:
    python scrape_by_names.py --names "塞尔达传说 王国之泪" "艾尔登法环" "黑神话悟空"
    python scrape_by_names.py --names-file games.txt
    python scrape_by_names.py --names "..." --tag souls   # 给文件名打 tag

games.txt 格式 (一行一个):
    塞尔达传说 王国之泪
    艾尔登法环
    黑神话悟空
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import steam_scraper

STEAM_SEARCH_API = "https://store.steampowered.com/api/storesearch"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,en;q=0.8"}


def search_steam(name: str, region: str = "cn", lang: str = "schinese"):
    """在 Steam 搜索框里查一个游戏名, 返回最匹配的那条 (含 appid)."""
    params = {"term": name, "cc": region, "l": lang}
    resp = requests.get(STEAM_SEARCH_API, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return None
    return items[0]


def fetch_one(name: str, with_trailer: bool = True,
              region: str = "cn", lang: str = "schinese") -> dict | None:
    """一个游戏名 -> 完整数据 (沿用 steam_scraper 的 normalize + enrich)."""
    hit = search_steam(name, region=region, lang=lang)
    if not hit:
        print(f"  [!] 没搜到: {name}", file=sys.stderr)
        return None
    appid = hit.get("id")
    # Steam CDN 高清封面: 460x215 横版 header (用作 Steam 库/商店头图)
    # 这是 Steam 所有游戏都有的标准图, 由 appid 直接构造 URL
    hd_header = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
    base = {
        "platform": "Steam",
        "appid": appid,
        "name": hit.get("name", name),
        "price_original_cny": (hit.get("price", {}) or {}).get("initial", 0) / 100
                              if hit.get("price") else None,
        "price_final_cny": (hit.get("price", {}) or {}).get("final", 0) / 100
                           if hit.get("price") else None,
        "discount_percent": (hit.get("price", {}) or {}).get("discount_percent"),
        "currency": "CNY",
        "store_url": f"https://store.steampowered.com/app/{appid}/",
        "header_image": hd_header,
        "trailers": [],
    }
    if with_trailer:
        steam_scraper.enrich_with_trailer(base, region=region, lang=lang)
    return base


def scrape_names(names: list[str], with_trailer: bool = True) -> list[dict]:
    results = []
    for i, name in enumerate(names, 1):
        name = name.strip()
        if not name:
            continue
        print(f"[{i}/{len(names)}] {name}")
        item = fetch_one(name, with_trailer=with_trailer)
        if item:
            results.append(item)
        time.sleep(0.5)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", nargs="*", default=[],
                    help="游戏名列表 (空格分隔, 含空格的名字用引号)")
    ap.add_argument("--names-file", default=None,
                    help="一行一个游戏名的 txt 文件")
    ap.add_argument("--tag", default="custom",
                    help="给输出文件起个 tag, 如 souls / jrpg / nostalgia")
    ap.add_argument("--no-trailer", action="store_true")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    names = list(args.names)
    if args.names_file:
        with open(args.names_file, "r", encoding="utf-8") as f:
            names.extend(line.strip() for line in f if line.strip()
                         and not line.strip().startswith("#"))
    if not names:
        print("错误: 没传任何游戏名 (--names 或 --names-file)", file=sys.stderr)
        sys.exit(1)

    print(f"=== 按游戏名抓取, tag={args.tag}, 共 {len(names)} 个 ===\n")
    results = scrape_names(names, with_trailer=not args.no_trailer)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"all_{args.tag}_{date_tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[done] 保存: {out_path}  ({len(results)}/{len(names)} 命中)")


if __name__ == "__main__":
    main()
