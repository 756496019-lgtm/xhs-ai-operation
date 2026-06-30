"""
Steam 新品 & 特惠页面爬虫
============================
爬取 Steam 商店首页的新品发售、特别优惠等版块。
直接使用 Steam 官方 storefront API，比解析 HTML 更稳。

输出: data/steam_<板块>_<日期>.json
每条记录包含: 游戏名、原价、现价、折扣、商店URL、封面图URL、appid

使用:
    python steam_scraper.py --section new       # 新品
    python steam_scraper.py --section specials  # 特价
    python steam_scraper.py --section topsellers
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Steam Storefront featured API (官方公开接口)
FEATURED_API = "https://store.steampowered.com/api/featuredcategories/"
APPDETAILS_API = "https://store.steampowered.com/api/appdetails"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SECTION_KEYS = {
    "new": "new_releases",
    "specials": "specials",
    "topsellers": "top_sellers",
    "coming_soon": "coming_soon",
}


def fetch_featured(section_key: str, region: str = "cn", lang: str = "schinese"):
    """从 featuredcategories 拉取整个板块。"""
    params = {"cc": region, "l": lang}
    resp = requests.get(FEATURED_API, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if section_key not in data:
        raise KeyError(f"Steam API 返回里没有板块 {section_key}; 可用: {list(data.keys())}")
    items = data[section_key].get("items", [])
    return items


def normalize_item(raw: dict) -> dict:
    """把 Steam 返回的原始字段统一到我们的输出格式。"""
    # 价格在 final_price, original_price, 单位是分
    final = raw.get("final_price")
    original = raw.get("original_price") or final
    discount = raw.get("discount_percent", 0)
    appid = raw.get("id")
    return {
        "platform": "Steam",
        "appid": appid,
        "name": raw.get("name", ""),
        "price_original_cny": (original / 100) if original else None,
        "price_final_cny": (final / 100) if final else None,
        "discount_percent": discount,
        "currency": raw.get("currency", "CNY"),
        "store_url": f"https://store.steampowered.com/app/{appid}/",
        "header_image": raw.get("header_image") or raw.get("large_capsule_image"),
        # 预告片要单独拉 appdetails 才有
        "trailers": [],
    }


def enrich_with_trailer(item: dict, region: str = "cn", lang: str = "schinese") -> dict:
    """对单个游戏调用 appdetails 拿预告片 (mp4 直链)。"""
    appid = item["appid"]
    params = {"appids": appid, "cc": region, "l": lang}
    try:
        resp = requests.get(APPDETAILS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        node = payload.get(str(appid), {})
        if not node.get("success"):
            return item
        details = node.get("data", {})
        movies = details.get("movies", []) or []
        trailers = []
        for m in movies:
            mp4 = (m.get("mp4") or {})
            # 优先 480 (体积小、够用) 否则 max
            url = mp4.get("480") or mp4.get("max")
            if url:
                trailers.append({
                    "title": m.get("name", ""),
                    "url": url,
                    "thumbnail": m.get("thumbnail"),
                })
        item["trailers"] = trailers
        # 顺手补一下简介
        item["short_description"] = details.get("short_description", "")
        item["genres"] = [g.get("description") for g in details.get("genres", [])]
    except Exception as e:
        print(f"    [warn] appid={appid} 拉详情失败: {e}", file=sys.stderr)
    return item


def scrape(section: str, with_trailer: bool = True, limit: int | None = None,
           region: str = "cn", lang: str = "schinese") -> list[dict]:
    if section not in SECTION_KEYS:
        raise ValueError(f"不支持的 section={section}; 可选: {list(SECTION_KEYS.keys())}")
    print(f"[steam] 拉取板块: {section}")
    raw_items = fetch_featured(SECTION_KEYS[section], region=region, lang=lang)
    if limit:
        raw_items = raw_items[:limit]
    print(f"[steam] 共 {len(raw_items)} 条")

    results = []
    for i, raw in enumerate(raw_items, 1):
        item = normalize_item(raw)
        if with_trailer:
            print(f"  [{i}/{len(raw_items)}] {item['name']}  补充预告片...")
            enrich_with_trailer(item, region=region, lang=lang)
            time.sleep(0.5)  # 礼貌限速
        else:
            print(f"  [{i}/{len(raw_items)}] {item['name']}")
        results.append(item)
    return results


def save(results: list[dict], section: str, out_dir: str = "data"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = Path(out_dir) / f"steam_{section}_{date_tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[steam] 已保存: {out_path}  ({len(results)} 条)")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="specials",
                    choices=list(SECTION_KEYS.keys()),
                    help="抓哪个板块")
    ap.add_argument("--limit", type=int, default=15, help="最多抓多少条 (默认15)")
    ap.add_argument("--no-trailer", action="store_true", help="跳过拉取预告片(更快)")
    ap.add_argument("--out", default="data", help="输出目录")
    args = ap.parse_args()

    results = scrape(args.section, with_trailer=not args.no_trailer, limit=args.limit)
    save(results, args.section, out_dir=args.out)


if __name__ == "__main__":
    main()
