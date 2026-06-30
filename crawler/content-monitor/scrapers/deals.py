"""游戏折扣监控：Epic 免费游戏、Steam 特惠、Nintendo eShop 折扣。"""

import logging
import time
from datetime import datetime, UTC
from typing import List, Dict, Any

import requests

from config import REQUEST_TIMEOUT, REQUEST_DELAY

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_TODAY = lambda: datetime.now(UTC).date().isoformat()

# 固定参考汇率（美元/英镑/欧元 → 人民币），定期可手动更新
_FX = {"USD": 7.25, "GBP": 9.35, "EUR": 7.90}


def _foreign_to_cny(price_str: str) -> str:
    """将 '$12.34' / '£12.34' / '€12.34' 格式的价格转换为人民币显示。
    保留原币价格作参考，例如：¥89.4（$12.34）。
    """
    import re
    price_str = price_str.strip()
    m = re.match(r"([\$£€])\s*([\d,]+\.?\d*)", price_str)
    if not m:
        return price_str
    sym, num_str = m.group(1), m.group(2).replace(",", "")
    sym_map = {"$": "USD", "£": "GBP", "€": "EUR"}
    code = sym_map.get(sym)
    if not code:
        return price_str
    try:
        cny = float(num_str) * _FX[code]
        return f"¥{cny:.1f}（{sym}{num_str}）"
    except (ValueError, KeyError):
        return price_str


# ==================== Epic ====================

def fetch_epic_free_games() -> List[Dict[str, Any]]:
    """抓取 Epic 当前 + 即将免费游戏。"""
    url = (
        "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
        "?locale=zh-CN&country=CN&allowCountries=CN"
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        data = resp.json()
    except Exception as e:
        logger.error("Epic API 失败: %s", e)
        return []

    elements = (
        data.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
    )
    rows: List[Dict[str, Any]] = []
    for game in elements:
        promos = game.get("promotions") or {}
        current  = promos.get("promotionalOffers") or []
        upcoming = promos.get("upcomingPromotionalOffers") or []
        if not current and not upcoming:
            continue

        title = game.get("title", "")
        desc  = (game.get("description") or "")[:200]
        slug  = game.get("productSlug") or game.get("urlSlug") or ""
        game_url = (
            f"https://store.epicgames.com/zh-CN/p/{slug}"
            if slug else "https://store.epicgames.com/zh-CN/free-games"
        )

        if current:
            offers = current[0].get("promotionalOffers", [])
            start  = (offers[0].get("startDate", "") if offers else "")[:10]
            end    = (offers[0].get("endDate",   "") if offers else "")[:10]
            status = "免费领取中"
        else:
            offers = upcoming[0].get("promotionalOffers", [])
            start  = (offers[0].get("startDate", "") if offers else "")[:10]
            end    = (offers[0].get("endDate",   "") if offers else "")[:10]
            status = "即将免费"

        price_info = game.get("price", {}).get("totalPrice", {})
        # fmtVatPrice 在 CN 区常为 null；originalPrice 单位是"分"，需除以100
        fmt = price_info.get("fmtVatPrice")
        if fmt:
            original_price = fmt
        else:
            cents = price_info.get("originalPrice") or 0
            currency = price_info.get("currencyCode", "CNY")
            if currency == "CNY":
                original_price = f"¥{cents / 100:.2f}" if cents else ""
            else:
                original_price = _foreign_to_cny(f"${cents / 100:.2f}") if cents else ""

        # 封面图：优先宽幅促销图，其次缩略图
        cover_image = ""
        for img in (game.get("keyImages") or []):
            if img.get("type") in ("DieselStoreFrontWide", "OfferImageWide", "Thumbnail"):
                cover_image = img.get("url", "")
                if img.get("type") != "Thumbnail":
                    break

        rows.append({
            "source":         "deals",
            "label":          "epic",
            "platform":       "Epic",
            "title":          f"【Epic 喜加一】{title} — {status}",
            "content":        f"{status}\n原价：{original_price}\n\n{desc}",
            "url":            game_url,
            "time":           _TODAY(),
            "price_original": original_price,
            "price_current":  "免费",
            "discount":       "100% OFF",
            "cover_image":    cover_image,
            "deal_start":     start,
            "deal_end":       end,
        })

    return rows


# ==================== Steam ====================

def _is_english(text: str) -> bool:
    """判断文本是否主要为英文（中文字符占比 < 15%）。"""
    if not text:
        return False
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese / len(text) < 0.15


def fetch_steam_specials(limit: int = 20) -> List[Dict[str, Any]]:
    """抓取 Steam 当前特惠游戏，并补充游戏简介 / 评分等信息，英文简介自动翻译。"""
    from qwen_client import batch_translate_to_zh

    url = "https://store.steampowered.com/api/featuredcategories/?cc=cn&l=schinese"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        data = resp.json()
    except Exception as e:
        logger.error("Steam API 失败: %s", e)
        return []

    specials = data.get("specials", {}).get("items", [])
    rows: List[Dict[str, Any]] = []
    for game in specials[:limit]:
        app_id       = game.get("id")
        title        = game.get("name", "")
        discount_pct = game.get("discount_percent", 0)
        final        = (game.get("final_price",    0) or 0) / 100
        original     = (game.get("original_price", 0) or 0) / 100

        if not discount_pct:
            continue

        game_url = (
            f"https://store.steampowered.com/app/{app_id}/"
            if app_id else "https://store.steampowered.com/specials"
        )
        # Steam CDN 封面图（header.jpg 无需额外 API 请求）
        cover_image = (
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
            if app_id else ""
        )

        # 通过 appdetails API 获取简介 + 评分 + 折扣时间
        desc_extra = ""
        review_summary = ""
        deal_start = ""
        deal_end = ""
        if app_id:
            try:
                detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=cn&l=schinese"
                detail_resp = requests.get(detail_url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
                detail_json = detail_resp.json()
                app_data = detail_json.get(str(app_id), {})
                if app_data.get("success"):
                    d = app_data.get("data", {})
                    desc_extra = (d.get("short_description") or "").strip()
                    meta = d.get("metacritic") or {}
                    score = meta.get("score")
                    if score:
                        review_summary = f"Metacritic 评分：{score}"
                    else:
                        reviews = d.get("reviews") or ""
                        if isinstance(reviews, str) and reviews.strip():
                            review_summary = reviews.strip()
                    # 折扣结束时间（Unix 时间戳）
                    price_overview = d.get("price_overview") or {}
                    expiry_ts = price_overview.get("discount_expiry")
                    if expiry_ts:
                        from datetime import datetime, timezone
                        deal_end = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception as e:
                logger.warning("Steam 详情 API 失败 (app_id=%s): %s", app_id, e)
            finally:
                time.sleep(0.4)

        rows.append({
            "source":         "deals",
            "label":          "steam",
            "platform":       "Steam",
            "title":          f"【Steam】{title} — {discount_pct}% OFF",
            "_desc":          desc_extra,       # 暂存，后续按需翻译
            "_review":        review_summary,
            "url":            game_url,
            "time":           _TODAY(),
            "price_original": f"¥{original:.2f}",
            "price_current":  f"¥{final:.2f}",
            "discount":       f"-{discount_pct}%",
            "cover_image":    cover_image,
            "deal_start":     deal_start,
            "deal_end":       deal_end,
        })

    if not rows:
        return rows

    # 批量翻译英文简介（中文的直接跳过）
    desc_list   = [r.pop("_desc",   "") for r in rows]
    review_list = [r.pop("_review", "") for r in rows]
    en_indices  = [i for i, d in enumerate(desc_list) if _is_english(d)]
    if en_indices:
        try:
            logger.info("通义翻译 Steam 英文简介（%d 条）…", len(en_indices))
            translated = batch_translate_to_zh([desc_list[i] for i in en_indices])
            for j, idx in enumerate(en_indices):
                if j < len(translated):
                    desc_list[idx] = translated[j]
        except Exception as e:
            logger.warning("Steam 简介翻译失败: %s", e)

    # 组装最终 content
    for i, row in enumerate(rows):
        content_lines = [
            f"折扣：{row['discount']}",
            f"原价：{row['price_original']}",
            f"折后价：{row['price_current']}",
        ]
        if desc_list[i]:
            content_lines += ["", desc_list[i]]
        if review_list[i]:
            content_lines += ["", review_list[i]]
        row["content"] = "\n".join(content_lines)

    return rows


# ==================== Nintendo ====================

def fetch_nintendo_deals(limit: int = 20) -> List[Dict[str, Any]]:
    """抓取 Nintendo eShop 折扣信息（NintendoLife eshop/offers 页面）。"""
    from bs4 import BeautifulSoup
    from qwen_client import batch_translate_to_zh

    _BASE = "https://www.nintendolife.com"
    url = f"{_BASE}/eshop/offers"
    try:
        resp = requests.get(
            url,
            headers={**_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error("NintendoLife offers 抓取失败: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.select("article.item")

    rows: List[Dict[str, Any]] = []
    for art in articles[:limit]:
        # 标题
        title_tag = art.select_one("span.game-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        # 游戏链接
        link_tag = art.select_one("a.game-info")
        href = (link_tag.get("href") or "").lstrip("/") if link_tag else ""
        game_url = f"{_BASE}/{href}" if href else url

        # 封面图（选 300x.jpg）
        img_tag = art.select_one(".image img")
        cover_image = img_tag.get("src", "") if img_tag else ""

        # 折扣文本：优先 US → UK → EU
        discount = ""
        for region_cls in ("region-us", "region-uk", "region-eu"):
            offer_li = art.select_one(f"ul.offers li.{region_cls}")
            if offer_li and offer_li.get_text(strip=True):
                discount = offer_li.get_text(strip=True)
                break
        # 没有折扣的卡片跳过
        if not discount:
            continue

        # 价格解析：取与折扣同地区的 price li，优先 US → UK → EU
        # HTML 结构：<del>$原价</del><sup class="cur">$</sup>折后数字
        # 注意：某地区 price li 可能没有 del（无折扣），此时 original 为空
        original_price = ""
        current_price = ""

        for region_cls in ("region-us", "region-uk", "region-eu"):
            price_li = art.select_one(f"ul.prices li.{region_cls}")
            if not price_li:
                continue
            del_tag = price_li.find("del")
            sup_tag = price_li.find("sup", class_="cur")
            cur_sym = sup_tag.get_text(strip=True) if sup_tag else ""
            if del_tag:
                orig = del_tag.get_text(strip=True)
                # 折后数字 = 全文本去掉 del 文本和 sup 文本后剩余
                full = price_li.get_text(strip=True)
                curr_num = full.replace(del_tag.get_text(strip=True), "").replace(cur_sym, "").strip()
                original_price = orig
                current_price  = cur_sym + curr_num
                break
            else:
                # 该地区无折扣标记，只记录参考价格，继续找有 del 的地区
                if not current_price:
                    current_price = price_li.get_text(strip=True)

        # 将外币价格换算为人民币
        original_price = _foreign_to_cny(original_price) if original_price else ""
        current_price  = _foreign_to_cny(current_price)  if current_price  else ""

        # content 组装（简介在详情抓取后追加）
        content_parts = [f"折扣：{discount}"]
        if original_price:
            content_parts.append(f"原价：{original_price}")
        if current_price:
            content_parts.append(f"折后价：{current_price}")

        rows.append({
            "source":         "deals",
            "label":          "nintendo",
            "platform":       "Nintendo",
            "title":          title,   # 暂存英文，稍后批量翻译
            "content":        "\n".join(content_parts),
            "url":            game_url,
            "time":           _TODAY(),
            "price_original": original_price,
            "price_current":  current_price,
            "discount":       discount,
            "cover_image":    cover_image,
        })

    if not rows:
        return rows

    # 补充每款游戏的简介 + 高清封面（从详情页抓取）
    _NL_HEADERS = {**_HEADERS, "Accept": "text/html,*/*"}
    from bs4 import BeautifulSoup as _BS
    for row in rows:
        try:
            detail_resp = requests.get(row["url"], headers=_NL_HEADERS, timeout=REQUEST_TIMEOUT)
            detail_soup = _BS(detail_resp.text, "html.parser")

            # 高清封面：优先详情页 images.nintendolife.com img（900x），无则保留列表页图
            detail_img = detail_soup.find(
                "img", src=lambda s: s and "images.nintendolife.com" in s
            )
            if detail_img:
                row["cover_image"] = detail_img["src"]  # 900x.jpg
            elif not row["cover_image"]:
                # 没有封面时尝试从 srcset 取高清
                detail_img2 = detail_soup.find(
                    "img", srcset=lambda s: s and "images.nintendolife.com" in (s or "")
                )
                if detail_img2:
                    row["cover_image"] = detail_img2.get("src", "")

            # 简介（英文原文，后续批量翻译）
            desc_en = ""
            h1 = detail_soup.find("h1", class_="headline")
            if h1:
                for p in h1.find_all_next("p"):
                    text = p.get_text(strip=True)
                    if len(text) > 40:
                        desc_en = text[:300]
                        break

            # 元数据：dl > dt/dd
            genre = ""
            deal_start = ""
            deal_end = ""
            dl = detail_soup.find("dl")
            if dl:
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                meta = {dt.get_text(strip=True): dd.get_text(strip=True)
                        for dt, dd in zip(dts, dds)}
                genre = meta.get("Genre", "")
                # 折扣时间：Sale Starts / Sale Ends
                deal_start = meta.get("Sale Starts", meta.get("Sale Start", ""))
                deal_end   = meta.get("Sale Ends",   meta.get("Sale End",   ""))

            # 暂存英文简介用于后续批量翻译
            row["_desc_en"]    = desc_en
            row["_genre"]      = genre
            row["deal_start"]  = deal_start
            row["deal_end"]    = deal_end

        except Exception as e:
            logger.warning("Nintendo 详情抓取失败 (%s): %s", row["url"], e)
            row.setdefault("_desc_en",   "")
            row.setdefault("_genre",     "")
            row.setdefault("deal_start", "")
            row.setdefault("deal_end",   "")
        finally:
            time.sleep(0.4)

    # 批量翻译：标题 + 简介（合并一次 API 调用）
    titles_en = [r["title"] for r in rows]
    descs_en  = [r.pop("_desc_en", "") for r in rows]
    genres    = [r.pop("_genre",   "") for r in rows]

    # 需要翻译的文本 = 标题列表 + 简介列表（拼接，用 len 分割）
    all_texts_en = titles_en + descs_en
    try:
        logger.info("通义翻译 Nintendo 标题+简介（共 %d 条）…", len(all_texts_en))
        all_texts_zh = batch_translate_to_zh(all_texts_en)
        titles_zh = all_texts_zh[:len(titles_en)]
        descs_zh  = all_texts_zh[len(titles_en):]
    except Exception as e:
        logger.warning("Nintendo 批量翻译失败，使用原文: %s", e)
        titles_zh = titles_en
        descs_zh  = descs_en

    for i, row in enumerate(rows):
        row["title"] = f"【任天堂】{titles_zh[i]}"
        extra_parts = []
        if genres[i]:
            extra_parts.append(f"类型：{genres[i]}")
        desc_zh = descs_zh[i] if i < len(descs_zh) else ""
        if desc_zh:
            extra_parts.append(f"\n{desc_zh}")
        if extra_parts:
            row["content"] += "\n" + "\n".join(extra_parts)

    return rows


# ==================== 统一入口 ====================

def run_deals_monitor(platforms: List[str], limit: int = 20) -> List[Dict[str, Any]]:
    """按需抓取各平台折扣信息。"""
    if not platforms:
        platforms = ["epic", "steam", "nintendo"]

    all_rows: List[Dict[str, Any]] = []

    if "epic" in platforms:
        logger.info("抓取 Epic 免费游戏...")
        all_rows.extend(fetch_epic_free_games())
        time.sleep(REQUEST_DELAY)

    if "steam" in platforms:
        logger.info("抓取 Steam 特惠（limit=%d）...", limit)
        all_rows.extend(fetch_steam_specials(limit))
        time.sleep(REQUEST_DELAY)

    if "nintendo" in platforms:
        logger.info("抓取 Nintendo 折扣（limit=%d）...", limit)
        all_rows.extend(fetch_nintendo_deals(limit))

    return all_rows
