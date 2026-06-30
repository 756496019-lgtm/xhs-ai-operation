# -*- coding: utf-8 -*-
"""
weekly_output_builder.py
------------------------
微信公众号 + 小红书周报 HTML 生成器（集成版）。
由 app.py 调用，不再需要独立运行 gen_output_html.py。

对外接口：
  build_wechat_html(full_md, week_label, week_short, date_range, issue)
      -> str  完整的微信公众号 HTML

  build_xhs_html(cards_html_list)
      -> str  完整的小红书卡片 HTML（含下载按钮）

  read_sheet_rows(wb, sheet_name)
      -> [(rank, [names...])]  从 openpyxl workbook 读取榜单数据

辅助函数（构建卡片内容）：
  xhs_h2, xhs_h3, xhs_para, xhs_quote, anomaly_li, rank_table,
  section_label, xhs_card, badge_bar, footer_bar
"""
import re
from collections import Counter


# ──────────────────────────────────────────────────────────────────────────────
# Markdown → 微信 HTML 转换器
# ──────────────────────────────────────────────────────────────────────────────

def md_to_wechat_html(md_text):
    lines = md_text.split("\n")
    out = []
    section_counter = [0]
    i = 0
    while i < len(lines):
        line = lines[i]

        # H1 -> hidden（banner 已有标题）
        if re.match(r'^# ', line):
            i += 1
            continue

        # H2 -> 橙色编号区块标题
        m2 = re.match(r'^## (.+)', line)
        if m2:
            section_counter[0] += 1
            num = str(section_counter[0]).zfill(2)
            title = re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]\s*', '', m2.group(1)).strip()
            out.append(
                f'<table cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;word-break:break-all;margin:32px 0 16px 0;">'
                f'<tr>'
                f'<td bgcolor="#E8820C" width="48" style="background-color:#E8820C;padding:10px 0;text-align:center;">'
                f'<span style="font-size:13px;font-weight:900;color:#FFFFFF;letter-spacing:1px;">{num}</span></td>'
                f'<td style="padding:10px 16px;background-color:#141E2E;">'
                f'<span style="font-size:18px;font-weight:900;color:#E8820C;letter-spacing:1px;">{title}</span>'
                f'</td></tr></table>'
            )
            i += 1
            continue

        # H3 -> 黄色左边线小节标题
        m3 = re.match(r'^### (.+)', line)
        if m3:
            title = m3.group(1).strip()
            out.append(
                f'<table cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;word-break:break-all;margin:18px 0 8px 0;">'
                f'<tr>'
                f'<td width="4" bgcolor="#F5B820" style="background-color:#F5B820;padding:0;">&nbsp;</td>'
                f'<td style="padding:8px 14px;">'
                f'<span style="font-size:15px;font-weight:700;color:#F5B820;">{title}</span>'
                f'</td></tr></table>'
            )
            i += 1
            continue

        # 水平分割线
        if re.match(r'^---+$', line.strip()):
            out.append('<table cellpadding="0" cellspacing="0" width="100%" style="margin:20px 0;"><tr><td height="1" bgcolor="#1E2D40" style="background:#1E2D40;font-size:1px;line-height:1px;">&nbsp;</td></tr></table>')
            i += 1
            continue

        # Markdown 管道表格  | col | col |
        if re.match(r'^\s*\|', line):
            table_rows = []
            while i < len(lines) and re.match(r'^\s*\|', lines[i]):
                table_rows.append(lines[i])
                i += 1
            header_row = None
            data_rows = []
            for row in table_rows:
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                if all(re.match(r'^:?-+:?$', c) for c in cells if c):
                    continue  # 分隔行
                if header_row is None:
                    header_row = cells
                else:
                    data_rows.append(cells)
            if header_row:
                tbl = '<table cellpadding="0" cellspacing="1" bgcolor="#1E2D40" width="100%" style="width:100%;background:#1E2D40;margin:12px 0;font-size:12px;word-break:break-all;">'
                tbl += '<tr>'
                for cell in header_row:
                    tbl += f'<td bgcolor="#0F1824" style="background:#0F1824;padding:7px 8px;font-size:11px;font-weight:700;color:#F5B820;text-align:center;white-space:nowrap;">{cell}</td>'
                tbl += '</tr>'
                for ri, row in enumerate(data_rows):
                    row_bg = '#141E2E' if ri % 2 == 0 else '#0F1824'
                    tbl += '<tr>'
                    for ci, cell in enumerate(row):
                        if ci == 0:
                            rank_num = ri + 1
                            try:
                                rank_num = int(cell.replace('🆕', '').strip())
                            except Exception:
                                pass
                            rc = '#FFD700' if rank_num == 1 else '#C0C0C0' if rank_num == 2 else '#CD7F32' if rank_num == 3 else '#7A9BB0'
                            fw = '800' if rank_num <= 3 else '400'
                            tbl += f'<td bgcolor="{row_bg}" style="background:{row_bg};padding:6px 8px;text-align:center;color:{rc};font-weight:{fw};white-space:nowrap;">{cell}</td>'
                        else:
                            display = cell.replace('🆕', '<span style="color:#E8820C;font-weight:700;">🆕</span>') if '🆕' in cell else cell
                            tbl += f'<td bgcolor="{row_bg}" style="background:{row_bg};padding:6px 8px;text-align:center;color:#C8D4E0;font-size:11px;">{display}</td>'
                    tbl += '</tr>'
                tbl += '</table>'
                out.append(tbl)
            continue

        # 无序列表
        if re.match(r'^[-*] ', line):
            items = []
            while i < len(lines) and re.match(r'^[-*] ', lines[i]):
                raw_item = lines[i][2:].strip()
                mb = re.match(r'\*\*(.+?)\*\*[：:]?\s*(.*)', raw_item)
                if mb:
                    bold = mb.group(1)
                    rest = mb.group(2)
                    items.append(f'<li style="color:#C8D8E8;margin-bottom:12px;font-size:14px;line-height:1.8;"><strong style="color:#F5B820;">{bold}</strong>{"：" if rest else ""}{rest}</li>')
                else:
                    items.append(f'<li style="color:#C8D8E8;margin-bottom:12px;font-size:14px;line-height:1.8;">{raw_item}</li>')
                i += 1
            out.append(f'<ul style="padding-left:1.4em;margin:8px 0;">{"".join(items)}</ul>')
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 普通段落
        para = line.strip()
        if para:
            para = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#EAF0F8;font-weight:700;">\1</strong>', para)
            para = re.sub(r'\*(.+?)\*', r'<em style="color:#F5B820;">\1</em>', para)
            out.append(f'<p style="word-break:break-word;margin:0 0 14px 0;font-size:15px;color:#C8D8E8;line-height:1.8;">{para}</p>')
        i += 1

    return "\n".join(out)


def build_wechat_html(full_md, week_label, week_short, date_range, issue):
    """生成完整微信公众号 HTML 字符串。"""
    article_html = md_to_wechat_html(full_md)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>游戏行业周报 {week_label} - GAME RADAR HQ</title>
<style>
  body {{ margin: 0; padding: 0; word-break: break-word; background-color: #0F1824; font-family: "PingFang SC","Noto Sans SC","Microsoft YaHei",Arial,sans-serif; color: #C8D8E8; }}
  .wrap {{ max-width: 680px; width: 100%; margin: 0 auto; padding: 0 0 40px 0; box-sizing: border-box; }}
  p, li {{ line-height: 1.8; font-size: 15px; color: #C8D8E8; }}
  ul {{ padding-left: 0; list-style: none; }}
  li {{ margin-bottom: 14px; }}
</style>
</head>
<body>
<div class="wrap">

<!-- 操作提示 -->
<p style="word-break:break-word;background-color:#1E2D40;color:#F5B820;font-size:13px;padding:10px 16px;text-align:center;margin:0;">全选（Ctrl+A）→ 复制（Ctrl+C）→ 粘贴到公众号编辑器</p>

<!-- 顶部 Banner -->
<table cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;word-break:break-all;margin:0;">
  <tr>
    <td bgcolor="#E8820C" style="background-color:#E8820C;padding:28px 32px;">
      <div style="font-size:11px;color:#7A3800;letter-spacing:4px;font-weight:700;text-transform:uppercase;margin-bottom:6px;">GAME RADAR HQ · 第{issue}期</div>
      <div style="font-size:26px;font-weight:900;color:#FFFFFF;letter-spacing:2px;">游戏行业周报</div>
      <div style="font-size:13px;color:#FFDDAA;margin-top:6px;">{week_short} &nbsp;|&nbsp; {date_range}</div>
    </td>
  </tr>
</table>

<!-- 正文区域 -->
<table cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;word-break:break-all;">
  <tr>
    <td style="padding:0 12px;">

{article_html}

    </td>
  </tr>
</table>

<!-- 页脚 -->
<table cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;word-break:break-all;margin-top:40px;">
  <tr>
    <td bgcolor="#E8820C" style="background-color:#E8820C;padding:16px 20px;text-align:center;">
      <span style="font-size:13px;color:#FFFFFF;font-weight:800;letter-spacing:2px;">游戏雷达局 &nbsp;·&nbsp; GAME RADAR HQ &nbsp;·&nbsp; 情报已送达</span>
    </td>
  </tr>
</table>

</div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# 小红书卡片辅助函数（与 gen_xhs.py 3/9 原版完全一致）
# ──────────────────────────────────────────────────────────────────────────────

def badge_bar(right=''):
    return (
        '<div style="background-color:#0A1220;border-bottom:2px solid #E8820C;padding:6px 14px;'
        'display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">'
        '<span style="color:#E8820C;font-size:10px;font-weight:800;letter-spacing:2px;">&#9632; GAME RADAR HQ</span>'
        '<span style="color:#6080A0;font-size:10px;letter-spacing:1px;">' + right + '</span>'
        '</div>'
    )


def footer_bar():
    return (
        '<div style="background-color:#E8820C;padding:8px 14px;'
        'display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">'
        '<span style="color:#fff;font-size:11px;font-weight:800;letter-spacing:1px;">游戏雷达局</span>'
        '<span style="color:rgba(255,255,255,0.8);font-size:10px;letter-spacing:2px;">WEEKLY</span>'
        '</div>'
    )


def xhs_card(id_, right_tag, body_html):
    return (
        '<div id="card' + str(id_) + '" style="width:375px;min-height:500px;background-color:#0F1824;'
        'box-shadow:0 8px 24px rgba(0,0,0,0.25);display:flex;flex-direction:column;overflow:hidden;'
        'font-family:\'PingFang SC\',\'Noto Sans SC\',\'Microsoft YaHei\',sans-serif;">'
        + badge_bar(right_tag)
        + '<div style="flex:1;padding:14px 14px 12px;display:flex;flex-direction:column;">'
        + body_html
        + '</div>'
        + footer_bar()
        + '</div>'
    )


def xhs_h2(num, text):
    return (
        '<table cellpadding="0" cellspacing="0" width="100%" style="margin:0 0 10px 0;">'
        '<tr>'
        '<td width="26" bgcolor="#E8820C" style="background-color:#E8820C;color:#fff;font-size:10px;font-weight:900;text-align:center;padding:3px 0;">' + num + '</td>'
        '<td style="padding-left:8px;font-size:14px;font-weight:900;color:#E8820C;">' + text + '</td>'
        '</tr></table>'
    )


def xhs_h3(text):
    return (
        '<table cellpadding="0" cellspacing="0" width="100%" style="margin:8px 0 5px 0;">'
        '<tr>'
        '<td width="3" bgcolor="#F5B820" style="background-color:#F5B820;"> </td>'
        '<td style="padding-left:7px;font-size:11px;font-weight:800;color:#F5B820;line-height:1.4;">' + text + '</td>'
        '</tr></table>'
    )


def xhs_para(text):
    return '<p style="color:#B0C4D8;font-size:11px;line-height:1.7;margin:0 0 7px 0;">' + text + '</p>'


def xhs_quote(label, text):
    return (
        '<table cellpadding="0" cellspacing="0" width="100%" style="margin:4px 0 8px 0;">'
        '<tr>'
        '<td width="3" bgcolor="#E8820C" style="background-color:#E8820C;"> </td>'
        '<td bgcolor="#111C28" style="background-color:#111C28;padding:6px 9px;">'
        '<div style="font-size:9px;color:#E8820C;font-weight:700;margin-bottom:3px;">' + label + '</div>'
        '<div style="font-size:10px;color:#8AACBE;line-height:1.6;">' + text + '</div>'
        '</td></tr></table>'
    )


def anomaly_li(badge, name, note):
    bc = '#C8500A' if '★' in badge else '#1A5FAA'
    return (
        '<div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:7px;">'
        '<span style="background-color:' + bc + ';color:#fff;font-size:9px;font-weight:800;padding:2px 5px;'
        'border-radius:3px;white-space:nowrap;flex-shrink:0;">' + badge + '</span>'
        '<div>'
        '<span style="color:#EAF0F8;font-size:11px;font-weight:700;">' + name + '</span>'
        '<div style="color:#7090B0;font-size:10px;margin-top:1px;">' + note + '</div>'
        '</div></div>'
    )


def rank_table(rows):
    rank_colors = {1: '#FFD700', 2: '#C0C0C0', 3: '#CD7F32'}
    lines = ''
    for rank, names in rows:
        valid = [n for n in names if n and n != '-']
        top = Counter(valid).most_common(1)[0][0] if valid else '-'
        rc = rank_colors.get(rank, '#C8D8E8')
        fw = '800' if rank <= 3 else '400'
        bg = '#141E2E' if rank % 2 == 1 else '#0F1824'
        lines += (
            '<tr>'
            '<td bgcolor="' + bg + '" style="background-color:' + bg + ';padding:4px 6px;color:' + rc + ';'
            'font-weight:' + fw + ';font-size:11px;text-align:center;width:24px;">' + str(rank) + '</td>'
            '<td bgcolor="' + bg + '" style="background-color:' + bg + ';padding:4px 6px;color:' + rc + ';'
            'font-weight:' + fw + ';font-size:11px;word-break:break-all;">' + top + '</td>'
            '</tr>'
        )
    return (
        '<table cellspacing="1" bgcolor="#1E2D40" width="100%" style="background-color:#1E2D40;'
        'table-layout:fixed;word-break:break-all;margin:4px 0 8px 0;">'
        + lines + '</table>'
    )


def section_label(text):
    return '<p style="color:#6080A0;font-size:10px;margin:0 0 3px 0;letter-spacing:1px;">' + text + '</p>'


# ──────────────────────────────────────────────────────────────────────────────
# 从 openpyxl workbook 读取榜单数据
# ──────────────────────────────────────────────────────────────────────────────

def read_sheet_rows(wb, sheet_name):
    """从 sheet 读排名 1-10，每行返回 (rank, [7天游戏名列表])"""
    if sheet_name not in wb.sheetnames:
        return []
    ws = wb[sheet_name]
    mc = ws.max_column
    date_cols = []
    for ci in range(2, mc + 1):
        hv = str(ws.cell(row=2, column=ci).value or '').strip()
        if hv and '资料来源' not in hv:
            date_cols.append(ci)
    rows = []
    for r in range(3, 13):
        rv = ws.cell(row=r, column=1).value
        if not isinstance(rv, int):
            continue
        names = [str(ws.cell(row=r, column=ci).value or '').strip() for ci in date_cols]
        rows.append((rv, names))
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# 生成小红书完整 HTML（含下载按钮）
# ──────────────────────────────────────────────────────────────────────────────

def build_xhs_html(cards_html_list):
    """接收卡片 HTML 列表，返回完整的小红书页面 HTML。"""
    n = len(cards_html_list)
    cards_joined = '\n'.join(cards_html_list)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>游戏行业周报 小红书图文 - GAME RADAR HQ</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background-color: #C8CDD4; font-family: 'PingFang SC','Noto Sans SC','Microsoft YaHei',sans-serif; padding: 28px 16px 48px; }}
.tip {{ text-align:center; color:#555; font-size:12px; background:#fff; padding:10px 20px; border-radius:6px; max-width:1500px; margin:0 auto 20px; line-height:1.8; }}
.cards-row {{ display:flex; flex-direction:row; gap:16px; justify-content:flex-start; flex-wrap:wrap; max-width:1500px; margin:0 auto; align-items:flex-start; }}
#dl-btn {{
  display:inline-flex; align-items:center; gap:8px;
  background:#E8820C; color:#fff; font-size:13px; font-weight:700;
  padding:8px 20px; border-radius:6px; cursor:pointer; border:none;
  letter-spacing:1px; margin-top:4px;
}}
#dl-btn:disabled {{ background:#999; cursor:not-allowed; }}
</style>
</head>
<body>
<div class="tip">
  共 {n} 张卡片 &nbsp;·&nbsp; 每张 375px 宽 &nbsp;·&nbsp; 对单张卡片截图发布小红书，或点击下载全部<br>
  <button id="dl-btn" onclick="downloadAllCards()">⬇ 下载全部 {n} 张图片</button>
</div>
<script>
async function downloadAllCards() {{
  const btn = document.getElementById('dl-btn');
  btn.disabled = true;
  const cards = document.querySelectorAll('[id^="card"]');
  for (let i = 0; i < cards.length; i++) {{
    btn.textContent = '导出中 ' + (i+1) + ' / ' + cards.length + ' ...';
    try {{
      const dataUrl = await htmlToImage.toJpeg(cards[i], {{ quality:0.92, pixelRatio:3, backgroundColor:'#0F1824' }});
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = '游戏行业周报_小红书_' + String(i+1).padStart(2,'0') + '.jpg';
      a.click();
      if (i < cards.length-1) await new Promise(r => setTimeout(r, 400));
    }} catch(e) {{ console.error('卡片'+(i+1)+'导出失败', e); }}
  }}
  btn.disabled = false;
  btn.textContent = '⬇ 下载全部 {n} 张图片';
}}
</script>
<div class="cards-row">
{cards_joined}
</div>
</body>
</html>"""
