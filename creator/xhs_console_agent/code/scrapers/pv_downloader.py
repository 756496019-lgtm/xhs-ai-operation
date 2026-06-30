"""
PV / 预告片批量下载器
=======================
读取 scrape_all.py 输出的 JSON, 把每个游戏的预告片 mp4 下载到本地。

输出结构:
    pv_library/
      <游戏slug>/
        trailer_01.mp4
        meta.json   # 这个游戏的简要信息

用法:
    python pv_downloader.py --input data/all_deals_20260507.json
    python pv_downloader.py --input ... --max-per-game 1   # 每个游戏只下第一个预告片
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}


def slugify(name: str) -> str:
    """把游戏名转成安全的目录名"""
    s = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", name).strip("_")
    return s[:60] or "untitled"


def download(url: str, out_path: Path, chunk: int = 1024 * 256):
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"    已存在, 跳过: {out_path.name}")
        return out_path
    print(f"    下载: {url}")
    with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        last_pct = -10
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for piece in r.iter_content(chunk_size=chunk):
                if not piece:
                    continue
                f.write(piece)
                done += len(piece)
                if total:
                    pct = int(done * 100 / total)
                    if pct - last_pct >= 10:
                        print(f"      {pct}%  ({done/1e6:.1f}/{total/1e6:.1f} MB)")
                        last_pct = pct
    print(f"    完成: {out_path}")
    return out_path


def process(items: list[dict], out_root: Path, max_per_game: int = 1):
    out_root.mkdir(parents=True, exist_ok=True)
    summary = []
    for i, item in enumerate(items, 1):
        name = item.get("name", "未命名")
        trailers = item.get("trailers") or []
        # Switch 的 trailers 可能是字典列表也可能是字符串列表, 兼容
        urls = []
        for t in trailers:
            if isinstance(t, str):
                urls.append(t)
            elif isinstance(t, dict) and t.get("url"):
                urls.append(t["url"])
        if not urls:
            print(f"[{i}/{len(items)}] {name}  没有预告片, 跳过")
            continue
        print(f"[{i}/{len(items)}] {name}  ({len(urls)} 个预告片, 取前 {max_per_game})")
        slug = slugify(name)
        game_dir = out_root / slug
        game_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        for j, url in enumerate(urls[:max_per_game], 1):
            ext = Path(urlparse(url).path).suffix or ".mp4"
            out_path = game_dir / f"trailer_{j:02d}{ext}"
            try:
                download(url, out_path)
                downloaded.append(str(out_path))
            except Exception as e:
                print(f"    [!] 失败: {e}", file=sys.stderr)
            time.sleep(0.3)

        meta = {
            "name": name,
            "platform": item.get("platform"),
            "store_url": item.get("store_url"),
            "header_image": item.get("header_image"),
            "price_original": item.get("price_original_cny") or item.get("price_original_hkd")
                              or item.get("price_original_display"),
            "price_final": item.get("price_final_cny") or item.get("price_final_hkd")
                           or item.get("price_final_display"),
            "discount_percent": item.get("discount_percent"),
            "short_description": item.get("short_description", ""),
            "genres": item.get("genres", []),
            "trailers_local": downloaded,
        }
        with open(game_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        summary.append({"slug": slug, **meta})

    # 全局索引
    index_path = out_root / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[done] 索引文件: {index_path}")
    print(f"[done] 共下载 {len(summary)} 个游戏的预告片到 {out_root}/")
    return index_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="scrape_all.py 输出的 JSON 文件")
    ap.add_argument("--out", default="pv_library", help="预告片仓库目录")
    ap.add_argument("--max-per-game", type=int, default=1,
                    help="每个游戏最多下几个预告片")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        items = json.load(f)
    process(items, Path(args.out), max_per_game=args.max_per_game)


if __name__ == "__main__":
    main()
