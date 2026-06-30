"""Vendored 依赖说明

本目录是从其他项目"整体复制"过来的单文件依赖，仅供本仓自给自足跑通。

| 文件 | 来源 | 复制日期 | 角色 |
|---|---|---|---|
| `render_xhs_cards.py` | `D:/project/xhs-weeklyreport/render_xhs_cards.py` | 2026-06-29 | 双风格小红书卡片 HTML 渲染器，提供 `render_dual_html(data: dict) -> str` |

## 为什么 vendor 而不是 sys.path 引用

按用户的硬约束"只允许复制代码库，不要拆分原有代码"，本目录是单文件 vendored copy。
- 原仓 `xhs-weeklyreport` 继续日常迭代，本副本不双向同步
- 复制后**不修改文件内容**，仅供 `report_renderer.py` 通过本地 import 调用
- 这样 `git clone xhs-yunying` 一个仓即可跑通，不需要再 clone xhs-weeklyreport

如果上游 `render_xhs_cards.py` 有重要更新，手动同步本目录文件即可。
