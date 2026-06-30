"""
三主机统一爬虫入口
==================
一条命令同时爬 Steam / PS / Switch, 合并到一个 JSON 文件里。

用法:
    python scrape_all.py --section deals --limit 10
    python scrape_all.py --section new --skip ps   # 跳过 PS
    python scrape_all.py --ps-url "https://store.playstation.com/zh-hans-hk/category/..."

输出: data/all_<板块>_<日期>.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 让脚本无论在哪个目录跑都能找到兄弟模块
sys.path.insert(0, str(Path(__file__).parent))

import steam_scraper
import switch_scraper
import ps_scraper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="deals",
                    help="deals / new / coming_soon (各平台名字会自动映射)")
    ap.add_argument("--limit", type=int, default=10, help="每个平台最多拿多少条")
    ap.add_argument("--skip", nargs="*", default=[], choices=["steam", "ps", "switch"],
                    help="跳过哪些平台")
    ap.add_argument("--ps-url", default=None,
                    help="PS Store 分类页 URL (从浏览器复制); 没传就跳过 PS")
    ap.add_argument("--no-trailer", action="store_true",
                    help="不抓预告片(更快, 但后续剪视频用不了)")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_items = []

    # ---- Steam ----
    if "steam" not in args.skip:
        steam_section_map = {"deals": "specials", "new": "new",
                             "coming_soon": "coming_soon", "topsellers": "topsellers"}
        s_section = steam_section_map.get(args.section, args.section)
        try:
            items = steam_scraper.scrape(s_section, limit=args.limit,
                                         with_trailer=not args.no_trailer)
            all_items.extend(items)
        except Exception as e:
            print(f"[!] Steam 失败: {e}", file=sys.stderr)

    # ---- Switch ----
    if "switch" not in args.skip:
        sw_section_map = {"deals": "deals", "new": "new", "coming_soon": "coming_soon"}
        sw_section = sw_section_map.get(args.section, "deals")
        try:
            items = switch_scraper.scrape(sw_section, limit=args.limit,
                                          with_trailer=not args.no_trailer)
            all_items.extend(items)
        except Exception as e:
            print(f"[!] Switch 失败: {e}", file=sys.stderr)

    # ---- PS ----
    if "ps" not in args.skip:
        if args.ps_url:
            try:
                items = ps_scraper.fetch_by_url(args.ps_url, limit=args.limit)
                all_items.extend(items)
            except Exception as e:
                print(f"[!] PS 失败: {e}", file=sys.stderr)
        else:
            print("[ps] 跳过: 没提供 --ps-url; "
                  "请在浏览器打开 PS Store 折扣页, 复制 URL 后用 --ps-url 传入",
                  file=sys.stderr)

    # 保存
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"all_{args.section}_{date_tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n=== 汇总 ===")
    print(f"总计 {len(all_items)} 条游戏数据")
    by_platform = {}
    for it in all_items:
        by_platform.setdefault(it.get("platform", "?"), 0)
        by_platform[it.get("platform", "?")] += 1
    for p, n in by_platform.items():
        print(f"  {p}: {n}")
    print(f"已保存到: {out_path}")


if __name__ == "__main__":
    main()
