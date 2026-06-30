"""
Nintendo eShop 新品 & 折扣爬虫
================================
任天堂港服 eShop 网页 (store.nintendo.com.hk) 数据来自 Algolia 搜索接口,
返回 JSON, 含价格、折扣、封面、Nintendo Direct 预告片链接 (在商品详情页)。

输出: data/switch_<板块>_<日期>.json

如果接口结构变化, 退回到 web_fetch + Claude 帮忙解析 HTML 的方式。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# 港服 eShop 用 Algolia 搜索, 公开 API key (前端可见)
# 注意: 这个 key 和 app_id 来自港服 store HTML, 任天堂偶尔会换
ALGOLIA_APP_ID = "U3B6GR4UA3"
ALGOLIA_API_KEY = "9a20c93440cf63cf1a7008d75f7438bf"
ALGOLIA_INDEX = "store_game_zh-Hant_HK_rank_asc"

ALGOLIA_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
)

HEADERS = {
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def search(filters: str, limit: int = 24) -> list[dict]:
    payload = {
        "params": (
            f"hitsPerPage={limit}"
            f"&filters={filters}"
            f"&attributesToRetrieve=title,nsuid,priceRange,salePriceRange,"
            f"onSale,headerImage,boxArt,productImage,url,publisher,genres,releaseDate"
        )
    }
    resp = requests.post(ALGOLIA_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("hits", [])


def normalize(hit: dict) -> dict:
    pr = hit.get("priceRange", {})
    sp = hit.get("salePriceRange", {})
    base = pr.get("min") if pr else None
    sale = sp.get("min") if sp else None
    discount = None
    if base and sale and base > 0:
        discount = round((1 - sale / base) * 100)

    url = hit.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://store.nintendo.com.hk" + url

    return {
        "platform": "Switch",
        "nsuid": hit.get("nsuid"),
        "name": hit.get("title", ""),
        "price_original_hkd": base,
        "price_final_hkd": sale or base,
        "discount_percent": discount,
        "on_sale": hit.get("onSale", False),
        "store_url": url,
        "header_image": hit.get("headerImage") or hit.get("boxArt") or hit.get("productImage"),
        "publisher": hit.get("publisher"),
        "genres": hit.get("genres", []),
        "trailers": [],  # 任天堂预告片在商品详情页, 需另外抓 (见 fetch_trailer)
    }


def fetch_trailer(item: dict) -> dict:
    """
    去商品详情页抓预告片 mp4。
    Switch 商品页里的视频通常嵌在 <video> 或 cloudfront 直链。
    """
    import re
    url = item.get("store_url")
    if not url:
        return item
    try:
        resp = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
        if resp.status_code != 200:
            return item
        html = resp.text
        # 抓 mp4 直链 (.cloudfront 或 .nintendo.)
        urls = re.findall(r'https://[^\s"\']+\.mp4', html)
        urls = list(dict.fromkeys(urls))  # 去重保序
        item["trailers"] = [{"title": "", "url": u} for u in urls[:3]]
    except Exception as e:
        print(f"    [warn] 取预告片失败 {item.get('name')}: {e}", file=sys.stderr)
    return item


def scrape(section: str, limit: int = 20, with_trailer: bool = True) -> list[dict]:
    if section == "deals":
        # 折扣中
        filters = "onSale:true"
    elif section == "new":
        # 新品: 用 release date 过滤近 60 天 (Algolia 时间戳是秒)
        recent = int(time.time()) - 60 * 24 * 3600
        filters = f"releaseDate >= {recent}"
    elif section == "coming_soon":
        future = int(time.time())
        filters = f"releaseDate > {future}"
    else:
        raise ValueError(f"未知 section={section}")

    print(f"[switch] 拉取 {section} ...")
    hits = search(filters, limit=limit)
    results = [normalize(h) for h in hits]
    print(f"[switch] 共 {len(results)} 条")

    if with_trailer:
        for i, item in enumerate(results, 1):
            print(f"  [{i}/{len(results)}] {item['name']}  补充预告片...")
            fetch_trailer(item)
            time.sleep(0.5)
    return results


def save(results: list[dict], section: str, out_dir: str = "data"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = Path(out_dir) / f"switch_{section}_{date_tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[switch] 已保存: {out_path}  ({len(results)} 条)")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="deals", choices=["deals", "new", "coming_soon"])
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--no-trailer", action="store_true")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    results = scrape(args.section, limit=args.limit, with_trailer=not args.no_trailer)
    save(results, args.section, out_dir=args.out)


if __name__ == "__main__":
    main()
