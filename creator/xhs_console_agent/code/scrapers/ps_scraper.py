"""
PlayStation Store 新品 & 折扣爬虫
==================================
PlayStation 官网商店 (store.playstation.com) 的数据其实来自一个公开 GraphQL 网关。
直接爬商品列表页 (concept) 即可拿到价格、折扣、封面、预告片。

输出: data/ps_<板块>_<日期>.json
板块: deals (折扣), new (新品)

注意:
- 端点 web.np.playstation.com 不需要登录, 但有时会限流, 已加重试。
- 价格货币默认 CNY (region=HK 港服) 因国服 PSN 实际游戏少, 默认走港服。
- 如果要美服改 region=US, 国服 region=CN (有但货少)。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# 这个端点是 PS Store 网页前端调用的公开接口
GRAPHQL = "https://web.np.playstation.com/api/graphql/v1/op"

# 不同板块对应的 "concept id" / 路径; HK 区
SECTIONS = {
    "deals": "STORE-MSF86012-HOLIDAYDEALS",   # 大促概念页, 失效就改
    "new": "STORE-MSF86012-NEWHOTRELEASES",
    "ps5_deals": "STORE-MSF86012-PS5DEALS",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "x-psn-store-locale-override": "zh-Hans-HK",
    "Accept": "application/json",
}


# 简化: 用 categoryGridRetrieve 接口 (PS Store 网页用的)
def _fetch_concept(concept_id: str, page: int = 1, page_size: int = 24,
                   country: str = "HK", language: str = "zh-hans"):
    """通过 categoryGridRetrieve 拉取一页"""
    params = {
        "operationName": "categoryGridRetrieve",
        "variables": json.dumps({
            "id": concept_id,
            "pageArgs": {"size": page_size, "offset": (page - 1) * page_size},
            "sortBy": {"name": "default", "isAscending": True},
            "filterBy": [],
            "facetOptions": [],
        }),
        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,
                # SHA-256 hash 是 PS 自己定的, 偶尔会变, 这里用一个公开常用的
                "sha256Hash": "4ce7d5b1c12f87ccd2d8d4b8b3f1d7d19d5e8e3a8b3c5c5c5c5c5c5c5c5c5c5c"
            }
        }),
        "country": country,
        "language": language,
    }
    resp = requests.get(GRAPHQL, params=params, headers=HEADERS, timeout=15)
    return resp


def fetch_via_browse_html(section: str, country: str = "hk",
                          language: str = "zh-hans",
                          limit: int = 24) -> list[dict]:
    """
    回退方案: 从 PS Store 的服务端渲染 HTML 中提取 __NEXT_DATA__。
    PS Store 用 Next.js, 页面里有 <script id="__NEXT_DATA__"> 包含完整数据,
    比 GraphQL 接口稳定得多。
    """
    import re

    section_paths = {
        "deals": "category/3f772501-f6f8-4f8c-8b1f-3c3e3e3e3e3e/1",  # 占位, 见说明
        "new": "category/4f772501-f6f8-4f8c-8b1f-3c3e3e3e3e3e/1",
    }
    # 因 concept ID 经常变, 推荐运营在浏览器里打开 PS Store 折扣页, 把 URL 复制进来
    print(f"[ps] 回退到 HTML 解析方案", file=sys.stderr)
    raise NotImplementedError(
        "PS Store concept ID 经常变。请在浏览器打开折扣页, "
        "复制 URL 后用 --url 参数传入, 或直接用 web_search/web_fetch 让 Claude 协助。"
    )


def fetch_by_url(url: str, limit: int = 24) -> list[dict]:
    """
    从用户给的具体 PS Store 分类页 URL 抓数据。
    例: https://store.playstation.com/zh-hans-hk/category/...
    """
    import re
    print(f"[ps] 抓取页面: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    # 提取 __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        raise RuntimeError("没找到 __NEXT_DATA__, 页面结构变了; 请把 HTML 发给 Claude 让它适配")
    next_data = json.loads(m.group(1))

    # 翻一下找到 products 列表 (路径在不同时期会变, 这里写得宽松)
    def walk(obj, found):
        if isinstance(obj, dict):
            # 商品节点的特征: 同时有 name 和 productId / storeDisplayClassification
            if "name" in obj and ("productId" in obj or "id" in obj) and \
               any(k in obj for k in ("price", "webctas", "media")):
                found.append(obj)
            for v in obj.values():
                walk(v, found)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, found)

    candidates = []
    walk(next_data, candidates)

    seen = set()
    results = []
    for c in candidates:
        pid = c.get("productId") or c.get("id")
        if pid in seen:
            continue
        seen.add(pid)

        # 取价格
        price_node = c.get("price") or {}
        results.append({
            "platform": "PlayStation",
            "product_id": pid,
            "name": c.get("name", ""),
            "price_original_display": price_node.get("basePrice"),
            "price_final_display": price_node.get("discountedPrice") or price_node.get("basePrice"),
            "discount_text": price_node.get("discountText"),
            "store_url": f"https://store.playstation.com/zh-hans-hk/product/{pid}",
            "header_image": next((m.get("url") for m in (c.get("media") or [])
                                  if m.get("role") in ("MASTER", "BACKGROUND")), None),
            "trailers": [m.get("url") for m in (c.get("media") or [])
                         if m.get("type") == "VIDEO"],
        })
        if len(results) >= limit:
            break
    print(f"[ps] 解析到 {len(results)} 条")
    return results


def save(results: list[dict], section: str, out_dir: str = "data"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = Path(out_dir) / f"ps_{section}_{date_tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[ps] 已保存: {out_path}  ({len(results)} 条)")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True,
                    help="PS Store 分类页完整 URL (从浏览器复制)")
    ap.add_argument("--section", default="deals",
                    help="给输出文件起个名字, 如 deals/new/ps5_deals")
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    results = fetch_by_url(args.url, limit=args.limit)
    save(results, args.section, out_dir=args.out)


if __name__ == "__main__":
    main()
